"""
VectorService — Hybrid Search tương thích qdrant-client 1.9.x

GIẢI PHÁP:
- Không dùng Prefetch/FusionQuery/Fusion (chỉ có từ qdrant-client 1.10+)
- Dùng 2 lần search() riêng biệt + Manual RRF Fusion
- Sparse encoding qua BGEM3FlagModel (FlagEmbedding), fallback dense-only
- Reranker + BGEM3 lazy load: KHÔNG nạp lúc __init__, chỉ nạp khi cần
"""

import uuid
from typing import List, Dict, Any, Tuple, Optional

# ── Core imports ────────────────────────────────────────────────────────────
from qdrant_client.models import Distance, VectorParams, PointStruct

# ── Sparse vector support (qdrant-client >= 1.7.x) ──────────────────────────
try:
    from qdrant_client.models import SparseVectorParams, SparseIndexParams
    from qdrant_client.http.models import SparseVector, NamedSparseVector
    _QDRANT_SPARSE_OK = True
except ImportError:
    _QDRANT_SPARSE_OK = False
    print("ℹ️ [VectorService] Sparse vector không khả dụng (qdrant-client < 1.7).")

from src.config import Config
from src.core.database import QdrantDatabaseProvider
from src.services.parser_service import PDFParserService


class VectorService:
    """
    Dịch vụ Vector DB với:
    1. Parent-Child Chunking: index child (400 ký tự), retrieve parent (2000 ký tự) cho LLM
    2. Hybrid Search: Dense (SentenceTransformer) + Sparse (BGEM3FlagModel nếu có) → Manual RRF
    3. BGE-Reranker: Lazy-load, chỉ chạy khi retrieve_context() được gọi
    """

    DENSE_VECTOR_NAME  = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    def __init__(self):
        db = QdrantDatabaseProvider()
        self.client      = db.qdrant_client
        self.embed_model = db.embedding_model   # SentenceTransformer — luôn OK, nạp sẵn
        self._db         = db                   # Giữ ref để lazy-get BGEM3/Reranker sau

        # Lazy state — KHÔNG gọi db.bgem3_model hay db.reranker_model ở đây
        self._bgem3_checked  = False
        self._bgem3          = None             # BGEM3FlagModel hoặc None
        self._hybrid_enabled = False            # Xác định khi BGEM3 check lần đầu
        self._reranker       = None             # FlagReranker hoặc None

        self._init_collection()

    # =========================================================================
    # LAZY LOADERS
    # =========================================================================
    def _ensure_bgem3(self):
        """Lazy-check BGEM3FlagModel. Chỉ load 1 lần, tái sử dụng mãi."""
        if not self._bgem3_checked:
            self._bgem3_checked = True
            bgem3 = self._db.bgem3_model   # @st.cache_resource — an toàn
            if bgem3 is not None:
                self._bgem3          = bgem3
                self._hybrid_enabled = Config.ENABLE_HYBRID_SEARCH and _QDRANT_SPARSE_OK
                status = "BẬT" if self._hybrid_enabled else "TẮT (thiếu Sparse Qdrant)"
                print(f"⚡ [VectorService] Hybrid Search: {status}")
            else:
                print("ℹ️ [VectorService] Hybrid Search: TẮT (FlagEmbedding chưa cài)")

    def _ensure_reranker(self):
        """Lazy-load Reranker khi lần đầu retrieve. Không block init()."""
        if self._reranker is None:
            self._reranker = self._db.reranker_model  # None nếu chưa cài

    # =========================================================================
    # KHỞI TẠO COLLECTION
    # =========================================================================
    def _get_schema_type(self) -> str:
        """Xác định schema cần dùng: 'hybrid' hoặc 'dense'."""
        self._ensure_bgem3()
        return "hybrid" if self._hybrid_enabled else "dense"

    def _init_collection(self):
        """Tạo collection Qdrant nếu chưa tồn tại."""
        existing = [c.name for c in self.client.get_collections().collections]
        if Config.VECTOR_COLLECTION_NAME not in existing:
            print(f"📦 [Qdrant] Tạo collection: {Config.VECTOR_COLLECTION_NAME}")
            schema = self._get_schema_type()

            if schema == "hybrid":
                self.client.create_collection(
                    collection_name=Config.VECTOR_COLLECTION_NAME,
                    vectors_config={
                        self.DENSE_VECTOR_NAME: VectorParams(
                            size=1024, distance=Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        self.SPARSE_VECTOR_NAME: SparseVectorParams(
                            index=SparseIndexParams(on_disk=False)
                        )
                    }
                )
                print("   ↳ Schema: Hybrid (Dense + Sparse)")
            else:
                self.client.create_collection(
                    collection_name=Config.VECTOR_COLLECTION_NAME,
                    vectors_config={
                        self.DENSE_VECTOR_NAME: VectorParams(
                            size=1024, distance=Distance.COSINE
                        )
                    }
                )
                print("   ↳ Schema: Dense-only")
            print(f"✅ [Qdrant] Collection '{Config.VECTOR_COLLECTION_NAME}' đã sẵn sàng.")
        else:
            print(f"📦 [Qdrant] Collection '{Config.VECTOR_COLLECTION_NAME}' đã tồn tại.")

    def _reset_collection(self):
        """Xóa và tạo lại collection khi re-index toàn bộ."""
        existing = [c.name for c in self.client.get_collections().collections]
        if Config.VECTOR_COLLECTION_NAME in existing:
            print(f"🗑️ [Qdrant] Xóa collection cũ: {Config.VECTOR_COLLECTION_NAME}")
            self.client.delete_collection(Config.VECTOR_COLLECTION_NAME)
        # Reset lazy state để _init_collection dùng đúng schema
        self._bgem3_checked  = False
        self._bgem3          = None
        self._hybrid_enabled = False
        self._init_collection()

    # =========================================================================
    # ENCODE
    # =========================================================================
    def _encode_dense(self, text: str) -> List[float]:
        """Dense vector 1024d qua SentenceTransformer — luôn hoạt động."""
        return self.embed_model.encode(text, normalize_embeddings=True).tolist()

    def _encode_hybrid(self, text: str) -> Tuple[List[float], Optional[Dict]]:
        """
        Dense + Sparse trong 1 forward pass nếu BGEM3FlagModel có sẵn.
        Trả về (dense_vec, sparse_dict) hoặc (dense_vec, None).
        """
        self._ensure_bgem3()
        if self._bgem3 is not None:
            try:
                out = self._bgem3.encode(
                    [text],
                    return_dense=True,
                    return_sparse=True,
                    return_colbert_vecs=False,
                    batch_size=1,
                )
                dense      = out["dense_vecs"][0].tolist()
                sparse_raw = out.get("lexical_weights", [{}])[0]
                indices    = [int(k) for k in sparse_raw.keys()]
                values     = [float(v) for v in sparse_raw.values()]
                return dense, {"indices": indices, "values": values}
            except Exception as e:
                print(f"⚠️ BGEM3 hybrid encode lỗi: {e} → fallback dense-only")

        # Fallback: SentenceTransformer dense-only
        return self._encode_dense(text), None

    # =========================================================================
    # MANUAL RRF FUSION
    # =========================================================================
    @staticmethod
    def _rrf_merge(dense_hits, sparse_hits, k: int = 60) -> List[Any]:
        """
        Reciprocal Rank Fusion — Kết hợp dense + sparse search results.
        rrf_score(d) = Σ 1/(k + rank)   (k=60, chuẩn paper RRF 2009)
        """
        scores:   Dict[str, float] = {}
        payloads: Dict[str, Any]   = {}

        for rank, hit in enumerate(dense_hits):
            hid          = str(hit.id)
            scores[hid]  = scores.get(hid, 0.0) + 1.0 / (k + rank + 1)
            payloads[hid] = hit.payload

        for rank, hit in enumerate(sparse_hits):
            hid          = str(hit.id)
            scores[hid]  = scores.get(hid, 0.0) + 1.0 / (k + rank + 1)
            if hid not in payloads:
                payloads[hid] = hit.payload

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

        class _Hit:
            __slots__ = ("id", "score", "payload")
            def __init__(self_, hid, sc, pl):
                self_.id      = hid
                self_.score   = sc
                self_.payload = pl

        return [_Hit(hid, scores[hid], payloads[hid]) for hid in sorted_ids]

    # =========================================================================
    # SMART INCREMENTAL SYNC (thay thế index_documents cũ)
    # =========================================================================
    def sync_documents(self, force: bool = False) -> dict:
        """
        Đồng bộ tri thức thông minh — chỉ xử lý file thay đổi.

        Cơ chế Idempotent:
        - NEW files      → Parse + Encode + Upsert
        - MODIFIED files → Xóa points cũ + Re-upsert
        - DELETED files  → Xóa points khỏi Qdrant
        - UNCHANGED      → Bỏ qua hoàn toàn

        Args:
            force: Nếu True, xóa sạch và nạp lại toàn bộ (Force Re-index)

        Returns:
            Dict báo cáo: {added, updated, deleted, unchanged, total_chunks}
        """
        from src.services.ingestion_tracker import IngestionTracker, IngestionReport

        self._ensure_bgem3()
        tracker = IngestionTracker()

        # Force Re-index: xóa sạch state + collection
        if force:
            print("🔥 [Sync] Force Re-index — xóa sạch và nạp lại...")
            tracker.reset()
            self._reset_collection()

        diff = tracker.compute_diff()
        report = IngestionReport()

        # Nếu không có thay đổi → trả về ngay
        if not diff.has_changes and not force:
            report.unchanged = len(diff.unchanged_files)
            print("✅ [Sync] Không có thay đổi — kho tri thức đã đồng bộ!")
            return self._report_to_dict(report)

        # Đảm bảo collection tồn tại
        self._init_collection()

        # Quét danh sách file trên đĩa để lấy đường dẫn
        file_paths = IngestionTracker._scan_pdf_files()

        # ── Xử lý file ĐÃ XÓA ──────────────────────────────────────────────
        for fname in diff.deleted_files:
            print(f"🗑️ [Sync] Xóa points của file đã xóa: {fname}")
            self._delete_points_by_source(fname)
            tracker.mark_deleted(fname)
            report.deleted += 1

        # ── Xử lý file SỬA ĐỔI (xóa cũ + nạp mới) ────────────────────────
        for fname in diff.modified_files:
            print(f"✏️ [Sync] Cập nhật file sửa đổi: {fname}")
            self._delete_points_by_source(fname)
            fpath = file_paths.get(fname)
            if fpath:
                chunk_count = self._index_single_file(fpath, fname)
                tracker.mark_indexed(fname, fpath, chunk_count)
                report.updated += chunk_count

        # ── Xử lý file MỚI ─────────────────────────────────────────────────
        for fname in diff.new_files:
            print(f"🆕 [Sync] Nạp file mới: {fname}")
            fpath = file_paths.get(fname)
            if fpath:
                chunk_count = self._index_single_file(fpath, fname)
                tracker.mark_indexed(fname, fpath, chunk_count)
                report.added += chunk_count

        report.unchanged = len(diff.unchanged_files)

        # Commit state ra đĩa
        tracker.commit()

        total = report.added + report.updated
        print(f"✅ [Sync] Hoàn thành! +{report.added} mới, ~{report.updated} cập nhật, "
              f"-{report.deleted} xóa, ={report.unchanged} giữ nguyên")
        report.total_chunks = total
        return self._report_to_dict(report)

    def _index_single_file(self, file_path: str, file_name: str) -> int:
        """
        Parse + Encode + Upsert MỘT file PDF vào Qdrant.
        Trả về số child chunks đã nạp.
        """
        parents, children = PDFParserService.extract_single_file(file_path, file_name)
        if not children:
            return 0

        parent_map = {p["parent_id"]: p for p in parents}
        batch_size = 16
        total = 0

        for batch_start in range(0, len(children), batch_size):
            batch  = children[batch_start: batch_start + batch_size]
            points = []

            for child in batch:
                parent_id  = child["parent_id"]
                parent     = parent_map.get(parent_id, {})
                child_text = child["text"]

                if self._hybrid_enabled:
                    dense_vec, sparse_dict = self._encode_hybrid(child_text)
                    if sparse_dict and sparse_dict["indices"]:
                        vectors = {
                            self.DENSE_VECTOR_NAME: dense_vec,
                            self.SPARSE_VECTOR_NAME: SparseVector(
                                indices=sparse_dict["indices"],
                                values=sparse_dict["values"],
                            )
                        }
                    else:
                        vectors = {self.DENSE_VECTOR_NAME: dense_vec}
                else:
                    vectors = {self.DENSE_VECTOR_NAME: self._encode_dense(child_text)}

                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vectors,
                    payload={
                        "child_text":  child_text,
                        "parent_text": parent.get("text", child_text),
                        "parent_id":   parent_id,
                        "source":      child["metadata"]["source"],
                        "doc_type":    child["metadata"].get("doc_type", "static"),
                    }
                ))

            self.client.upsert(
                collection_name=Config.VECTOR_COLLECTION_NAME,
                points=points,
            )
            total += len(points)

        print(f"   ↳ {file_name}: {total} chunks nạp thành công")
        return total

    def _delete_points_by_source(self, source_filename: str):
        """Xóa tất cả points trong Qdrant có payload.source == filename."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        self.client.delete(
            collection_name=Config.VECTOR_COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=source_filename),
                    )
                ]
            ),
        )
        print(f"   ↳ Đã xóa points của: {source_filename}")

    @staticmethod
    def _report_to_dict(report) -> dict:
        """Chuyển IngestionReport thành dict để trả về cho UI."""
        return {
            "added":        report.added,
            "updated":      report.updated,
            "deleted":      report.deleted,
            "unchanged":    report.unchanged,
            "total_chunks": report.total_chunks,
        }

    # ── Backward compat — giữ tên cũ, gọi nội bộ sync_documents ────────────
    def index_documents(self) -> int:
        """Backward compatible: gọi sync_documents(force=True)."""
        result = self.sync_documents(force=True)
        return result.get("added", 0) + result.get("updated", 0)

    # =========================================================================
    # RETRIEVE — HYBRID SEARCH + MANUAL RRF + RERANKER
    # =========================================================================
    def retrieve_context(
        self,
        query:           str,
        top_k:           int  = None,
        top_n:           int  = None,
        enable_reranker: bool = None,
    ) -> Tuple[str, List[Dict]]:
        """
        Pipeline truy vấn đầy đủ:
        1. Encode query → Dense (+ Sparse nếu BGEM3 có sẵn)
        2. Dense search + (Sparse search) → Manual RRF merge
        3. De-duplicate theo parent_id → lấy parent text đầy đủ
        4. Lazy-load Reranker → chấm điểm lại top_n tốt nhất
        5. Format context string + sources list
        """
        if top_k          is None: top_k          = Config.RETRIEVAL_TOP_K
        if top_n          is None: top_n          = Config.RERANK_TOP_N
        if enable_reranker is None: enable_reranker = Config.ENABLE_RERANKER

        # Lazy load reranker lần đầu gọi
        if enable_reranker:
            self._ensure_reranker()

        # ── Bước 1: Encode ─────────────────────────────────────────────────
        dense_vec, sparse_dict = self._encode_hybrid(query)

        # ── Bước 2: Dense Search ───────────────────────────────────────────
        try:
            dense_results = self.client.search(
                collection_name=Config.VECTOR_COLLECTION_NAME,
                query_vector=(self.DENSE_VECTOR_NAME, dense_vec),
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            print(f"⚠️ [VectorService] Dense search lỗi: {e}")
            return "Kho tri thức chưa có dữ liệu. Hãy bấm 'Cập Nhật Kho Tri Thức' trước.", []

        # ── Bước 3: Sparse Search (nếu có) ────────────────────────────────
        sparse_results = []
        if (self._hybrid_enabled
                and sparse_dict
                and sparse_dict.get("indices")):
            try:
                sparse_results = self.client.search(
                    collection_name=Config.VECTOR_COLLECTION_NAME,
                    query_vector=NamedSparseVector(
                        name=self.SPARSE_VECTOR_NAME,
                        vector=SparseVector(
                            indices=sparse_dict["indices"],
                            values=sparse_dict["values"],
                        )
                    ),
                    limit=top_k,
                    with_payload=True,
                )
                print(f"   ↳ Sparse: {len(sparse_results)} hits | Dense: {len(dense_results)} hits")
            except Exception as e:
                print(f"⚠️ [VectorService] Sparse search không khả dụng: {e}")

        # ── Bước 4: Manual RRF Merge ───────────────────────────────────────
        if sparse_results:
            merged = self._rrf_merge(dense_results, sparse_results)
        else:
            merged = dense_results

        if not merged:
            return "Không tìm thấy dữ liệu liên quan trong kho tri thức.", []

        # ── Bước 5: De-duplicate theo parent_id ───────────────────────────
        seen_pids: set      = set()
        candidates: List   = []
        for hit in merged:
            payload   = hit.payload or {}
            parent_id = payload.get("parent_id")
            if parent_id not in seen_pids:
                seen_pids.add(parent_id)
                candidates.append({
                    "parent_text": payload.get("parent_text", payload.get("child_text", "")),
                    "source":      payload.get("source", "Không rõ nguồn"),
                    "doc_type":    payload.get("doc_type", "static"),
                    "score":       getattr(hit, "score", 0.0),
                })

        # ── Bước 6: BGE Reranker (lazy-loaded) ────────────────────────────
        if enable_reranker and self._reranker is not None and len(candidates) > top_n:
            pairs = [[query, p["parent_text"]] for p in candidates]
            try:
                scores = self._reranker.compute_score(pairs, normalize=True)
                if not isinstance(scores, list):
                    scores = list(scores)
                for i, sc in enumerate(scores):
                    candidates[i]["rerank_score"] = float(sc)
                candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
                print(f"   ↳ Reranked {len(candidates)} → lấy top {top_n}")
            except Exception as e:
                print(f"⚠️ [Reranker] Lỗi: {e}")

        # ── Bước 7: Format output ──────────────────────────────────────────
        final   = candidates[:top_n]
        parts   = [
            f"[Nguồn {i}: {p['source']} | Loại: {p['doc_type'].upper()}]\n{p['parent_text']}"
            for i, p in enumerate(final, 1)
        ]
        context_str = ("\n\n" + "─" * 60 + "\n\n").join(parts)
        return context_str, final


if __name__ == "__main__":
    print("=== SMOKE TEST: VECTOR SERVICE ===")
    svc = VectorService()
    print(f"Hybrid: {svc._hybrid_enabled} | BGEM3 checked: {svc._bgem3_checked}")

    print("\n📥 Index documents...")
    total = svc.index_documents()
    print(f"✅ {total} chunks indexed")

    if total > 0:
        print("\n🔍 Retrieve context...")
        ctx, srcs = svc.retrieve_context("Lạm phát ảnh hưởng đến vàng như thế nào?")
        print(f"📄 {len(srcs)} nguồn | preview: {ctx[:300]}...")
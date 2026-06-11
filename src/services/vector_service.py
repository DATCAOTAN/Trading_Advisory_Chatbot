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

    def __init__(self):
        db = QdrantDatabaseProvider()
        self.client      = db.qdrant_client

        # Khởi tạo Cohere Client cho Embedding và Reranker
        import cohere
        import os
        cohere_api_key = Config.COHERE_API_KEY
        if not cohere_api_key:
            raise ValueError("COHERE_API_KEY chưa được cấu hình.")
        self.cohere_client = cohere.ClientV2(cohere_api_key)

        print("🔥 [VectorService] WARM-UP Phase: Khởi tạo kết nối Qdrant & Cohere Cloud...")
        self._init_collection()

    # =========================================================================
    # KHỞI TẠO COLLECTION
    # =========================================================================
    def _init_collection(self):
        """Tạo collection Qdrant (Dense-only) nếu chưa tồn tại."""
        existing = [c.name for c in self.client.get_collections().collections]
        if Config.VECTOR_COLLECTION_NAME not in existing:
            print(f"📦 [Qdrant] Tạo collection: {Config.VECTOR_COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=Config.VECTOR_COLLECTION_NAME,
                vectors_config={
                    self.DENSE_VECTOR_NAME: VectorParams(
                        size=1024, distance=Distance.COSINE
                    )
                }
            )
            print("   ↳ Schema: Dense-only (Cohere 1024d)")
            print(f"✅ [Qdrant] Collection '{Config.VECTOR_COLLECTION_NAME}' đã sẵn sàng.")
        else:
            print(f"📦 [Qdrant] Collection '{Config.VECTOR_COLLECTION_NAME}' đã tồn tại.")

    def _reset_collection(self):
        """Xóa và khởi tạo lại collection Qdrant để quét sạch toàn bộ point rác cũ."""
        if self.client.collection_exists(collection_name=Config.VECTOR_COLLECTION_NAME):
            print(f"🗑️ [Qdrant] Xóa collection cũ: {Config.VECTOR_COLLECTION_NAME}")
            self.client.delete_collection(collection_name=Config.VECTOR_COLLECTION_NAME)
            
        self.client.create_collection(
            collection_name=Config.VECTOR_COLLECTION_NAME,
            vectors_config={
                self.DENSE_VECTOR_NAME: VectorParams(
                    size=1024, distance=Distance.COSINE
                )
            }
        )
        print("✅ [Qdrant] Đã khởi tạo lại Collection mới (1024d).")

    # =========================================================================
    # ENCODE
    # =========================================================================
    def _encode_dense(self, texts: List[str], input_type: str = "search_document") -> List[List[float]]:
        """
        Dense vector 1024d qua Cohere API Cloud.
        input_type: "search_document" khi nạp PDF, "search_query" khi tìm kiếm.
        """
        import time
        max_retries = 15  # Tăng số lần thử lại lên 15 lần để đợi Rate Limit (Trial API rất gắt)
        for attempt in range(max_retries):
            try:
                response = self.cohere_client.embed(
                    texts=texts,
                    model="embed-multilingual-v3.0",
                    input_type=input_type,
                    embedding_types=["float"]
                )
                return response.embeddings.float
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate limit" in error_str:
                    wait_time = 60  # Trial API limit is strictly per minute
                    print(f"⚠️ [Embedding] Cohere Rate Limit (429). Đang chờ {wait_time}s rồi thử lại (Lần {attempt+1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ [Embedding] Lỗi gọi Cohere API: {e}")
                    raise
        raise RuntimeError("❌ [Embedding] Đã thử lại nhiều lần nhưng vẫn bị Rate Limit từ Cohere.")

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
        batch_size = 96  # Tăng batch size lên tối đa của Cohere (96) để giảm số lượng Request (tránh 429 RPM)
        total = 0

        for batch_start in range(0, len(children), batch_size):
            batch  = children[batch_start: batch_start + batch_size]
            points = []

            # Gom text để gọi API 1 lần (Batching)
            batch_texts = [child["text"] for child in batch]
            dense_vectors = self._encode_dense(batch_texts, input_type="search_document")

            for i, child in enumerate(batch):
                parent_id  = child["parent_id"]
                parent     = parent_map.get(parent_id, {})
                child_text = child["text"]
                dense_vec  = dense_vectors[i]

                vectors = {self.DENSE_VECTOR_NAME: dense_vec}

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
    def retrieve_candidates(self, query: str, top_k: int = None) -> List[Dict]:
        """
        Pure Dense Search Pipeline:
        1. Encode query → Dense Vector qua Cohere API (search_query)
        2. Dense search trên Qdrant
        3. De-duplicate theo parent_id → lấy candidate list (Không Rerank)
        """
        if top_k is None: top_k = Config.RETRIEVAL_TOP_K

        # ── Bước 1: Encode ─────────────────────────────────────────────────
        dense_vecs = self._encode_dense([query], input_type="search_query")
        dense_vec = dense_vecs[0]

        # ── Bước 2: Dense Search ───────────────────────────────────────────
        try:
            merged = self.client.search(
                collection_name=Config.VECTOR_COLLECTION_NAME,
                query_vector=(self.DENSE_VECTOR_NAME, dense_vec),
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            print(f"⚠️ [VectorService] Dense search lỗi: {e}")
            return "Kho tri thức chưa có dữ liệu. Hãy bấm 'Cập Nhật Kho Tri Thức' trước.", []

        if not merged:
            return "Không tìm thấy dữ liệu liên quan trong kho tri thức.", []

        # ── Bước 3: De-duplicate theo parent_id ───────────────────────────
        seen_pids: set      = set()
        candidates: List   = []
        for hit in merged:
            payload   = hit.payload or {}
            parent_id = payload.get("parent_id")
            if parent_id not in seen_pids:
                seen_pids.add(parent_id)
                candidates.append({
                    "content": payload.get("parent_text", payload.get("child_text", "")),
                    "metadata": {
                        "source": payload.get("source", "Không rõ nguồn"),
                        "doc_type": payload.get("doc_type", "static"),
                    },
                    "score": getattr(hit, "score", 0.0),
                })
                
        return candidates

    def search_chat_history(self, session_id: str, query: str, top_k: int = 5) -> str:
        """Tìm kiếm trong Long-term Memory (Vector DB) của riêng phiên chat hiện tại."""
        try:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            dense_vec = self._encode_dense([query], input_type="search_query")[0]
            
            # Kiểm tra xem collection tồn tại không
            try:
                self.client.get_collection("chat_history_collection")
            except Exception:
                return "Lịch sử dài hạn hiện trống."

            hits = self.client.search(
                collection_name="chat_history_collection",
                query_vector=(self.DENSE_VECTOR_NAME, dense_vec),
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id",
                            match=MatchValue(value=session_id)
                        )
                    ]
                ),
                limit=top_k,
                with_payload=True
            )
            
            if not hits:
                return "Không tìm thấy manh mối nào trong lịch sử dài hạn."
                
            # Tổng hợp các tin nhắn liên quan
            parts = []
            for hit in hits:
                p = hit.payload
                parts.append(f"[{p.get('timestamp', '')[:19]}] {p.get('role', '').upper()}: {p.get('content', '')}")
            
            # Sắp xếp lại theo thời gian
            parts.sort()
            return "\n".join(parts)
        except Exception as e:
            print(f"⚠️ [VectorService] Lỗi search chat history: {e}")
            return "Lỗi trích xuất lịch sử."


if __name__ == "__main__":
    print("=== SMOKE TEST: VECTOR SERVICE ===")
    svc = VectorService()
    print(f"Hybrid: {svc._hybrid_enabled} | BGEM3 checked: {svc._bgem3_checked}")

    print("\n📥 Index documents...")
    total = svc.index_documents()
    print(f"✅ {total} chunks indexed")

    if total > 0:
        print("\n🔍 Retrieve context...")
        cands = svc.retrieve_candidates("Lạm phát ảnh hưởng đến vàng như thế nào?")
        print(f"📄 Lấy được {len(cands)} candidates.")
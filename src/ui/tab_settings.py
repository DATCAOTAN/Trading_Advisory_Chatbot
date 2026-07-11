"""
Tab Settings — Isolated Component: Cấu hình hệ thống & quản lý kho tri thức.

Component-Based Architecture:
  - Feature Toggles (Query Rewriting, Reranker, Self-Correction)
  - Nút cập nhật kho tri thức (Incremental / Force Re-index)
  - Cấu hình Broker (placeholder)
  - Thông tin phiên bản hệ thống
"""

import traceback
import streamlit as st
from src.config import Config
from src.ui.runtime_flags import (
    KNOWLEDGE_V3_FALLBACK_KEY,
    USE_KNOWLEDGE_V3_KEY,
    ensure_knowledge_v3_flags,
)


# =============================================================================
# PUBLIC API — Được gọi từ app.py Main Shell
# =============================================================================
def render(orchestrator, feature_flags: dict):
    """
    Render toàn bộ giao diện Settings trong tab hiện tại.

    Args:
        orchestrator:  RAGOrchestrator instance (dependency injection)
        feature_flags: Dict chứa trạng thái feature toggles (read/write)
    """
    st.markdown("### ⚙️ Cấu Hình Hệ Thống")
    st.markdown("---")

    # ── Phần 1: Feature Toggles AI ──────────────────────────────────────
    st.markdown("#### 🎛️ Tính Năng AI Pipeline")

    col1, col2, col3 = st.columns(3)

    with col1:
        feature_flags["query_rewriting"] = st.toggle(
            "✏️ Query Rewriting",
            value=feature_flags["query_rewriting"],
            help="Tự động mở rộng câu hỏi thành câu truy vấn chuẩn tài chính",
            key="settings_qr",
        )

    with col2:
        feature_flags["reranker"] = st.toggle(
            "🎯 BGE Reranker",
            value=feature_flags["reranker"],
            help="Chấm điểm lại top 10 → chọn 3 đoạn tốt nhất (chậm thêm ~1-2s)",
            key="settings_reranker",
        )

    with col3:
        feature_flags["self_correction"] = st.toggle(
            "🔍 Self-Correction",
            value=feature_flags["self_correction"],
            help="Kiểm tra hallucination sau khi AI trả lời (chậm hơn ~30-50%)",
            key="settings_sc",
        )

    st.markdown("#### Knowledge Retrieval")
    ensure_knowledge_v3_flags(st.session_state)
    st.session_state[USE_KNOWLEDGE_V3_KEY] = st.toggle(
        "Use Knowledge Platform V3 (experimental)",
        value=st.session_state[USE_KNOWLEDGE_V3_KEY],
        help="Routes VectorDB_Search through RetrievalAdapter -> KnowledgeService V3.",
        key="settings_use_knowledge_v3",
    )
    st.session_state[KNOWLEDGE_V3_FALLBACK_KEY] = st.toggle(
        "Fallback to legacy if V3 fails",
        value=st.session_state[KNOWLEDGE_V3_FALLBACK_KEY],
        help="If V3 retrieval fails or cannot infer a domain, use legacy xauusd_knowledge_v2 retrieval.",
        key="settings_knowledge_v3_fallback",
    )
    if st.session_state[USE_KNOWLEDGE_V3_KEY]:
        st.warning(
            "Knowledge V3 experimental retrieval enabled. "
            "V3 uses knowledge_current. Legacy uses xauusd_knowledge_v2. "
            "Enable V3 only after running staging verification."
        )
    else:
        st.caption(
            "Knowledge V3 is disabled. Legacy retrieval uses xauusd_knowledge_v2 by default."
        )

    _render_knowledge_v3_update_panel()
    _render_retrieval_debug_panel(orchestrator)

    st.markdown("---")

    # ── Phần 2: Quản lý kho tri thức ────────────────────────────────────
    st.markdown("#### 📚 Quản Lý Kho Tri Thức")

    st.caption(
        "**Incremental Sync**: Chỉ nạp file mới/sửa đổi, bỏ qua file không đổi.  \n"
        "**Force Re-index**: Xóa sạch và nạp lại toàn bộ (dùng khi đổi schema)."
    )

    col_sync, col_force = st.columns(2)

    with col_sync:
        if st.button("🔄 Đồng Bộ Thông Minh", use_container_width=True, type="primary",
                      key="settings_sync"):
            _run_sync(orchestrator, force=False)

    with col_force:
        if st.button("🔥 Force Re-index", use_container_width=True, key="settings_force"):
            _run_sync(orchestrator, force=True)

    st.markdown("---")

    # ── Phần 3: Bộ nhớ hội thoại ────────────────────────────────────────
    st.markdown("#### 💬 Bộ Nhớ Hội Thoại")

    msg_count = len(st.session_state.messages)
    col_mem1, col_mem2 = st.columns([3, 1])
    col_mem1.metric(
        "Số lượt chat",
        msg_count,
        f"Nhớ {min(msg_count, Config.MEMORY_WINDOW)} lượt",
    )

    with col_mem2:
        st.markdown("")  # spacing
        if st.button("🗑️ Xóa Lịch Sử", use_container_width=True, key="settings_clear"):
            st.session_state.messages = []
            st.rerun()

    st.markdown("---")

    # ── Phần 4: Cấu hình Broker (Placeholder) ──────────────────────────
    st.markdown("#### 🏦 Cấu Hình Broker (Sắp ra mắt)")

    with st.expander("🔑 Oanda API Configuration"):
        st.text_input("API Key", type="password", key="oanda_key",
                       placeholder="Nhập Oanda API Key...", disabled=True)
        st.text_input("Account ID", key="oanda_account",
                       placeholder="Nhập Account ID...", disabled=True)
        st.caption("⏳ Tính năng kết nối Broker sẽ được kích hoạt trong phiên bản tiếp theo.")

    st.markdown("---")

    # ── Phần 5: Thông tin phiên bản ─────────────────────────────────────
    st.markdown("#### ℹ️ Thông Tin Phiên Bản")
    embedding_model_name = "Cohere Embed (v3.0)" if Config.COHERE_API_KEY else "BGE-M3 (Local)"
    if Config.LLM_PROVIDER == "openrouter":
        active_llm_name = Config.OPENROUTER_MODEL_NAME
    elif Config.LLM_PROVIDER == "google":
        active_llm_name = Config.GOOGLE_MODEL_NAME
    elif Config.LLM_PROVIDER == "groq":
        active_llm_name = Config.GROQ_MODEL_NAME
    else:
        active_llm_name = Config.LLM_MODEL_NAME

    st.code(
        "📦 Trading Advisory Chatbot v3.0\n"
        f"🧠 LLM: {active_llm_name}\n"
        f"📐 Embedding: {embedding_model_name}\n"
        f"🎯 Reranker: {'Cohere API' if Config.ENABLE_RERANKER else 'Tắt'}\n"
        "💾 Vector DB: Qdrant Local\n"
        "🚪 Intent Router: LLM Gatekeeper (Few-Shot)\n"
        "📊 Architecture: Facade + Component-Based + Incremental Ingestion",
        language="text",
    )


# =============================================================================
# HELPERS NỘI BỘ
# =============================================================================
def _run_sync(orchestrator, force: bool):
    """Chạy đồng bộ kho tri thức và hiển thị kết quả."""
    mode = "Force Re-index" if force else "Incremental Sync"

    with st.spinner(f"📚 Đang {mode}..."):
        try:
            report = orchestrator.sync_knowledge_base(force=force)

            added     = report.get("added", 0)
            updated   = report.get("updated", 0)
            deleted   = report.get("deleted", 0)
            unchanged = report.get("unchanged", 0)

            if added == 0 and updated == 0 and deleted == 0:
                st.success(
                    f"✅ Kho tri thức đã đồng bộ! "
                    f"**{unchanged}** file không thay đổi."
                )
            else:
                st.success(
                    f"✅ Hoàn thành {mode}!\n\n"
                    f"- 🆕 **{added}** chunks mới  \n"
                    f"- ✏️ **{updated}** chunks cập nhật  \n"
                    f"- 🗑️ **{deleted}** file đã xóa  \n"
                    f"- ✅ **{unchanged}** file giữ nguyên"
                )

        except Exception as e:
            st.error(f"❌ Lỗi: {e}")
            st.code(traceback.format_exc())


def _render_knowledge_v3_update_panel():
    st.markdown("#### Knowledge Platform V3 Update")
    repository_path = str(Config.DATA_DIR / "knowledge_repository")
    st.code(repository_path, language="text")
    st.caption(
        "Place PDF/EPUB files under "
        "data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{owner_slug}/{file.ext}. "
        "The updater can auto-create missing manifests/checksums for normal documents."
    )

    col_scan, col_update = st.columns(2)
    with col_scan:
        if st.button("Scan Knowledge V3 Repository", use_container_width=True, key="settings_v3_scan"):
            _run_knowledge_v3_scan(repository_path)
    with col_update:
        if st.button("Update Knowledge V3", use_container_width=True, type="primary", key="settings_v3_update"):
            _run_knowledge_v3_update(repository_path)


def _render_retrieval_debug_panel(orchestrator):
    """Compact Knowledge V3 retrieval diagnostics without direct UI Qdrant/Cohere calls."""
    with st.expander("Knowledge V3 retrieval debug"):
        st.caption(
            "Preview deterministic query routing, generated filters, retrieved chunks, "
            "and source-grounding roles. Retrieval runs through RetrievalAdapter."
        )
        query = st.text_input(
            "Debug query",
            key="settings_v3_debug_query",
            placeholder="Example: CPI ảnh hưởng XAUUSD như thế nào?",
        )
        top_k = st.number_input(
            "Top K",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
            key="settings_v3_debug_top_k",
        )
        if not query:
            return

        try:
            from src.services.knowledge.answer_grounding import AnswerGroundingPlanner
            from src.services.knowledge.query_intent import QueryFilterBuilder, QueryIntentRouter

            intent = QueryIntentRouter().route(query)
            filters = QueryFilterBuilder().build(intent)
            st.json({
                "query_intent": intent.as_dict(),
                "filters": filters,
            })

            if st.button("Run V3 retrieval debug", key="settings_v3_debug_run"):
                adapter = getattr(orchestrator, "retrieval_adapter", None)
                if adapter is None:
                    st.warning("RetrievalAdapter is not available on the orchestrator.")
                    return

                docs = adapter.retrieve(
                    query,
                    filters=filters,
                    top_k=int(top_k),
                    use_v3=True,
                    fallback_to_legacy=False,
                )
                trace = getattr(adapter, "last_trace", None)
                grounded_docs, grounding_plan = AnswerGroundingPlanner().build(query, docs, intent)
                st.json({
                    "retrieval_trace": trace.as_dict() if trace else {},
                    "grounding_plan": grounding_plan.to_dict(),
                })

                rows = []
                for index, doc in enumerate(grounded_docs, 1):
                    metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
                    rows.append({
                        "rank": index,
                        "title": metadata.get("title") or metadata.get("source") or doc.get("source", ""),
                        "author": metadata.get("author", ""),
                        "organization": metadata.get("organization", ""),
                        "role": metadata.get("source_role", ""),
                        "why_used": ", ".join(metadata.get("source_usage_reasons", []) or []),
                        "domain": metadata.get("domain", ""),
                        "subdomain": metadata.get("subdomain", ""),
                        "event_type": metadata.get("event_type", ""),
                        "period": metadata.get("period", ""),
                        "score": doc.get("score", ""),
                        "rank_score": metadata.get("retrieval_rank_score", ""),
                        "ranking_reasons": ", ".join(metadata.get("retrieval_ranking_reasons", []) or []),
                        "penalties": ", ".join(metadata.get("retrieval_ranking_penalties", []) or []),
                        "excerpt": str(doc.get("content") or doc.get("text") or "")[:240],
                    })
                st.dataframe(rows, use_container_width=True)
        except Exception as exc:
            st.error(f"Knowledge V3 retrieval debug failed: {exc}")
            st.code(traceback.format_exc())


def _run_knowledge_v3_scan(repository_path: str):
    try:
        from src.services.knowledge.update_service import KnowledgeUpdateService

        report = KnowledgeUpdateService(repository_path=repository_path).scan_repository()
        _render_knowledge_update_report(report)
    except Exception as exc:
        st.error(f"Knowledge V3 scan failed: {exc}")
        st.code(traceback.format_exc())


def _run_knowledge_v3_update(repository_path: str):
    try:
        from src.services.knowledge.update_service import KnowledgeUpdateService

        service = KnowledgeUpdateService(repository_path=repository_path)
        with st.spinner("Updating Knowledge Platform V3..."):
            report = service.update_repository()
        _render_knowledge_update_report(report)
    except Exception as exc:
        st.error(f"Knowledge V3 update failed: {exc}")
        st.code(traceback.format_exc())


def _render_knowledge_update_report(report):
    summary = report.summary()
    st.success(
        "Knowledge V3 summary: "
        f"discovered={summary['discovered']}, precheck_skipped={summary.get('precheck_skipped', 0)}, "
        f"fast_precheck_backfilled={summary.get('fast_precheck_backfilled', 0)}, "
        f"fast_precheck_missing={summary.get('fast_precheck_missing', 0)}, "
        f"parsed={summary.get('parsed', 0)}, indexed={summary['indexed']}, "
        f"skipped_after_parse={summary.get('skipped_after_parse', 0)}, skipped={summary['skipped']}, "
        f"pending_retry={summary.get('pending_retry', 0)}, "
        f"failed_upsert={summary.get('failed_upsert', 0)}, needs_ocr={summary['needs_ocr']}, "
        f"quarantined={summary['quarantined']}, failed={summary['failed']}, "
        f"smoke_pass={summary.get('smoke_pass', 0)}, smoke_skipped={summary.get('smoke_skipped', 0)}, "
        f"rate_limit_count={summary.get('rate_limit_count', 0)}, "
        f"cache_hits={summary.get('embedding_cache_hits', 0)}, cache_misses={summary.get('embedding_cache_misses', 0)}, "
        f"total_ms={summary.get('total_duration_ms', 0)}, precheck_ms={summary.get('precheck_duration_ms', 0)}, "
        f"parse_ms={summary.get('parse_duration_ms', 0)}"
    )

    rows = []
    for item in report.results:
        rows.append({
            "file": item.path,
            "status": item.status,
            "reason": item.reason,
            "doc_id": item.doc_id,
            "domain": item.domain,
            "subdomain": item.subdomain,
            "type": item.document_type,
            "chunks": item.chunk_count,
            "policy": item.chunk_policy_id,
            "retrieval_smoke": getattr(item, "retrieval_smoke_status", ""),
            "smoke_reason": getattr(item, "retrieval_smoke_reason", ""),
            "precheck": getattr(item, "precheck_status", ""),
            "precheck_reason": getattr(item, "precheck_reason", ""),
            "precheck_skipped": getattr(item, "precheck_skipped", False),
            "fast_precheck_backfilled": getattr(item, "fast_precheck_backfilled", False),
            "fast_precheck_missing": getattr(item, "fast_precheck_missing", False),
            "parsed": getattr(item, "parsed", False),
            "precheck_ms": getattr(item, "precheck_duration_ms", 0),
            "parse_ms": getattr(item, "parse_duration_ms", 0),
            "failure_category": getattr(item, "failure_category", ""),
            "retryable": getattr(item, "retryable", False),
            "cache_hits": getattr(item, "embedding_cache_hits", 0),
            "cache_misses": getattr(item, "embedding_cache_misses", 0),
            "rate_limit_count": getattr(item, "rate_limit_count", 0),
            "top_source_title": getattr(item, "top_source_title", ""),
            "top_source_author": getattr(item, "top_source_author", ""),
            "top_source_organization": getattr(item, "top_source_organization", ""),
            "top_source_domain": getattr(item, "top_source_domain", ""),
            "top_source_subdomain": getattr(item, "top_source_subdomain", ""),
            "top_source_event_type": getattr(item, "top_source_event_type", ""),
            "top_source_period": getattr(item, "top_source_period", ""),
        })
    if rows:
        st.dataframe(rows, use_container_width=True)

    with st.expander("Knowledge V3 detailed logs"):
        for line in report.logs:
            st.text(line)
        for item in report.results:
            for line in item.logs:
                st.text(line)

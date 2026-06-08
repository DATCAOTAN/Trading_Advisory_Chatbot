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
    st.code(
        "📦 Trading Advisory Chatbot v3.0\n"
        f"🧠 LLM: {Config.OPENROUTER_MODEL_NAME if Config.LLM_PROVIDER=='openrouter' else Config.LLM_MODEL_NAME}\n"
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

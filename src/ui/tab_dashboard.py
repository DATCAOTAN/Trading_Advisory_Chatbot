"""
Tab Dashboard — Isolated Component: Bảng theo dõi trạng thái hệ thống & dữ liệu thời gian thực.

Component-Based Architecture:
  - Hiển thị: trạng thái Qdrant, giá live, lịch kinh tế, thống kê kho tri thức.
  - Giao tiếp với orchestrator qua dependency injection (tham số).
  - Có thể rút bỏ hoàn toàn mà không ảnh hưởng tab Chatbot hay Settings.
"""

import streamlit as st
from src.config import Config


# =============================================================================
# PUBLIC API — Được gọi từ app.py Main Shell
# =============================================================================
def render(orchestrator):
    """
    Render toàn bộ giao diện Dashboard trong tab hiện tại.

    Args:
        orchestrator: RAGOrchestrator instance (dependency injection)
    """
    st.markdown("### 📊 Dashboard Tổng Quan")
    st.markdown("---")

    # ── Hàng 1: Trạng thái hệ thống AI ──────────────────────────────────
    st.markdown("#### 🤖 Trạng Thái Hệ Thống AI")
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("🧠 LLM", "Qwen 2.5 7B", help="Mô hình ngôn ngữ chính")
    col2.metric("📐 Embedding", "BGE-M3", help="Mô hình nhúng vector 1024d")
    col3.metric("🎯 Reranker", "BGE-v2-M3", help="Chấm điểm lại top chunks")
    col4.metric("💾 Vector DB", "Qdrant Local", help="Cơ sở dữ liệu vector")

    st.markdown("---")

    # ── Hàng 2: Thống kê kho tri thức ───────────────────────────────────
    st.markdown("#### 📚 Kho Tri Thức")

    try:
        client = orchestrator.vector_service.client
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if Config.VECTOR_COLLECTION_NAME in collection_names:
            info = client.get_collection(Config.VECTOR_COLLECTION_NAME)
            points_count = info.points_count
            vectors_count = info.vectors_count if hasattr(info, 'vectors_count') else points_count

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("📦 Collection", Config.VECTOR_COLLECTION_NAME)
            col_b.metric("🔢 Tổng Chunks", f"{points_count:,}")
            col_c.metric("📏 Vector Dim", "1024d")

            # Hiển thị trạng thái ingestion
            _render_ingestion_state()
        else:
            st.warning("⚠️ Chưa có collection nào trong Qdrant. Hãy nạp PDF trước!")

    except Exception as e:
        st.error(f"❌ Lỗi kết nối Qdrant: {e}")

    st.markdown("---")

    # ── Hàng 3: Dữ liệu thời gian thực ─────────────────────────────────
    st.markdown("#### 📡 Dữ Liệu Thời Gian Thực")

    col_live1, col_live2 = st.columns(2)

    with col_live1:
        st.markdown("**💰 Giá XAUUSD Live**")
        if st.button("🔄 Cập nhật giá", use_container_width=True, key="dash_price"):
            with st.spinner("Đang lấy giá..."):
                price_info = orchestrator.live_service.get_live_price()
                st.info(price_info)

    with col_live2:
        st.markdown("**📅 Lịch Kinh Tế**")
        if st.button("🔄 Xem lịch tuần này", use_container_width=True, key="dash_calendar"):
            with st.spinner("Đang tải lịch kinh tế..."):
                calendar_info = orchestrator.live_service.get_economic_calendar()
                st.info(calendar_info)

    st.markdown("---")

    # ── Hàng 4: Cấu hình đường dẫn ─────────────────────────────────────
    st.markdown("#### 📂 Đường Dẫn Hệ Thống")
    st.code(
        f"📁 Project Root:  {Config.BASE_DIR}\n"
        f"📁 PDF Static:    {Config.STATIC_PDF_DIR}\n"
        f"📁 PDF Dynamic:   {Config.DYNAMIC_PDF_DIR}\n"
        f"📁 Qdrant DB:     {Config.QDRANT_DIR}\n"
        f"📁 Logs:          {Config.LOGS_DIR}",
        language="text",
    )


# =============================================================================
# HELPERS NỘI BỘ
# =============================================================================
def _render_ingestion_state():
    """Hiển thị trạng thái file đã index từ ingestion_state.json."""
    try:
        from src.services.ingestion_tracker import IngestionTracker
        tracker = IngestionTracker()
        state = tracker._state.get("files", {})

        if state:
            with st.expander(f"📋 Chi tiết file đã index ({len(state)} file)"):
                for fname, info in state.items():
                    chunks = info.get("chunk_count", "?")
                    indexed_at = info.get("indexed_at", "?")
                    st.markdown(
                        f"- **{fname}** — `{chunks} chunks` — _{indexed_at}_"
                    )
        else:
            st.caption("📋 Chưa có file nào được index.")
    except Exception:
        st.caption("📋 Không thể đọc trạng thái ingestion.")

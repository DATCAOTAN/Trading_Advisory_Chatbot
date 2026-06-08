"""
Tab Dashboard — Isolated Component: Bảng theo dõi trạng thái hệ thống & dữ liệu thời gian thực.

Component-Based Architecture:
  - Hiển thị: trạng thái Qdrant, giá live, lịch kinh tế, thống kê kho tri thức.
  - Giao tiếp với orchestrator qua dependency injection (tham số).
  - Có thể rút bỏ hoàn toàn mà không ảnh hưởng tab Chatbot hay Settings.
"""

import streamlit as st
from src.config import Config


import json
import streamlit as st
from src.config import Config


@st.cache_data(ttl=5)
def load_tracker_state():
    """Đọc Ingestion State từ ổ cứng và cache lại để tránh nghẽn luồng Stream."""
    if Config.INGESTION_STATE_FILE.exists():
        try:
            with open(Config.INGESTION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                files = data.get("files", {})
                print(f"📋 [Tracker Cache] Đã load state: {len(files)} file vào RAM.")
                return files
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

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

    embedding_model_name = "Cohere Embed (v3.0)" if Config.COHERE_API_KEY else "BGE-M3 (Local)"

    col1.metric("🧠 LLM", Config.OPENROUTER_MODEL_NAME if Config.LLM_PROVIDER=="openrouter" else Config.LLM_MODEL_NAME, help="Mô hình ngôn ngữ chính")
    col2.metric("📐 Embedding", embedding_model_name, help="Mô hình nhúng vector 1024d")
    col3.metric("🎯 Reranker", "Cohere API" if Config.ENABLE_RERANKER else "Tắt", help="Chấm điểm lại top chunks")
    col4.metric("💾 Vector DB", "Qdrant Local", help="Cơ sở dữ liệu vector")

    st.markdown("---")

    # ── Hàng 2: Thống kê kho tri thức ───────────────────────────────────
    st.markdown("#### 📚 Kho Tri Thức")

    try:
        client = orchestrator.vector_service.client
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if Config.VECTOR_COLLECTION_NAME in collection_names:
            # Lấy state từ hàm Cache thay vì gọi IngestionTracker trực tiếp
            state = load_tracker_state()
            real_points_count = sum(info.get("chunk_count", 0) for info in state.values())

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("📦 Collection", Config.VECTOR_COLLECTION_NAME)
            col_b.metric("🔢 Tổng Chunks", f"{real_points_count:,}")
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
        state = load_tracker_state()

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

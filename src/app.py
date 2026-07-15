"""
Main Shell (Facade) — Bộ khung Layout tổng của ứng dụng.

Design Pattern: Facade Pattern + Component-Based Architecture
  - File này CHỈ chứa: page config, CSS theme, khởi tạo orchestrator, tab navigation.
  - Toàn bộ logic chức năng được đóng gói cô lập trong src/ui/tab_*.py.
  - Thêm tab mới = thêm 1 import + 1 dòng render() → KHÔNG ảnh hưởng tab khác.
  - ~100 dòng (giảm từ 367 dòng app.py cũ).
"""

import sys
import traceback
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st

# =============================================================================
# 1. CẤU HÌNH TRANG — Chạy đầu tiên, trước mọi thứ
# =============================================================================
st.set_page_config(
    page_title="AI XAUUSD Advisor — Advanced RAG",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# 2. CSS THEME TOÀN CỤC — Giao diện premium dark theme
# =============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Main header gradient */
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    border-left: 4px solid #e94560;
    margin-bottom: 1rem;
}
.main-header h1 { color: #f5f5f5; font-size: 1.6rem; font-weight: 700; margin: 0; }
.main-header p  { color: #a0aec0; font-size: 0.85rem; margin: 0.3rem 0 0; }

/* Intent badge */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}
.badge-rag     { background: #1a365d; color: #63b3ed; border: 1px solid #2b6cb0; }
.badge-trash   { background: #7c2d12; color: #fdba74; border: 1px solid #c2410c; }
.badge-greet   { background: #2d2a42; color: #b794f4; border: 1px solid #6b46c1; }

/* Sources card */
.source-card {
    background: #1a1a2e;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin: 0.4rem 0;
    font-size: 0.8rem;
}
.source-card strong { color: #63b3ed; }

/* Sidebar style */
section[data-testid="stSidebar"] { background: #0d1117; }
section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
    border: 1px solid #2d3748;
    background: #161b22;
    color: #c9d1d9;
    transition: all 0.2s;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #21262d;
    border-color: #58a6ff;
    color: #58a6ff;
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 3. KHỞI TẠO HỆ THỐNG (Singleton — chỉ chạy 1 lần)
# =============================================================================
from src.orchestrator import RAGOrchestrator
from src.config import Config

if "orchestrator" not in st.session_state:
    with st.spinner("🔄 Đang khởi động hệ thống AI..."):
        try:
            st.session_state.orchestrator = RAGOrchestrator()
        except Exception as e:
            st.error(f"❌ Lỗi khởi tạo hệ thống: {e}")
            st.code(traceback.format_exc())
            st.stop()

if "current_session_id" not in st.session_state:
    from src.services.history_service import HistoryService
    history_svc = HistoryService()
    sessions = history_svc.get_all_sessions()
    if sessions is None:
        st.error("❌ Mất kết nối CSDL (MongoDB). Vui lòng tải lại trang sau ít phút!")
        st.stop()
    elif sessions:
        st.session_state.current_session_id = sessions[0]["_id"]
    else:
        st.session_state.current_session_id = history_svc.create_session("New Chat")

if "messages" not in st.session_state:
    from src.services.history_service import HistoryService
    st.session_state.messages = HistoryService().load_history(st.session_state.current_session_id)

if "feature_flags" not in st.session_state:
    st.session_state.feature_flags = {
        "self_correction": Config.ENABLE_SELF_CORRECTION,
        "reranker":        Config.ENABLE_RERANKER,
        "query_rewriting": Config.ENABLE_QUERY_REWRITING,
    }

orchestrator  = st.session_state.orchestrator
feature_flags = st.session_state.feature_flags

# =============================================================================
# 4. SIDEBAR — Trạng thái hệ thống tóm tắt
# =============================================================================
with st.sidebar:
    st.markdown("## 📈 AI XAUUSD Advisor")
    st.markdown("---")
    st.markdown("**📡 Trạng Thái**")
    col1, col2 = st.columns(2)
    if Config.LLM_PROVIDER == "openrouter":
        active_llm_name = Config.OPENROUTER_MODEL_NAME
    elif Config.LLM_PROVIDER == "google":
        active_llm_name = Config.GOOGLE_MODEL_NAME
    elif Config.LLM_PROVIDER == "groq":
        active_llm_name = Config.GROQ_MODEL_NAME
    else:
        active_llm_name = Config.LLM_MODEL_NAME

    col1.metric("LLM", active_llm_name)
    col2.metric("DB", "Qdrant")
    st.caption(f"💬 Chat: {len(st.session_state.messages)} lượt")
    
    
    st.markdown("---")
    st.markdown("**💬 Phiên Trò Chuyện**")
    from src.services.history_service import HistoryService
    history_svc = HistoryService()
    
    # Nút tạo phiên mới
    if st.button("➕ Tạo Chat Mới"):
        new_id = history_svc.create_session("New Chat")
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()

    # Lấy danh sách session để hiển thị
    all_sessions = history_svc.get_all_sessions()
    if all_sessions is None:
        st.error("❌ MongoDB đang gián đoạn, không tải được danh sách chat cũ.")
    elif all_sessions:
        # Đảm bảo current_session_id hợp lệ
        valid_ids = [s["_id"] for s in all_sessions]
        if st.session_state.current_session_id not in valid_ids:
            st.session_state.current_session_id = valid_ids[0]
            
        for s in all_sessions:
            s_id = s["_id"]
            s_title = s.get("title", "New Chat")
            
            col1, col2 = st.columns([8, 2])
            with col1:
                btn_type = "primary" if s_id == st.session_state.current_session_id else "secondary"
                if st.button(s_title, key=f"btn_{s_id}", use_container_width=True, type=btn_type):
                    st.session_state.current_session_id = s_id
                    st.session_state.messages = history_svc.load_history(s_id)
                    st.rerun()
            with col2:
                with st.popover("⋮", use_container_width=True):
                    new_title = st.text_input("Tên mới", value=s_title, key=f"rename_{s_id}")
                    if st.button("✏️ Đổi tên", key=f"save_{s_id}"):
                        history_svc.rename_session(s_id, new_title)
                        st.rerun()
                    st.markdown("---")
                    if st.button("🗑️ Xóa", key=f"del_{s_id}"):
                        history_svc.delete_session(s_id)
                        if s_id == st.session_state.current_session_id:
                            sessions_after = history_svc.get_all_sessions()
                            if sessions_after:
                                st.session_state.current_session_id = sessions_after[0]["_id"]
                                st.session_state.messages = history_svc.load_history(st.session_state.current_session_id)
                            else:
                                new_id = history_svc.create_session("New Chat")
                                st.session_state.current_session_id = new_id
                                st.session_state.messages = []
                        st.rerun()
        
    st.markdown("---")
    st.caption("v3.0 — Facade + Component-Based Architecture")

# =============================================================================
# 5. HEADER
# =============================================================================
st.markdown("""
<div class="main-header">
    <h1>📈 AI Cố Vấn Tài Chính Chiến Lược XAUUSD</h1>
    <p>Cloud LLM · Hybrid Search · Cohere Reranker · Parent-Child RAG · Multi-Hop Reasoning</p>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# 6. TAB NAVIGATION — Facade điều phối đến Isolated Components
# =============================================================================
from src.ui import tab_chatbot, tab_dashboard, tab_evaluation_dashboard, tab_settings

tab1, tab2, tab3, tab4 = st.tabs(["💬 Chatbot Tư Vấn", "📊 Dashboard", "Dashboard Đánh Giá", "⚙️ Cấu Hình"])

with tab1:
    tab_chatbot.render(orchestrator, feature_flags)

with tab2:
    tab_dashboard.render(orchestrator)

with tab3:
    tab_evaluation_dashboard.render(orchestrator)

with tab4:
    tab_settings.render(orchestrator, feature_flags)

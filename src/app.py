import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
from src.orchestrator import RAGOrchestrator

# 1. Cấu hình giao diện Streamlit chuẩn tối ưu
st.set_page_config(
    page_title="AI XAUUSD Advisor", 
    page_icon="📈", 
    layout="wide"
)

# 2. Khởi tạo Hệ thống Điều phối (Lưu vào session_state để tránh khởi tạo lại khi re-run)
if "orchestrator" not in st.session_state:
    with st.spinner("🔄 Đang khởi động hệ thống AI Cố vấn (Nạp Singleton Models)..."):
        st.session_state.orchestrator = RAGOrchestrator()

orchestrator = st.session_state.orchestrator

# 3. Thiết kế khu vực tiêu đề (Header)
st.title("📈 HỆ THỐNG AI TRỢ LÝ CỐ VẤN TÀI CHÍNH CHIẾN LƯỢC XAUUSD")
st.caption("Bộ não: Qwen 2.5 (7B) | Cơ sở dữ liệu: Qdrant Vector DB Cục bộ | Kiến trúc: Kiến trúc phân lớp RAG")
st.markdown("---")

# 4. Thanh điều hướng bên trái (Sidebar) để quản lý
with st.sidebar:
    st.header("⚙️ Quản Lý Hệ Thống")
    st.markdown("Nếu anh mới thêm file PDF mới vào thư mục `data/raw_pdfs`, hãy bấm nút dưới đây để cập nhật tri thức cho Bot.")
    
    if st.button("🔄 Cập nhật Kho Tri thức (Ingestion)", use_container_width=True):
        with st.spinner("📚 Đang quét PDF và đồng bộ hóa vào Qdrant DB..."):
            total_chunks = orchestrator.sync_knowledge_base()
            st.success(f"✅ Thành công! Đã nạp {total_chunks} đoạn tri thức mới.")

# 5. Quản lý lịch sử cuộc hội thoại (Chat History)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lại các tin nhắn cũ khi người dùng tương tác trên UI
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Nếu là câu trả lời của Assistant, hiển thị thêm hộp chứa nguồn tài liệu trích dẫn
        if msg["role"] == "assistant" and "context" in msg:
            with st.expander("🔍 Xem nguồn tài liệu đối chiếu từ PDF"):
                st.code(msg["context"], language="text")

# 6. Khu vực nhận câu hỏi từ Trader (Chat Input)
if user_query := st.chat_input("Hãy hỏi tôi về xu hướng vàng, dữ liệu vĩ mô hoặc chiến lược kỹ thuật..."):
    
    # Hiển thị câu hỏi của User lên màn hình và lưu lịch sử
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # Hệ thống RAG xử lý và trả lời
    with st.chat_message("assistant"):
        with st.spinner("🧠 AI đang truy vấn dữ liệu vĩ mô và lập luận chiến lược..."):
            # Gọi hàm Facade duy nhất từ Orchestrator
            answer, retrieved_context = orchestrator.query_financial_advisor(user_query)
            
            # Hiển thị câu trả lời dạng chữ
            st.markdown(answer)
            
            # Hiển thị nguồn trích dẫn ẩn trong expander
            with st.expander("🔍 Xem nguồn tài liệu đối chiếu từ PDF"):
                st.code(retrieved_context, language="text")
                
    # Lưu câu trả lời của AI vào lịch sử bộ nhớ
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "context": retrieved_context
    })
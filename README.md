# 📈 AI Trading Advisory Chatbot — XAUUSD

Hệ thống **Chatbot Cố vấn Giao dịch Vàng (XAUUSD)** chạy hoàn toàn **cục bộ (offline)** trên máy tính cá nhân, không phụ thuộc vào bất kỳ API trả phí nào. Sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)** để trả lời các câu hỏi tài chính dựa trên tài liệu PDF do người dùng cung cấp.

---

## 🧠 Kiến trúc hệ thống

```
data/raw_pdfs/          ← Bạn đặt file PDF tài liệu tài chính vào đây
       ↓ PDFParserService (PyMuPDF)
   Sliding Window Chunks (800 ký tự, overlap 150)
       ↓ VectorService (BAAI/bge-m3)
   Qdrant Local Vector DB  ←→  data/qdrant_db/
       ↑ Retrieve Top-K Context
   RAGOrchestrator (Facade Pattern)
       ↓ LLMService (Ollama)
   Qwen 2.5 7B (chạy cục bộ)
       ↓
   Streamlit UI  →  http://localhost:8501
```

### 🏗️ Design Patterns sử dụng
| Pattern | Vị trí áp dụng | Mục đích |
|---|---|---|
| **Singleton** | `src/core/database.py` | Đảm bảo chỉ có 1 kết nối Qdrant & 1 model nhúng trong RAM |
| **Facade** | `src/orchestrator.py` | Bọc sự phức tạp của Vector DB + LLM thành 1 đầu mối duy nhất |

---

## 🔧 Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Python | 3.10+ | |
| Ollama | Mới nhất | Phải cài trước, chạy nền |
| RAM | 8 GB+ | Model BGE-M3 ~1.5GB, Qwen 7B ~5GB |
| Ổ cứng | 10 GB+ trống | Cho model LLM và Vector DB |

---

## 🚀 Hướng dẫn cài đặt từ đầu

### Bước 1 — Clone repository

```bash
git clone https://github.com/<your-username>/Trading_Advisory_Chatbot.git
cd Trading_Advisory_Chatbot
```

### Bước 2 — Cài đặt Ollama & tải model LLM

Tải và cài đặt **Ollama** tại: https://ollama.com/download

Sau khi cài xong, mở terminal và tải model Qwen 2.5 7B:

```bash
ollama pull qwen2.5:7b
```

> ⚠️ **Lưu ý:** Ollama phải đang **chạy nền** trước khi khởi động app. Kiểm tra bằng: `ollama list`

### Bước 3 — Tạo môi trường Python ảo

**Windows (PowerShell):**
```powershell
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Bước 4 — Cài đặt thư viện Python

```bash
pip install -r requirements.txt
```

> 📦 Các thư viện được cài:
> - `streamlit` — Giao diện web
> - `qdrant-client` — Vector database cục bộ
> - `sentence-transformers` — Mô hình nhúng văn bản (BAAI/bge-m3)
> - `pymupdf` — Đọc và bóc tách nội dung file PDF
> - `ollama` — Kết nối với Ollama LLM

### Bước 5 — Thêm tài liệu PDF

Đặt các file PDF tài liệu tài chính, phân tích XAUUSD, hoặc chiến lược giao dịch vào thư mục:

```
data/raw_pdfs/
```

> 💡 **Ví dụ:** báo cáo kinh tế, tài liệu phân tích kỹ thuật vàng, chiến lược giao dịch, v.v.

### Bước 6 — Khởi chạy ứng dụng

```bash
streamlit run src/app.py
```

Truy cập trình duyệt tại: **http://localhost:8501**

---

## 📚 Hướng dẫn sử dụng lần đầu

Sau khi app mở trên trình duyệt, thực hiện theo thứ tự:

```
1. Sidebar bên trái → Bấm "🔄 Cập nhật Kho Tri thức (Ingestion)"
   └─ Hệ thống sẽ đọc tất cả PDF → mã hóa → lưu vào Qdrant DB

2. Nhập câu hỏi vào khung chat bên dưới
   └─ Ví dụ: "Lạm phát ảnh hưởng như thế nào đến giá vàng?"

3. AI sẽ trả lời dựa trên nội dung tài liệu PDF của bạn
   └─ Bấm "🔍 Xem nguồn tài liệu đối chiếu" để xem đoạn trích dẫn gốc
```

> ⚠️ **Quan trọng:** Mỗi lần thêm PDF mới vào `data/raw_pdfs/`, bạn phải bấm lại nút **"Cập nhật Kho Tri thức"** để hệ thống nhận dạng tài liệu mới.

---

## 🧪 Kiểm thử từng module độc lập

Dùng các lệnh sau để kiểm tra từng tầng riêng lẻ (chạy từ thư mục gốc project):

```bash
# Kiểm tra bóc tách PDF
python -m src.services.parser_service

# Kiểm tra nạp dữ liệu vào Vector DB
python -m src.services.vector_service

# Kiểm tra kết nối Ollama LLM
python -m src.services.llm_service

# Kiểm thử toàn bộ pipeline RAG (end-to-end)
python -m src.orchestrator
```

---

## 📁 Cấu trúc thư mục

```
Trading_Advisory_Chatbot/
├── data/
│   ├── raw_pdfs/           ← Đặt file PDF tài liệu vào đây
│   └── qdrant_db/          ← Vector DB tự động tạo (không commit git)
├── src/
│   ├── core/
│   │   └── database.py     ← Singleton: Quản lý Qdrant client & Embedding model
│   ├── services/
│   │   ├── parser_service.py   ← Bóc tách & chunking PDF (PyMuPDF)
│   │   ├── vector_service.py   ← Mã hóa vector & tìm kiếm (Qdrant + BGE-M3)
│   │   └── llm_service.py      ← Gọi Qwen 2.5 7B qua Ollama
│   ├── orchestrator.py     ← Facade: Điều phối toàn bộ pipeline RAG
│   ├── config.py           ← Cấu hình tập trung (paths, model names, params)
│   └── app.py              ← Giao diện Streamlit
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ Cấu hình nâng cao

Chỉnh sửa file `src/config.py` để thay đổi các tham số:

```python
LLM_MODEL_NAME       = "qwen2.5:7b"     # Thay bằng model Ollama khác nếu muốn
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"    # Model nhúng (vector 1024 chiều)
CHUNK_SIZE           = 800              # Độ dài mỗi đoạn văn bản (ký tự)
CHUNK_OVERLAP        = 150             # Đoạn gối đầu giữa các chunk
```

---

## ❓ Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Giải pháp |
|---|---|---|
| `Error connecting to Ollama` | Ollama chưa chạy | Khởi động Ollama, chạy `ollama serve` |
| `model not found` | Chưa tải model | Chạy `ollama pull qwen2.5:7b` |
| `Qdrant AlreadyLocked` | Nhiều tiến trình Streamlit cùng chạy | Tắt hết tab cũ, khởi động lại `streamlit run` |
| `Không có đoạn văn bản nào` | Thư mục PDF trống | Đặt file `.pdf` vào `data/raw_pdfs/` |

---

## 📝 License

MIT License — Tự do sử dụng, chỉnh sửa và phân phối.

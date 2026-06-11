<div align="center">

# AI Trading Advisory System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Groq API](https://img.shields.io/badge/Groq-Llama_3.3-F55036)](https://groq.com/)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Cloud_LLM-4A90E2)](https://openrouter.ai/)
[![Google AI Studio](https://img.shields.io/badge/Google-Gemini_Flash-blue)](https://aistudio.google.com/)
[![Cohere](https://img.shields.io/badge/Cohere-Reranker-FF0000)](https://cohere.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B)](https://streamlit.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-purple)](https://qdrant.tech/)
[![Docker](https://img.shields.io/badge/Docker-Container-2496ED)](https://www.docker.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Persistent_Storage-47A248)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/Redis-Memory_Cache-DC382D)](https://redis.io/)

**Hệ thống Tư vấn Giao dịch Tài chính (XAUUSD & Forex) dựa trên Kiến trúc Micro-Model Agentic RAG.**

</div>

---

## Tổng Quan Dự Án

Trading Advisory System là một hệ thống phần mềm tư vấn tài chính cấp độ chuyên nghiệp, được thiết kế để phân tích hành vi giá (Price Action), cấu trúc thị trường (SMC) và dữ liệu vĩ mô theo thời gian thực. Hệ thống loại bỏ hoàn toàn các điểm nghẽn của một ứng dụng RAG (Retrieval-Augmented Generation) truyền thống bằng cách áp dụng kiến trúc **Micro-Model Agentic Routing**, chia nhỏ các luồng suy luận phức tạp và giao phó cho các mô hình AI chuyên biệt. 

Dự án này là minh chứng cho khả năng thiết kế hệ thống phân tán, tối ưu hóa API đa nền tảng và xử lý dữ liệu tài chính độ trễ thấp, hoàn toàn phù hợp để triển khai trong môi trường thực tế (Production-ready).

---

## Kiến Trúc Cốt Lõi & Đột Phá Kỹ Thuật

### 1. Kiến trúc Micro-Model Agentic Routing
Thay vì phụ thuộc vào một mô hình ngôn ngữ khổng lồ (Monolithic LLM) gây chậm trễ và lãng phí tài nguyên, hệ thống triển khai một Pipeline điều phối thông minh:
- **Ultra-low Latency Gateway (Groq Llama 3.3 70B):** Chịu trách nhiệm phân loại ý định (Intent Classification), viết lại truy vấn (Query Rewriting) và đánh giá độ chính xác (Hallucination Evaluation). Với tốc độ xử lý >800 tokens/giây, Groq đảm bảo giai đoạn tiền xử lý diễn ra gần như tức thời.
- **Dynamic Tool Selector (OpenRouter / NVIDIA Nemotron):** Hoạt động như một bộ gọi hàm (Function Calling) chuyên dụng. Hệ thống tự động phân tích ngữ cảnh người dùng để trích xuất các tham số tĩnh như mã tài sản (`symbol`), khung thời gian (`timeframe`), và giới hạn dữ liệu nến (`limit`).
- **Core Reasoning Engine (Google Gemini 2.5 Flash):** Đóng vai trò là trung tâm phân tích cuối cùng. Khả năng nạp ngữ cảnh lớn (Long-context Window) giúp mô hình này tiêu hóa đồng thời hàng ngàn cụm từ (chunks) từ VectorDB và bảng dữ liệu giá để tổng hợp ra các quyết định giao dịch chiến lược.

### 2. Tích hợp Dữ liệu Thời gian thực & Nhận thức ngữ cảnh
- **Dynamic Time Awareness:** Hệ thống được cấy ghép module nhận thức thời gian, cho phép AI tính toán chính xác ngày, giờ, múi giờ và các mốc thời gian tương đối (ví dụ: "15 phút trước", "giá mở cửa hôm qua") để gán tham số gọi API chuẩn xác.
- **Multi-Timeframe OHLCV Parsing:** Tích hợp trực tiếp với Oanda và Yahoo Finance API, tự động trích xuất biểu đồ nến trên các khung thời gian linh hoạt (1m, 5m, 15m, 1h, 1d). Mã nguồn bao gồm cơ chế chuẩn hóa múi giờ (Timezone Normalization) từ EST sang chuẩn UTC để đảm bảo thuật toán AI phân tích độ lệch giá không bị sai số.
- **Macroeconomic Event Scraper:** Tự động thu thập Lịch kinh tế (ForexFactory) với bộ nhớ đệm (Memory Cache) tích hợp nhằm vượt qua các giới hạn Rate Limit (Lỗi 429), đồng thời quy đổi toàn bộ lịch phát hành tin tức sang múi giờ địa phương (UTC+7).

### 3. Advanced Retrieval-Augmented Generation (RAG)
- **Hybrid Search & Cloud Reranking:** Kết hợp cơ sở dữ liệu Qdrant (Dense Retrieval) và API Cohere Rerank. Tài liệu được truy xuất sẽ trải qua bước chấm điểm lại (Cross-encoder Reranking) để giữ lại top 3 đoạn văn bản chính xác nhất, giảm thiểu tối đa Token Overhead.
- **Smart Incremental Ingestion:** Quá trình nạp tài liệu được kiểm soát chặt chẽ bằng thuật toán băm (SHA-256). Hệ thống chỉ thực hiện quy trình Embedding đối với những tệp PDF mới thêm vào hoặc bị thay đổi, giúp tiết kiệm triệt để tài nguyên tính toán nội bộ.

### 4. Hệ thống Bộ nhớ Lai (Resilient Hybrid Memory)
- **Global Session Memory:** Áp dụng cấu trúc lưu trữ song song: Redis (Cache tốc độ cao phục vụ luồng chat) và MongoDB (Lưu trữ vĩnh cửu dữ liệu JSON).
- **Graceful Fallback & Push-Only Strategy:** Trong trường hợp Redis Cache bị dọn dẹp hoặc khởi động lại, hệ thống sẽ tự động khôi phục toàn bộ ngữ cảnh từ MongoDB. Cơ chế sử dụng toán tử `$push` đảm bảo dữ liệu luôn được ghi tuần tự, loại trừ tuyệt đối nguy cơ ghi đè hoặc mất mát dữ liệu phiên.

---

## Sơ Đồ Kiến Trúc Hệ Thống (Architecture Diagram)

```mermaid
graph TD
    User(["Client / User"]) -->|HTTP Request| UI["Streamlit Interface"]
    UI -->|Query| Gatekeeper{"Intent Gateway (Groq)"}
    
    Gatekeeper -->|TRASH| Reject["Static Warning"]
    Gatekeeper -->|GREETING| ChitChat["Social Response"]
    Gatekeeper -->|FINANCIAL_RAG| QR["Query Normalizer (Groq)"]
    
    QR --> Orchestrator["Agent Orchestrator"]
    
    Orchestrator -->|1. Request Tools| ToolSelector["Tool Selector (Groq)"]
    ToolSelector -.->|2. Return JSON| Orchestrator
    
    subgraph Execution Layer
        Orchestrator -->|3. Call| VS["Qdrant Vector DB"]
        VS -->|Retrieve| Reranker["Cohere Cloud Reranker"]
        Orchestrator -->|3. Call| Live["Data Service (Oanda/YFinance)"]
        Orchestrator -->|3. Call| Mem["MongoDB & Redis Cache"]
    end
    
    Execution Layer -->|4. Augmented Context| MainLLM["Reasoning Engine (Gemini)"]
    
    MainLLM --> Evaluator["Hallucination Evaluator (Groq)"]
    Evaluator -->|Approved| UI
    Evaluator -->|Rejected| Orchestrator
```

---

## Yêu Cầu Cấu Hình Hệ Thống

| Thành Phần | Yêu Cầu Kỹ Thuật |
|:---|:---|
| **Hệ Điều Hành** | Tương thích đa nền tảng (Windows, macOS, Linux) |
| **Môi Trường** | Đòi hỏi **Docker** và **Docker Compose** |
| **Phần Cứng** | Tối thiểu 4GB RAM (Khuyến nghị 8GB để chạy DB & Qdrant) |
| **API Keys** | Cần có API từ Google AI Studio, Groq, OpenRouter, Cohere |

---

## Hướng Dẫn Triển Khai (Deployment)

**Bước 1: Sao chép mã nguồn**
```bash
git clone https://github.com/DATCAOTAN/Trading_Advisory_Chatbot.git
cd Trading_Advisory_Chatbot
```

**Bước 2: Cấu hình Môi trường**
Tạo tệp `.env` tại thư mục gốc và cung cấp các khóa API cần thiết:
```env
# Core Reasoning Engine
LLM_PROVIDER=google
GOOGLE_API_KEY=your_google_api_key
GOOGLE_MODEL_NAME=gemini-2.5-flash

# Pre-processing & Fast Evaluation
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL_NAME=llama-3.3-70b-versatile

# Function Calling / Routing
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL_NAME=nvidia/nemotron-3-super-120b-a12b:free

# Document Reranking
COHERE_API_KEY=your_cohere_api_key
```

**Bước 3: Nạp Tri Thức Cốt Lõi**
Đặt các tài liệu tài chính, chiến lược (định dạng `.pdf`) vào các thư mục tương ứng:
- `data/raw_pdfs/static/`: Kiến thức nền tảng (Ví dụ: Phương pháp SMC, Price Action).
- `data/raw_pdfs/dynamic/`: Báo cáo vĩ mô hoặc tin tức cập nhật định kỳ.

**Bước 4: Khởi chạy bằng Docker**
Hệ thống được đóng gói Container hoàn chỉnh. Triển khai bằng một lệnh duy nhất:
```bash
docker-compose up --build -d
```
Giao diện người dùng sẽ sẵn sàng tại `http://localhost:8501`.

---

## Cấu Trúc Thư Mục (Directory Structure)

```text
Trading_Advisory_Chatbot/
├── data/
│   ├── raw_pdfs/               # Kho lưu trữ tài liệu PDF đầu vào
│   ├── qdrant_db/              # Phân vùng lưu trữ Vector DB
│   └── ingestion_state.json    # Trạng thái theo dõi SHA-256
├── src/                        
│   ├── core/
│   │   ├── database.py         # Kết nối MongoDB & Redis
│   │   └── llm_client.py       # Bộ gọi API đa nền tảng (Dynamic Provider)
│   ├── pipelines/
│   │   ├── intent_router.py    # Phân luồng câu hỏi
│   │   └── modules/            # Các tác vụ xử lý tiền kỳ (Query Rewriter)
│   ├── services/
│   │   ├── history_service.py  # Hybrid Memory Manager
│   │   ├── live_data_service.py# Tương tác API thị trường (Oanda/Yahoo)
│   │   ├── vector_service.py   # Embedding & Retrieval Controller
│   │   └── llm_service.py      # Lõi Orchestrator cho luồng Agent
│   ├── ui/                     # Giao diện người dùng (Streamlit Components)
│   ├── config.py               # Quản lý biến môi trường
│   ├── orchestrator.py         # Bộ não điều phối toàn bộ Agentic Pipeline
│   └── app.py                  # Entrypoint giao diện UI
├── docker-compose.yml          # Tệp cấu hình Container
├── Dockerfile                  # Chỉ thị đóng gói ứng dụng
├── launcher.py                 # Tệp khởi chạy cục bộ (Non-docker)
└── requirements.txt            # Danh sách thư viện Python
```

---

## Giấy Phép (License)
Dự án được phân phối dưới giấy phép **MIT**. Hoàn toàn tự do cho các mục đích nghiên cứu, học tập và triển khai thương mại.

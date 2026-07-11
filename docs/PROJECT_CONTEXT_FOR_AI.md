# Project Context For AI Assistants

Tài liệu này là bản handoff ngữ cảnh hiện tại của repo `Trading_Advisory_Chatbot`, dùng để đưa cho GPT, Gemini, Claude hoặc AI coding assistant khác đọc trước khi phân tích/sửa code.

Ngày review cập nhật: 2026-06-22

## 1. Tóm Tắt Nhanh

`Trading_Advisory_Chatbot` là ứng dụng Streamlit tư vấn giao dịch tài chính, tập trung vào XAUUSD/vàng và Forex. Repo hiện có hai lớp phát triển song song:

1. **Runtime app hiện đang chạy**: Streamlit chatbot + legacy RAG pipeline.
2. **Knowledge Platform V3/Sprint 2**: lớp ingestion/catalog/vector mới dùng manifest, metadata registry, SQLite catalog, lock/heartbeat và collection `knowledge_current`; hiện vẫn đứng riêng, chưa được nối vào app chat chính.

Runtime app hiện tại kết hợp:

- Streamlit UI.
- Intent routing bằng LLM.
- Query rewriting.
- Tool selection theo kiểu agentic controller.
- Retrieval từ Qdrant local collection legacy `xauusd_knowledge_v2`.
- Embedding/reranking qua Cohere.
- LLM qua Google AI Studio, Groq, OpenRouter hoặc Ollama fallback.
- Live data qua Oanda, Yahoo Finance, Binance và ForexFactory.
- Chat memory qua MongoDB, Redis và Qdrant collection `chat_history_collection`.

## 2. Entrypoint Và Cách Chạy

Entrypoint chính:

- `src/app.py`: Streamlit app chính.
- `launcher.py`: launcher local Windows, pre-import native libs để tránh crash DLL/thread của Streamlit.
- `Dockerfile`: chạy `streamlit run src/app.py`.
- `docker-compose.yml`: chạy app + Redis + MongoDB.

Chạy bằng Docker:

```bash
docker-compose up --build -d
```

App mặc định ở:

```text
http://localhost:8501
```

Chạy local Windows:

```bash
python launcher.py
```

## 3. Cấu Trúc Repo Quan Trọng

```text
src/
  app.py
  config.py
  orchestrator.py

  core/
    llm_client.py
    database.py

  services/
    llm_service.py
    vector_service.py              # Legacy RAG VectorService đang được app chính dùng
    parser_service.py
    live_data_service.py
    history_service.py
    ingestion_tracker.py
    knowledge/
      catalog_manager.py           # NEW Sprint 2: SQLite catalog + locks
      vector_service.py            # NEW Sprint 2: VectorServiceV3 cho knowledge_current
      metadata_resolver.py
      chunk_builder.py
      validator.py
      manifest_reader.py
      registry_loader.py

  pipelines/
    intent_router.py
    modules/
      router.py
      query_rewriter.py
      reranker.py
      evaluator.py

  ui/
    tab_chatbot.py
    tab_dashboard.py
    tab_settings.py

src/metadata/                      # Registry YAML cho Knowledge Platform V3
docs/architecture/                 # Specs V3.1
scripts/
  kp_manifest.py                   # Tạo manifest/checksum cho PDF
  test_sprint2_safety.py           # Test duplicate/stale-lock cho Sprint 2
data/                              # Qdrant DB, raw PDFs, SQLite catalog, ingestion state
```

## 4. Runtime App Chính Hiện Tại

### 4.1 App Shell

`src/app.py`:

1. Cấu hình Streamlit page.
2. Inject CSS theme.
3. Khởi tạo singleton `RAGOrchestrator`.
4. Khôi phục hoặc tạo chat session bằng `HistoryService`.
5. Render sidebar session list.
6. Render 3 tab:
   - Chatbot
   - Dashboard
   - Settings

### 4.2 Chat Flow

`src/ui/tab_chatbot.py`:

1. Nhận input từ `st.chat_input`.
2. Lưu user message vào session state.
3. Ghi message vào MongoDB/Redis qua `HistoryService`.
4. Gọi `RAGOrchestrator.query_financial_advisor(...)`.
5. Stream answer bằng `st.write_stream`.
6. Render sources nếu có.
7. Parse Entry/SL/TP bằng regex và vẽ Plotly chart nếu đủ dữ liệu.
8. Lưu assistant message vào history.

### 4.3 Orchestrator Flow

`src/orchestrator.py` là facade điều phối runtime RAG:

1. `RouterModule.process()` gọi `IntentRouter.classify()`.
2. Nếu intent là `GREETING` hoặc `TRASH`: early exit, không chạy RAG nặng.
3. Nếu intent là `FINANCIAL_RAG`: chạy pipeline chính.
4. `QueryRewriterModule.process()` rewrite query bằng Groq.
5. `_agent_tool_selector()` gọi LLM để chọn tool:
   - `VectorDB_Search`
   - `Live_API`
   - `Search_Chat_History`
6. Tổng hợp context từ tool outputs.
7. `LLMService.generate_multihop_stream()` sinh câu trả lời.
8. Nếu bật self-correction: sinh draft, gọi evaluator, nếu fail thì reflect query và lặp tối đa 3 vòng.

## 5. Các Service Runtime Chính

### 5.1 LLMClient

File: `src/core/llm_client.py`

Vai trò:

- Chuẩn hóa interface gọi LLM.
- Provider hỗ trợ:
  - `openrouter`
  - `groq`
  - `google`
  - `ollama`
- Hỗ trợ streaming/non-streaming.
- Lọc `<think>...</think>`.
- Cloud provider lỗi thì fallback Ollama.

Lưu ý hiện trạng:

- `LLMService` đang ép generation chính qua `LLMClient(provider_override="google")`.
- Intent router, query rewriter, evaluator và tool selector thường ép Groq.
- `Config.LLM_PROVIDER` không điều khiển toàn bộ pipeline một cách tuyệt đối.

### 5.2 Legacy VectorService

File: `src/services/vector_service.py`

Đây là VectorService đang được `RAGOrchestrator` dùng trong app chính.

Chức năng:

- Qdrant local path: `data/qdrant_db`.
- Collection: `xauusd_knowledge_v2`.
- Cohere embedding: `embed-multilingual-v3.0`, vector 1024d.
- Parse PDF từ `data/raw_pdfs`.
- Parent-child chunking:
  - Child text dùng để embedding/search.
  - Parent text lưu payload để đưa vào LLM.
- Incremental sync qua `IngestionTracker` và `data/ingestion_state.json`.

Lưu ý:

- Comment/docstring vẫn nhắc hybrid/sparse/BGE local, nhưng code hiện tại là dense-only Cohere + Qdrant.
- Reranking nằm ở `src/pipelines/modules/reranker.py`, dùng Cohere Rerank.

### 5.3 PDFParserService

File: `src/services/parser_service.py`

- Đọc PDF bằng PyMuPDF.
- Sliding window chunking.
- Tự phân loại `doc_type = dynamic` nếu path có `dynamic`, ngược lại `static`.
- Dùng `Config.ADAPTIVE_CHUNK_CONFIG` để thay đổi chunk size theo folder.

### 5.4 HistoryService

File: `src/services/history_service.py`

- MongoDB lưu session/messages bền vững.
- Redis cache session 24h.
- Khi append message đủ dài, embed và lưu vào Qdrant collection `chat_history_collection`.
- `Search_Chat_History` query theo `session_id`.

### 5.5 LiveDataService

File: `src/services/live_data_service.py`

Nguồn dữ liệu:

- Crypto: Binance API.
- Forex/vàng:
  - Oanda nếu có API key/account.
  - Yahoo Finance fallback.
- Economic calendar: ForexFactory JSON endpoint, cache 1 giờ.

Cập nhật mới:

- `get_historical_candles(...)` hiện hỗ trợ:
  - `target_date`: tra nến gần nhất trước một thời điểm cụ thể, user time được hiểu là giờ Việt Nam rồi quy đổi UTC.
  - `indicators`: danh sách indicator config.
- Indicator hiện hỗ trợ:
  - EMA: output key `ema_{period}`
  - SMA: output key `sma_{period}`
  - RSI: output key `rsi_{period}`
  - MACD: output keys `macd`, `macd_signal`, `macd_hist`
- Khi target date không có giao dịch chính xác, service trả warning và candle gần nhất trước đó.
- Với indicator cần nhiều lịch sử hơn, service tự tăng `padding_limit`.

## 6. Pipeline Prompt/Behavior Mới Cần Biết

### 6.1 Tool Selector

Trong `src/orchestrator.py`, `_agent_tool_selector()` đã được mở rộng:

- `Live_API` được gọi không chỉ khi hỏi giá hiện tại, mà khi cần bất kỳ dữ liệu giá/nến/xu hướng thực tế/indicator kỹ thuật.
- Nếu người dùng hỏi thời điểm cụ thể nhưng không nói timeframe, prompt yêu cầu dùng timeframe `1m`.
- Tool args có thể gồm:

```json
{
  "symbol": "XAUUSD",
  "timeframe": "1m",
  "limit": 10,
  "target_date": "2026-06-12 01:30:00",
  "indicators": [{"name": "ema", "period": 50}]
}
```

### 6.2 Query Rewriter

File: `src/pipelines/modules/query_rewriter.py`

Cập nhật mới:

- Nếu query có đại từ hoặc bị khuyết chủ ngữ/tên tài sản, rewriter phải nội suy từ chat history.
- Ví dụ câu hỏi kiểu "còn hôm qua thì sao?" cần tự điền lại asset như XAUUSD/vàng/BTC nếu lịch sử có ngữ cảnh.

### 6.3 LLMService Prompt

File: `src/services/llm_service.py`

Cập nhật mới:

- Với phân tích vĩ mô/tín hiệu giao dịch/số liệu: vẫn phải dựa vào context và không bịa số.
- Với kiến thức tài chính cơ bản như định nghĩa SMC, quan hệ DXY-vàng, lý thuyết trading: LLM được phép dùng kiến thức chuyên gia sẵn có, kết hợp tài liệu trích xuất.

## 7. UI Hiện Tại

### 7.1 Chatbot Tab

File: `src/ui/tab_chatbot.py`

- Hiển thị lịch sử chat.
- Gửi query vào orchestrator.
- Stream answer.
- Render badge intent.
- Render sources.
- Trích Entry/SL/TP và vẽ chart.

### 7.2 Dashboard Tab

File: `src/ui/tab_dashboard.py`

- Hiển thị LLM, embedding, reranker, Qdrant.
- Đọc `ingestion_state.json` để thống kê số chunks legacy.
- Button cập nhật live price và economic calendar.
- Hiển thị path hệ thống.

### 7.3 Settings Tab

File: `src/ui/tab_settings.py`

- Toggle:
  - Query Rewriting
  - Reranker
  - Self-Correction
- Button incremental sync legacy.
- Button force re-index legacy.
- Clear history UI.
- Broker/Oanda config hiện vẫn là placeholder disabled.

## 8. Knowledge Platform V3/Sprint 2

Knowledge Platform V3 là lớp mới trong `src/services/knowledge` và `docs/architecture`. Nó đang phát triển theo hướng source-of-truth độc lập cho multi-agent trading, nhưng hiện chưa được nối vào `src/app.py`, `RAGOrchestrator` hoặc legacy `VectorService`.

### 8.1 Path Convention

`MetadataResolver` và `kp_manifest.py` giả định tài liệu nằm theo convention:

```text
data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{author_slug}/{file.pdf}
```

Nếu path không chứa `knowledge_repository`, file không phải `.pdf`, path quá ngắn, hoặc thiếu `.manifest.yaml`, resolver trả:

```python
{"error": "...", "lifecycle": "QUARANTINE"}
```

### 8.2 Manifest Tool

File: `scripts/kp_manifest.py`

CLI:

```bash
python scripts/kp_manifest.py init <pdf_path>
python scripts/kp_manifest.py checksum <pdf_path>
```

Chức năng:

- Tính SHA-256 checksum.
- Tạo skeleton `<file>.manifest.yaml`.
- Tự suy luận `knowledge_type`, `domain`, `subdomain`, `author_slug` từ path convention.
- Manifest mặc định có `lifecycle: ACTIVE`.

### 8.3 Registry

Folder: `src/metadata`

Các registry YAML:

- `authors.yaml`: dùng key dạng slug như `john_murphy`, có `display_name`, `source_tier`, `aliases`.
- `domains.yaml`: domain/subdomain hợp lệ.
- `knowledge_types.yaml`: book, paper, documentation, regulation, manual, blog, research, note, dataset.
- `assets.yaml`: forex, crypto, stocks, futures, bonds, commodities, macro, all.
- `strategies.yaml`: trend_following, mean_reversion, breakout, scalping, swing, intraday, pairs_trading, statistical_arbitrage, market_making.
- `languages.yaml`: en, vi, ja, zh.

### 8.4 MetadataResolver

File: `src/services/knowledge/metadata_resolver.py`

Chức năng:

- Strict path validation.
- Bắt buộc có manifest cạnh file PDF.
- Đọc manifest và registry.
- Sinh `doc_id` dạng:

```text
{knowledge_type}_{title_slug}_{author_slug}_{version}
```

- Lookup author bằng slug, lấy `display_name` và `source_tier`.
- Duplicate detection bằng checksum qua `KnowledgeCatalog.find_doc_id_by_checksum`.
- Nếu checksum trùng với doc khác, trả `POSSIBLE_DUPLICATE` và `QUARANTINE`.

### 8.5 Validator

File: `src/services/knowledge/validator.py`

Validation layers:

- Schema: domain, knowledge_type, publisher, doc_id.
- Business: domain/subdomain hợp lệ theo registry, lifecycle.
- Integrity: checksum trong manifest phải khớp file thật.

Normalize:

- Chỉ normalize routing metadata, enum/id/slug.
- Không lowercase title/author/publisher để giữ UI display đẹp.

### 8.6 ChunkBuilder

File: `src/services/knowledge/chunk_builder.py`

Cập nhật mới:

- Trả dict thay vì list trực tiếp:

```python
{
  "status": "CHUNKED|EMPTY_DOCUMENT|NEEDS_OCR|PARTIAL_TEXT|FAILED",
  "chunks": [...],
  "operational_metadata": {...}
}
```

- Có OCR guardrail:
  - Tính `extraction_quality_score`.
  - Đếm `empty_pages`/`total_pages`.
  - Nếu toàn bộ rỗng: `EMPTY_DOCUMENT`.
  - Nếu quality < 0.2: `NEEDS_OCR`, không trả chunks.
  - Nếu quality < 0.8: `PARTIAL_TEXT`.
- Chunker version hiện là `v1.2`.

### 8.7 KnowledgeCatalog

File: `src/services/knowledge/catalog_manager.py`

SQLite catalog path mặc định:

```text
data/knowledge_catalog/catalog.sqlite
```

Chức năng:

- SQLite WAL mode.
- `documents` table:
  - `doc_id`, `source_path`, `manifest_path`, `checksum`, `lifecycle`, `index_status`, parser/chunker/embedding/index versions, `chunk_count`, `chunk_ids_hash`, `last_indexed_at`, `error_message`.
- `index_jobs` table:
  - `job_id`, `doc_id`, `job_status`, `worker_id`, `started_at`, `heartbeat_at`, `completed_at`, `log`.
- `acquire_index_lock(doc_id, job_id, worker_id)`.
- `heartbeat(job_id)`.
- `get_stale_jobs(timeout_seconds)`.
- `release_index_lock(doc_id, job_id, status, error_msg)`.
- `find_doc_id_by_checksum(checksum)` để duplicate detection.
- `upsert_document(doc_id, data)`.

### 8.8 VectorServiceV3

File: `src/services/knowledge/vector_service.py`

Collection mặc định:

```text
knowledge_current
```

Chức năng:

- Qdrant local qua `QdrantDatabaseProvider`.
- Cohere `ClientV2` embedding 1024d.
- Tạo collection nếu chưa tồn tại.
- `upsert_document(doc_id, chunks, job_id, collection_name="knowledge_current")`:
  - Heartbeat sau mỗi batch.
  - Delete vectors cũ theo `doc_id`.
  - Upsert points với deterministic point id `uuid5(NAMESPACE_URL, chunk_id)`.
  - Payload giàu metadata: `doc_id`, `chunk_id`, `text`, page, routing metadata, lifecycle, document metadata, operational metadata.
  - Tính `chunk_ids_hash`.
  - Update catalog và release lock thành `INDEXED`.
  - Nếu lỗi: delete orphan vectors, release lock `FAILED`.
- `reconcile_index_jobs(timeout_seconds=300)`:
  - Tìm stale running jobs.
  - Delete vectors theo `doc_id`.
  - Mark job/document `FAILED` với log stale lock timeout.

### 8.9 Sprint 2 Safety Test

File: `scripts/test_sprint2_safety.py`

Test hiện có:

1. Duplicate detection qua checksum trong SQLite catalog.
2. Stale lock/heartbeat timeout:
   - Tạo lock.
   - Ép `heartbeat_at` về quá khứ.
   - Gọi `VectorServiceV3.reconcile_index_jobs`.
   - Kỳ vọng document status thành `FAILED`.

Lưu ý: test cần import package từ project root và `VectorServiceV3` cần `COHERE_API_KEY`/Qdrant khả dụng; nếu không sẽ skip phần vector.

## 9. Hai Pipeline Ingestion Đang Song Song

Hiện cần phân biệt rõ:

### 9.1 Legacy Ingestion Đang Được App Dùng

- File: `src/services/vector_service.py`
- Trigger từ Settings tab qua `orchestrator.sync_knowledge_base()`.
- Input: `data/raw_pdfs/static`, `data/raw_pdfs/dynamic`, hoặc `data/raw_pdfs`.
- State: `data/ingestion_state.json`.
- Collection: `xauusd_knowledge_v2`.
- Metadata đơn giản: `source`, `doc_type`, `parent_text`, `child_text`.

### 9.2 Knowledge Platform V3 Ingestion

- Files: `src/services/knowledge/*`, `scripts/kp_manifest.py`.
- Input expected: `data/knowledge_repository/...`.
- State/catalog: `data/knowledge_catalog/catalog.sqlite`.
- Collection: `knowledge_current`.
- Metadata giàu hơn, lifecycle, checksum, locks, heartbeat.
- Chưa được app chính gọi.

AI assistant khi sửa ingestion phải hỏi/nhận diện task đang nhắm vào legacy app hay V3 platform. Đừng trộn hai đường nếu user không yêu cầu.

## 10. Cấu Hình Và Dependencies

File `.env.example` mô tả:

```env
LLM_PROVIDER=openrouter|google|groq|ollama
OPENROUTER_API_KEY=
OPENROUTER_MODEL_NAME=
GROQ_API_KEY=
GROQ_MODEL_NAME=
GOOGLE_API_KEY=
GOOGLE_MODEL_NAME=
COHERE_API_KEY=
OANDA_API_KEY=
OANDA_ACCOUNT_ID=
REDIS_URL=
MONGO_URI=
```

Dependencies trong `requirements.txt` hiện có:

- pymupdf
- qdrant-client
- streamlit
- ollama
- plotly
- openai
- cohere
- python-dotenv
- redis
- pymongo
- requests
- yfinance
- groq

Lưu ý dependency:

- Code mới import `yaml` trong `scripts/kp_manifest.py` và `src/services/knowledge/*`, nhưng `requirements.txt` hiện **chưa có `PyYAML`**.
- `live_data_service.py` import `pandas` và `numpy`, nhưng `requirements.txt` hiện **chưa khai báo trực tiếp `pandas`/`numpy`**. Chúng có thể được kéo theo bởi `yfinance`, nhưng production nên khai báo rõ nếu code dùng trực tiếp.

## 11. Điểm Lệch Giữa Docs Và Runtime

1. README/docs mô tả kiến trúc rất rộng, nhưng app chính hiện vẫn dùng legacy RAG path.
2. Knowledge Platform V3/Sprint 2 đã có code thực tế hơn trước, nhưng chưa nối vào UI/runtime chat.
3. `knowledge_current`/SQLite catalog là nhánh mới; app chat vẫn search `xauusd_knowledge_v2`.
4. Docs nói blue-green alias cho `knowledge_current`, nhưng `VectorServiceV3` hiện đang dùng collection name trực tiếp và sẽ create collection nếu thiếu.
5. `Config.ENABLE_HYBRID_SEARCH` tồn tại nhưng legacy retrieval hiện là dense-only Cohere.
6. UI gọi "BGE Reranker" nhưng thực tế reranker hiện là Cohere API.
7. Broker/Oanda config trong Settings vẫn là placeholder disabled.

## 12. Bug/Rủi Ro Hiện Biết

### 12.1 EvaluatorModule sai kiểu response

File: `src/pipelines/modules/evaluator.py`

Code hiện xử lý:

```python
response = self.llm_client.chat(...)
result = response.strip().upper()
```

Nhưng `LLMClient.chat(stream=False)` trả dict:

```python
{"message": {"content": "..."}}
```

Kết quả: evaluator raise exception rồi fallback `(True, "")`, khiến self-correction gần như không hoạt động đúng.

### 12.2 Toggle reranker có thể chưa tác dụng đầy đủ

`query_financial_advisor(..., enable_reranker=True)` nhận tham số nhưng orchestrator không truyền trực tiếp vào `RerankerModule`. Module đọc `Config.ENABLE_RERANKER`.

### 12.3 Source rendering sai schema

`RerankerModule` trả docs dạng:

```python
{"content": "...", "metadata": {"source": "..."}, "score": ...}
```

Nhưng `tab_chatbot._render_sources()` đọc `parent_text` và `source` ở top-level. Preview nguồn có thể trống/sai.

### 12.4 Legacy VectorService fallback trả sai kiểu

`retrieve_candidates()` annotate `List[Dict]`, nhưng khi lỗi/no data có thể trả tuple/string. Orchestrator/reranker có thể gặp lỗi schema.

### 12.5 Dependency thiếu

- Thiếu `PyYAML`.
- Nên khai báo trực tiếp `pandas` và `numpy`.

### 12.6 Sprint 2 test có tác dụng phụ local

`scripts/test_sprint2_safety.py` ghi vào `data/knowledge_catalog/catalog.sqlite`, tạo/ghi trạng thái test như `book_original_john_murphy_v1` và `test_doc_stale`. Khi chạy test nhiều lần cần biết catalog local sẽ bị thay đổi.

### 12.7 Encoding/mojibake khi đọc bằng PowerShell

Một số output tiếng Việt hiển thị mojibake trong terminal. Cần phân biệt lỗi hiển thị terminal với file encoding thật. Nếu chỉnh tài liệu, nên giữ UTF-8.

## 13. Worktree Hiện Tại Khi Review

Tại thời điểm review cập nhật, `git status --short`:

```text
 M src/orchestrator.py
 M src/pipelines/modules/query_rewriter.py
 M src/services/live_data_service.py
 M src/services/llm_service.py
?? data/
?? docs/
?? scripts/
?? src/metadata/
?? src/services/knowledge/
```

Các thay đổi/untracked này có thể là cập nhật của user. AI assistant không được revert nếu không được yêu cầu.

## 14. Thứ Tự Đọc Repo Cho AI Khác

Nếu task liên quan app/chat runtime:

1. `src/app.py`
2. `src/orchestrator.py`
3. `src/core/llm_client.py`
4. `src/services/llm_service.py`
5. `src/services/vector_service.py`
6. `src/services/live_data_service.py`
7. `src/pipelines/intent_router.py`
8. UI tab liên quan trong `src/ui`

Nếu task liên quan Knowledge Platform V3/Sprint 2:

1. `docs/architecture/*.md`
2. `scripts/kp_manifest.py`
3. `src/services/knowledge/metadata_resolver.py`
4. `src/services/knowledge/validator.py`
5. `src/services/knowledge/chunk_builder.py`
6. `src/services/knowledge/catalog_manager.py`
7. `src/services/knowledge/vector_service.py`
8. `scripts/test_sprint2_safety.py`

Nếu task liên quan live data:

1. `src/services/live_data_service.py`
2. `_agent_tool_selector()` trong `src/orchestrator.py`
3. Prompt output context trong `query_financial_advisor`

## 15. Ưu Tiên Sửa Tiếp

Ưu tiên cao:

1. Sửa `EvaluatorModule` để đọc `response["message"]["content"]`.
2. Sửa source rendering schema trong `tab_chatbot.py`.
3. Chuẩn hóa return type của legacy `VectorService.retrieve_candidates()`.
4. Làm toggle reranker thực sự điều khiển reranker.
5. Thêm `PyYAML`, `pandas`, `numpy` vào `requirements.txt`.

Ưu tiên trung bình:

1. Quyết định khi nào migration từ legacy `xauusd_knowledge_v2` sang V3 `knowledge_current`.
2. Viết CLI/pipeline end-to-end cho V3: resolve -> validate -> chunk -> acquire lock -> upsert -> release lock.
3. Đồng bộ docs với thực tế `VectorServiceV3` đang dùng collection trực tiếp thay vì alias blue-green.
4. Thêm tests không cần network/API bằng mock Cohere/Qdrant.
5. Dọn comment/docstring cũ về hybrid/sparse/BGE trong legacy path.

Ưu tiên thấp:

1. Dọn import trùng trong `tab_dashboard.py`.
2. Dọn hàm không còn dùng trong orchestrator.
3. Đổi label UI "BGE Reranker" thành "Cohere Reranker" nếu tiếp tục dùng Cohere.

## 16. Clean Code Architecture Guide Cho AI Agents

Phần này mô tả cách nhìn dự án theo clean code/clean architecture để AI coding agents không sửa code theo kiểu phá ranh giới module.

### 16.1 Ranh Giới Trách Nhiệm Hiện Tại

Runtime app đang có các lớp trách nhiệm tương đối rõ:

```text
UI Layer
  src/app.py
  src/ui/*.py

Application Orchestration Layer
  src/orchestrator.py
  src/pipelines/*.py
  src/pipelines/modules/*.py

Domain/Service Layer
  src/services/*.py
  src/services/knowledge/*.py

Infrastructure Layer
  src/core/llm_client.py
  src/core/database.py
  external APIs: Cohere, Groq, Google, OpenRouter, Ollama, MongoDB, Redis, Qdrant, Yahoo/Oanda/Binance

Configuration/Data Contracts
  src/config.py
  src/metadata/*.yaml
  docs/architecture/*.md
```

Nguyên tắc sửa code:

- UI chỉ render và nhận input, không gọi trực tiếp Cohere/Qdrant/LLM nếu đã có service tương ứng.
- Orchestrator chỉ điều phối flow, không nên chứa logic parsing PDF, embedding, database schema hoặc UI rendering.
- Service layer xử lý nghiệp vụ/hạ tầng cụ thể, nhưng nên giữ interface rõ ràng để orchestrator gọi.
- `core` là wrapper hạ tầng dùng chung, không nên biết logic trading/RAG cụ thể.
- `services/knowledge` là nhánh V3 riêng; không được trộn vào legacy `services/vector_service.py` nếu task không yêu cầu migration.

### 16.2 Dependency Direction Nên Giữ

Hướng phụ thuộc mong muốn:

```text
UI -> Orchestrator/Pipelines -> Services -> Core/External APIs
Knowledge scripts -> services/knowledge -> core/database + external APIs
```

Không nên tạo phụ thuộc ngược:

- `services/*` import từ `ui/*`.
- `core/*` import từ `orchestrator.py` hoặc `ui/*`.
- `services/knowledge/*` phụ thuộc vào legacy `services/vector_service.py`.
- Legacy runtime tự động dùng `VectorServiceV3` nếu chưa có migration plan.

### 16.3 Hai Bounded Context Cần Tách Rõ

#### Legacy Runtime Context

Mục tiêu: app Streamlit đang hoạt động.

Các file chính:

- `src/app.py`
- `src/orchestrator.py`
- `src/services/vector_service.py`
- `src/services/parser_service.py`
- `src/services/ingestion_tracker.py`
- `src/ui/*.py`

Data contracts:

- Qdrant collection: `xauusd_knowledge_v2`
- PDF input: `data/raw_pdfs/...`
- State: `data/ingestion_state.json`
- Source docs schema: thường là `{content, metadata, score}` sau rerank.

#### Knowledge Platform V3 Context

Mục tiêu: ingestion/catalog/vector platform mới.

Các file chính:

- `src/services/knowledge/metadata_resolver.py`
- `src/services/knowledge/validator.py`
- `src/services/knowledge/chunk_builder.py`
- `src/services/knowledge/catalog_manager.py`
- `src/services/knowledge/vector_service.py`
- `scripts/kp_manifest.py`
- `scripts/test_sprint2_safety.py`

Data contracts:

- Input path: `data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{author_slug}/{file.pdf}`
- Manifest: `<file>.manifest.yaml`
- Catalog: `data/knowledge_catalog/catalog.sqlite`
- Qdrant collection: `knowledge_current`
- ChunkBuilder output: dict có `status`, `chunks`, `operational_metadata`
- Index lock: `KnowledgeCatalog.acquire_index_lock(...)` trước khi upsert

AI agents phải hỏi rõ hoặc suy luận rõ task đang thuộc context nào. Nếu task nói "chatbot hiện tại", "Settings sync", "Qdrant đang trả lời chat" thì thường là legacy runtime. Nếu task nói "manifest", "catalog", "knowledge_repository", "heartbeat", "Sprint 2" thì là Knowledge Platform V3.

### 16.4 Data Contract Cần Giữ Ổn Định

Các contract quan trọng:

```python
# LLMClient non-stream response
{"message": {"content": "..."}}

# RerankerModule document output
{"content": "...", "metadata": {"source": "...", "doc_type": "..."}, "score": 0.123}

# LiveDataService candle
{
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "open": float,
  "high": float,
  "low": float,
  "close": float,
  "volume": float
}

# Knowledge Platform chunk result
{
  "status": "CHUNKED|EMPTY_DOCUMENT|NEEDS_OCR|PARTIAL_TEXT|FAILED",
  "chunks": [...],
  "operational_metadata": {...}
}
```

Khi sửa code, ưu tiên sửa consumer/producer để thống nhất schema, không thêm nhiều schema phụ tùy tiện.

### 16.5 Clean Code Rules Cho Repo Này

Nên làm:

1. Giữ function nhỏ, mỗi function chỉ làm một việc rõ.
2. Dùng return type nhất quán, đặc biệt ở service boundaries.
3. Bọc external API calls trong service/core wrapper, không gọi lẻ tẻ từ UI.
4. Với LLM prompts, đặt ở module pipeline/service liên quan, tránh nhét prompt dài vào UI.
5. Với lỗi hạ tầng, trả object lỗi có cấu trúc hoặc raise rõ ràng; tránh trả lúc string, lúc tuple, lúc list.
6. Với code V3, luôn đi qua catalog lock khi indexing.
7. Với code legacy, giữ backward compatibility với UI hiện tại nếu chưa migrate.
8. Khi thêm dependency mới, cập nhật `requirements.txt`.
9. Khi thêm schema mới, cập nhật tài liệu context này hoặc docs architecture tương ứng.
10. Khi sửa logic nhiều tầng, thêm smoke test hoặc script test tối thiểu.

Không nên làm:

1. Không cho UI gọi trực tiếp Cohere/Qdrant/Groq.
2. Không xóa/recreate collection quan trọng nếu không có yêu cầu rõ.
3. Không trộn `knowledge_current` vào `xauusd_knowledge_v2` trong cùng một hàm.
4. Không sửa prompt bằng cách thêm chỉ dẫn mâu thuẫn với prompt hiện có.
5. Không swallow exception rồi trả success giả ở các module kiểm duyệt/evaluator.
6. Không thay đổi path convention của V3 nếu không cập nhật `kp_manifest.py`, `MetadataResolver`, docs và tests.

### 16.6 Thông Tin Đủ Để Chatbot Khác Tự Tạo Prompt Cho CLI Agent

Tài liệu này không cần chứa prompt mẫu cụ thể. Thay vào đó, chatbot khác nên dùng các dữ kiện dưới đây để tự sinh prompt phù hợp với task cụ thể.

Khi tạo prompt cho CLI coding agent, chatbot nên luôn xác định:

1. **Task thuộc bounded context nào**
   - Legacy runtime app.
   - Knowledge Platform V3/Sprint 2.
   - Live data.
   - UI rendering.
   - LLM/prompt behavior.
   - Migration giữa legacy và V3.

2. **Mục tiêu hành vi**
   - Agent cần sửa lỗi, thêm tính năng, refactor, viết test hay chỉ phân tích.
   - Kết quả mong muốn nên mô tả bằng behavior/output, không chỉ bằng tên file.

3. **Ranh giới file**
   - Chỉ định file/module được phép sửa.
   - Chỉ định file/module chỉ được đọc để tham khảo.
   - Nếu task nhỏ, tránh cho agent sửa toàn repo.

4. **Contract phải giữ**
   - LLM response dict.
   - Source schema cho UI.
   - Candle schema.
   - ChunkBuilder result schema.
   - Collection name và storage path.

5. **Ràng buộc an toàn**
   - Không revert unrelated changes.
   - Không xóa collection/database nếu không được yêu cầu.
   - Không gọi network trong test nếu không cần.
   - Không trộn legacy runtime với Knowledge Platform V3 khi task chưa yêu cầu migration.

6. **Verification**
   - Ít nhất chạy AST parse cho `src/` và `scripts/`.
   - Nếu có pure function, thêm/chạy test nhỏ không cần API.
   - Nếu liên quan external API, ưu tiên mock/dry-run.

7. **Output mong muốn từ CLI agent**
   - File đã sửa.
   - Hành vi trước/sau.
   - Test/verification đã chạy.
   - Rủi ro còn lại.

### 16.7 Ma Trận Gợi Ý Sinh Prompt Theo Loại Task

| Loại task | Context cần nêu | File nên đọc | File thường được sửa | Contract cần nhắc |
|---|---|---|---|---|
| Fix evaluator/self-correction | Legacy runtime, LLM pipeline | `src/core/llm_client.py`, `src/pipelines/modules/evaluator.py`, `src/orchestrator.py` | `src/pipelines/modules/evaluator.py` | `LLMClient.chat(stream=False)` trả `{"message": {"content": "..."}}` |
| Fix source rendering | Legacy runtime UI | `src/ui/tab_chatbot.py`, `src/pipelines/modules/reranker.py`, `src/services/vector_service.py` | `src/ui/tab_chatbot.py` | Source sau rerank là `{content, metadata, score}` |
| Fix retrieval schema | Legacy RAG service | `src/services/vector_service.py`, `src/orchestrator.py`, `src/pipelines/modules/reranker.py` | `src/services/vector_service.py`, có thể `src/orchestrator.py` | `retrieve_candidates()` nên trả list ổn định hoặc error object rõ ràng |
| Live data/timeframe/indicator | Legacy runtime live data | `src/services/live_data_service.py`, `src/orchestrator.py` | `src/services/live_data_service.py`, có thể `src/orchestrator.py` | Candle timestamp UTC `YYYY-MM-DDTHH:MM:SSZ`, indicator keys hiện có |
| UI feature/toggle | Streamlit UI + config | `src/app.py`, `src/ui/*.py`, `src/config.py` | tab UI liên quan, có thể `src/config.py` | UI không gọi trực tiếp external APIs nếu đã có service |
| V3 manifest/metadata | Knowledge Platform V3 | `scripts/kp_manifest.py`, `src/services/knowledge/metadata_resolver.py`, `src/metadata/*.yaml` | `scripts/kp_manifest.py`, `metadata_resolver.py`, metadata YAML | Path convention `data/knowledge_repository/...`, manifest cạnh PDF |
| V3 validation/chunking | Knowledge Platform V3 | `validator.py`, `chunk_builder.py`, docs architecture | `validator.py`, `chunk_builder.py` | Validator severity, ChunkBuilder result dict |
| V3 indexing/catalog | Knowledge Platform V3 | `catalog_manager.py`, `vector_service.py`, `scripts/test_sprint2_safety.py` | `catalog_manager.py`, `vector_service.py`, scripts | Acquire/release lock, heartbeat, `knowledge_current`, no full collection delete |
| Migration legacy -> V3 | Cross-context migration | Legacy VectorService, V3 VectorService, orchestrator, UI source schema | Prefer new adapter/config, minimal orchestrator change | Keep fallback to `xauusd_knowledge_v2`, stable `{content, metadata, score}` |

### 16.8 Prompt-Generation Checklist Cho Chatbot Khác

Trước khi sinh prompt cho CLI agent, chatbot nên tự điền checklist này:

```text
Task context:
Primary goal:
Non-goals:
Files to read:
Files allowed to edit:
Files forbidden to edit:
Data contracts to preserve:
External systems involved:
Network/API usage allowed? yes/no:
Persistence side effects allowed? yes/no:
Verification required:
Expected final report:
```

Nếu không điền được `Task context` hoặc `Data contracts to preserve`, chatbot nên đọc lại các section 4-10 và 16 của tài liệu này trước khi tạo prompt.

### 16.9 Scope Control Cho CLI Agents

Để CLI agents code hiệu quả, prompt nên giới hạn phạm vi theo kiểu:

- **Single-file fix**: dùng khi bug nằm rõ ở một file và contract xung quanh đã biết.
- **Two-layer fix**: dùng khi producer/consumer schema lệch nhau, ví dụ service output và UI render.
- **Adapter addition**: dùng khi cần nối hai hệ thống mà không rewrite hệ thống cũ.
- **CLI/script addition**: dùng cho Knowledge Platform V3, ingestion, migration, test tooling.
- **Read-only review**: dùng khi chưa rõ tác động hoặc cần thiết kế trước.

Không nên giao prompt kiểu "refactor toàn bộ project" trừ khi có plan nhiều bước và tiêu chí rollback rõ.

### 16.10 Verification Guidance Cho CLI Agents

Các verification phù hợp theo loại task:

- Sửa Python syntax/logic nhỏ: AST parse `src/` và `scripts/`.
- Sửa pure function: thêm/chạy test local không cần API.
- Sửa live data: test bằng sample candles, tránh network nếu không bắt buộc.
- Sửa LLM wrapper/evaluator: mock response dict/string/error.
- Sửa Streamlit UI helper: test helper function bằng dữ liệu mẫu nếu tách được.
- Sửa V3 catalog: dùng temp SQLite path nếu viết test mới, tránh làm bẩn `data/knowledge_catalog/catalog.sqlite`.
- Sửa V3 vector: mock Cohere/Qdrant hoặc hỗ trợ dry-run nếu thiếu API key.

### 16.11 Output Contract Cho CLI Agents

Prompt sinh ra cho CLI agent nên yêu cầu agent trả lời cuối cùng theo các ý:

- Files changed.
- Behavior changed.
- Contracts preserved.
- Tests/verification run.
- Known remaining risks.

Nếu agent tạo branch/stage/commit thì phải báo rõ. Nếu không chạy được test vì thiếu API key, Docker, Redis, MongoDB hoặc network, phải nói rõ lý do và verification thay thế đã dùng.

## 17. Context Ngắn Để Copy Sang Chatbot Khác

```text
Repo Trading_Advisory_Chatbot là app Python Streamlit tư vấn XAUUSD/Forex dùng RAG. App chính chạy qua src/app.py và src/orchestrator.py. Runtime hiện tại dùng legacy RAG: IntentRouter -> QueryRewriter -> LLM tool selector -> VectorDB_Search/Live_API/Search_Chat_History -> context từ Qdrant collection xauusd_knowledge_v2, live data Yahoo/Oanda/Binance/ForexFactory, chat memory Mongo/Redis/Qdrant -> LLMService stream câu trả lời tiếng Việt. Có nhánh Knowledge Platform V3/Sprint 2 mới trong src/services/knowledge và scripts: manifest/checksum tool, MetadataResolver strict path data/knowledge_repository, Validator, ChunkBuilder OCR guardrail, SQLite KnowledgeCatalog với lock/heartbeat, VectorServiceV3 upsert vào collection knowledge_current và reconcile stale jobs. Nhánh V3 chưa nối vào app chat chính. Bug/rủi ro hiện biết: EvaluatorModule xử lý sai response dict, source rendering sai schema, legacy VectorService fallback sai return type, toggle reranker chưa chắc tác dụng, thiếu PyYAML/pandas/numpy trong requirements, app chính vẫn dùng legacy xauusd_knowledge_v2 chứ chưa dùng knowledge_current.
```

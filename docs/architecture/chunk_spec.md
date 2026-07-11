# Chunking & ID Generation Specification V3.1

Quá trình chia nhỏ văn bản (Chunking) phải gắn kết chặt chẽ với việc định danh tĩnh. Tuyệt đối không dùng UUID ngẫu nhiên cho ID của tài liệu và chunk, giúp việc truy vết và re-index diễn ra chớp nhoáng.

## 1. Document ID Generator
Định danh duy nhất của một tài liệu dựa trên manifest:
```text
doc_id = {knowledge_type}_{title_slug}_{author_slug}_{version}
```
**Ví dụ:** `book_technical_analysis_john_murphy_v1`

## 2. Chunk ID Generator
Định danh duy nhất của một chunk:
```text
chunk_id = {doc_id}_p{page_number}_c{chunk_index}
```
**Ví dụ:** `book_technical_analysis_john_murphy_v1_p132_c04`
- `p132`: Ở trang vật lý 132
- `c04`: Là chunk thứ 4 trên trang đó.

## 3. Chunk Object Structure (Nội bộ)
Chunk Builder sẽ ghép payload:
```json
{
  "chunk_id": "book_technical_analysis_john_murphy_v1_p132_c04",
  "doc_id": "book_technical_analysis_john_murphy_v1",
  "text": "The moving average crossover is...",
  "page": 132,
  "paragraph": 4,
  "offset": 1500,
  
  // Thông tin Chunk chất lượng
  "token_count": 245,
  "char_count": 950,
  "section_title": "EMA Crossover Systems",
  "heading_level": 2,

  "routing_metadata": { ... },
  "document_metadata": { ... },
  "operational_metadata": { ... }
}
```
Việc bổ sung các thông tin chunk chất lượng (`token_count`, `char_count`, `section_title`, `heading_level`) giúp hệ thống sau này dễ dàng thống kê, phân tích nguyên nhân Retrieval lỗi (chunk quá ngắn, mất ngữ cảnh tiêu đề).

Cấu trúc này được bọc lại và bàn giao cho Embedding Service, từ đó Vector Service đẩy vào Qdrant với `id` chính là chuỗi `chunk_id`.

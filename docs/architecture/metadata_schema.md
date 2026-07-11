# Metadata Schema V3.1

Hệ thống Metadata được chia làm các nhóm độc lập để tối ưu hóa hiệu suất Vector DB, độ sạch của Context cho LLM và công tác Debug hệ thống.

## A. Routing Metadata (Qdrant Filters)
Các trường này được index nghiêm ngặt trong Vector DB để phục vụ truy vấn (Hard Filtering). Tất cả đều là Keyword/Enum.

- `domain` (str): Ví dụ `technical`, `risk`, `macro`
- `subdomain` (str): Ví dụ `indicators`, `price_action`
- `strategies` (list[str]): Ví dụ `["trend_following", "breakout"]`
- `assets` (list[str]): Ví dụ `["forex", "crypto", "futures"]`
- `timeframe_focus` (list[str]): Ví dụ `["m15", "h4", "multi"]`
- `knowledge_type` (str): `book`, `paper`, `regulation`, `blog`, `documentation`
- `source_tier` (str): `tier1`, `tier2`, `tier3`
- `language` (str): `en`, `vi`, `ja`

## B. Document Metadata (Hiển thị & Trích dẫn)
Các trường này không tham gia vào logic Lọc (Filtering) mà chỉ đi kèm Payload để trả về cho Agent phục vụ Citation.

- `doc_id` (str): Định danh tĩnh của tài liệu (VD: `book_technical_analysis_john_murphy_v1`)
- `chunk_id` (str): Định danh tĩnh của chunk (VD: `book_technical_analysis_p132_c04`)
- `title` (str): Tiêu đề tài liệu
- `author` (str): Tác giả
- `publisher` (str): Nhà xuất bản (nếu có)
- `edition` (str): Phiên bản ấn bản
- `publish_year` (int): Năm xuất bản
- `page_number` (int): Số trang vật lý
- `original_filename` (str): Tên file gốc
- `checksum` (str): SHA-256 hash của tài liệu gốc

## C. Operational Metadata (Vận hành & Debug)
Nhóm metadata này hoàn toàn ẩn với LLM, chỉ phục vụ cho đội ngũ kỹ sư Audit, Rollback, Re-index, và theo dõi Pipeline.

- `parser_version` (str): Phiên bản của module bóc tách PDF (VD: `v1.2.0`)
- `chunker_version` (str): Phiên bản thuật toán cắt chunk
- `embedding_model` (str): Tên model embedding (VD: `bge-m3`)
- `embedding_version` (str): Phiên bản model embedding (VD: `v2`)
- `index_version` (str): Phiên bản của collection Qdrant
- `ingestion_timestamp` (float): Thời điểm nạp file vào DB
- `last_reindex_at` (float): Thời điểm cập nhật lại file
- `ingestion_status` (str): `SUCCESS`, `FAILED`, `PARTIAL`

## D. Metadata Lưới (Kiến thức Phụ thuộc - Tương lai)
- `related_to`: Các doc_id liên quan
- `prerequisite`: Kiến thức nền tảng cần đọc trước
- `extends`: Phần mở rộng của tài liệu nào
- `same_concept`: Khái niệm tương đương

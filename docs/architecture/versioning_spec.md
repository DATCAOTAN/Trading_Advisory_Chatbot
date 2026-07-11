# Versioning & Re-index Specification V3.1

Kiểm soát vòng đời và cập nhật phiên bản Tri thức theo chuẩn Zero-Downtime.

## 1. Quản lý Vòng Đời (Knowledge Lifecycle)
Mỗi manifest chứa trường `lifecycle` quyết định số phận tài liệu:
- `DRAFT`: Đang trong quá trình viết/biên soạn, Validator sẽ bỏ qua.
- `REVIEWING`: Validator đẩy vào alias staging để dev test.
- `ACTIVE`: Hoạt động và LLM có thể tìm thấy.
- `DEPRECATED`: Đã lỗi thời (VD: Murphy 1999 bị thay bằng Murphy 2025). Không tự động search trừ khi user chỉ định version cũ.
- `ARCHIVED`: Đóng băng, chỉ giữ trên đĩa, không nạp lên RAM/Qdrant.

## 2. Re-index Manager
Cung cấp các lệnh công cụ (CLI/Script) linh hoạt, không bắt buộc quét lại cả Repo:
- `reindex_document(doc_id="book_abc")`: Chỉ xóa và nạp lại đúng doc_id này (dựa vào Qdrant Delete Filter theo doc_id).
- `reindex_author(author="john_murphy")`: Xóa và nạp lại tất cả các sách của John Murphy.
- `reindex_domain(domain="macro")`: Re-index lại toàn bộ mảng Vĩ mô.
- `reindex_repository()`: Build mới toàn bộ hệ thống.

## 3. Qdrant Alias (Blue-Green Deployment)
- Không bao giờ chạy lệnh `client.delete_collection("knowledge_current")`.
- Quy trình `reindex_repository()`:
  1. Tạo collection mới có timestamp hoặc version suffix (VD: `knowledge_v2`).
  2. Nạp toàn bộ vectors mới vào `knowledge_v2`.
  3. Cập nhật Alias (Pointer) `knowledge_current` trỏ sang `knowledge_v2`.
  4. Alias trỏ thành công mới xóa (drop) `knowledge_v1`.
- Quá trình này giúp Agent không bị rớt mạng dù tốn 5 giờ để Embedding.

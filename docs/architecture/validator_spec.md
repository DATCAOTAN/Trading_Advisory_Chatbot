# Validator Specification V3.1

Tầng Validator có nhiệm vụ chặn đứng rác dữ liệu trước khi chúng được đưa vào Embedding Service. 

## Severity Levels
- **INFO**: Báo cáo hành vi bình thường.
- **WARNING**: Thiếu thông tin không quá nghiêm trọng (Ví dụ: Thiếu `publisher`). Vẫn cho phép đi tiếp.
- **ERROR**: Sai logic nghiệp vụ nhưng có thể bỏ qua chunk đó.
- **FATAL**: Thiếu Routing Metadata (VD: Không có `domain`). Đình chỉ lập tức toàn bộ file.

## 3 Lớp Validation (3 Validation Layers)

### 1. Schema Validation (Kiểm tra Cấu trúc)
Đảm bảo các trường bắt buộc (Required fields) tồn tại và đúng kiểu dữ liệu.
- Chunk sau khi ghép từ Parser và Resolver phải chứa đầy đủ các trường Routing Metadata thiết yếu (`domain`, `subdomain`, `knowledge_type`, `source_tier`).
- Kiểm tra kiểu dữ liệu: `publish_year` phải là số, `assets` phải là mảng.

### 2. Business Validation (Kiểm tra Nghiệp vụ)
Đối chiếu với Registry và Logic kinh doanh.
- Giá trị `domain/subdomain` có nằm trong cấu trúc hợp lệ của `domains.yaml` không?
- `author_slug` có map được với file `authors.yaml` không? Mảng `assets` có chứa giá trị ngoại lai không?
- **Lifecycle Check**: Nếu manifest chỉ định `lifecycle: DEPRECATED` hoặc `lifecycle: ARCHIVED`, Validator sẽ từ chối nạp (WARNING/INFO).

### 3. Integrity Validation (Kiểm tra Toàn vẹn)
Đảm bảo tính nhất quán của dữ liệu vật lý và định danh.
- **Duplicate Detection / Checksum**: Kiểm tra `checksum` của file hiện tại so với checksum cấu hình trong `manifest.yaml` xem file thật có bị sửa đổi trái phép không.
- `doc_id` phải unique trong toàn bộ hệ thống tri thức.
- `chunk_id` không được phép trùng lặp.
- **Normalize**: Đưa toàn bộ Metadata về chữ thường (lowercase), loại bỏ khoảng trắng thừa.

# Citation Engine Specification V3.1

Mục đích: Không cho phép LLM "bịa" nguồn. Nếu Agent tìm thấy kết quả từ Knowledge Platform, nó phải trả về thông tin trích dẫn vật lý chính xác.

## Format Trích Dẫn Chuẩn (Trả về từ Knowledge Service)
`KnowledgeService` sẽ không trả về plain text. Dữ liệu (Data) và Hiển thị (Presentation) phải độc lập. Nó sẽ trả về **Structured Citation Object**:

```json
{
    "content": "Sự giao cắt đường trung bình động (EMA Crossover) là tín hiệu xác nhận xu hướng chậm...",
    "citation": {
        "doc_id": "book_technical_analysis_john_murphy_v1",
        "title": "Technical Analysis of the Financial Markets",
        "author": "John Murphy",
        "page": 132,
        "chunk_id": "book_technical_analysis_john_murphy_v1_p132_c04",
        "source_tier": "tier2"
    },
    "score": 0.91
}
```

## Render Layer (Dành cho Agent/UI)
Sau khi Agent hoặc giao diện người dùng nhận được Object trên, chúng có quyền tự do biến tấu định dạng hiển thị (Markdown, HTML...).
Ví dụ một Template Render mặc định có thể là:
```text
[CITATION BEGIN]
Doc ID: {doc_id}
Title: {title}
Author: {author}
Page: {page}
Source Tier: {source_tier}
[CONTENT]
{chunk_text}
[CITATION END]
```

## Agent Citation Prompt Injection
System Prompt của mọi Agent sử dụng nền tảng này sẽ tự động được tiêm thêm chỉ thị:
> "Khi giải thích kiến thức, bạn bắt buộc phải trích dẫn theo định dạng [Tên sách - Tác giả, Trang X]. Tuyệt đối không tự suy diễn nếu kiến thức không nằm trong các object citation được cung cấp."

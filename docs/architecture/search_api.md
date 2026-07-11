# Search API Specification V3.1

`KnowledgeService` cung cấp giao thức giao tiếp duy nhất cho tất cả các Agent, đóng gói hoàn toàn sự tồn tại của Vector Database.

## 1. SearchRequest Object
Một yêu cầu truy xuất tri thức phải được đóng gói vào object chuẩn hóa:

```python
class SearchRequest:
    query: str
    routing_filters: Dict[str, Any]  # Map 1-1 với Routing Metadata
    retrieval_mode: str = "hybrid"   # Các chế độ: "vector", "keyword", "hybrid"
    rerank: bool = True              # Bật/tắt Cross-Encoder Reranker
    top_k: int = 8                   # Số lượng chunk trả về cuối cùng
    score_threshold: float = 0.7     # Ngưỡng Similarity (Cosine/Dot)
    citation_required: bool = True   # Ép buộc kèm theo thông tin trích dẫn
    allowed_source_tier: List[str] = ["tier1", "tier2", "tier3"] # Giới hạn uy tín
    language: str = "en"             # Ngôn ngữ tìm kiếm
```

## 2. Fallback Logic 5 Cấp
Nếu kết quả `retrieval == 0`, `KnowledgeService` tự động thực hiện nới lỏng Filter (Nới lỏng cấp bậc):
- Cấp 1: `Domain -> Subdomain -> Strategies -> Assets -> Timeframes`
- Cấp 2: `Domain -> Subdomain -> Strategies -> Assets`
- Cấp 3: `Domain -> Subdomain -> Strategies`
- Cấp 4: `Domain -> Subdomain`
- Cấp 5: `Domain`

Không bao giờ tự ý loại bỏ `Domain` filter.

## 3. SearchResponse Object
```python
class SearchResponse:
    chunks: List[Dict]      # Danh sách các chunk sau rerank
    total_found: int        # Tổng số tìm thấy (trước rerank)
    fallback_level: int     # Cấp độ fallback đã kích hoạt (0 là không kích hoạt)
    latency_ms: float       # Thời gian phản hồi
```

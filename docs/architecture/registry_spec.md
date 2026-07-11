# Registry Specification V3.1

Tách bạch quản lý siêu dữ liệu thông qua nhiều file YAML độc lập, giúp việc mở rộng dễ dàng và không xung đột (Merge Conflict) khi sử dụng Git.

## Cấu trúc Thư mục Registry
```text
src/metadata/
├── authors.yaml
├── domains.yaml
├── assets.yaml
├── strategies.yaml
├── knowledge_types.yaml
└── languages.yaml
```

## 1. domains.yaml
Định nghĩa cấu trúc phân cấp chuẩn giữa Domain và Subdomain.
```yaml
technical:
  subdomains:
    - indicators
    - price_action
    - patterns
    - market_structure
    - volume
risk:
  subdomains:
    - position_sizing
    - psychology
    - portfolio_management
```

## 2. authors.yaml
Định danh mức độ uy tín của tác giả.
```yaml
"Federal Reserve":
  source_tier: tier1
"John Murphy":
  source_tier: tier2
"Ray Dalio":
  source_tier: tier1
"Unknown Blog":
  source_tier: tier3
```

## 3. knowledge_types.yaml
Các thể loại tài liệu được phép đưa vào Repository.
```yaml
types:
  - book
  - paper
  - documentation
  - regulation
  - manual
  - blog
  - research
  - note
```

## 4. strategies.yaml / assets.yaml / languages.yaml
Chỉ chứa danh sách mảng (Enums phẳng) để Validator đối chiếu.
```yaml
# assets.yaml
assets:
  - forex
  - crypto
  - stocks
  - futures
  - macro
  - all
```

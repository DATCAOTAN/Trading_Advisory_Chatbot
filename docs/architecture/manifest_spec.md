# Manifest Specification V3.1

`Manifest` là tệp kề vai (sidecar file) bắt buộc đi kèm với từng tài liệu trong Knowledge Repository. Nó định nghĩa Metadata gốc rễ của một tài liệu.

## Quy Tắc Định Danh
Bất kỳ file nào có trong Repository (VD: `technical_analysis.pdf`) ĐỀU PHẢI có file manifest với hậu tố `.manifest.yaml` (VD: `technical_analysis.manifest.yaml`).

## Cấu Trúc Manifest
```yaml
# Thông tin Định danh (ID Generation)
title_slug: "technical_analysis_financial_markets"
author_slug: "john_murphy"
version: "v1"

# Thông tin Hiển thị (Document Metadata)
title: "Technical Analysis of the Financial Markets"
author: "John Murphy"
edition: "2nd Edition"
publish_year: 1999
language: "en"
knowledge_type: "book"

# Thông tin Quản lý Vòng đời
lifecycle: "ACTIVE"  # ACTIVE, DEPRECATED, ARCHIVED, DRAFT, REVIEWING

# Thông tin Mã Hóa (Validation)
checksum: "sha256_hash_cua_file_pdf"

# Gắn nhãn Bổ sung (Routing Metadata)
tags:
  strategies: ["trend_following", "breakout"]
  assets: ["forex", "stocks", "crypto", "futures"]
  timeframe_focus: ["multi"]
```

## Quy Trình Xử Lý
1. `Metadata Resolver` đọc Manifest.
2. Đối chiếu `author_slug` với `authors.yaml` để sinh ra `source_tier`.
3. Đối chiếu `tags` với `strategies.yaml` và `assets.yaml`.
4. Ép tất cả vào Chunk Payload.

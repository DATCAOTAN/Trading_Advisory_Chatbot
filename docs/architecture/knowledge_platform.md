# Knowledge Platform Architecture V3.1

## 1. Mục Tiêu (Objective)
Xây dựng một **Nền tảng Tri thức Tập trung (Centralized Knowledge Platform)** độc lập hoàn toàn với tầng ứng dụng (LLM, Agent) và tầng lưu trữ (Vector DB). Nền tảng này đóng vai trò là "Nguồn chân lý" (Source of Truth) cho toàn bộ hệ sinh thái Multi-Agent Trading (Technical Agent, Risk Agent, Portfolio Agent, v.v.).

## 2. Kiến Trúc Cốt Lõi (Core Architecture)
Hệ thống tuân thủ nghiêm ngặt nguyên lý Single Responsibility và Dependency Inversion.

```mermaid
flowchart TD
    subgraph Knowledge_Repository [Knowledge Repository (Source of Truth)]
        books[books/]
        papers[papers/]
        regs[regulations/]
        docs[documentation/]
    end

    subgraph Ingestion_Pipeline [Ingestion Pipeline (7 Layers)]
        parser[PDF Parser] --> resolver[Metadata Resolver]
        resolver --> registry[Registry Lookup]
        registry --> validator[Schema Validator]
        validator --> chunk[Chunk Builder]
        chunk --> emb[Embedding Service]
        emb --> vec[Vector Service]
    end

    subgraph Vector_Layer [Vector Layer (Search Engine)]
        qd[(Qdrant Index)]
        rr[Cross-Encoder Reranker]
    end

    subgraph Application_Layer [Application Layer]
        ks[Knowledge Service API]
        agents[Technical / Risk / Execution Agents]
    end

    Knowledge_Repository --> parser
    vec --> qd
    qd --> ks
    rr --> ks
    ks --> agents
```

## 3. Định Nghĩa Thành Công (Definition of Done)
Dự án hoàn thành Phase 0 - Kiến trúc khi:
1. Có thể thay Qdrant bằng Milvus mà Agent không cần sửa.
2. Có thể thay Embedding Model mà Search API không thay đổi.
3. Có thể thay LLM mà Citation vẫn hoạt động.
4. Có thể thêm Agent mới mà không phải sửa Knowledge Platform.
5. Có thể re-index một tài liệu mà không ảnh hưởng toàn bộ hệ thống.
6. Có thể rollback sang phiên bản tri thức trước chỉ bằng cách đổi Alias.

## 4. Nguyên Tắc Viết Code (Coding Principles)
- **Dependency Một Chiều**: Không bao giờ đi ngược từ dưới lên trên. `Repository -> Metadata -> Embedding -> Vector -> Knowledge Service -> Agent`.
- **Decoupled**: Mỗi module chỉ biết Input và Output của nó, không quan tâm implementation của module kế tiếp.

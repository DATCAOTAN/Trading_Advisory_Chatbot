# Dashboard, Review, and Analytics

The Evaluation Dashboard is a read/review layer over EvaluationRegistry and related governance artifacts. It does not modify answer generation and does not call providers, retrieval, market APIs, MT5, broker APIs, or account services.

## Dashboard Sections

- Evaluation Registry table: lists normalized registry entries and filterable metadata.
- Detail panel: shows task index, source refs, agent refs, safety index, evaluation index, hashes, limitations, and linked records.
- Chain view: groups JournalReview, BacktestEvaluation, and PaperTradingEvaluation records by request ID and final answer hash.
- Replay view: displays deterministic ReplayHarness results when present.
- Export panel: previews safe review datasets and supports JSON/CSV downloads.
- Persistence panel: saves and reloads safe registry entries through local JSONL and manifest files.
- Human Review section: lets a reviewer add bounded labels, reason codes, redacted notes, and workflow state.
- Review Analytics section: shows coverage, quality score, grounding issue rate, safety issue rate, task leakage rate, reason-code distribution, reviewer activity, and dataset health.
- System Health / Recovery section: validates stores and dashboard state, previews recovery plans, and exports diagnostics.

## Filtering and Inspection

Reviewers can filter by request ID, final answer hash, symbol, record type, status, quality label, review priority, task ID, intent family, safety flag, review status, and severity.

Rows and exports exclude raw prompts, hidden/system prompts, full final answers, full raw documents, secrets, account data, broker data, MT5 data, and order data.

## Dataset Versions

Dataset versions are local snapshots of safe registry rows. They preserve hashes, record counts, request IDs, quality counts, status counts, and safety counts. They are designed for review and regression analysis, not model training automation.

## Human Annotation

Annotations bind to registry ID, request ID, final answer hash, task ID, and record type. Reviewer notes are redacted or rejected if unsafe. Reason codes are bounded so labels remain comparable.

## Metrics

Metrics are deterministic. They summarize review coverage, quality decisions, correctness, grounding, safety, task scope, reason codes, evaluation consistency, dataset quality, reviewer activity, and reviewer disagreement.

## Diagnostics

The health section can detect missing files, corrupt JSONL, invalid manifests, partial chains, malformed task indexes, unsafe fields, and benchmark file errors. Recovery is non-destructive by default.

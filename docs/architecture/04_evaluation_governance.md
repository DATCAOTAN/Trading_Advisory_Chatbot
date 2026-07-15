# Evaluation Governance

Evaluation Governance starts after a final answer exists. It records how the answer behaved, whether its advisory thesis was traceable, and whether follow-up evaluation artifacts remain review-safe.

## Components

- JournalReviewAgent: reviews final answer quality, source reference preservation, compliance status, completeness status, and task coverage.
- BacktestEvaluation: evaluates advisory thesis behavior against historical observation fixtures.
- PaperTradingEvaluation: evaluates advisory follow-up behavior over simulated observation timelines.
- EvaluationRegistry: normalizes journal, backtest, and paper evaluation records for indexing and review.
- ReplayHarness: replays deterministic evaluation fixtures without provider, retrieval, market, MT5, broker, or account calls.
- EvaluationPersistenceStore: persists safe registry entries to local JSONL and dataset version manifests.
- DatasetVersionManifest: tracks versioned review datasets.
- HumanReviewAnnotation: stores reviewer labels, bounded reason codes, redacted notes, and task binding.
- ReviewWorkflowState: summarizes current review state for a registry entry.
- AnnotatedDatasetVersion: snapshots reviewed datasets with annotation hashes.
- ReviewAnalyticsEngine: computes deterministic quality metrics from registry and review data.
- QualityMetricsReport: summarizes coverage, quality, correctness, grounding, safety, task scope, reason codes, evaluation consistency, and reviewer activity.

## Important Clarifications

BacktestEvaluation is advisory thesis evaluation, not a PnL trading backtest. It does not calculate position size, account risk, live PnL, or win-rate optimization.

PaperTradingEvaluation is paper advisory follow-up evaluation, not paper bot execution. It does not create orders, signals, broker payloads, or MT5 instructions.

HumanReview is annotation and quality review, not execution approval.

ReviewAnalytics is quality governance, not signal ranking.

## Integrity Rules

Evaluation layers must not mutate source records, final answers, EvidenceItems, or compliance outcomes. They preserve request IDs, task IDs, final answer hashes, source refs, agent refs, and `execution_allowed=false`.

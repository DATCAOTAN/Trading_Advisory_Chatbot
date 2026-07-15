# Validated Baselines

This summary consolidates the validated implementation baselines present in the repository. It is a documentation index, not a new runtime layer.

## Completed Baselines

1. Frozen RAG/Evidence Core.
2. Controlled Failure Gate.
3. Generic Agent Runtime.
4. MarketContextAgent.
5. StrategyAgent.
6. RiskAgent.
7. StrategyRiskConsistencyAgent.
8. Agent-to-Answer Compliance Gate.
9. Agent Stack Input and Prompt Compression.
10. Static Source Reference Preservation.
11. JournalReviewAgent.
12. BacktestEvaluation design.
13. PaperTradingEvaluation design.
14. EvaluationRegistry and ReplayHarness.
15. Evaluation Dashboard / Review UI.
16. Evaluation Persistence and Dataset Versioning.
17. Human Review Workflow and Annotation.
18. Review Analytics and Quality Metrics.
19. Golden Evaluation Benchmark.
20. System Hardening and Error Recovery.

## Current Chain

```text
User Query
-> RAG/Evidence Core
-> Agent Runtime
-> Compliance Gate
-> FinalAnswerArtifact
-> JournalReviewRecord
-> BacktestEvaluationRecord
-> PaperTradingEvaluationRecord
-> EvaluationRegistry
-> Persistence
-> HumanReview
-> ReviewAnalytics
-> GoldenBenchmark
-> SystemHardening
```

## Safety Baseline

- No ExecutionAgent.
- No MT5 execution.
- No broker order execution.
- No account data.
- No BUY/SELL command generation.
- No executable entry price, stop-loss, take-profit, lot size, position size, or account-risk percent output.
- `execution_allowed=false`.

## Reused Baseline Notes

Detailed baseline notes remain in `docs/architecture/*_baseline.md` for specific sprints. This file provides the final cross-sprint summary.

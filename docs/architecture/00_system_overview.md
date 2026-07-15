# System Overview

Trading Advisory Chatbot is an evidence-grounded financial advisory and evaluation governance platform. It combines RAG evidence retrieval, task-scoped analytical agents, safety compliance, post-answer evaluation, human review, quality analytics, golden benchmark checks, and defensive hardening.

It is not a simple RAG chatbot because the final answer is only one artifact in a larger governance chain. The system plans context, validates evidence, runs analytical agents only where task scope allows, checks compliance, preserves final answer identity, records evaluation artifacts, supports replay, allows human annotations, computes quality metrics, and validates canonical benchmark scenarios.

The system is not a live trading bot. It may read market data through a host-side MT5 bridge, but it does not perform MT5 order execution, place orders, use account data for advice, or create executable trading instructions. The expected boundary is `execution_allowed=false`.

## Main Pipeline

```text
User Query
-> QueryPlan / ContextRequirements
-> ContextAcquisitionExecutor
-> EvidenceBundle
-> Agent Runtime
-> Compliance Gate
-> FinalAnswerArtifact
-> JournalReviewRecord
-> BacktestEvaluationRecord
-> PaperTradingEvaluationRecord
-> EvaluationRegistry
-> Dashboard / Persistence / HumanReview / Analytics
-> GoldenBenchmark / Hardening
```

## Architectural Layers

- RAG/Evidence Core: builds task-scoped evidence and controls answer eligibility.
- Agent Runtime: adds analytical context from market, strategy, risk, and consistency agents.
- Compliance Gate: checks that final answers remain advisory, grounded, and non-executable.
- Evaluation Governance: records post-answer review artifacts and replayable evaluation records.
- Dashboard and Review: exposes registry, chain, replay, persistence, annotation, analytics, and health views.
- Benchmark and Hardening: validates canonical scenarios and detects corrupt or unsafe artifacts.

## Component Table

| Component | Purpose | Status | Notes |
|---|---|---|---|
| QueryPlan | Decompose user request into tasks | Implemented | Supports multi-intent isolation |
| ContextRequirements | Describe needed evidence per task | Implemented | Keeps static/book and market/macro needs separate |
| ContextAcquisitionExecutor | Acquires context from configured sources | Implemented | Not changed by evaluation layers |
| EvidenceBundle | Grounding authority for answer support | Implemented | Agent outputs do not replace evidence |
| ResponseGate | Controls insufficient-evidence behavior | Implemented | Supports controlled failure |
| ClaimEvidenceValidator | Checks answer claims against evidence | Implemented | Preserves source policy |
| Agent Runtime | Runs task-scoped analytical agents | Implemented | No agent enables execution |
| Compliance Gate | Checks final answer safety | Implemented | Blocks executable output classes |
| FinalAnswerArtifact | Stable answer identity artifact | Implemented | Hashes are preserved by evaluation layers |
| JournalReviewAgent | Reviews final answer quality and traceability | Implemented | Does not change final answer |
| BacktestEvaluation | Evaluates advisory thesis behavior on fixtures | Implemented | Not a PnL backtest |
| PaperTradingEvaluation | Evaluates advisory follow-up behavior | Implemented | Not a paper trading bot |
| EvaluationRegistry | Normalizes evaluation records | Implemented | Local/offline indexing |
| ReplayHarness | Replays deterministic fixtures | Implemented | No provider or retrieval calls |
| EvaluationDashboard | Review UI over registry records | Implemented | Read/review layer |
| EvaluationPersistenceStore | JSONL/manifest persistence | Implemented | Local storage only |
| HumanReview | Manual annotation workflow | Implemented | Not an execution approval system |
| ReviewAnalytics | Quality metrics from annotations | Implemented | Not signal ranking |
| GoldenBenchmark | Canonical regression cases | Implemented | Fixture mode is deterministic |
| SystemHardening | Integrity and recovery diagnostics | Implemented | Non-destructive by default |

## Safety Boundary

The system can provide evidence-grounded analysis, but it cannot perform live execution. It must not output BUY/SELL commands, account-based sizing, broker order payloads, or MT5 order actions. Documentation, code, benchmark fixtures, and hardening diagnostics all preserve `execution_allowed=false`.

# Trading Advisory Chatbot

Evidence-grounded Financial Advisory Platform with Multi-Agent Reasoning, Safety Compliance, Evaluation Governance, and Human Review Analytics.

Trading Advisory Chatbot is a Streamlit-based research and review platform for evidence-grounded financial advisory answers. It combines a RAG/evidence core, task-scoped analytical agents, compliance validation, post-answer evaluation records, human review, quality analytics, golden benchmark checks, and defensive hardening utilities.

This project is not a live trading bot. It can read live market data through a host-side MT5 bridge, but it does not execute trades, perform MT5 order execution, place broker orders, or output executable entry/SL/TP/lot/account-risk instructions. The system boundary is advisory and review-only, and `execution_allowed=false` is the expected invariant.

## What It Does

- Plans user queries into task-scoped context requirements.
- Retrieves and validates evidence before answer synthesis.
- Runs analytical agents for market context, strategy, risk, and consistency when appropriate.
- Preserves EvidenceBundle authority over agent outputs.
- Validates final answers through safety, compliance, source, and completeness gates.
- Records JournalReview, BacktestEvaluation, and PaperTradingEvaluation artifacts.
- Stores and reviews evaluation records through an EvaluationRegistry.
- Supports deterministic replay, local persistence, human annotations, analytics reports, golden benchmarks, and system hardening diagnostics.

## What It Does Not Do

- It does not execute trades.
- It does not perform MT5 order execution.
- It does not place orders.
- It does not store broker credentials or use account data for advice.
- It does not output BUY/SELL commands.
- It does not output entry price, stop-loss, take-profit, lot size, position size, or account-risk percent instructions.
- It does not optimize PnL or win rate.
- It does not claim guaranteed market correctness or regulated advice readiness.
- `execution_allowed=false`.

## Architecture Overview

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

The system is more than a simple RAG chatbot because answer quality is checked across multiple layers: evidence sufficiency, topic coverage, task isolation, analytical agent handoff, compliance, final artifact identity, post-answer evaluation, review workflow, analytics, benchmark fixtures, and recovery diagnostics.

## Main Components

- RAG/Evidence Core: QueryPlan, ContextRequirements, ContextAcquisitionExecutor, EvidenceBundle, EvidenceSelector, EvidenceSufficiency, EvidenceCoverage, TopicEvidenceBinding, AnswerContract, ResponseGate, ClaimEvidenceValidator, AnswerCompleteness.
- Agent Runtime: AgentExecutionPlan, AgentTaskEnvelope, AgentRuntimeRegistry, AgentDispatcher, AgentResultEnvelope, AgentResultValidator, AgentResultAggregator, AgentHandoffContext.
- Analytical Agents: MarketContextAgent, StrategyAgent, RiskAgent, StrategyRiskConsistencyAgent.
- Safety: Agent-to-Answer Compliance Gate, controlled failure behavior, source policy, no-execution boundary.
- Evaluation Governance: JournalReviewAgent, BacktestEvaluation, PaperTradingEvaluation, EvaluationRegistry, ReplayHarness.
- Review and Analytics: Evaluation Dashboard, EvaluationPersistenceStore, HumanReviewAnnotation, ReviewWorkflowState, ReviewAnalyticsEngine.
- Benchmark and Hardening: GoldenBenchmarkRunner, GoldenBenchmarkReport, SystemHardeningService, IntegrityReport, RecoveryPlan, DiagnosticReport.
- Market Data Boundary: MarketDataProvider facade with MT5BridgeMarketDataProvider for host-side MT5 terminal data.

## Quick Start

1. Create a Python virtual environment and install project dependencies using the repository's dependency files.
2. Copy `.env.example` to `.env` and fill only the providers you intend to use.
3. For live market data, start the host-side MT5 bridge if you want real MT5 tick/OHLCV data:

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.server
```

4. Start services:

```powershell
docker-compose up -d
```

4. Open the app:

```text
http://localhost:8501
```

For ordinary Python source changes, prefer:

```powershell
docker-compose restart app
```

Do not rebuild the Docker image unless Dockerfile or dependency files changed.

## Run Tests

Use the project virtual environment explicitly:

```powershell
.\venv\Scripts\python.exe -m pytest scripts -q
.\venv\Scripts\python.exe -m compileall -q src scripts
docker-compose config
```

Focused test commands are listed in [docs/operations/testing_guide.md](docs/operations/testing_guide.md).

## Run Golden Benchmark

```powershell
.\venv\Scripts\python.exe scripts\run_golden_benchmark.py --cases data\evaluations\benchmarks\golden_cases.v1.json --out data\evaluations\benchmarks\reports\latest.json
```

The benchmark uses deterministic fixtures. It does not call providers, retrieval, market APIs, MT5, broker APIs, or account services.

## Open Dashboard

The Streamlit app includes an Evaluation Dashboard tab. It can show registry rows, details, chain view, replay results, persistence status, human review controls, analytics reports, safe exports, and system health diagnostics.

## Data and Evaluation Storage

Evaluation governance data is local and offline by default:

- `data/evaluations/registry/evaluation_registry.jsonl`
- `data/evaluations/versions/dataset_versions.json`
- `data/evaluations/reviews/`
- `data/evaluations/benchmarks/`
- `data/evaluations/quarantine/`
- `data/evaluations/diagnostics/`

These stores are designed for review artifacts, not secrets, account data, broker data, MT5 data, order data, raw prompts, or full raw documents.

## MT5 Market Data Bridge

The default live market data path is `MARKET_DATA_PROVIDER=mt5_bridge`. The Docker app calls a host-side HTTP bridge at `MT5_BRIDGE_URL=http://host.docker.internal:8765`; the bridge runs outside Docker and talks to the locally logged-in MT5 terminal. The bridge has no order endpoint, no credentials endpoint, and no login endpoint. See [docs/operations/mt5_bridge_setup.md](docs/operations/mt5_bridge_setup.md).

## Safety Boundary

The platform can analyze evidence and market context, but it cannot enable execution. Compliance and hardening layers treat trading commands, executable order language, account data, MT5 references, and position-sizing instructions as prohibited output classes. The expected execution invariant is `execution_allowed=false`.

## Limitations

- No ExecutionAgent.
- No MT5 or broker order integration.
- MT5 is used only through a host-side market-data bridge when configured.
- No account data or position sizing.
- No live paper-trading bot.
- No PnL or win-rate optimizer.
- Dashboard persistence is local JSONL/JSON.
- Human reviewer IDs are V1 labels, not authenticated identities.
- Benchmark and replay are deterministic unless externally supplied artifacts are validated.

## Repository Structure

```text
src/
  orchestrator.py
  ui/
  services/
    agents/
    evidence/
scripts/
  test_*.py
  run_golden_benchmark.py
docs/
  architecture/
  operations/
  demo/
  baselines/
data/
  evaluations/
```

## Demo Scenarios

- Static book concept query.
- Macro report summary query.
- Macro market impact query.
- Market state analysis query.
- Multi-intent macro plus book query.
- Safety boundary query.
- Evaluation Dashboard review flow.
- Golden Benchmark and System Health diagnostic flow.

See [docs/demo/demo_script.md](docs/demo/demo_script.md) and [docs/demo/interview_talking_points.md](docs/demo/interview_talking_points.md).

## CV / Interview Summary

Built an evidence-grounded financial advisory platform with RAG, multi-agent analytical reasoning, compliance validation, evaluation governance, human review, quality analytics, deterministic benchmarks, and system hardening. The system is intentionally advisory and review-only; it does not perform live trading or order execution.

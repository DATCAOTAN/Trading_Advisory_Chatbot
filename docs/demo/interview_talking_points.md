# Interview Talking Points

## 30-Second Explanation

I built an evidence-grounded financial advisory platform that combines RAG, task-scoped analytical agents, compliance gates, post-answer evaluation, human review, quality analytics, deterministic benchmarks, error recovery, and a host-side MT5 market-data bridge. It is intentionally advisory and review-only: it does not execute trades, perform MT5 order execution, or produce executable order instructions.

## 2-Minute Architecture Explanation

The system starts with query planning and context requirements, then acquires evidence into an EvidenceBundle. That EvidenceBundle remains the grounding authority. A generic agent runtime can add bounded market, strategy, risk, and consistency analysis for tasks that need it, but agent outputs do not become EvidenceItems.

Before final output is accepted, the answer passes source, compliance, and completeness checks. After that, the answer becomes a FinalAnswerArtifact with stable hashes. Post-answer governance creates JournalReview, BacktestEvaluation, and PaperTradingEvaluation records. These records go into an EvaluationRegistry, can be replayed deterministically, persisted locally, reviewed by humans, analyzed for quality metrics, validated against golden benchmark cases, and checked by system hardening utilities.

## Technical Challenges

- Keeping multi-intent tasks isolated.
- Preserving EvidenceBundle authority while still using analytical agents.
- Preventing unsafe executable trading language.
- Maintaining final answer artifact identity across evaluation layers.
- Designing local persistence without storing prompts, secrets, account data, or order data.
- Building deterministic replay and benchmark fixtures without live provider calls.
- Handling corrupt files and partial chains without dashboard crashes.

## Trade-Offs

- Local JSONL/JSON persistence is simple and reviewable, but not a multi-user database.
- Deterministic benchmarks are stable, but they do not replace broader scenario coverage.
- Human reviewer IDs are lightweight labels in V1, not authenticated accounts.
- Hardening is non-destructive by default, which favors safety over automatic cleanup.

## Safety Boundary

The platform can analyze evidence and market context, but it cannot place trades or create executable instructions. The invariant is `execution_allowed=false`.

## Evaluation Governance

The project treats AI answer quality as a lifecycle: answer artifact, journal review, advisory thesis evaluation, simulated follow-up evaluation, registry indexing, deterministic replay, dashboard review, persistence, human annotation, analytics, benchmark, and hardening.

## Improvements Next

- Expand golden benchmark coverage.
- Add richer demo artifacts.
- Improve authenticated reviewer workflow.
- Add optional dashboard screenshot automation.
- Harden deployment configuration.

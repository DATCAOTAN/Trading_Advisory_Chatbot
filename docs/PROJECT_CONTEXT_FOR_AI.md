# Project Context and Return-to-Work Map

Reviewed: 2026-11-04 against `main@e377ce7` and the remaining local cleanup.

## Goal and Reading Order

Trading Advisory Chatbot joins financial research with authorized MT5 DEMO
operations. Its lifecycle is understand, complete, analyze, propose, review,
authorize, execute, observe/manage, explain, reconcile, and retain history.

Read [AGENTS.md](../AGENTS.md), the
[locked target](architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md), and the
latest [handoff](../TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md) and
[changelog](engineering/SPRINT_CHANGELOG.md) sections. Source/tests/Git determine
what actually exists. Earlier numbered advisory architecture and demo notes
are historical subsystem documentation.

## Current Owners

| Responsibility | Start here |
| --- | --- |
| UI entry and history reload | `src/app.py`, `src/ui/tab_chatbot.py`, `src/services/history_service.py` |
| Common semantic ingress | `src/orchestrator.py`, `src/services/semantic/structured_interpreter.py` |
| Typed schema, completion, resolution | `src/services/semantic/structured_semantics.py`, `src/services/semantic/resolved_semantics.py` |
| Capability plan and evidence acquisition | `src/services/semantic/query_plan.py`, `src/services/semantic/context_acquisition.py`, `src/services/semantic/capability_registry.py` |
| Research retrieval | `src/services/retrieval_adapter.py`, `src/services/vector_service.py`, `src/services/knowledge/` |
| Grounding and analytical agents | `src/services/evidence/`, `src/services/agents/` |
| Tick/bar evidence and deterministic features | `src/services/trading/market/` |
| User request and strategy identity | `src/services/trading/decision/conversational_authorization.py`, `src/services/trading/reasoning/strategy_evidence.py` |
| Immutable proposal calculation | `src/services/trading/proposal/editable_trade_draft.py` |
| Candidate persistence and policy | `src/services/trading/decision/autonomous_orchestrator.py`, `src/services/trading/decision/autonomous_execution_policy.py` |
| Completed-bar coordination | `src/services/trading/decision/autonomous_candidate_monitor.py`, `src/services/trading/decision/autonomous_trading_coordinator.py` |
| Supervisor process ownership | `src/services/trading/decision/autonomous_runtime.py`, `scripts/run_autonomous_candidate_monitor.py` |
| Mode and Standing Mandate authority | `src/services/trading/execution/mt5_live_adapter_pre_submit/trading_authority.py`, `src/services/trading/execution/mt5_live_adapter_pre_submit/authority_runtime.py` |
| Exact human confirmation | `src/services/trading/proposal/confirmation_service.py`, `src/ui/autonomous_candidate_review.py` |
| Final validation, pre-submit, controlled request | `src/services/trading/execution/mt5_live_adapter_pre_submit/approval_pre_submit.py`, `src/services/trading/execution/mt5_live_adapter_pre_submit/controlled.py`, `src/services/trading/execution/mt5_live_adapter_pre_submit/adapter.py` |
| Broker lifecycle and recovery | `src/services/trading/execution/mt5_live_adapter_pre_submit/lifecycle_supervisor.py`, `src/services/trading/execution/mt5_live_adapter_pre_submit/reconciliation.py` |
| Position/P&L/history reads | `src/services/trading/position_read_model.py` |
| Host terminal and isolated broker call | `tools/mt5_bridge/server.py`, `tools/mt5_bridge/execution.py`, `tools/mt5_bridge/management.py`, `tools/mt5_bridge/mt5_client.py` |

For the supported startup and shutdown commands use the
[local runbook](operations/local_runbook.md) and
[bridge guide](operations/mt5_bridge_setup.md).

## Contracts to Preserve

- Arbitrary language is interpreted once at the structured semantic boundary.
  Pydantic v2 validates its output; the UI and domain services do not reparse chat.
- Knowledge responses use retrieved evidence. Account/position/P&L/history reads
  use `PositionReadModel`, never model memory or book passages.
- Entry/SL/TP/risk/volume are deterministic. Draft revisions preserve user-owned
  values and recompute dependent system/policy values from fresh evidence.
- `human_confirmed_live` requires exact per-trade confirmation and separate
  submission authority. `autonomous_live` requires a current bounded Standing
  Mandate; sizing consumes its limits before Candidate persistence.
- Mode authority, broker exposure, risk, lifecycle, and reconciliation are
  account-global. Strategy, mandate ownership, Candidate provenance, and
  Supervisor controls carry conversation scope.
- Supervisor subprocess handles are in memory, keyed by trading scope. A browser
  rerun is not a whole application restart; persisted journals and authority do
  not by themselves prove that a Supervisor process is currently running.
- App and bridge enforce independent permission, account, freshness, integrity,
  idempotency, capability, and kill-switch gates. `RESULT_UNKNOWN` never retries
  automatically. Only the host bridge imports `MetaTrader5`.

## Retained Evidence and Current Limits

The latest local checkpoints are `0bfaa8b` (account-aware lifecycle recovery)
and `e377ce7` (live position provenance), on top of the human-confirmed execution
implementation `88f175f`. Sprint 6 verified a real DEMO trade's open/closed
broker evidence and exact strategy/Draft/Candidate/execution/lifecycle linkage.
Authorization is not yet joined in that read projection; management and
unknown-result recovery were not live-accepted by Sprint 6.

Retained combined-worktree checks: 232 focused tests, full regression 3,798
tests plus 156 subtests, documentation 13 tests. Exact isolated commit checks
were 62 tests for recovery and 243 for Sprint 6/neighbor/baseline documentation.
These are distinct evidence scopes. No current runtime health, profitability,
real-account readiness, or autonomous end-to-end acceptance follows from them.
Check the active process, account, market evidence, mode, mandate and journals
before resuming operations.

The 2026-11-01 housekeeping follow-up removed 20 unused exception-only modules,
one receipt alias, and two root experiments without changing trading behavior.
Its full default pytest collection passed 3,771 tests plus 156 subtests;
documentation integrity now has 13 tests. See handoff section 111 for evidence.

The remaining-cleanup review (handoff section 117) additionally verified the
staged code without a local .env: 3,799 tests and 156 subtests passed. It fixed
one environment-dependent observability test using explicit/fallback fixtures,
not production provider behavior. This establishes a code checkpoint only;
autonomous DEMO runtime readiness still needs a separate read-only preflight.

`RetrievalAdapter` still supports both legacy `VectorService` and feature-gated
Knowledge V3. The compatibility execution packages and old check scripts have
real references; do not remove them based only on age or naming.

## What Is Safe to Clean

- Regenerable Python bytecode and pytest cache can be removed while no test run
  is using them. Leave the virtual environment installed.
- Root patch dumps and empty terminal captures are not source or release evidence.
- Preserve knowledge books/manifests, compiled policy cards, SQLite databases,
  Qdrant, MongoDB volumes, protected requests/journals, credentials, backups,
  local logs, and `.agents/` until their retention is explicitly reviewed.
- Git-ignore does not exclude files from Docker images. Keep host secrets,
  backups, agent settings, and protected runtime stores out of the build context.

See [storage and cleanup](operations/data_storage_and_cleanup.md) for the
directory classification. Keep new work bounded and run focused verification;
do not start a new architecture or execution sprint merely to tidy files.

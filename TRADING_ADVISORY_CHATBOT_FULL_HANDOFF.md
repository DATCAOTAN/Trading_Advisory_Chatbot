# TRADING_ADVISORY_CHATBOT — FULL CODEBASE, RUNTIME, ROADMAP, AND AGENT HANDOFF

**Handoff version:** 4.0
**Prepared from:** the uploaded `Trading_Advisory_Chatbot.zip`, the current Codex handoff snapshot, and the reported runtime/test results.
**Snapshot period:** 2026-07-20 to 2026-07-21
**Primary workspace:** repository root

---

## 0. HOW TO USE THIS HANDOFF

This document is intended to be pasted into:

- ChatGPT or another LLM chatbot;
- Codex CLI;
- Claude Code;
- Antigravity or another coding agent;
- a human architecture/code reviewer.

Its purpose is to let the reviewer understand:

- what the project is;
- what is actually implemented;
- what is still blocked;
- how the codebase is organized;
- which modules own which responsibilities;
- what the current runtime path is;
- what the immediate milestone is;
- what the long-term autonomous goal is;
- which areas are overengineered or duplicated;
- how to recommend changes without breaking current boundaries.

This is **not** a byte-for-byte source dump. Before changing code, an agent must inspect the repository and verify every referenced file, symbol, configuration value, and current test result.

### Fact labels used in this handoff

- **VERIFIED IN UPLOADED ZIP**: observed directly in the uploaded source snapshot.
- **REPORTED BY CURRENT WORKSPACE HANDOFF**: stated in the Codex-generated handoff or sprint result.
- **PLANNED**: future architecture, not currently implemented.
- **RECOMMENDED REVIEW TARGET**: likely improvement, not yet an accepted implementation task.

Do not silently convert a planned item into an implemented fact.

---

# 1. PROJECT IDENTITY

## Project name

`Trading_Advisory_Chatbot`

## Original project purpose

The project began as an advisory chatbot for financial-market analysis, combining:

- RAG and evidence-aware answer generation;
- knowledge ingestion and vector retrieval;
- query planning and context acquisition;
- live market-data access;
- market-context, strategy, risk, and consistency agents;
- structured decision artifacts;
- human review;
- simulated and dry-run execution artifacts.

## Current project direction

The project is now being extended into a controlled MetaTrader 5 execution architecture.

The immediate development focus is no longer broad RAG tuning, UI polish, or adding more review dashboards. The immediate focus is completing and validating the execution path.

---

# 2. CURRENT MILESTONE AND LONG-TERM GOAL

## 2.1 Current completed milestone

The latest completed sprint is:

`MT5 Live Adapter Disabled + Pre-Submit Gate`

Current validated state reported by the workspace:

```text
adapter_status=BLOCKED_BY_DISABLED_ADAPTER
pre_submit_status=PASSED_DISABLED_PRE_SUBMIT_CHECK
validation_valid=true
controlled_demo_integration_workflow_allowed=true
live_submission_allowed=false
bridge_write_skeleton_reachable=true
bridge_write_skeleton_status=BLOCKED
kill_switch_engaged=true
idempotency_status=CHECK_REGISTERED
live_execution_allowed=false
order_send_allowed=false
execution_allowed=false
executable=false
order_sent=false
ticket=None
deal=None
hard_live_block_required=true
```

Meaning:

- the app-side live adapter shape exists;
- it is intentionally disabled;
- the bridge write-skeleton endpoint is reachable;
- the bridge returns `BLOCKED`;
- the kill switch exists and is engaged;
- check-only idempotency exists;
- the pre-submit safety gate passes as a disabled safety check;
- no real order request is submitted;
- no `order_send` function call exists in the current verified path.

## 2.2 Immediate goal

Finish a minimal, controlled, one-shot MT5 execution path on a demo/local terminal.

The immediate target is:

```text
validated request artifact
→ pre-submit validation
→ explicit controlled-demo permission
→ narrow host bridge write endpoint
→ one MT5 submission attempt
→ immediate result journal
→ no automatic retry
→ follow-up reconciliation
```

The first write path must be demo-first, explicitly enabled, independently checked by the host bridge, journaled, and non-autonomous.

## 2.3 Long-term end-state

The long-term product goal is an **autonomous MT5 decision and execution system** that can:

1. accept a user prompt or persistent operating intent;
2. obtain current market data from the connected MT5 terminal;
3. retrieve and validate relevant knowledge;
4. build market, regime, calendar, strategy, and risk context;
5. produce structured machine-readable decisions;
6. apply deterministic policy checks independent of the LLM;
7. submit an order only when the selected account mode and all runtime controls allow it;
8. monitor and manage the complete position lifecycle;
9. reconcile internal journals against MT5 state;
10. detect duplicates, timeouts, partial state, stale data, bridge failure, and unexpected broker state;
11. stop safely when conditions are unknown;
12. review outcomes and improve validated components.

A user prompt must express **intent**, not direct submission authority. The prompt must never bypass:

- structured decision validation;
- risk and execution policy;
- kill switch;
- idempotency;
- account-mode policy;
- bridge-side validation;
- reconciliation requirements.

The system may be designed to improve robust expected performance, but it cannot guarantee maximum profit or guaranteed profitability.

## 2.4 Demo and live accounts

Both demo and live accounts use a real MT5 terminal connection. Their operational consequences differ.

The architecture should eventually support both through an explicit account-environment policy:

- demo is the default development and soak-testing environment;
- live account enablement is a later explicit promotion;
- no automatic promotion from demo to live;
- no prompt may switch account class;
- raw credentials and raw account identifiers remain outside the app;
- the host terminal remains responsible for login;
- account mode must be independently detected or configured and safely redacted.

---

# 3. CURRENT AND FUTURE SCOPE

## Current scope

- advisory and RAG system;
- live MT5 market data;
- structured context, scoring, and readiness;
- human-reviewed execution-preparation artifacts;
- dry-run request boundaries;
- final validation;
- blocked bridge write skeleton;
- disabled live adapter;
- kill switch check;
- check-only idempotency;
- pre-submit safety gate;
- append-only journals.

## Not currently implemented

- a broker-submittable MT5 request dictionary;
- real MT5 execution constants in an active submit path;
- `order_send`;
- actual ticket/deal creation;
- order/position reconciliation after submission;
- automatic retry;
- complete position lifecycle management;
- continuous runtime supervisor;
- autonomous execution policy;
- autonomous position management;
- live-account production promotion.

## Areas that should not be expanded now unless they block execution work

- parser/MinerU improvements;
- embeddings and Qdrant tuning;
- RAG content expansion;
- evidence dashboard expansion;
- agent evaluation dashboards;
- UI theme/polish;
- broad strategy optimization;
- broad refactoring of all old execution boundaries.

---

# 4. RUNTIME ARCHITECTURE

## 4.1 Current runtime split

```text
Docker app / Streamlit / Python services
        |
        | HTTP
        v
host.docker.internal:8765
        |
        v
Host-side MT5 Bridge
        |
        | MetaTrader5 Python package
        v
Local MetaTrader 5 terminal
```

## 4.2 Verified bridge address

**VERIFIED IN UPLOADED ZIP:**

```text
MT5_BRIDGE_URL=http://host.docker.internal:8765
```

Native host-side alternative:

```text
MT5_BRIDGE_URL=http://127.0.0.1:8765
```

The current bridge server defaults to port `8765`.

## 4.3 Runtime boundaries

- Code under `src/` must not import `MetaTrader5`.
- Only `tools/mt5_bridge/` may import and call the MetaTrader5 package.
- The Docker app communicates with MT5 only through HTTP.
- The local terminal is already logged in by the user.
- The app must not manage MT5 login/password credentials.
- Raw account ids must not be logged or journaled.
- The bridge returns redacted or hashed identifiers.
- The bridge must independently validate any future write request.
- App-side validation alone is never sufficient.

## 4.4 Docker composition

**VERIFIED IN UPLOADED ZIP:**

`docker-compose.yml` defines:

- `app`
- `redis`
- `mongo`

The app mounts:

```text
./data:/app/data
./src:/app/src
./scripts:/app/scripts
./.env:/app/.env
```

The app uses `host.docker.internal` to reach host services.

Important snapshot discrepancy:

- `docker-compose.yml` references a build context;
- the uploaded zip did not contain a `Dockerfile`;
- the actual workspace may contain it, but an agent must verify before assuming it exists.

For Python/source/UI changes, the established workflow is:

```powershell
docker-compose restart app
```

Do not rebuild unless dependency files or the Docker image definition changed.

---

# 5. ACTUAL TOP-LEVEL SOURCE STRUCTURE

## 5.1 Verified main source tree

```text
src/
├── app.py
├── config.py
├── orchestrator.py
├── core/
│   ├── database.py
│   ├── llm_client.py
│   └── models.py
├── metadata/
│   ├── assets.yaml
│   ├── authors.yaml
│   ├── domains.yaml
│   ├── knowledge_types.yaml
│   ├── languages.yaml
│   └── strategies.yaml
├── pipelines/
│   ├── context_packer.py
│   ├── intent_router.py
│   └── modules/
│       ├── context_acquisition.py
│       ├── evaluator.py
│       ├── query_rewriter.py
│       ├── refinement_builder.py
│       ├── reranker.py
│       └── router.py
├── services/
│   ├── agents/
│   ├── evidence/
│   ├── knowledge/
│   ├── semantic/
│   ├── trading/
│   ├── decision_context.py
│   ├── history_service.py
│   ├── ingestion_tracker.py
│   ├── live_data_service.py
│   ├── llm_service.py
│   ├── orchestrator_contract.py
│   ├── parser_service.py
│   ├── response_gate.py
│   ├── retrieval_adapter.py
│   └── vector_service.py
└── ui/
    ├── runtime_flags.py
    ├── tab_chatbot.py
    ├── tab_dashboard.py
    ├── tab_evaluation_dashboard.py
    └── tab_settings.py
```

Important correction to the previous Codex handoff:

- the application entry file in the uploaded snapshot is `src/app.py`;
- there is no verified root-level `app.py` in the uploaded zip.

## 5.2 Host bridge tree

**VERIFIED IN UPLOADED ZIP:**

```text
tools/mt5_bridge/
├── README.md
├── __init__.py
├── models.py
├── mt5_client.py
├── redaction.py
└── server.py
```

The previous Codex handoff mentioned:

```text
tools/mt5_bridge/config.py
tools/mt5_bridge/requirements.txt
```

Those two files were not present in the uploaded zip. Verify the current workspace before relying on them.

## 5.3 Other root paths

**VERIFIED IN UPLOADED ZIP:**

```text
.env.example
.gitignore
docker-compose.yml
requirements.txt
scripts/
src/
tools/
```

The Codex handoff also mentioned `data/`, `tests/`, and `docs/`. These may exist in the full workspace or be generated/runtime paths, but they were not present as top-level directories in the uploaded source zip. Verify rather than assume.

---

# 6. HIGH-LEVEL CLEAN ARCHITECTURE

The project has two primary logical cores.

## 6.1 Intelligence Core

Purpose:

- understand the query;
- retrieve and validate knowledge;
- acquire current context;
- reason about market state;
- score and classify readiness;
- create advisory and non-executable decision artifacts.

It must not directly submit orders.

Main logical areas:

- RAG and retrieval;
- semantic context planning;
- market data and features;
- regime and calendar context;
- method selection;
- scoring;
- readiness decision;
- human review;
- non-executable proposal artifacts.

## 6.2 Trading Execution Core

Root:

```text
src/services/trading/execution/
```

Purpose:

- consume structured artifacts;
- create execution-preparation boundaries;
- validate request shape and provenance;
- enforce safety state;
- call the bridge through a narrow client;
- journal checks and future results;
- later submit controlled demo requests;
- later reconcile MT5 state.

The execution core must not depend on free-form chatbot text as an executable contract.

---

# 7. DEPENDENCY DIRECTION

## Allowed direction

```text
UI / dashboard
    → application services
    → builders / gates / validators / stores
    → app-side bridge client
    → HTTP host bridge
    → MetaTrader5 package
    → local MT5 terminal
```

```text
Intelligence Core
    → structured market/context/decision artifacts
    → Trading Execution Core
```

## Forbidden direction

```text
RAG / agents / orchestrator
    ✗ directly calling order_send

src/services/live_data_service.py
    ✗ becoming an execution submit service

src/
    ✗ importing MetaTrader5

Streamlit dashboard
    ✗ implementing direct order-submission business logic

LLM free-form output
    ✗ becoming a broker request without deterministic validation

Host bridge
    ✗ trusting the app without independent validation

User prompt
    ✗ bypassing policy, kill switch, idempotency, and account controls
```

---

# 8. IMPORTANT ENTRY POINTS AND RESPONSIBILITIES

## `src/app.py`

Role:

- Streamlit application shell;
- initialize UI and orchestrator;
- tab/navigation setup;
- presentation-level behavior.

It should not own execution decisions or MT5 request-building logic.

## `src/orchestrator.py`

Role:

- main advisory/RAG orchestration;
- coordinate retrieval, query decomposition, LLM service, context acquisition, evidence, and agent runtime.

This is part of the Intelligence Core.

It must not become the live execution controller.

## `src/config.py`

Role:

- central environment parsing;
- feature flags;
- LLM/parser/embedding configuration;
- market-data configuration;
- trading/execution flags;
- journal paths and TTLs.

Known issue:

- it is large;
- repeated execution-stage configuration increases maintenance risk;
- some definitions may be duplicated;
- split only after the first execution/reconciliation path is proven, unless a duplicate currently causes incorrect runtime behavior.

## `src/services/live_data_service.py`

Role:

- compatibility/legacy facade for live data;
- route older callers through the newer provider architecture.

Rule:

- do not add new order-submission logic here.

## `src/ui/tab_dashboard.py`

Role:

- display system state;
- invoke safe service methods;
- render summaries and manual checks.

Known issue:

- large file;
- likely too coupled to execution-stage details;
- split into smaller renderers later.

## `tools/mt5_bridge/mt5_client.py`

Role:

- host-side MT5 read client;
- the verified location allowed to import `MetaTrader5`;
- health/account/symbol/tick/OHLCV/position reads;
- redact identifiers.

## `tools/mt5_bridge/server.py`

Role:

- host-side HTTP bridge;
- current read endpoints;
- current blocked write-skeleton endpoint;
- future controlled-demo endpoint must be implemented here, not inside `src/`.

---

# 9. INTELLIGENCE CORE PACKAGE MAP

## `src/services/agents/`

Observed responsibilities include:

- market-context agent;
- strategy agent;
- risk agent;
- consistency agent;
- answer compliance;
- backtest and paper-trading evaluation;
- human review;
- journal review;
- projection;
- evaluation persistence/registry/dashboard;
- system hardening.

Current priority:

Do not expand this package unless it blocks the execution path.

## `src/services/evidence/`

Observed responsibilities include:

- answer coverage;
- answer depth;
- evidence coverage;
- cross-layer alignment;
- topic-evidence binding;
- evidence pipeline.

Current priority:

Keep stable while execution is being completed.

## `src/services/knowledge/`

Observed responsibilities include:

- document parsing;
- chunking;
- metadata and manifests;
- ingestion fingerprints;
- embedding reliability;
- vector service;
- query decomposition/intent;
- retrieval smoke tests;
- update service;
- grounding and answer mode.

Current priority:

Do not perform broad parser/embedding/vector work unless a current execution dependency requires it.

## `src/services/semantic/`

Responsibilities:

- query plan;
- capability registry;
- context requirements;
- context acquisition;
- context execution;
- context sufficiency.

## `src/pipelines/`

Responsibilities:

- intent routing;
- context packing;
- query rewriting;
- acquisition;
- evaluation;
- refinement;
- reranking;
- routing.

---

# 10. TRADING INTELLIGENCE PACKAGE MAP

## `src/services/trading/market/`

Verified files include:

```text
data_quality.py
feature_engine.py
feature_models.py
indicators.py
live_feature_service.py
market_snapshot_bundle.py
models.py
mt5_bridge_provider.py
provider.py
provider_registry.py
regime_detector.py
regime_models.py
regime_service.py
timeframes.py
```

Responsibilities:

- market-data provider abstraction;
- MT5 bridge provider;
- tick/OHLCV acquisition;
- data quality;
- feature and indicator generation;
- regime detection;
- structured market snapshots.

Must remain read-oriented.

## `src/services/trading/calendar/`

Responsibilities:

- calendar provider abstraction;
- Forex Factory provider;
- event relevance;
- calendar context;
- formatting.

## `src/services/trading/knowledge/`

Responsibilities:

- trading knowledge cards/models;
- runtime context pack;
- routing and validation;
- stores.

## `src/services/trading/reasoning/`

Responsibilities:

- method selection;
- optional LLM reasoning adapter;
- prompt building;
- output parsing;
- validation;
- deterministic fallback.

Rule:

The LLM may propose or explain. It must not directly authorize submission.

## `src/services/trading/scoring/`

Responsibilities:

- component scores;
- normalization;
- scoring policies;
- score engine;
- validation.

## `src/services/trading/decision/`

Responsibilities:

- readiness models;
- decision policy;
- policy engine;
- validation.

Expected result classes may represent concepts such as:

- wait;
- no trade;
- blocked;
- review-ready;
- manage-existing-position.

## `src/services/trading/review/`

Responsibilities:

- human review artifact;
- review formatting;
- validation.

## `src/services/trading/proposal/`

Responsibilities:

- human-confirmed proposal boundary;
- proposal intents;
- non-executable proposal drafts;
- proposal confirmation;
- formatters;
- validators;
- append-only stores/journals.

---

# 11. TRADING EXECUTION CORE PACKAGE MAP

Root:

```text
src/services/trading/execution/
```

## Root-level execution components

Verified root files include concepts for:

- adapter interface and registry;
- dry-run adapter/service;
- idempotency;
- kill switch;
- execution gate;
- receipt;
- execution journal;
- simulated adapter and contract;
- MT5 hard-block skeleton;
- policies and validators.

## Verified execution subpackages

```text
live_design/
live_order_contract/
live_order_contract_final_review/
live_order_contract_parameterization/
live_order_intent/
live_order_parameter_policy/
live_order_parameter_source/
live_parameter_draft/
live_parameter_value_proposal/
live_value_approval_lock/
mt5_bridge_write_skeleton/
mt5_dry_run_payload_validator/
mt5_live_adapter_pre_submit/
mt5_request_dict_dry_run_builder/
mt5_request_dict_final_validation/
mt5_request_draft/
mt5_request_draft_final_approval/
permission/
pre_mt5_order_mapping/
preflight/
```

---

# 12. COMMON EXECUTION PACKAGE PATTERN

Many execution packages follow:

```text
package/
├── __init__.py
├── models.py
├── policy.py
├── builder.py
├── gate.py
├── validator.py
├── formatter.py
├── store.py
├── service.py
└── errors.py
```

Some packages add specialized files such as:

- `confirmation.py`
- `client.py`
- `checks.py`
- `runner.py`
- `evidence.py`
- `adapter.py`
- `kill_switch.py`
- `idempotency.py`

## Intended responsibilities

### `models.py`

- enums;
- dataclasses;
- immutable or structured artifacts;
- serialization helpers;
- no network or MT5 calls.

### `policy.py`

- policy dataclass;
- safe defaults;
- flags;
- TTL;
- limits;
- journal path.

### `builder.py`

- deterministic conversion from upstream artifact to current boundary;
- no broker mutation;
- no hidden network side effects.

### `gate.py`

- pass/block decision;
- explicit block reasons;
- workflow permission flags;
- dangerous flags remain false unless the relevant milestone explicitly changes them.

### `validator.py`

- shape validation;
- safety invariant validation;
- source/provenance checks;
- marker checks;
- size checks.

### `formatter.py`

- safe UI/CLI summary;
- no credentials;
- no raw account id;
- no unsafe payload exposure.

### `store.py`

- append-only JSONL;
- create parent directory;
- read latest;
- summarize;
- tolerate bad lines where implemented;
- redact sensitive values.

### `service.py`

- orchestration facade;
- connect builder/gate/validator/store/client;
- keep business rules out of the UI.

## Clean-code concern

The pattern is consistent but likely over-applied. Many packages may be mechanically separated without enough independent responsibility.

Do not broadly consolidate before controlled demo execution and reconciliation work. After runtime behavior is proven, inspect duplication in:

- JSONL stores;
- safety flag fields;
- forbidden-marker scans;
- payload-size checks;
- source-reference checks;
- idempotency propagation;
- formatter summaries;
- repeated `as_dict` structures;
- repeated service orchestration;
- large `__init__.py` exports.

---

# 13. SYSTEM MODES

The system should be understood through explicit operating modes.

## 13.1 `advisory_only`

Purpose:

- answer questions;
- use RAG and current market context;
- explain methods, macro state, and risk;
- produce non-executable advisory output.

Allowed:

- retrieval;
- context;
- reasoning;
- scoring;
- review artifacts.

Forbidden:

- executable request;
- MT5 submission;
- position mutation.

## 13.2 `human_confirmed_live`

Purpose:

- transition from advisory to controlled execution preparation;
- require human confirmation;
- create intent, contract, parameter, mapping, request, and pre-submit artifacts.

Current status:

- this is the principal implemented execution-preparation path;
- submission remains disabled.

## 13.3 `autonomous_live`

Purpose:

- future continuous decision and execution mode;
- consume current market/context state;
- create structured decisions;
- pass independent deterministic execution policy;
- submit and manage positions without step-by-step manual approval.

Current status:

- not implemented as a safe end-to-end runtime;
- must remain blocked until demo execution, reconciliation, lifecycle management, supervision, and soak testing work.

Naming concern:

A current live-check script reportedly uses the string `autonomous_live` while actual autonomous execution is disabled. Verify whether this is only a knowledge-routing label. Rename or document it to avoid a false impression of enabled autonomous execution.

## 13.4 `manage_existing_position`

Purpose:

- manage the lifecycle of an already open position;
- monitor broker state;
- detect thesis/regime/risk changes;
- propose or later execute management actions.

Current status:

- future;
- no verified mutation path.

Dependency:

- requires reliable position reads and reconciliation first.

## 13.5 `learning_review`

Purpose:

- review decisions, execution journals, and outcomes;
- compare expected vs observed behavior;
- update performance memory or recommendations.

Rule:

- no hidden automatic mutation of execution policy;
- changes must be versioned, tested, and reviewed.

---

# 14. CURRENT IMPLEMENTED EXECUTION PIPELINE

```text
Real MT5 Market Data
→ Feature / Regime / Calendar
→ Knowledge / Method / Score
→ Trade Readiness
→ Human Review Artifact
→ Dry-Run Gate
→ Execution Journal
→ Proposal Boundary
→ Non-Executable Proposal Draft
→ Simulated Adapter Contract
→ MT5 Hard-Block Skeleton
→ Live Execution Design Spec
→ Preflight Harness
→ Human-Confirmed Live Permission Gate
→ Live Order Intent
→ Live Order Contract Skeleton
→ Live Order Parameter Policy Validator
→ Live Order Parameter Source Boundary
→ Human-Reviewed Live Parameter Draft
→ Controlled Live Parameter Value Proposal
→ Human Value Approval and Lock Boundary
→ Live Order Contract Parameterization Boundary
→ Contract Parameter Validation and Final Human Review
→ Pre-MT5 Order Request Mapping Boundary
→ MT5 Order Request Dry-Run Payload Validator
→ MT5 Request Draft Boundary
→ MT5 Request Draft Final Approval Boundary
→ MT5 Request Dict Dry-Run Builder Boundary
→ MT5 Request Dict Final Validation
→ MT5 Bridge Write Endpoint Skeleton
→ MT5 Live Adapter Disabled + Pre-Submit Gate
```

No real submission stage is present after this point in the current verified snapshot.

---

# 15. IMPLEMENTATION MILESTONE HISTORY

The project has progressed through the following engineering milestones:

1. Real MT5 Bridge Market Data Migration
2. Live OHLCV Feature Engine and Market Snapshot
3. Market Regime, Calendar, and LiveData Compatibility
4. Knowledge Router and Runtime Context Pack
5. Method Selector and LLM Reasoning Adapter
6. Signal Scoring Engine
7. Trade Decision Policy Engine
8. Human Review Artifact
9. Execution Gate Foundation and Dry-Run Receipt
10. Execution Journal and Dry-Run Confirmation UI
11. Human-Confirmed Proposal Boundary
12. Non-Executable Trade Proposal Draft
13. Execution Adapter Interface and Simulated Order Contract
14. MT5 Execution Adapter Skeleton with Hard Live Block
15. Live Execution Design Spec and Threat Model
16. Live Execution Preflight Readiness Harness
17. Human-Confirmed Live Permission Gate
18. Live Order Intent Builder
19. Live Order Contract Skeleton
20. Live Order Parameter Policy Validator
21. Live Order Parameter Source Boundary
22. Human-Reviewed Live Parameter Draft
23. Controlled Live Parameter Value Proposal
24. Human Value Approval and Lock Boundary
25. Live Order Contract Parameterization Boundary
26. Contract Parameter Validation and Final Human Review
27. Pre-MT5 Order Request Mapping Boundary
28. MT5 Order Request Dry-Run Payload Validator
29. MT5 Request Draft Boundary
30. MT5 Request Draft Final Approval Boundary
31. MT5 Request Dict Dry-Run Builder Boundary
32. MT5 Request Dict Final Validation and Bridge Write Endpoint Skeleton
33. MT5 Live Adapter Disabled and Pre-Submit Gate

Current milestone:

```text
33 complete
```

---

# 16. IMPORTANT LATE-STAGE EXECUTION PACKAGES

## 16.1 `mt5_request_dict_final_validation/`

Purpose:

- consume dry-run request-dict boundary;
- verify all fields are schema-only;
- reject concrete values, real payloads, MT5 constants, broker submission markers, executable state, and order submission;
- permit bridge skeleton checking only.

Reported status:

```text
FINAL_VALIDATION_PASSED
bridge_write_skeleton_check_allowed=true
all execution flags=false
```

## 16.2 `mt5_bridge_write_skeleton/`

Purpose:

- app-side client for:

```text
POST /execution/write-skeleton/check
```

Validation expectations:

- reachable;
- status `BLOCKED`;
- write skeleton available;
- live execution false;
- order send false;
- order sent false;
- ticket/deal null;
- metadata redacted.

## 16.3 `mt5_live_adapter_pre_submit/`

Verified files:

```text
adapter.py
errors.py
formatter.py
gate.py
idempotency.py
kill_switch.py
models.py
policy.py
service.py
store.py
validator.py
```

Core responsibilities:

- disabled app-side adapter;
- bridge-skeleton health/check;
- kill-switch evaluation;
- check-only idempotency;
- pre-submit gate;
- journal;
- safe summary.

Reported core classes include:

```text
MT5KillSwitchCheck
MT5IdempotencyCheck
MT5LiveAdapterDisabledReceipt
MT5PreSubmitGateReport
MT5PreSubmitJournalRecord
MT5PreSubmitSummary
MT5LiveAdapterPreSubmitConfig
MT5LiveAdapterDisabled
MT5KillSwitchService
MT5PreSubmitIdempotencyGuard
MT5PreSubmitGate
MT5LiveAdapterPreSubmitValidator
MT5LiveAdapterPreSubmitFormatter
MT5PreSubmitJournalStore
MT5LiveAdapterPreSubmitService
```

Current behavior:

- adapter disabled;
- kill switch engaged;
- idempotency is check-only;
- bridge must be reachable and blocked;
- controlled-demo integration workflow may be marked ready;
- live submission remains false.

---

# 17. CURRENT MT5 BRIDGE

## 17.1 Verified read endpoints

The bridge README lists:

```text
GET /health
GET /account
GET /symbols
GET /tick?symbol=...
GET /ohlcv?symbol=...&timeframe=...&count=...
GET /positions?symbol=...
```

## 17.2 Current write-skeleton endpoint

```text
POST /execution/write-skeleton/check
```

Expected result:

```json
{
  "status": "BLOCKED",
  "endpoint": "/execution/write-skeleton/check",
  "write_skeleton_available": true,
  "live_execution_allowed": false,
  "order_send_allowed": false,
  "execution_allowed": false,
  "hard_live_block_required": true,
  "reason": "MT5 bridge write endpoint skeleton is disabled by design",
  "order_sent": false,
  "ticket": null,
  "deal": null,
  "metadata_redacted": true
}
```

## 17.3 Current bridge restrictions

No verified active endpoint for:

```text
/order
/execute
/send_order
/order_send
/trade
/position/open
```

No verified real `order_send` call.

---

# 18. CONFIGURATION AND ENVIRONMENT

## 18.1 Verified MT5 market-data configuration

```text
MARKET_DATA_PROVIDER=mt5_bridge
MT5_BRIDGE_URL=http://host.docker.internal:8765
MT5_SYMBOL_MAP_XAUUSD=XAUUSD
OANDA_LEGACY_ENABLED=false
```

The previous handoff contained `http://host.docker.internal:8001`. That is inconsistent with the uploaded zip and should be corrected to `8765` unless the current workspace has intentionally changed.

## 18.2 Current bridge write controls

Reported configuration includes:

```text
MT5_BRIDGE_WRITE_SKELETON_ENABLED=true
MT5_BRIDGE_WRITE_SKELETON_HARD_BLOCK=true
MT5_BRIDGE_ORDER_SEND_ENABLED=false
MT5_BRIDGE_LIVE_EXECUTION_ENABLED=false
```

## 18.3 Pre-submit controls

Verified/reported configuration:

```text
TRADING_MT5_LIVE_ADAPTER_PRE_SUBMIT_ENABLED=true
TRADING_MT5_LIVE_ADAPTER_ENABLED=false
TRADING_MT5_LIVE_ADAPTER_HARD_BLOCK=true
TRADING_MT5_PRE_SUBMIT_GATE_ENABLED=true
TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION=false
TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND=false
TRADING_MT5_PRE_SUBMIT_REQUIRE_FINAL_VALIDATION=true
TRADING_MT5_PRE_SUBMIT_REQUIRE_BRIDGE_SKELETON_CHECK=true
TRADING_MT5_PRE_SUBMIT_REQUIRE_IDEMPOTENCY=true
TRADING_MT5_PRE_SUBMIT_REQUIRE_KILL_SWITCH=true
TRADING_MT5_KILL_SWITCH_ENGAGED=true
TRADING_MT5_IDEMPOTENCY_CHECK_TTL_SECONDS=300
TRADING_MT5_PRE_SUBMIT_JOURNAL_ENABLED=true
TRADING_MT5_PRE_SUBMIT_JOURNAL_PATH=data/trading/execution_journal/mt5_pre_submit_checks.jsonl
TRADING_MT5_PRE_SUBMIT_MAX_READ_RECORDS=100
```

Meaning:

- the pre-submit checker is enabled;
- the live adapter is disabled;
- the hard block is active;
- live submission is disabled;
- order send is disabled;
- kill switch is engaged;
- idempotency is check-only.

---

# 19. JOURNALING

Runtime journal root:

```text
data/trading/execution_journal/
```

Expected journal categories include:

- execution dry-run;
- proposal intent;
- proposal draft;
- permission;
- order intent;
- contract;
- parameter policies and sources;
- parameter drafts and proposals;
- approval locks;
- contract parameterization;
- final review;
- pre-MT5 mapping;
- payload validation;
- request draft;
- request-draft approval;
- request-dict dry-run builder;
- final validation;
- pre-submit checks;
- pre-submit idempotency.

## Journal rules

- append-only JSONL;
- create parent directory when needed;
- tolerate corrupt lines where implemented;
- never store credentials;
- never store raw account id;
- never store raw complete market candles;
- never store full book/report text;
- never store a real broker-submittable payload before that capability exists;
- hash idempotency keys;
- store ticket/deal only after an actual MT5 response;
- distinguish blocked, rejected, failed, submitted, unknown, and reconciled states;
- do not automatically retry an unknown submission result.

The gitignore rule should include:

```text
data/trading/execution_journal/*.jsonl
```

---

# 20. DASHBOARD AND UI

Main execution dashboard:

```text
src/ui/tab_dashboard.py
```

Current safe actions include concepts such as:

- validate request-dict boundary;
- check bridge write skeleton;
- run pre-submit safety check.

Current UI must communicate:

- request artifacts are dry-run/non-submittable;
- bridge skeleton is reachable but blocked;
- live adapter is disabled;
- pre-submit check does not submit;
- kill switch is engaged;
- order send remains disabled.

Until controlled-demo execution is explicitly implemented, there should be no user control implying unrestricted submission, such as:

```text
Execute Trade
Place Order
Buy
Sell
```

Known clean-code concern:

- dashboard is large;
- likely contains repeated stage-rendering code;
- split later into smaller section renderers after runtime path is working.

---

# 21. TESTING AND COMMAND CONVENTIONS

## Required Windows venv style

Always use:

```powershell
.\venv\Scripts\python.exe -m pytest ...
```

Never use bare:

```text
pytest
```

## Focused sprint workflow

For an ordinary focused sprint:

1. run the new focused test;
2. run adjacent upstream tests;
3. run compileall;
4. run exact static safety scans;
5. run `docker-compose config`;
6. restart the app;
7. run the relevant live check.

Commands:

```powershell
.\venv\Scripts\python.exe -m compileall -q src scripts tools
docker-compose config
docker-compose restart app
```

## Full regression policy

Do not run the entire scripts regression after every narrow sprint.

Run it for:

- major milestones;
- before introducing the first real `order_send`;
- shared-core changes;
- release/merge;
- after execution/reconciliation changes with broad impact.

---

# 22. REPORTED LATEST TEST STATE

Latest pre-submit sprint:

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_mt5_live_adapter_disabled_pre_submit_gate.py -q
```

Reported result:

```text
12 passed
```

Adjacent tests:

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_mt5_request_dict_final_validation_and_bridge_skeleton.py -q
```

Reported result:

```text
24 passed
```

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_mt5_request_dict_dry_run_builder.py -q
```

Reported result:

```text
75 passed
```

Other reported checks:

```text
compileall: passed
docker-compose config: passed
docker-compose restart app: passed
app health: healthy
Streamlit health: ok
latest pre-submit live check: passed
```

Full scripts regression was not rerun after the pre-submit sprint.

Older reported full regression:

```text
2461 passed
156 subtests passed
3 warnings
```

Do not present the latest focused PASS as a latest full-regression PASS.

---

# 23. STATIC SAFETY INVARIANTS

Until the first controlled-demo execution sprint explicitly changes them:

- no real `order_send` call;
- no `MetaTrader5` import under `src/`;
- no real MT5 payload;
- no broker-submittable request dictionary;
- no real execution constants in an active submit path;
- no broker submission object;
- no executable order;
- no ticket/deal id;
- no live order submission;
- no autonomous execution;
- no broad uncontrolled bridge endpoint;
- no raw account id;
- no credentials;
- runtime JSONL ignored by git;
- bridge write skeleton returns `BLOCKED`;
- disabled adapter returns blocked receipt;
- kill switch engaged;
- idempotency check-only;
- all execution flags false.

Allowed harmless field/config names:

```text
order_send_allowed
ORDER_SEND_ENABLED
MT5_BRIDGE_ORDER_SEND_ENABLED
```

Scanner must distinguish fields from real function calls.

Relevant forbidden call patterns:

```text
.order_send(
MetaTrader5.order_send(
mt5.order_send(
order_send(
```

---

# 24. WHAT THE SYSTEM CAN DO NOW

The current system can:

1. access real MT5 market data through the host bridge;
2. build features, regime, and calendar context;
3. retrieve knowledge and build runtime context;
4. select methods and score decisions;
5. create trade-readiness and human-review artifacts;
6. create non-executable proposal artifacts;
7. create simulated execution artifacts;
8. create live order intent and contract-preparation artifacts;
9. validate parameter sources and proposal boundaries;
10. create Pre-MT5 mapping;
11. validate dry-run request fields;
12. create request-draft and approval boundaries;
13. create schema-only request-dict boundaries;
14. final-validate the dry-run request-dict boundary;
15. reach the bridge write-skeleton endpoint;
16. verify that the bridge is blocked;
17. run a disabled app-side live adapter;
18. evaluate a kill switch;
19. register check-only idempotency;
20. run a disabled pre-submit gate;
21. append safe journal records.

---

# 25. WHAT THE SYSTEM CANNOT DO YET

The current system cannot:

1. create a verified real broker-submittable MT5 request;
2. call `order_send`;
3. return a real order result;
4. create a ticket/deal;
5. determine whether a timed-out request was accepted by MT5;
6. reconcile an order journal against MT5 state;
7. safely retry or prevent a duplicate after unknown submission status;
8. manage a complete open-position lifecycle;
9. supervise the runtime continuously;
10. execute autonomously;
11. promote itself from demo to live;
12. guarantee profitable outcomes.

---

# 26. KNOWN CLEAN-CODE AND ARCHITECTURE ISSUES

## 26.1 Execution fragmentation

The execution core contains many small, repetitive boundary packages.

Likely repeated concepts:

- models;
- policy flags;
- workflow booleans;
- validators;
- JSONL stores;
- formatters;
- source refs;
- idempotency propagation;
- safety flag serialization;
- payload-size checks;
- forbidden-marker checks.

This improved traceability during staged development but now increases:

- code volume;
- maintenance cost;
- test volume;
- cognitive load;
- risk of inconsistent flags;
- difficulty identifying the real runtime path.

## 26.2 Large central files

Reported/observed hotspots include:

- `src/config.py`
- `src/ui/tab_dashboard.py`
- `src/orchestrator.py`
- `src/services/trading/execution/__init__.py`
- long end-to-end live-check scripts.

## 26.3 Configuration drift

Known discrepancy:

- current zip uses bridge port `8765`;
- previous handoff wrote `8001`.

Agents must verify values from source rather than copy old handoff values.

## 26.4 Snapshot packaging quality

The uploaded zip included many `__pycache__` and `.pyc` files.

Future snapshots should exclude:

```text
__pycache__/
*.pyc
venv/
.git/
.env
runtime journals
large generated caches
```

## 26.5 Mode naming ambiguity

The `autonomous_live` label may appear in a live check despite autonomous execution being disabled.

Review whether:

- it is only a router/context mode;
- it should be renamed;
- it should be documented separately from execution authorization.

## 26.6 Missing snapshot files

The uploaded zip did not include a Dockerfile despite `docker-compose.yml` using a build context.

Verify whether:

- the actual workspace has a Dockerfile;
- the snapshot omitted it;
- Docker is using an already-built image unexpectedly.

---

# 27. IMMEDIATE NEXT MILESTONE: CONTROLLED DEMO SUBMISSION

The next engineering milestone is:

`Controlled Demo order_send Integration`

This is the first milestone where a real MT5 write call may exist.

## Required design properties

- demo/local account only;
- one-shot request;
- explicit configuration;
- no autonomous trigger;
- narrow bridge endpoint;
- app-side kill switch;
- bridge-side kill switch;
- idempotency reservation, not only check;
- exact artifact/provenance linkage;
- independent bridge schema validation;
- append pre-submit journal before calling MT5;
- append result journal after return;
- no automatic retry;
- safe response redaction;
- record unknown state when timeout makes outcome uncertain.

## The bridge must not trust the app

Before calling MT5, the bridge must independently check:

- endpoint enabled;
- account environment allowed;
- controlled-demo mode enabled;
- write permission enabled;
- bridge kill switch state;
- request schema;
- idempotency reservation;
- artifact/provenance references;
- required freshness constraints;
- no duplicate/unknown previous state.

## Mandatory validation before implementation

Before adding the first real call:

- focused pre-submit tests;
- all adjacent MT5 boundary tests;
- full scripts regression;
- compileall;
- Docker config;
- app health;
- bridge live data check;
- pre-submit live check;
- exact static scan;
- confirmation that no secret/raw account data leaks.

---

# 28. ROADMAP TO THE AUTONOMOUS END-STATE

The remaining work should be divided into release milestones.

## Release A — Controlled Demo Execution MVP

### Sprint 34 — Controlled Demo `order_send` Integration

Deliver:

- narrow bridge submit-once endpoint;
- bridge-side independent gate;
- one-shot demo submission;
- idempotency reservation;
- immediate result journal;
- no automatic retry;
- all autonomous paths disabled.

### Sprint 35 — Order/Position Reconciliation and Failure Recovery

Deliver:

- reconcile internal request/result records with MT5 orders/positions;
- detect timeout-with-unknown-outcome;
- duplicate detection;
- failure classification;
- no blind retry;
- recovery journal;
- emergency stop behavior.

### Sprint 36 — End-to-End Runtime Testing and Simplification

Deliver:

- test full flow;
- test bridge/app restarts;
- test stale/missing data;
- test duplicate input;
- test corrupt/missing journal;
- test disconnect and timeout;
- measure stage latency;
- identify redundant boundaries from runtime evidence;
- perform targeted simplification;
- milestone full regression.

## Release B — Autonomous Demo System

### Sprint 37 — Autonomous Decision Orchestrator

Deliver a structured continuous decision flow:

```text
market data
→ quality/freshness
→ regime/calendar
→ knowledge/context
→ method selection
→ scoring
→ readiness
→ structured autonomous decision candidate
```

The output must be structured and validated, not executable free-form LLM text.

### Sprint 38 — Autonomous Execution Policy Gate

Deliver:

- deterministic authorization separate from the LLM;
- account-mode policy;
- current-position conflict checks;
- freshness and confidence checks;
- execution cadence/duplicate controls;
- kill switch;
- no prompt bypass;
- default block on unknown state.

### Sprint 39 — Position Lifecycle Manager

Deliver:

- no-position/pending/submitted/filled/open/managing/closing/closed/reconciled state machine;
- read and reconcile existing positions;
- handle externally created or manually modified positions;
- no conflicting simultaneous lifecycle operations;
- position-management actions remain policy controlled.

### Sprint 40 — Continuous Runtime Supervisor

Deliver:

- one authoritative runtime loop;
- stale data detection;
- bridge/terminal health;
- lease/lock preventing duplicate supervisors;
- journal consistency;
- lifecycle consistency;
- safe shutdown;
- pause/resume;
- operator-visible health.

### Sprint 41 — Autonomous Demo Soak Testing and Production Hardening

Deliver:

- long-running demo validation;
- restart recovery;
- network interruption;
- terminal closure;
- model/schema failures;
- unknown order outcome;
- journal corruption;
- clock/freshness issues;
- duplicate prompts;
- concurrency tests;
- observability;
- incident/runbook documentation.

## Release C — Live Account Promotion Gate

After autonomous demo soak testing succeeds, create a separate promotion milestone.

Requirements:

- explicit human-controlled environment promotion;
- live account allowlist or verified environment state;
- bridge-side live permission;
- no prompt-controlled environment switching;
- rollback and emergency stop;
- operator monitoring;
- versioned configuration;
- deployment checklist;
- live account remains disabled by default.

This promotion is not simply another boolean in the chatbot.

---

# 29. TARGET AUTONOMOUS RUNTIME FLOW

The intended final runtime flow is:

```text
User prompt or persistent operating intent
        |
        v
Intent Router and Mode Resolver
        |
        v
Runtime Supervisor
        |
        +--> MT5 health / account environment / market-data freshness
        +--> current orders and positions
        +--> execution journal and lifecycle state
        |
        v
Autonomous Decision Orchestrator
        |
        +--> Feature / regime / calendar
        +--> Knowledge and context
        +--> Method selection
        +--> Scoring
        +--> Readiness
        |
        v
Structured Decision Candidate
        |
        v
Deterministic Autonomous Execution Policy Gate
        |
        +--> account mode
        +--> kill switch
        +--> idempotency
        +--> position conflict
        +--> data freshness
        +--> journal/reconciliation state
        +--> execution availability
        |
        v
Controlled Execution Adapter
        |
        v
Host MT5 Bridge Independent Validation
        |
        v
MetaTrader5 submission
        |
        v
Immediate Result Journal
        |
        v
Order / Position Reconciliation
        |
        v
Position Lifecycle Manager
        |
        v
Learning and Review
```

Critical rule:

```text
LLM recommendation != permission to submit
```

Only deterministic policy and verified runtime state can authorize the execution adapter.

---

# 30. EXPECTED REVIEW BEHAVIOR FOR ANY LLM OR CLI AGENT

When reviewing this repository, follow this protocol.

## Step 1 — Verify before advising

Inspect at minimum:

```text
src/app.py
src/config.py
src/orchestrator.py
src/services/live_data_service.py
src/services/trading/
src/services/trading/execution/
src/ui/tab_dashboard.py
tools/mt5_bridge/
scripts/test_mt5_*.py
scripts/check_mt5_*_live.py
.env.example
docker-compose.yml
requirements.txt
.gitignore
```

Do not assume this handoff is current if source differs.

## Step 2 — Separate fact from inference

For every important claim, label it as:

- directly observed in code;
- verified by test output;
- reported but not rerun;
- inferred;
- proposed.

## Step 3 — Review the runtime path, not only file style

Trace:

```text
market acquisition
→ intelligence artifacts
→ execution artifact chain
→ pre-submit
→ bridge
```

Identify which method is the actual entry point for each stage.

## Step 4 — Avoid generic recommendations

Do not merely say:

- add logging;
- add tests;
- use clean architecture;
- improve security.

Name:

- exact file or package;
- exact duplicated behavior;
- why it is a problem;
- runtime impact;
- minimal recommended change;
- when to make the change.

## Step 5 — Do not over-refactor before runtime proof

Prioritize:

1. correctness of the next runtime boundary;
2. observability;
3. reconciliation;
4. failure safety;
5. then consolidation.

## Step 6 — Do not create query-specific hacks

Any proposed change should work across symbols, prompts, and market conditions through structured contracts and policy, not hard-coded special cases.

## Step 7 — Keep the Intelligence and Execution cores separated

Do not place submission logic in:

- RAG;
- agents;
- orchestrator;
- `live_data_service.py`;
- Streamlit callback code.

## Step 8 — Keep changes small and testable

For implementation tasks:

- minimal diff;
- focused module;
- focused tests;
- adjacent regression tests;
- compileall;
- live check;
- no unrelated cleanup.

---

# 31. EXPECTED REVIEW OUTPUT FORMAT

A high-quality reviewer should return:

## A. Executive verdict

- current milestone;
- whether the reported state matches code;
- whether the system is ready for the next milestone;
- confidence level.

## B. Verified architecture map

- entry points;
- dependency direction;
- important services;
- real runtime path.

## C. Critical findings

For each:

```text
Severity:
File/package:
Observed evidence:
Why it matters:
Minimal fix:
When to fix:
Required tests:
```

Use severities:

- Blocker
- High
- Medium
- Low
- Cleanup

## D. Clean-code findings

Identify:

- duplication;
- mechanical package fragmentation;
- large files;
- config drift;
- leaky abstractions;
- unsafe coupling;
- confusing naming;
- dead or legacy paths.

## E. Next sprint recommendation

Provide:

- sprint name;
- goal;
- in scope;
- out of scope;
- files likely changed;
- acceptance criteria;
- failure conditions;
- test commands;
- rollback criteria.

## F. Longer roadmap impact

Explain how the recommendation supports:

- controlled demo;
- reconciliation;
- autonomous demo;
- position management;
- supervisor;
- live-account promotion.

---

# 32. IMPLEMENTATION RULES FOR CLI AGENTS

When asked to implement a sprint:

1. Read this handoff.
2. Inspect the actual files.
3. State discrepancies before editing.
4. Keep `Reasoning = High`.
5. Do not change unrelated RAG/evidence/UI code.
6. Keep the app free of `MetaTrader5` imports.
7. Put MT5 package calls only in the host bridge.
8. Keep dangerous defaults disabled.
9. Add exact tests for pass and block paths.
10. Do not fake a live PASS.
11. Do not claim full regression unless it was run.
12. Use Windows venv test commands.
13. Restart the app rather than rebuilding unless required.
14. Do not run an enormous full regression for every small sprint.
15. Before first real submission, full regression is mandatory.
16. Report changed files, test results, live results, static scan, and remaining limitations.
17. Never silently enable autonomous or live account behavior.
18. Never use a prompt as the sole execution authorization.
19. Never add automatic retry before reconciliation can resolve unknown states.
20. Keep ticket/deal and account data redacted in user-visible output.

---

# 33. HIGH-PRIORITY REVIEW QUESTIONS

1. Does the actual source match the reported milestone 33 state?
2. Are the Intelligence Core and Trading Execution Core truly separated at dependency level?
3. Which execution packages participate in the real runtime path, and which are historical scaffolding?
4. Is `src/services/trading/execution/` over-fragmented?
5. Are workflow and safety flags consistent across all late-stage models?
6. Are there duplicated config definitions in `src/config.py`?
7. Is `src/ui/tab_dashboard.py` too coupled to internal artifacts?
8. Is `src/services/trading/execution/__init__.py` exporting too much?
9. Can repeated JSONL stores be consolidated after reconciliation is proven?
10. Can repeated safety fields be represented by a shared value object without hiding state?
11. Are forbidden-marker scans checking real call syntax rather than harmless field names?
12. Is pre-submit idempotency truly check-only, and what exact change is needed for reservation?
13. How should the bridge independently verify a controlled-demo request?
14. What is the narrowest safe write endpoint contract?
15. How should timeout/unknown submission state be represented?
16. What minimum immediate result journal must exist in the first write sprint?
17. What reconciliation queries are required before any retry?
18. How should current positions block conflicting autonomous decisions?
19. How should a runtime supervisor prevent duplicate concurrent loops?
20. Which refactors must wait until runtime evidence exists?
21. Which issue is a blocker before `order_send`?
22. Which current safety boundary is redundant but harmless?
23. Which current safety boundary could create inconsistent state?
24. How should demo-to-live promotion be isolated from user prompts?
25. What is the shortest safe path from milestone 33 to autonomous demo operation?

---

# 34. CORE REQUEST TO THE REVIEWER

Given the current codebase, provide a concrete engineering review and upgrade plan that:

1. verifies the actual current state;
2. identifies architecture and clean-code problems with exact file references;
3. confirms or rejects readiness for controlled demo submission;
4. proposes the smallest safe next sprint;
5. preserves the MT5 host-bridge boundary;
6. adds no unnecessary approval-of-approval layer;
7. prioritizes execution correctness, reconciliation, and failure recovery;
8. defines the path toward autonomous demo operation;
9. keeps autonomous and live-account behavior disabled until their explicit milestones;
10. recommends targeted consolidation only after the runtime path is proven.

Do not produce generic advice.
Do not assume the handoff is more authoritative than the source.
Do not implement a real submission path from this text alone.
Inspect the repository, verify the current state, and cite exact files and symbols in the review.

---

# 35. CURRENT ONE-PARAGRAPH SUMMARY

`Trading_Advisory_Chatbot` is a large RAG, market-context, decision, and MT5 integration codebase whose execution side has progressed through 33 staged milestones. The current system reads real MT5 market data through a host-side bridge, builds structured intelligence and execution-preparation artifacts, final-validates a schema-only MT5 request boundary, reaches a blocked write-skeleton endpoint, and passes a disabled pre-submit check with kill switch and check-only idempotency. It cannot yet submit an order. The immediate objective is a one-shot controlled-demo submission with bridge-side independent validation and immediate journaling, followed by reconciliation and failure recovery. The long-term objective is an autonomous demo-first MT5 system in which prompts express operating intent, structured decision logic proposes actions, deterministic policy authorizes or blocks them, the bridge independently validates them, and a lifecycle supervisor reconciles and manages positions. Live-account operation is a separate explicit promotion after autonomous demo soak testing; no system component may promise guaranteed profit or bypass the policy chain.

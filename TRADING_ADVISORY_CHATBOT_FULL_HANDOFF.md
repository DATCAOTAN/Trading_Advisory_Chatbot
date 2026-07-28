# TRADING_ADVISORY_CHATBOT — FULL CODEBASE, RUNTIME, ROADMAP, AND AGENT HANDOFF

**Handoff version:** 4.3
**Prepared from:** the uploaded `Trading_Advisory_Chatbot.zip`, the current Codex handoff snapshot, and the reported runtime/test results.
**Snapshot period:** 2026-07-20 to 2026-07-23
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

The latest completed engineering task is:

`Sprint 41 - Soak Test, Hardening, and Release Closure`

Current verified state:

```text
verification_level=FULL_REGRESSION_SOAK_AND_RUNTIME_PASS
release_closure_tests=7 passed
full_regression_tests=2744 passed
full_regression_subtests=156 passed
full_regression_warnings=3
full_regression_duration_seconds=132.69
fake_soak_decision_cycles=300
fake_soak_policy_cycles=300
fake_soak_lifecycle_cycles=200
fake_soak_reconciliation_reads=50
runtime_soak_duration_seconds=620.2
runtime_health_checks=60
runtime_lifecycle_snapshots=60
runtime_decision_checks=10
runtime_policy_checks=10
production_order_send_call_sites=1
src_metatrader5_imports=0
runtime_mutation_markers=0
live_submission_allowed=false
live_execution_allowed=false
order_send_allowed=false
execution_allowed=false
executable=false
order_sent=false
automatic_retry_allowed=false
kill_switch_engaged=true
controlled_management_enabled=false
autonomous_policy_gate_enabled=false
autonomous_policy_hard_block=true
broker_mutation=NOT_RUN
```

Meaning:

- the complete scripts regression, release-closure suite, bounded fake soak, and ten-minute authenticated read-only terminal soak completed without product crash or deadlock;
- decision, policy, lifecycle, reconciliation, restart, duplicate, bridge-loss, timeout, authentication, overlap, stale-state, malformed-journal, and conflicting-persistence behavior remains fail-closed;
- duplicate fake soak cycles produced only 3 decision, 3 policy, and 5 lifecycle records; total fake-soak journal growth was 15,248 bytes;
- fake soak RSS grew 24,576 bytes after warm-up with threads stable at 15; runtime measurement RSS grew 12,288 bytes with bridge threads stable at 13;
- app and bridge restart, Streamlit health, bridge health/market data, write-skeleton block, controlled execution/management blockers, lifecycle health, and blocked policy checks passed;
- no production defect or safely removable redundant Sprint 37-40 code was demonstrated, so production behavior was not changed;
- all mutation permissions remain disabled, no broker mutation occurred, and exact broker identifiers remain protected.

## 2.2 Immediate goal

The planned sprint roadmap is complete. Further work is operational acceptance or a narrowly scoped maintenance fix only when runtime evidence demonstrates a defect; no Sprint 42 is planned.

Do not add another adapter, approval boundary, scheduler, or continuous runtime loop. Reuse deterministic policy, lifecycle/reconciliation state, protected journals, account fingerprinting, idempotency, kill switches, and the existing bridge trust boundary.
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

- advisory, RAG, and live MT5 market-data system;
- structured intelligence, decision, review, and execution-preparation artifacts;
- immutable approved semantic execution parameters with deterministic integrity hashing;
- final validation and disabled pre-submit safety gate;
- authenticated, account-agnostic controlled execution endpoint;
- account-context fingerprint capture and immediate pre-submit revalidation;
- atomic restart-safe execution idempotency and protected result classification;
- one isolated host-bridge `order_send` call-site behind disabled-by-default manual controls;
- append-only general and protected execution journals.

## Not currently implemented

- operator-verified controlled submission on a selected demo account;
- terminal-backed reconciliation of an actual broker result;
- authorization of retry after an unknown result;
- complete position lifecycle management;
- continuous runtime supervisor;
- autonomous execution policy and position management;
- live-account production promotion.
## Areas that should not be expanded now unless they block execution work

- parser/MinerU improvements;
- embeddings and Qdrant tuning;
- RAG content expansion;
- evidence dashboard expansion;
- broad UI redesign;
- another execution approval layer;
- generic execution framework work.

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
-> Feature / Regime / Calendar
-> Knowledge / Method / Score
-> Trade Readiness
-> Human Review Artifact
-> Dry-Run Gate and Execution Journal
-> Proposal and Simulated Contract Boundaries
-> Live Permission, Intent, Contract, Parameter, Approval, and Final Review
-> Pre-MT5 Mapping and Dry-Run Request Boundaries
-> MT5 Request Dict Final Validation
-> MT5 Bridge Write Skeleton and Disabled Pre-Submit Gate
-> Protected Controlled Execution Request
-> Authenticated Host Bridge Validation
-> Account Context Revalidation
-> Atomic Execution Idempotency Reservation
-> Isolated One-Shot MT5 Submission Function
-> Protected Result Classification and Journal
```

The controlled submission path is implemented but disabled by default. Automated verification used fake MT5; no manual broker submission was run.

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
34A. Immutable Approved Semantic Execution Parameters
34B. Controlled MT5 Execution Integration

Current milestone:

```text
Sprint 41 implemented and full-regression/soak/runtime verified
manual broker submission not run
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

The existing package remains the single app-side adapter boundary. Sprint 34B extended it rather than creating Demo/Real adapters.

Core responsibilities now include:

- existing disabled adapter, bridge skeleton check, kill switch, check-only pre-submit idempotency, gate, journal, and safe summary;
- protected controlled execution request construction from the approved semantic contract and final/pre-submit validation;
- account-context capture before confirmation and recheck before bridge submission;
- authenticated HTTP call to the controlled bridge endpoint;
- redacted accepted, rejected, blocked, or unknown receipt;
- transport failure classified as unknown, with no automatic retry.

Current default behavior remains disabled, hard-blocked, and kill-switch engaged.

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

## 17.3 Controlled execution endpoint

```text
POST /execution/controlled-submit
```

Current properties:

- shared across whichever account is intentionally logged into the host terminal;
- authenticated with an environment secret and constant-time comparison;
- independently validates protected semantics, references, freshness, confirmation, permissions, and terminal/account context;
- rechecks the account fingerprint immediately before submission;
- atomically reserves idempotency and records result states;
- contains one isolated production `order_send` call-site;
- returns redacted receipts with exact ticket/deal omitted;
- disabled by default and not broker-verified during automated tests.

## 17.4 Current bridge restrictions

No broad or unprotected endpoint for:

```text
/order
/execute
/send_order
/order_send
/trade
/position/open
```

Exactly one production `order_send` call-site exists in `tools/mt5_bridge/execution.py`. It is unreachable under default configuration.

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

## 18.3 Pre-submit and controlled execution controls

Safe defaults:

```text
TRADING_MT5_LIVE_ADAPTER_PRE_SUBMIT_ENABLED=true
TRADING_MT5_LIVE_ADAPTER_ENABLED=false
TRADING_MT5_LIVE_ADAPTER_HARD_BLOCK=true
TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION=false
TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND=false
TRADING_MT5_KILL_SWITCH_ENGAGED=true
TRADING_MT5_CONTROLLED_EXECUTION_ENABLED=false
TRADING_MT5_CONTROLLED_EXECUTION_HTTP_TIMEOUT_SECONDS=10
MT5_BRIDGE_CONTROLLED_EXECUTION_ENABLED=false
MT5_BRIDGE_CONTROLLED_EXECUTION_HARD_BLOCK=true
MT5_BRIDGE_EXECUTION_KILL_SWITCH=true
MT5_BRIDGE_ORDER_SEND_ENABLED=false
MT5_BRIDGE_LIVE_EXECUTION_ENABLED=false
MT5_BRIDGE_EXECUTION_TOKEN=
MT5_BRIDGE_EXECUTION_TIMEOUT_SECONDS=5
```

Pre-submit idempotency remains check-only. Controlled execution uses a separate atomic reservation journal only after every bridge gate passes. The app HTTP timeout is longer than the isolated bridge submission timeout so timeout ownership remains on the bridge.

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

Latest controlled execution integration sprint:

```text
new focused tests: 16 passed
direct neighboring execution/bridge tests: 130 passed
changed-path compileall: passed
docker-compose config: passed
docker-compose restart app: passed
Streamlit health: HTTP 200, ok
static scan: 0 MetaTrader5 imports under src; 1 production order_send call under tools
documentation fixture/credential scan: 0 matches
automated broker submission: NOT RUN
manual broker submission: NOT RUN
full scripts regression: NOT RUN
verification level: FOCUSED_PASS
```

Latest immutable approved semantic execution parameter sprint:

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_approved_semantic_execution_parameters.py -q
```

Reported result:

```text
19 passed
```

Adjacent focused groups reported for the same working tree:

```text
proposal/draft/approval: 198 passed
parameterization/final review: 129 passed
request-draft/dry-run/final-validation/pre-submit: 188 passed
focused total: 534 passed
compileall on changed paths: passed
docker-compose config: passed
docker-compose restart app: passed
Streamlit health: HTTP 200, ok
disabled pre-submit live check: passed after starting the existing local bridge
static scan: 0 MetaTrader5 imports under src; 0 real order_send calls under src/tools
```

Full scripts regression was not run for Sprint 34A.

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

Current controlled execution invariants:

- exactly one isolated production `order_send` call-site, under the host bridge only;
- no `MetaTrader5` import under `src/`;
- no automatic retry after timeout or unknown result;
- no autonomous execution or broad uncontrolled bridge endpoint;
- no raw account id or credentials in app requests, responses, logs, or documentation;
- runtime JSONL ignored by git;
- bridge write skeleton continues to return `BLOCKED`;
- the shared adapter and controlled endpoint remain disabled by default;
- kill switch engaged by default;
- pre-submit idempotency is check-only; controlled execution reservation is atomic and restart-safe;
- default live submission, execution, and order-send flags remain false;
- approved semantic values do not grant execution permission;
- exact values are absent from general logs and documentation;
- exact ticket/deal identifiers, if returned by a manual run, are protected-journal-only;
- automated verification must use fake MT5 and must not submit to a broker.

Scanner rules must distinguish harmless field/config names from the single isolated real call.

---
# 24. WHAT THE SYSTEM CAN DO NOW

In addition to its market-data, intelligence, review, proposal, and dry-run boundaries, the current system can:

1. bind approved semantic execution values to one immutable canonical hash;
2. build a protected controlled execution request from approved/final/pre-submit artifacts;
3. authenticate a narrow host-bridge request;
4. independently validate schema, hash, references, freshness, confirmation, permissions, and terminal capability;
5. fingerprint the logged-in account without returning the raw login and recheck it immediately before submission;
6. reserve idempotency atomically across restarts;
7. deterministically map validated semantics after every gate passes;
8. invoke one isolated host-side submission call only when every normally disabled control is deliberately enabled;
9. classify accepted, rejected, blocked, and unknown outcomes;
10. retain exact broker identifiers only in the protected journal;
11. block duplicate or unknown requests without automatic retry.

Automated tests verify this with fake MT5 only.

---
# 25. WHAT THE SYSTEM CANNOT DO YET

The current system cannot yet:

1. prove a real broker submission through automated verification;
2. reconcile confirmed, rejected, or unknown execution records against MT5 orders and positions;
3. determine whether a timed-out request was accepted by MT5;
4. authorize any retry after an unknown outcome;
5. manage a complete open-position lifecycle;
6. supervise the runtime continuously;
7. execute autonomously;
8. promote execution to a live account without a separate explicit release gate.

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

# 27. CONTROLLED EXECUTION MVP CLOSURE

`Sprint 36 - End-to-End Verification, Hardening and MVP Closure` is implemented and verified at `FULL_REGRESSION_AND_RUNTIME_PASS`.

Completed evidence:

- full fake-MT5 submit-once and reconciliation lifecycle coverage;
- restart, duplicate, account-change, transport-loss, stale-state, and corrupt-journal coverage;
- strict no-retry behavior for unknown, ambiguous, absent, and failed evidence;
- exact one-call host bridge submission invariant and zero app/reconciliation call-sites;
- full scripts regression, compileall, Docker Compose config, latency sampling, and static safety scans;
- live bridge health, blocked write skeleton, and missing/invalid reconciliation authorization checks;
- no automated or manual broker submission.


The controlled execution MVP is complete for automated fake-MT5 and non-submitting bridge verification. Manual broker submission and terminal-backed reconciliation remain explicit operator actions.

---# 28. ROADMAP TO THE AUTONOMOUS END-STATE

The remaining work should be divided into release milestones.

## Release A — Controlled Demo Execution MVP

### Sprint 34A - Immutable Approved Semantic Execution Parameters (completed)

Delivered:

- one typed immutable approved semantic-value contract in the existing approval/lock flow;
- deterministic canonical hash binding and mutation detection;
- downstream hash recognition without execution permission;
- redacted general serialization and unchanged execution hard blocks.

### Sprint 34B - Controlled MT5 Execution Integration (implemented)

Delivered:

- one shared account-agnostic protected execution path;
- authenticated bridge endpoint and independent integrity/runtime validation;
- account fingerprint capture and immediate revalidation;
- atomic idempotency reservation and protected result journal;
- one isolated submission call-site with no automatic retry;
- disabled-by-default manual entry point;
- fake-MT5 focused verification only; manual broker submission not run.
### Sprint 35 - Order/Position Reconciliation and Failure Recovery (implemented)

Delivered:

- authenticated, independently validated `POST /execution/reconcile` on the host bridge;
- stable protected correlation metadata and restart-safe reconciliation journaling;
- bounded read-only MT5 order, deal, and position evidence queries;
- explicit unique, ambiguous, no-match, query-failed, account-changed, and ineligible classifications;
- stale reservation abandonment and stale submission-start recovery to unknown state;
- exact broker identifiers restricted to the protected journal;
- no automatic retry and no additional submission call-site;
- fake-MT5 focused verification only; manual reconciliation and broker submission not run.

### Sprint 36 - End-to-End Verification, Hardening and MVP Closure (completed)

Delivered:

- one focused 21-test fake-MT5 lifecycle suite;
- restart-safe duplicate, timeout, unknown-result, and reconciliation verification;
- fail-closed protected journal handling for missing, truncated, malformed, and conflicting persistence;
- current-architecture preflight enforcement without weakening default execution locks;
- targeted reuse of the existing protected HTTP helper;
- full regression: 2577 passed and 156 subtests passed;
- non-submitting live bridge checks passed;
- Docker app restart and Streamlit HTTP 200 health check passed.

## Release B - Autonomous Demo System

### Sprint 37 - Read-Only Position Lifecycle and Runtime Supervisor (completed)

Delivered bounded authenticated lifecycle snapshots, protected broker-reference hashing, restart-safe lifecycle observations, overlap prevention, and a non-mutating one-shot/runtime supervisor path.

### Sprint 38 - Controlled MT5 Position Management (completed)

Delivered one explicitly confirmed controlled path for canceling one active pending order, modifying protection on one unique open position, or reducing/closing one unique open position. All mutation permissions remain disabled by default.

### Sprint 39 - Autonomous Decision Orchestrator (completed)

Delivered the deterministic non-executable flow:

```text
structured market/context inputs
-> method selection and score
-> deterministic readiness/risk
-> lifecycle and reconciliation constraints
-> structured autonomous decision candidate
-> validation and append-only decision journal
-> stop
```

The orchestrator is one-shot only, treats `NO_ACTION` as success, and has no execution authority or bridge mutation dependency.

### Sprint 40 - Autonomous Execution Policy Gate (completed)

Delivered a deterministic, non-executing policy gate that maps Sprint 39 candidates to `BLOCK`, `REQUIRE_HUMAN_REVIEW`, or eligibility for an existing controlled boundary. It validates provenance, freshness, risk, account context, lifecycle/reconciliation state, management exposure, close volume, and protected journal integrity. Defaults keep the gate and eligibility disabled with the hard block enabled; all execution-authority and mutation flags remain false.

### Sprint 41 - Soak Test, Hardening, and Release Closure (completed)

Delivered one focused release-closure suite plus complete regression and bounded runtime evidence. The fake soak completed 300 decision, 300 policy, 200 lifecycle, and 50 reconciliation-read samples; the terminal soak completed 60 health checks, 60 lifecycle snapshots, and 10 blocked decision/policy checks over 620.2 seconds. Restart, duplicate, bridge-loss, timeout, authentication, overlap, journal corruption, and persistence-unavailable scenarios remained fail-closed. No product defect, broker mutation, new boundary, scheduler, or evidence-supported simplification was introduced.

Full regression passed 2,744 tests and 156 subtests with 3 dependency deprecation warnings in 132.69 seconds. Static state remains exactly one production `.order_send(` call-site and zero `MetaTrader5` imports under `src/`.

### Post-release maintenance - Structured Market and Pending Order Intent Candidate

The existing Sprint 39 candidate now optionally carries a typed, non-executable market or pending-order proposal for all eight supported order types. A deterministic resolver derives `MARKET` or `PENDING` from `order_type`; it validates required prices, stop-limit trigger/limit separation, Bid/Ask relationships, optional symbol distance metadata, source freshness, and structured-order integrity. Exact prices, volume, side, and reasoning remain absent from public serialization and decision journals. Legacy `NO_ACTION`, review, management, and OPEN candidates without the optional proposal remain valid. Verification is `FOCUSED_AND_RUNTIME_PASS`: 29 new tests and 67 neighboring orchestrator/policy tests passed; changed-path compileall and static safety scans passed; Docker Compose config, app restart, healthy Streamlit HTTP 200, and one non-broker candidate v2 smoke passed. Full regression, bridge runtime, controlled endpoints, and broker mutation were not run for this maintenance task.

### Post-release maintenance - Read-only Streamlit Market/Pending Order Review Card

The dashboard now includes a read-only operator Review Card backed by a typed Streamlit-session owner for the latest `AutonomousDecisionRunResult`. An already-produced result is stored, retrieved, explicitly replaced, or explicitly cleared without candidate generation during render. A dedicated bounded operator projection exposes only the resolved proposal values needed for local review, while `to_public_dict()` and decision journals remain unchanged and redacted. MARKET, LIMIT, STOP, and STOP_LIMIT render conditionally; stop-limit trigger and limit values remain separate. Schema v1 and non-open candidates remain compatible, missing state displays `UNAVAILABLE`, blockers retain deterministic order, and the component contains no button, LLM call, journal access, bridge call, confirmation, permission, or broker mutation path.

Verification is `FOCUSED_AND_LIVE_PASS` for the Streamlit runtime scope: 20 focused Review Card tests and 132 neighboring candidate/orchestrator/policy/UI tests passed; changed-path compileall and static safety scans passed. Docker Compose config, app restart, healthy status, and Streamlit HTTP 200 (`ok`) passed. A two-render Streamlit AppTest proved typed candidate -> session owner -> Review Card with exact bounded proposal values, zero exceptions, zero buttons, one unchanged journal record, and non-executable safety. Full regression, MT5 bridge runtime, controlled endpoints, and broker mutation were not run.

### Post-release maintenance - Controlled Pending Order Contract and Dry-Run Mapping

The existing controlled execution ownership now includes one focused mapper from a reviewed `AutonomousDecisionCandidate` v2 to a frozen, typed `ControlledPendingOrderContract` and a semantic `PendingOrderDryRunRequestDraft`. It supports `BUY_LIMIT`, `SELL_LIMIT`, `BUY_STOP`, `SELL_STOP`, `BUY_STOP_LIMIT`, and `SELL_STOP_LIMIT`; stop-limit trigger and limit values remain separate. The mapper reuses the autonomous candidate validator and canonical market-snapshot hash, requires valid symbol metadata, binds candidate provenance and structured-order integrity through the existing human-review and dry-run confirmation artifacts, verifies fresh matching protected account context, and creates a draft only when every deterministic check passes.

Verification is `FOCUSED_AND_PENDING_DRY_RUN_PASS`: 35 focused pending-contract tests and 319 neighboring candidate, policy, approval, semantic-contract, request-draft, and dry-run-validator tests passed. Changed-path compileall passed. A fixture `BUY_STOP_LIMIT` dry-run was `VALID`, preserved separate trigger/limit fields, created no bridge request or JSONL journal, and kept all execution flags false. Static scans found exactly one unchanged production `.order_send(` call-site, zero `MetaTrader5` imports under `src/`, and zero controlled endpoint or broker-call markers in the mapper. Full regression, Docker/runtime checks, MT5 bridge pending execution, controlled submission, and broker mutation were not run.

## Operational live-account promotion gate (outside the completed sprint roadmap)

Any later live-account promotion requires a separate explicit operator decision; it is not Sprint 42 and is not implied by release closure.

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

# 35. CURRENT CONTROLLED PENDING-ORDER STATE

Post-release maintenance now extends the existing authenticated `/execution/controlled-submit` boundary to all six pending types: `BUY_LIMIT`, `SELL_LIMIT`, `BUY_STOP`, `SELL_STOP`, `BUY_STOP_LIMIT`, and `SELL_STOP_LIMIT`.

- App ownership: the immutable reviewed pending contract is revalidated for schema, canonical integrity, review/confirmation references, freshness, protected account context, explicit GTC policy, volume, protection values, execution metadata, permission, and pre-submit state before protected serialization.
- Bridge ownership: the host bridge independently validates the protected contract, current account, symbol capability, Bid/Ask relationship, digits, tick size, stops level, volume range/step, GTC support, and requested pending family before mapping MT5 constants.
- STOP_LIMIT mapping remains exact: semantic `trigger_price` maps to MT5 `price`; semantic `limit_price` maps to MT5 `stoplimit`. Unsupported terminal capability fails closed without conversion.
- Submission ownership remains the existing isolated call in `tools/mt5_bridge/execution.py`; no endpoint, adapter, journal, retry path, or call-site was added.
- The existing protected journal atomically reserves pending requests, replays identical completed results without resubmission, rejects conflicting duplicates, and preserves `RESULT_UNKNOWN` as retry-prohibited across restart.
- Read-only reconciliation now recognizes active, filled, cancelled, expired, and rejected pending orders; lifecycle reuses `ORDER_ACTIVE`, `POSITION_OPEN`, `BROKER_ACCEPTED`, `BROKER_REJECTED`, and `RECONCILIATION_REQUIRED`.
- Pending submission and every LIMIT/STOP/STOP_LIMIT family are disabled and hard-blocked by default on both app and bridge. Existing execution kill switches and `order_send` permissions remain blocked by default.
- Verification: `FULL_REGRESSION_PASS`; 28 focused pending-submission tests and 129 neighboring tests passed, changed-path compileall passed, Docker/Streamlit were healthy, bridge health was `OK`, a protected pending request was blocked with `EXECUTION_DISABLED`, lifecycle read returned `OK`, and reconciliation read returned `NOT_REQUIRED` with retry prohibited. The post-commit full scripts regression passed 2,865 tests and 156 subtests in 155.84 seconds with 3 dependency warnings.
- Broker mutation was NOT RUN. Pending-order operational acceptance is still required before any operator-enabled use.

`Trading_Advisory_Chatbot` remains complete through Sprint 41, with this work classified as explicit post-release maintenance rather than Sprint 42. Production still has exactly one `.order_send(` call-site and `src/` has zero `MetaTrader5` imports.

---

# 36. CURRENT PENDING ARTIFACT CAPTURE AND VALIDATION-ONLY STATE

Post-release maintenance now connects one authoritative typed reviewed pending candidate to the existing pending contract and protected-request builders without adding an execution boundary.

- Candidate ownership remains `AutonomousDecisionRunResult`; its private typed market snapshot is retained without changing public candidate serialization or decision journals.
- Streamlit exposes one explicit `Export Protected Pending Candidate` handoff action. Page render and refresh do not export, rerun the LLM, generate another candidate, or append a decision journal.
- The operator CLI accepts only protected candidate, account-context, output-directory references, and the exact export-only confirmation. It has no order parameter arguments.
- The existing `ControlledPendingOrderDryRunMapper` and `MT5ControlledExecutionRequest.from_pending_artifacts(...)` produce `controlled-mt5-pending-execution/v1` in validation-only mode.
- Protected handoff and bundle writes are integrity-bound, atomic, conflict-safe, idempotent for identical sources, and restricted to Git-ignored `data/trading/protected_requests/` storage.
- All six pending types are supported; STOP_LIMIT retains separate trigger and limit values.
- Every artifact preserves execution authority, execution permission, live submission, executable, order-send, and order-sent state as false. Pre-submit permission is not granted.
- Verification: 30 focused tests and 150 neighboring export/candidate/review/pending tests passed; changed-path compileall and `git diff --check` passed; Docker app restart, healthy status, and Streamlit HTTP 200 `ok` passed.
- Post-commit full scripts regression: 2,895 tests and 156 subtests passed in 132.11 seconds with 3 dependency warnings (FULL_REGRESSION_PASS).
- Runtime verification result: `PASS_WITH_RUNTIME_CANDIDATE_LIMITATION`. The current runtime had no authoritative typed reviewed pending candidate, so no runtime pending artifact was fabricated or exported.
- Static state remains exactly one production `.order_send(` call-site, zero `MetaTrader5` imports under `src/`, one existing controlled-submit endpoint, and disabled/hard-blocked pending defaults.
- Controlled submission, reconciliation, execution-journal mutation, and broker mutation were NOT RUN. Full regression passed; pending-order operational acceptance remains pending.

# 37. CURRENT OPERATOR-TRIGGERED CANDIDATE GENERATION STATE

Post-release maintenance now provides one explicit Streamlit action that connects the existing authoritative runtime pipeline to the existing autonomous decision orchestrator and Review Card.

- Input ownership remains the existing MT5 market provider, feature engine, calendar context, regime detector, knowledge router, context-pack builder, method selector, scoring engine, trade-readiness policy, and read-only lifecycle supervisor.
- `Generate Autonomous Candidate` is the only generation trigger. Page load, refresh, unrelated widget changes, and Review Card rendering do not call the orchestrator.
- The controller guards duplicate request identifiers and overlapping callbacks, calls the existing orchestrator at most once, and stores only a valid persistence-safe `AutonomousDecisionRunResult` through the existing session owner.
- Missing, stale, invalid, or conflicting market, symbol, account, lifecycle, reconciliation, evidence, and reference inputs block before orchestration. The previous typed result is preserved on failure; replacement and clearing require explicit operator actions.
- No result type is forced. NO_ACTION, MARKET, PENDING, human-review, management, and blocked candidates remain governed by the existing deterministic resolver and validator.
- Every stored result remains non-executable. Generation does not export an artifact, confirm, approve, submit, reconcile, mutate the bridge, or change execution permissions.
- Verification: 34 focused tests, 146 neighboring orchestrator/candidate/review/policy/export tests, and 36 dashboard safety tests passed. Changed-path compileall and static scans passed.
- Docker Compose config and app restart passed; the app became healthy, Streamlit returned HTTP 200 `ok`, and bridge health was `OK` with the terminal connected.
- Runtime verification result: `PASS_WITH_RUNTIME_INPUT_LIMITATION`. The explicit Streamlit action was present and no candidate existed before the click, but generation stopped before the orchestrator with `LIFECYCLE_UNAVAILABLE` because the configured runtime lacks the execution-auth token required by the read-only lifecycle endpoint.
- Execution journal content and hash were unchanged, no autonomous decision journal was created, protected artifact count was unchanged, and refresh did not create work after the blocked action.
- Static state remains exactly one production `.order_send(` call-site, zero `MetaTrader5` imports under `src/`, one unchanged controlled-submit endpoint, and disabled/hard-blocked autonomous and pending execution defaults.
- Automatic export, controlled submission, reconciliation mutation, broker mutation, and order submission were NOT RUN.
- Next after runtime lifecycle authentication is available: generate one typed result explicitly, review it, and only if it is a valid PENDING candidate continue with the existing validation-only pending artifact export.


# 38. CURRENT AUTHORITATIVE NON-EXECUTABLE PROPOSAL OWNER STATE

Post-release maintenance now gives the operator candidate flow one explicit upstream owner for typed, non-executable order proposals.

- `AutonomousOrderProposalProvider` consumes the existing typed feature result, current market bundle/tick, runtime context, method selection, score report, and trade-readiness decision.
- It reuses the project LLM router for one strict structured invocation per explicit operator generation request. It does not parse formatted prose or public serialization, retry for a preferred outcome, or use downstream approval artifacts.
- Strict output is converted to the existing `AutonomousOrderIntentProposal` and `AutonomousOrderMarketSnapshot` contracts. Side, entry intent, and MARKET/PENDING action are deterministically bound to the selected order type.
- Every mandatory binding identifier is independently required to be a non-empty, whitespace-free string and must match the current typed source IDs before orchestration. Stale evidence, missing or malformed provenance, symbol conflicts, malformed JSON, incomplete fields, invalid price relationships, unavailable/disabled model access, and source-binding mismatches return ordered blockers.
- The operator assembler still validates market, structured reasoning, lifecycle, reconciliation, and account context before invoking the proposal owner. The existing orchestrator remains authoritative for final classification and can naturally return NO_ACTION, REQUIRE_HUMAN_REVIEW, MARKET, PENDING, management, or blocked outcomes.
- Raw model output, hidden reasoning, credentials, and unrestricted provider responses are not persisted or exposed. Normalized proposal fields may appear only in the bounded operator Review Card, while approved references and integrity hashes may appear in redacted/public candidate serialization. Human approval remains downstream, and every execution/submission flag remains false.
- Verification is currently `FOCUSED_PASS`: 30 provider tests, 36 operator-generation tests, and 18 existing method-selector adapter tests passed after source-binding hardening. The earlier implementation pass also completed neighboring candidate/policy/Review Card tests and Docker/Streamlit health, but live generation and full regression have not been run for this uncommitted revision.
- Runtime candidate generation, live LLM invocation, protected export, controlled submission, reconciliation mutation, and broker mutation were NOT RUN.
- The current app-side market contract does not expose point, tick size, digits, or stops level. The proposal owner therefore binds only the authoritative bundle/tick/bid/ask/source metadata currently available; downstream pending validation remains fail-closed where deeper symbol metadata is mandatory.

# 39. OFFLINE AUTONOMOUS-CANDIDATE ACCEPTANCE HARNESS

Post-release maintenance now includes one deterministic developer CLI for candidate acceptance while live XAUUSDm data is unavailable.

- The harness uses typed offline market, symbol, account-context, lifecycle, reconciliation, reasoning, scoring, readiness, and proposal fixtures with an injected fixed timestamp.
- It reuses `AutonomousOrderProposalProvider`, the operator input validators, and `AutonomousDecisionOrchestrator`; it does not create a parallel candidate schema or policy.
- Built-in scenarios cover natural NO_ACTION, REQUIRE_HUMAN_REVIEW, MARKET, PENDING, stale market, account mismatch, unresolved reconciliation, and malformed proposal results.
- Candidate mode is `offline_fixture`; source and market references use `offline_fixture:` and are integrity-bound through existing candidate hashes.
- Protected handoff and pending dry-run mapping reject offline provenance with `OFFLINE_PROVENANCE_NOT_EXECUTABLE`, including after a superficial mode-only edit.
- The CLI fails closed when execution, submission, autonomous-policy, pending-family, or position-management permissions are enabled.
- Focused harness verification: 29 passed. Neighboring proposal, candidate, pending, lifecycle, reconciliation, export, and submission verification: 238 passed with 2 dependency warnings.
- Full regression passed with 2,990 tests and 156 subtests; compileall passed with 3 dependency warnings from the test suite. Ponytail full-mode review passed with no valid simplification finding.
- No bridge, Docker, external LLM, protected export, controlled submission, reconciliation mutation, or broker mutation was run.
- Live acceptance remains `DEFERRED_UNTIL_FRESH_XAUUSDM_MARKET_DATA`.
# 40. HERMETIC OFFLINE AND DEFAULT PYTEST LLM ISOLATION

Post-release maintenance now prevents ignored local `.env` reasoning settings from granting external-provider permission to automated tests or the offline acceptance harness.

- Root `conftest.py` sets process-local `TRADING_REASONING_LLM_ENABLED=false` and `TRADING_TEST_HERMETIC=true` before application settings load.
- The two root manual runners are excluded from default pytest discovery; they are not changed or treated as automated tests.
- `LLMClient` rejects Groq, Google/Gemini, and OpenRouter construction in hermetic test mode, and rejects every project LLM client in offline acceptance mode before provider construction.
- The offline harness sets and restores its process-local marker with `try/finally` and continues to use only `DeterministicProposalAdapter`.
- Normal production behavior remains unchanged when neither hermetic nor offline mode is active; this is verified with a fake provider constructor and no external request.
- Focused hermetic/offline verification: 37 passed. Default full regression: 2,998 passed and 156 subtests passed with 3 dependency warnings.
- External provider constructor and request counts were zero for Groq, Google/Gemini, and OpenRouter. `.env` remained ignored, untracked, unstaged, and hash-unchanged during the focused check.
- No bridge, Docker, live market provider, protected export, controlled submission, reconciliation mutation, `order_send`, or broker mutation was run.
- Live acceptance remains `DEFERRED_UNTIL_FRESH_XAUUSDM_MARKET_DATA`.

# 41. BROKER-ALIGNED MULTI-SYMBOL CANDIDATE FLOW

Post-release maintenance now carries separate canonical and broker symbols through the existing autonomous candidate and controlled pending-order flow.

- The existing shared resolver owns canonical-to-broker mapping. The existing XAUUSD mapping remains unchanged and `BTCUSD -> BTCUSDm` is configured through the same mechanism.
- The explicit operator generation action accepts `XAUUSD` or `BTCUSD`; no-symbol callers retain the existing XAUUSD default.
- Market bundles use the provider-resolved broker symbol, and tick snapshots carry digits, point, tick size/value, contract size, stops distance, and volume limits/step.
- Candidate, protected pending contract, dry-run draft, bridge validation, terminal mapping, reconciliation, and integrity hashes preserve both canonical and broker identities.
- BTCUSD fails closed when required broker metadata is absent. Volume is checked against broker minimum, maximum, and step; spread fallback is deny-by-default until configured.
- Calendar and knowledge fallback behavior no longer imports XAUUSD/gold relevance into BTCUSD processing. Existing XAUUSD behavior and legacy no-symbol callers remain covered.
- Verification: `FULL_REGRESSION_PASS`; 10 focused tests, 398 focused/neighboring tests, and the full regression of 3,008 tests plus 156 subtests passed. Three dependency warnings were unchanged.
- External LLM calls, candidate generation, bridge runtime calls, protected export, controlled submission, reconciliation mutation, `order_send`, and broker mutation were NOT RUN.
- Execution, pending submission, autonomous execution, and management defaults remain disabled and hard-blocked.
- BTCUSDm live acceptance remains pending and requires a separately authorized single generation attempt with fresh tick and M15/H1/H4 data.

# 42. TASK-SCOPED BTCUSD M1 LIVE-ACCEPTANCE PROFILE

Post-release maintenance now allows one explicit BTCUSD operator request to substitute M1 for the ordinary M15 short-term input without changing permanent defaults.

- The existing market and feature services already accepted request-scoped timeframes; the operator assembler/controller now preserve that input.
- The Streamlit action exposes a disabled-by-default BTCUSD M1 acceptance checkbox. It sends `M1,H1,H4` only when BTCUSD and the checkbox are both explicitly selected.
- M1 uses the existing OHLCV provider, data-quality gate, feature engine, reasoning context, candidate validator, and reason ordering. The bridge already supported MT5 `TIMEFRAME_M1`.
- `MARKET_DEFAULT_SYMBOL=XAUUSD`, the existing XAUUSD broker mapping, and `MARKET_DEFAULT_TIMEFRAMES=M15,H1,H4` remain unchanged. Requests without the override retain those defaults.
- M1 has a 300-second stale-bar threshold. Stale M1, missing H1/H4, and every existing market/lifecycle blocker remain fail-closed before proposal generation.
- Verification: `FULL_REGRESSION_PASS`; 16 focused tests, 164 neighboring tests, and 3,014 full-regression tests plus 156 subtests passed with 3 unchanged dependency warnings.
- Execution, export, controlled submission, reconciliation mutation, `order_send`, and broker mutation were NOT RUN during implementation verification.
- A separately authorized post-commit BTCUSDm live acceptance remains pending.

# 43. MT5 COMPLETED-BAR NORMALIZATION

Post-release maintenance now exposes only completed MT5 bars to the application market-data pipeline.

- Raw read-only MT5 diagnostics confirmed that `copy_rates_from_pos` position `0` is the currently forming bar and position `1` is the latest completed bar for M1, H1, and H4. Returned epochs already represent UTC and are normalized exactly once.
- The host bridge previously requested position `0`, so the application could treat a current H4 bar as complete while other timeframes reflected stale terminal history.
- `MT5Client.ohlcv(...)` now starts at position `1` for every supported timeframe. No new provider, snapshot path, synchronization mechanism, or threshold was introduced.
- Completed-bar freshness now derives close time from the shared timeframe duration and compares age since close against the unchanged timeframe-specific threshold.
- The earlier stale M1/H1 history synchronized at the terminal before the final comparison. No timezone conversion defect was found. After correction, M1 and H1 completed bars were available while H4 correctly remained stale rather than using its current bar.
- The BTCUSD `M1,H1,H4` task-scoped profile, default XAUUSD `M15,H1,H4` profile, symbol mappings, and all disabled execution/export/submission/management defaults remain unchanged.
- Verification: 45 focused/neighboring market-data tests passed; full regression passed with 3,016 tests and 156 subtests. Three dependency warnings were unchanged.
- External LLM calls, candidate generation, protected export, controlled submission, reconciliation mutation, `order_send`, and broker mutation were zero. Live candidate acceptance remains pending.

# 44. COMPLETED-BAR CLOSE-TIME FRESHNESS

Post-release maintenance now calculates market-data freshness from the completed bar's close time rather than its open time.

- `timeframe_duration_seconds(...)` is the shared duration source for M1, M5, M15, H1, H4, and D1.
- `DataQualityGate._evaluate_snapshot(...)` computes `close_time = open_time + timeframe_duration` and clamps future/negative age to zero before applying the existing stale threshold.
- MT5 position `0` remains excluded by the host bridge; no current forming bar is accepted as completed.
- M1, M15, H1, and H4 therefore use the same completed-bar and close-time semantics without a BTC-specific branch.
- XAUUSD `M15,H1,H4`, BTCUSD `M1,H1,H4`, symbol mappings, thresholds, reason ordering, and all disabled execution/submission defaults remain unchanged.
- Verification: 130 focused/neighboring tests passed; full regression passed with 3,017 tests and 156 subtests. Three dependency warnings were unchanged.
- External LLM calls, candidate generation, export, controlled submission, reconciliation mutation, `order_send`, and broker mutation were zero. Live acceptance was not run.

# 45. STRUCTURED PROPOSAL JSON COMPATIBILITY

Post-release maintenance now requests and consumes the autonomous proposal as bounded structured JSON without weakening its schema or execution boundary.

- The previous one-attempt BTCUSD acceptance reached Groq once and failed closed before orchestration with `STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON`; the raw provider text was intentionally not persisted, so its exact wrapper cannot be reconstructed.
- Offline reproduction proved that plain JSON passed, while one outer Markdown JSON fence and one double-encoded JSON object were rejected by the old parser. Leading prose, malformed JSON, non-finite constants, empty content, and schema-invalid objects also failed closed.
- The autonomous proposal path now requests Groq JSON-object mode through the existing project LLM client, forwards the configured token bound, and disables provider fallback for this structured call. Unsupported structured response-format/provider combinations fail before a request.
- Response extraction remains authoritative `message.content`; separate reasoning or hidden provider metadata is not parsed or persisted.
- Parsing accepts a JSON object directly, removes at most one exact outer `json` fence, and decodes at most one JSON-string wrapper. It does not search prose for embedded objects or repair malformed JSON.
- The exact proposal field set, enum semantics, numeric validation, provenance checks, and candidate-creation boundary are unchanged. Candidate construction still occurs only after parse and schema validation pass.
- Verification: 42 focused proposal/provider tests and 153 neighboring adapter/orchestrator/offline/hermetic tests passed. Full regression passed with 3,029 tests and 156 subtests; three dependency warnings were unchanged.
- External LLM calls, live generation, export, controlled submission, reconciliation mutation, `order_send`, and broker mutation were zero. A new live generation attempt requires separate authorization.

# 46. GROQ STRUCTURED-REQUEST DIAGNOSTIC AND WINDOWS-SAFE FAILURE REPORTING

Post-release maintenance now prevents the structured Groq request from failing before transport when a Windows console cannot encode the route-log emoji.

- The verified local failure was `UnicodeEncodeError` in `LLMClient._chat_groq_sync(...)` before the SDK transport call. Client construction, credential loading, model resolution, hermetic guards, and request arguments were valid.
- The Groq route log is now ASCII-only. Structured JSON calls apply the configured reasoning timeout and SDK `max_retries=0`; fallback remains disabled.
- Missing Groq credentials fail before client construction. Provider failures are mapped to fixed redacted categories for credential, authentication, authorization, model, request, rate-limit, timeout, connection, and runtime-encoding failures without persisting exception messages.
- One minimal non-trading JSON probe was attempted before the fix. It received no HTTP response and made no candidate, MT5, export, submission, reconciliation, `order_send`, or broker call. No second probe or candidate generation was run in this task.
- Verification: 96 focused provider/hermetic/operator tests passed. Full regression passed with 3,039 tests and 156 subtests; three dependency warnings were unchanged.
- Next: separately authorize one minimal post-fix Groq JSON transport probe. Candidate generation remains blocked until that probe succeeds.

# 47. STRUCTURED PROPOSAL FIELD-CONTRACT ALIGNMENT

Post-release maintenance now makes the natural `NO_PROPOSAL` response contract explicit without weakening exact-field validation.

- The post-fix transport probe passed with one direct JSON object. A later separately authorized BTCUSD acceptance passed fresh M1/H1/H4, account, lifecycle, reconciliation, mapping, and metadata preflight, then received one direct JSON object whose status was `NO_PROPOSAL` but whose top-level field set was incomplete.
- Raw provider content and the exact live key set were intentionally not persisted. An offline minimal reproducer containing only `status`, `reason_codes`, and `blockers` reproduces `STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID`; it is not represented as the exact historical response.
- The authoritative proposal contract remains one exact ten-field object. The prompt now lists every required field and includes one complete `NO_PROPOSAL` example with all trade fields set to `null`.
- `NO_PROPOSAL` remains the only natural no-trade provider status. `NO_ACTION` is still an orchestrator intent, not a provider-status alias.
- The parser still rejects missing fields, extra fields, unknown statuses, invalid code collections, malformed numeric inputs, and invalid actionable relationships. It now also requires non-empty no-proposal reason codes and rejects any non-null order type or trade value in a `NO_PROPOSAL` object with field-specific redacted blockers.
- No fields are inserted, renamed, coerced, repaired, or ignored. A valid `NO_PROPOSAL` maps deterministically to `STRUCTURED_PROPOSAL_NOT_AVAILABLE` and stops before candidate creation.
- Verification: 63 focused provider/contract tests and 118 neighboring operator, candidate, multi-symbol, offline, and hermetic tests passed. Full regression passed with 3,050 tests and 156 subtests; three dependency warnings were unchanged.
- External LLM calls, candidate generation, MT5 calls, market-data calls, retries, fallback, export, submission, controlled-submit, runtime `order_send`, and broker mutation were zero during this offline fix.

# 48. RUNTIME INPUT HANDOFF REFERENCE CLOCK

Post-release maintenance now validates freshly assembled structured reasoning artifacts against a post-reasoning handoff clock instead of the earlier market-preflight clock.

- `AuthoritativeAutonomousInputAssembler.build(...)` previously captured one reference time before market and reasoning work, then reused it after reasoning to validate `RuntimeContextPack`, `MethodSelectionResult`, `SignalScoreReport`, and `TradeReadinessDecision` creation timestamps.
- When reasoning lasted more than the existing five-second future-skew allowance, those newly created artifacts produced a negative age below `-5` seconds and incorrectly emitted `STRUCTURED_RUNTIME_INPUT_STALE` before the structured proposal provider.
- The market snapshot still uses the original preflight reference time. After reasoning and lifecycle checks, the assembler now captures a handoff reference time for structured-input validation and the proposal request.
- The exact feature snapshot, bundle, context, method, score, and risk references remain bound through the same objects and source identifiers. Streamlit session state is not an input source for assembly.
- The 300-second maximum age, five-second clock-skew allowance, completed-bar semantics, BTCUSD `M1,H1,H4` profile, XAUUSD defaults, Groq JSON contract, retry policy, and all execution safety gates are unchanged.
- Hermetic reproduction proved that a ten-second post-start artifact was rejected as `STRUCTURED_RUNTIME_INPUT_STALE` by the old reference clock even though it was newly created. The corrected handoff clock reaches the proposal provider once, while a genuinely 301-second-old input remains blocked.
- Verification: 177 focused/neighboring tests passed; full regression passed with 3,055 tests and 156 subtests. Three dependency warnings were unchanged.
- MT5, live market data, Streamlit generation, external LLM, candidate generation, retries, fallback, export, submission, controlled-submit, runtime `order_send`, and broker mutation were zero during diagnosis and verification.
- Next: separately authorize one fresh BTCUSD acceptance attempt. Do not retry the previous attempt or run acceptance as part of this maintenance fix.

# 49. OFFLINE ACTIONABLE CANDIDATE LIFECYCLE ACCEPTANCE

The first incomplete post-reasoning milestone is now verified deterministically without another live provider or market attempt.

- The existing offline harness now covers natural `NO_PROPOSAL`, valid MARKET and PENDING proposals, invalid market-price relation, invalid volume, stale evidence, source-reference mismatch, account-context mismatch, lifecycle discrepancy, malformed JSON, and schema-invalid output.
- Valid actionable fixtures use complete broker metadata and a volume aligned with minimum, maximum, and step constraints. They pass the existing proposal parser, source binding, orchestrator validation, structured-order hash, and provenance hash checks.
- Candidate admission uses the existing `AutonomousDecisionJournal`. MARKET and PENDING each append exactly one valid record; a second admission of the same candidate is rejected idempotently without adding another record.
- Natural `NO_PROPOSAL` is now exposed by the operator controller as `NO_ACTION`, stops before the decision orchestrator, and creates no candidate or journal record.
- Every invalid fixture stops at its authoritative blocker before candidate persistence. No approval, export, submission, reconciliation mutation, bridge mutation, runtime `order_send`, or broker mutation occurs.
- Offline candidates remain explicitly non-executable and retain offline provenance; the existing protected-handoff rejection remains unchanged.
- Verification: 95 focused offline/operator tests passed; the combined proposal, candidate, policy, review, operator, lifecycle, reconciliation, hermetic, and offline suites passed 327 tests. Full regression passed with 3,080 tests and 156 subtests in 220.78 seconds with 3 unchanged dependency warnings.
- Compile and diff checks passed. External LLM requests, live candidate generation, MT5 calls, export, submission, `order_send`, and broker mutation were zero.
- Next critical milestone: verify the existing operator review and human-confirmation lifecycle from an authoritative persisted offline actionable candidate, without enabling execution or creating a parallel acceptance path.

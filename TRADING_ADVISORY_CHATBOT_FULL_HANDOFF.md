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

# 50. OPERATOR REVIEW AND HUMAN CONFIRMATION LIFECYCLE

The authoritative persisted offline MARKET and PENDING candidates now continue through one shared non-executable operator review and confirmation lifecycle.

- `AutonomousDecisionJournal` retains a protected candidate payload inside the existing integrity-checked JSONL record and keeps `records()` redacted. Confirmation reloads by candidate reference and never trusts the editable Streamlit candidate object.
- The existing Review Card now exposes candidate identity, canonical/broker symbols, MARKET or pending price semantics, protection, volume, method summary, reason codes, market reference, timeframe profile, expiry, redacted account binding, integrity status, and the unchanged non-executable state.
- `HumanProposalConfirmationService` now handles explicit `CONFIRM` and `REJECT` actions using the existing `HumanConfirmedProposalIntent`, `ProposalIntentJournalRecord`, policy, validator, and journal store. No second approval schema, repository, or UI flow was added.
- A valid confirmation binds the candidate reference, provenance hash, structured-order hash, all proposal/source references, protected account context, fingerprint hash, canonical/broker symbols, order type, timeframe profile, phrase, nonce, confirmation time, expiry, and disabled permission state.
- Candidate tampering, switched references, wrong account context/fingerprint, stale candidate/account/confirmation, invalid phrase, modified source bindings, and corrupt or partial journals fail closed before a confirmation artifact is persisted.
- Candidate-level journal idempotency permits one authoritative confirm or reject transition. Double-clicks and reruns return the existing record without adding another artifact; Streamlit session state stores only the safe outcome summary.
- Confirmed candidates remain dry-run-only and non-executable. Rejection creates no confirmation binding hash. No execution contract, export artifact, submission, reconciliation mutation, bridge call, runtime `order_send`, or broker mutation is created.
- Verification: 24 focused lifecycle tests and 98 focused Review Card/confirmation tests passed; full regression passed with 3,105 tests and 156 subtests in 175.47 seconds with 3 unchanged dependency warnings.
- External LLM, MT5, live market data, live Streamlit generation, export, submission, controlled-submit, runtime `order_send`, and broker mutation counts were all zero.
- Verification level: `FULL_REGRESSION_PASS`. Next critical milestone: `APPROVAL INTEGRITY + FINAL VALIDATION + PRE-SUBMIT GATE`, as a separate task with execution still disabled by default.

# 51. APPROVAL INTEGRITY, FINAL VALIDATION, AND PRE-SUBMIT LIFECYCLE

The confirmed authoritative MARKET and PENDING candidates now reach one protected, idempotent pre-submit-ready state without broker submission.

- `AutonomousDecisionJournal` persists the protected market snapshot and lifecycle/reconciliation evidence in the existing integrity-checked candidate record while keeping public reads redacted.
- `ProposalIntentJournalRecord` persists confirmation time. Candidate confirmation now uses one exact source-reference contract covering candidate, structured-order, market/context, reasoning, score, risk, lifecycle, reconciliation, account, semantic, and knowledge bindings.
- `ApprovalPreSubmitLifecycleService` reloads candidate, market snapshot, runtime evidence, and confirmation from protected persistence. Editable Streamlit/session candidate data is not accepted as authority.
- Approval integrity independently verifies candidate and confirmation hashes, exact source bindings, account context/fingerprint, symbol/order/timeframes, nonce, confirmation time, and candidate/confirmation expiry.
- Final validation independently rechecks MARKET/PENDING price semantics, stop/target relationships, tick normalization, minimum stop distance, volume limits/step, metadata, terminal capability, lifecycle health, reconciliation state, and the current disabled permission state.
- The existing `MT5PreSubmitGateReport`, `MT5PreSubmitJournalRecord`, and `MT5PreSubmitJournalStore` now represent and persist `PRE_SUBMIT_READY_NON_EXECUTABLE`. The protected intent contains no ticket or deal and keeps live submission, execution, `order_send`, executable, and order-sent flags false.
- Persistent idempotency returns the same record for an exact repeat, blocks conflicting use of the key, and blocks reuse of one confirmation for a different intent. Corrupt or partial journals fail closed.
- The existing Review Card controller can transition by candidate identifier only and stores only a redacted outcome summary. It does not expose controlled submission or broker mutation.
- Valid MARKET and `BUY_LIMIT` PENDING flows pass. Rejection, candidate/confirmation tampering, source-ref injection, candidate switching, wrong account, expiry, permission changes, lifecycle/reconciliation conflicts, unresolved state, capability/metadata/volume/price errors, duplicate conflicts, approval reuse, and corrupt journals block before a new pre-submit record.
- Verification: 24 focused milestone tests and 100 directly affected confirmation/proposal tests passed. Full regression passed with 3,129 tests and 156 subtests in 215.32 seconds with 3 unchanged dependency warnings. Compileall passed.
- External LLM, MT5, live market data, Streamlit generation, export, controlled-submit, runtime `order_send`, and broker mutation counts were zero.
- Verification level: `FULL_REGRESSION_PASS`. Next critical milestone: separately authorized controlled demo submission acceptance using this protected pre-submit artifact; permissions remain disabled until that task explicitly authorizes them.

# 52. PROTECTED MANUAL OPERATOR CANDIDATE ENTRY

The existing candidate lifecycle now accepts one explicitly operator-entered proposal without invoking an external proposal model or creating a parallel candidate path.

- `MANUAL_OPERATOR` is an explicit proposal source, distinct from `AUTONOMOUS_LLM` and `OFFLINE_FIXTURE`, and its deterministic source reference is bound into candidate provenance, confirmation source references, and the protected pre-submit intent.
- The existing authoritative assembler reloads market data, account binding, terminal metadata, deterministic method selection, scoring, risk policy, lifecycle, and reconciliation evidence. The manual branch forces `use_llm=false`; it does not call the autonomous proposal provider.
- The existing order resolver validates MARKET and all supported pending-order semantics, canonical decimal values, tick size, stop distance, protection relationships, and volume metadata before actionable admission.
- Invalid or non-actionable manual proposals are not appended. Equivalent decimal representations resolve to the same source reference, and exact journal duplicates return the existing candidate without a second record.
- The dashboard adds one explicit form with no default symbol, order type, or protected parameter values. Candidate creation remains separate from Review Card confirmation, pre-submit, export, and controlled submission.
- A shared duplicate-journal comparison now canonicalizes protected JSON before comparison so tuple/list serialization does not create a false conflict.
- Verification: 123 focused manual/operator/review/confirmation/pre-submit tests and 229 neighboring candidate/policy/pending tests passed. Full regression passed with 3,142 tests and 156 subtests; three dependency warnings were unchanged.
- External LLM, controlled-submit, runtime `order_send`, retry, fallback, and broker mutation counts were zero. Runtime manual candidate creation and all subsequent operator acceptance stages remain pending explicit human input.
- Verification level: `FULL_REGRESSION_PASS`. Next: restart the app and let the operator enter one exact demo proposal in the Manual Operator Proposal form.

# 53. READ-ONLY COMPLETED-BAR CANDIDATE MONITOR

The existing autonomous candidate pipeline now has an operator-started CLI monitor that evaluates each completed short-term bar at most once.

- The monitor reuses `LiveFeatureService`, `AuthoritativeAutonomousInputAssembler`, `AutonomousDecisionOrchestrator`, and the existing protected decision journal. It does not introduce another candidate schema, proposal provider, execution boundary, or broker endpoint.
- A strict append-only monitor journal claims `canonical symbol + timeframe profile + completed-bar timestamp` before generation. A completed claim is idempotent; an interrupted `STARTED` claim becomes `RESULT_UNKNOWN` and is never retried automatically for that bar.
- Stale or incomplete market inputs and enabled execution/submission/management permissions block before the assembler or proposal provider is called.
- Natural `NO_ACTION`, blocked results, and generated candidate references are persisted as redacted monitor events. Candidate details remain owned by the existing protected autonomous decision journal.
- `scripts/run_autonomous_candidate_monitor.py` supports one explicit `--once` check or an operator-started `--watch` loop. Streamlit only reads monitor state and an existing protected candidate; page refresh does not start the monitor or call the LLM.
- Every monitor record fixes execution authority, export, submission, and `order_send` to false. No confirmation, approval, export, reconciliation mutation, controlled submission, bridge mutation, or broker mutation path was added.
- Verification: 8 focused monitor tests and 206 neighboring candidate/provider/orchestrator/review/manual/policy tests passed with 2 unchanged dependency warnings. Changed-path compileall, CLI help, diff check, and safety scans passed.
- Exactly one production `.order_send(` call-site remains in the host bridge, `src/` has zero MetaTrader5 imports, and the monitor journal path is Git-ignored.
- Verification level: `FOCUSED_PASS`. The watch loop and external proposal provider were not started during implementation verification.

# 54. STANDING MANDATE AND AUTHORITATIVE OPERATING MODE

Production completion Stage 1 adds one protected authority owner without replacing the existing human-confirmation lifecycle.

- `TradingAuthorityStore` is a strict append-only, hash-chained journal for authoritative mode changes, standing-mandate grant/update/revocation, and exact-candidate mandate authorization. Corrupt, partial, conflicting, or missing records fail closed.
- The supported authoritative modes are `advisory_only`, `human_confirmed_live`, and `autonomous_live`. Mode changes require an explicit operator grant, a nonce, a protected demo-account fingerprint, and an auditable record; LLM output and Streamlit session state are not authority.
- A standing mandate binds its version, demo account, canonical/broker symbols, MARKET/PENDING and management families, volume/risk/concurrent-position/trade/daily-loss limits, active window, expiry, nonce, idempotency key, operator grant, and kill-switch state. Revocation is immediate for subsequent validation.
- `MandateCandidateAuthorization` is distinct from `HumanConfirmedProposalIntent`. It binds the exact candidate/proposal/order hashes, source references, protected order parameters, account, evaluated risk/limits, mandate ID/version, nonce, authorization time/expiry, and deterministic idempotency key.
- `ApprovalPreSubmitLifecycleService` reloads the selected authority source from its protected store. Human confirmation is valid only for the human-confirmed path; autonomous candidates require standing-mandate authorization; advisory candidates cannot create approval authority.
- The existing final validation and `PRE_SUBMIT_READY_NON_EXECUTABLE` journal remain authoritative and non-submitting. Real-account inputs, mode/account/candidate/version/scope/limit mismatches, expiry, revocation, corruption, lifecycle/reconciliation conflict, or an engaged autonomous kill switch block before pre-submit.
- Verification: 153 focused and neighboring authority/approval/confirmation/permission tests passed with two unchanged dependency warnings; changed-package compileall passed. External LLM, MT5, controlled-submit, runtime `order_send`, and broker mutation counts were zero.
- Next production dependency: integrate the completed-bar monitor into one bounded coordinator that consumes this authority owner before any pre-submit path.

# 55. BOUNDED AUTONOMOUS COORDINATOR AND COMPLETED-BAR SUPERVISOR

The completed-bar monitor is now a trigger/checkpoint owned by one bounded production coordinator rather than a separate orchestration path.

- `AutonomousCandidateMonitor` owns only fresh completed-bar discovery, execution-permission fail-closed checks, persisted claim/completion records, duplicate prevention, and invocation of one injected handler. It no longer constructs the proposal assembler or decision orchestrator.
- `AutonomousTradingCoordinator` owns authoritative account capture, proposal input assembly, lifecycle/reconciliation admission, candidate orchestration, operating-mode dispatch, exact standing-mandate authorization, and the optional existing approval/pre-submit transition.
- Monitor identity is scoped by protected account fingerprint hash prefix, canonical symbol, and timeframe profile. One incomplete `STARTED` attempt blocks later bars for that account/profile; another account remains isolated.
- Previous monitor journal rows remain integrity-verified. A legacy unresolved `STARTED` row blocks the matching symbol/profile after upgrade instead of permitting an unsafe retry.
- Advisory mode produces a non-executable advisory candidate, human-confirmed mode stops awaiting protected human confirmation, and autonomous mode requires current mandate context. No mode creates submission authority by itself.
- The coordinator validates healthy lifecycle and reconciliation evidence before candidate admission. `RESULT_UNKNOWN`, reconciliation-required, submission-started, discrepancy, account mismatch, missing mandate context, or authority corruption fail closed.
- The operator CLI constructs this coordinator and closes its bridge client on normal exit or interruption. Streamlit continues to read persisted status only; reruns do not start work.
- Verification: 29 coordinator/monitor/mandate tests and 307 focused/neighboring pipeline tests passed with two unchanged dependency warnings. Changed-path compileall passed. External LLM, MT5, controlled-submit, runtime `order_send`, and broker mutation counts were zero.
- Next production dependency: connect the existing controlled execution, result, reconciliation, lifecycle, and management services through this coordinator with deterministic fake boundaries.

# 56. MANDATE-CONTROLLED EXECUTION INTEGRATION

The bounded coordinator now reaches the existing controlled-submit boundary without converting standing-mandate authority into human confirmation.

- `MT5ControlledExecutionRequest` supports a distinct `controlled-mt5-autonomous-execution/v1` protected request built only from the exact candidate, mandate authorization, final validation and pre-submit report.
- Human requests retain the previous schema and exact confirmation phrase. Mandate requests require no human phrase and cannot deserialize as human authority.
- The app adapter rechecks the current account fingerprint and requires host-reported `account_environment=DEMO` before sending a mandate request. Autonomous execution remains disabled by default.
- The host bridge reloads `TradingAuthorityStore` from the shared protected journal and independently validates the current authoritative mode, mandate integrity/version/revocation/window/kill switch, exact authorization, account hash, candidate/proposal/order bindings, protected parameters, expiry and idempotency.
- Non-demo or unknown account environments fail closed before reservation. The bridge also has an independent default-false `MT5_BRIDGE_AUTONOMOUS_EXECUTION_ENABLED` gate.
- MARKET requests without a fixed entry price use the current host-side bid/ask at mapping time; protected side, volume and protection values remain exact-authority bound. PENDING requests retain existing terminal capability and family gates.
- The existing coordinator optionally invokes the existing adapter after a second immediate mandate revalidation. Accepted, rejected and unknown outcomes use the existing result states; unknown results are not retried and block later coordinator cycles through existing lifecycle/reconciliation admission.
- Deterministic verification covered accepted, rejected, unknown, duplicate, revoked mandate, real/unknown account environment and existing human/pending paths. The focused execution/reconciliation/lifecycle/management set passed 157 tests with two unchanged dependency warnings.
- Real LLM, MT5, HTTP controlled-submit, runtime `order_send` and broker-mutation counts were zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` still has zero MetaTrader5 imports.
- Next production dependency: Streamlit authority/supervisor controls, redacted observability, and restart/readiness closure. Operational broker acceptance remains separate.

# 57. AUTONOMOUS TRADING SOFTWARE IMPLEMENTATION CLOSURE

Production completion Stage 4 closes the bounded runtime without enabling external execution.

- The existing completed-bar CLI now constructs the authoritative mode/mandate service, approval/pre-submit lifecycle, policy gate, coordinator, and disabled live adapter in one production path. The monitor remains only a persisted trigger/checkpoint.
- The coordinator requires a persisted valid autonomous-policy decision before standing-mandate authorization. Default-disabled policy, execution, submission, management, or kill-switch state therefore blocks before the controlled boundary.
- Read-only lifecycle snapshots now include active-position, daily-trade, and daily-loss evidence plus terminal/account trade capability. Missing or malformed aggregate evidence fails closed before mandate-limit evaluation.
- Mandate risk is calculated from the protected candidate and broker tick metadata. The current mode, mandate, account, limits, capability, lifecycle, reconciliation, authorization, final validation, and pre-submit artifact are reloaded at their existing protected boundaries.
- One Streamlit expander delegates mode changes, bounded mandate grant/revocation, supervisor start/stop, and redacted status to service/process controllers. It exposes lifecycle, policy, management-permission, pre-submit, execution, reconciliation, expiry/revocation, and unknown-result state without direct broker logic.
- Controlled position management continues through the existing human-confirmed controlled-management boundary; autonomous management eligibility remains independently default-disabled. No autonomous management mutation shortcut was added.
- Authority, mode, mandate, monitor checkpoint, candidate, authorization, pre-submit, execution, reconciliation, and lifecycle persistence retain their existing strict reload and fail-closed corruption behavior.
- Verification: 243 focused/neighboring authority, policy, monitor, coordinator, execution, lifecycle, reconciliation, management, and UI tests passed. Full regression passed with 3,186 tests and 156 subtests in 160.55 seconds with three unchanged dependency warnings. Compileall and diff checks passed.
- Static safety: exactly one production `.order_send(` call-site remains in the host bridge; `src/` has zero MetaTrader5 imports. Real LLM, MT5, controlled-submit HTTP, runtime `order_send`, and broker-mutation counts were zero.
- Classification: `AUTONOMOUS_TRADING_SOFTWARE_IMPLEMENTATION_COMPLETE`. Operational broker evidence remains `OPERATIONAL_ACCEPTANCE_PENDING` and requires a separately authorized demo-account procedure.

# 58. SOFTWARE RELEASE RECORD

- Software implementation commit: `e8f516d`.
- Release tag: `v1.0.0-software-complete` on the release-documentation commit that preserves `e8f516d` unchanged.
- Implementation classification: `AUTONOMOUS_TRADING_SOFTWARE_IMPLEMENTATION_COMPLETE`.
- Operational acceptance: `OPERATIONAL_ACCEPTANCE_PENDING`.
- Completed lifecycle: authoritative proposal/candidate, review, human-or-mandate authority, approval integrity, final validation, pre-submit, controlled execution, result handling, reconciliation, lifecycle, controlled management, completed-bar supervision, recovery, and redacted Streamlit observability.
- Verification evidence: full regression `3,186 passed`; `156 subtests passed`; Ponytail `PONYTAIL_REVIEW_PASS`; compileall, documentation integrity, static safety, and Git diff checks passed.
- Real implementation-verification operations: external LLM `0`, MT5 runtime `0`, controlled-submit HTTP `0`, runtime `order_send` `0`, broker mutations `0`.
- Static invariant: exactly one production `.order_send(` call-site, isolated in the host bridge; zero MetaTrader5 imports under `src/`.
- Security: credentials, raw account identifiers, protected hashes/payloads, and exact ticket/deal/position identifiers are excluded from public documentation, UI status, and general logs. Protected journals retain only the minimum internal evidence required for integrity, idempotency, and reconciliation.
- Release state: clean working tree after the release commit; no critical production blocker; branch and tag remain local until explicitly pushed.

# 59. AUTHORITATIVE DASHBOARD RUNTIME STATE

Post-release maintenance aligns the existing Streamlit Dashboard with current backend authority and market-profile state.

- The Dashboard reloads `TradingAuthorityOperatorService.status(refresh_runtime=True)` and visibly reports redacted DEMO account match, authoritative mode, bridge/lifecycle health, reconciliation discrepancies, unresolved execution states, execution/submission/management permissions, and both kill switches.
- The symbol selector now owns one explicit display intent. `BTCUSD` resolves through the existing mapping to `BTCUSDm` and activates `M1,H1,H4`; `XAUUSD` retains the configured default profile. Streamlit session state does not define either backend mapping or authority.
- Market features, completed-bar timestamps, freshness, symbol capability, price label, calendar, and regime are reloaded for the selected symbol. A symbol/profile mismatch is displayed as a blocker and never falls back silently.
- Browser verification showed `DEMO`, `human_confirmed_live`, `HEALTHY`, account match true, discrepancies 0, unresolved 0, disabled execution/submission/management permissions, and engaged kill switches. BTCUSD displayed `BTCUSDm`, `M1/H1/H4`, complete freshness and complete symbol capability with no stale XAUUSD metrics.
- Verification: 70 focused Dashboard/runtime/multi-symbol/operator tests passed. Full regression passed with 3,192 tests and 156 subtests; three dependency warnings were unchanged. Compileall, diff, and safety checks passed.
- Candidate generation, external LLM, confirmation, pre-submit creation, controlled-submit, runtime `order_send`, management mutation, broker mutation, and real-account action counts were zero.

# 60. STREAMLIT MODE AUTHORIZATION DEMO

Post-release maintenance completes the existing Dashboard mode-specific authorization presentation without adding another workflow.

- The Dashboard renders authority controls from the persisted backend mode: advisory mode has no confirmation or mandate controls, human-confirmed mode exposes per-candidate review authority, and autonomous mode exposes Standing Trading Mandate grant/revocation controls without per-trade confirmation.
- Candidate assembly receives the authoritative mode returned by the runtime authority service. Streamlit session state does not grant or replace operating authority.
- The authoritative mode form remains explicitly operator-authorized and now permits the initial selection to reach its backend validator instead of being permanently disabled before Streamlit can rerun.
- Browser verification persisted `advisory_only`, `human_confirmed_live`, and `autonomous_live` sequentially. No mandate was granted or revoked and no candidate was confirmed or rejected.
- The single authorized human-mode generation attempt ended naturally with `METHOD_BAD_REGIME`; no candidate, confirmation, export, pre-submit artifact, controlled submission, or broker mutation was created.
- Full regression passed with 3,194 tests and 156 subtests; three dependency warnings were unchanged. Focused mode/Dashboard/authority tests passed with 48 tests. Compileall, diff, and static safety checks passed.
- The software-complete release tag remains unchanged. Operational broker acceptance remains separate and requires explicit human authorization.

# 61. CONVERSATIONAL TRADING AUTHORIZATION

The existing chat surface now carries a typed, non-executable trading-authorization request into the existing protected authority and candidate-review workflow.

- A deterministic parser normalizes advisory-only, human-confirmed, and autonomous requests without adding an intent-classification LLM call. Conflicting automatic/per-trade-confirmation wording resolves to the safer human-confirmed mode.
- The typed public request binds the conversation request, configured canonical/broker symbol mapping, active timeframe profile, confirmation policy, demo-account scope, mandate requirement, allowed next action, blockers, and an explicitly non-executable state.
- Streamlit reloads the typed request from persisted chat history and reuses the existing authority service, candidate generator, Review Card, confirmation controls, and Standing Trading Mandate controls. Chat text and session state remain non-authoritative.
- Shared Dashboard/chat widgets use caller-scoped keys, so both surfaces can render in one Streamlit run without duplicate widget actions. Refresh reuses the persisted request and does not call the provider or generate a candidate.
- Browser acceptance sent one BTCUSD demo human-confirmed request. The conversation displayed `human_confirmed_live`, `CONFIRM_EVERY_TRADE`, `BTCUSD -> BTCUSDm`, `M1,H1,H4`, healthy DEMO/account/lifecycle evidence, disabled permissions, engaged kill switches, and the existing `Grant MT5 Demo Access` action.
- Acceptance stopped at the required human Grant boundary. Candidate generation, confirmation, mandate creation, export, pre-submit creation, controlled-submit, runtime `order_send`, management mutation, and broker mutation were zero.
- Verification: 83 focused/neighboring tests passed. Full regression passed with 3,205 tests and 156 subtests in 172.16 seconds; three dependency warnings were unchanged. Compile and diff checks passed.
- Verification level: `FULL_REGRESSION_PASS`. Next: the operator may explicitly grant the requested demo-account mode; only then may one candidate-generation action occur.

# 62. CONVERSATIONAL MT5 ACCESS GRANT IDEMPOTENCY

Post-release maintenance verifies the real human Grant boundary and makes repeated delivery of the same typed request idempotent.

- One real operator click reached the existing controller and protected authority service. The journal added exactly one valid record and the authoritative mode changed from `autonomous_live` to `human_confirmed_live` for the matching DEMO account fingerprint.
- A fresh store/service reload rendered `human_confirmed_live`; a successful Grant now triggers a native Streamlit rerun so the UI immediately reloads backend authority instead of retaining the pre-submit display value. Session state is not treated as authority.
- The stable conversational request ID is now passed to the existing mode service as its nonce/idempotency key. Repeating the same grant returns the existing record; reusing the key with different mode or account semantics fails closed.
- Ordinary non-conversational mode changes retain the existing generated nonce behavior. No new authority path, schema, journal, or execution boundary was added.
- Grant and verification caused zero LLM calls, candidate generations, controlled submissions, runtime `order_send` calls, or broker mutations. Execution permissions remained disabled and both kill switches remained engaged.
- Verification: 39 focused authority/Dashboard/conversation tests passed; full regression passed with 3,206 tests and 156 subtests; three dependency warnings were unchanged. Compileall, diff, and static safety checks passed.

# 63. REASONING EVIDENCE V2

Reasoning Engine v2 extends the existing conversational and candidate pipeline; it does not create a second strategy, market-data, scoring, candidate, or execution path.

- The existing indicator snapshot contained 17 calculated outputs: EMA fast/slow, SMA fast/slow, RSI, MACD line/signal/histogram, ATR, rolling volatility, latest close/range/body, swing high/low, and support/resistance zones. EMA, RSI, MACD, ATR, volatility, close and swing evidence drove features; support/resistance reached proposal context; SMA and latest range/body were calculated but did not materially affect the old decision score.
- `METHOD_BAD_REGIME` originated in regime/method compatibility scoring. `SCORING_BLOCKERS_PRESENT` originated in the deterministic decision policy whenever the score report retained blockers. V2 preserves these compatibility summaries and adds granular typed evidence beneath them.
- A typed conversational strategy now normalizes configurable EMA, SMA, RSI, ATR, MACD and Bollinger Bands specifications plus bounded comparison/crossover/trend rules. Unsupported indicators, parameters, timeframes, aliases and rule operands fail closed. Stable strategy ID/version/hash values bind reasoning, proposal provenance and candidate review.
- A per-timeframe planner derives completed-bar requirements from indicator warm-up, rule lookback, percentile baseline and a bounded safety margin. The existing MT5 provider remains authoritative and continues excluding the forming candle; live requests fetch only planned counts.
- Deterministic V2 evidence adds normalized slope, trend efficiency, ATR percentile, volatility ratio, swing structure, ATR-normalized structure distance, multi-timeframe alignment and ATR-normalized spread. It produces versioned regime, eight-dimension score, hard blockers and granular actual/threshold evidence.
- The existing method-selection and structured-proposal calls remain capped at one each. They receive compact evidence rather than raw candle history; LLM output still cannot calculate authority, bypass blockers, confirm, export or execute.
- Streamlit renders normalized strategy identity, indicators, rules, history availability, V2 regime, score breakdown and granular reasons in the existing authorization and non-executable Review Card surfaces.
- Frozen replay evaluation covers up/down trends, range, compression, expansion, breakout cases, timeframe conflict, wide spread, stale data, insufficient history and invalid strategy input. No backtesting platform or additional broker path was introduced.
- All execution, submission, management and autonomous permission defaults remain unchanged and blocked. Broker mutation remains outside this reasoning boundary.
- Verification: 267 focused and neighboring tests passed. The first full run exposed three backward-compatibility failures in the legacy three-argument feature-service call; the shared assembler fix restored that contract, and the final full regression passed with 3,224 tests and 156 subtests. Compileall, replay, diff and static safety checks passed.
- Browser-visible localhost acceptance was blocked by the browser automation URL policy before any interaction. Streamlit health returned HTTP 200 and the MT5 bridge health endpoint returned HTTP 200; no candidate generation, provider call, confirmation, authority change or broker operation was attempted.

# 64. CURRENT MARKET INDICATOR ROUTING

- Current indicator-value questions now take market-state precedence over generic indicator/book preference. Conceptual questions remain book-first, while mixed questions retain current-market evidence.
- Symbol extraction resolves canonical and broker aliases through the configured market symbol mapping. Unknown aliases remain explicit blockers and never fall back to XAUUSD.
- Requested indicator specifications and timeframe flow through the typed query plan into completed OHLCV acquisition and the existing deterministic indicator registry. Stale data and insufficient history fail closed.
- DecisionContext marks current indicator requests as market-required and book-optional. Evidence sufficiency requires market snapshot, OHLCV and technical snapshot before normal synthesis.
- Browser acceptance issued one BTCUSDm H1 request and displayed EMA(20), RSI(14), the completed-bar timestamp and authoritative technical evidence. No candidate or execution path was invoked.
- Verification: 65 focused compatibility tests passed; after the single full run exposed one fixed-date stale fixture, the corrected affected set passed 25 tests and 9 subtests. The full run itself recorded 3,237 passed and 156 subtests, so full-regression PASS is not claimed for this maintenance checkpoint.
- Candidate generation, confirmation, mandate changes, pre-submit, controlled-submit, runtime `order_send`, broker mutation and real-account actions remained zero.

# 65. CONVERSATIONAL INTENT AND STRATEGY ROUTING

- One typed, non-executable conversational context now carries normalized intent families, configured canonical/broker symbol binding, timeframe, indicator specifications, operating mode, confirmation policy, response format and granular blockers across parsing, QueryPlan, DecisionContext and Streamlit persistence.
- Resolution is field-specific: the newest valid explicit value overrides prior normalized context; prior valid context is inherited when omitted; unresolved symbols and unsupported timeframes block without XAUUSD or timeframe fallback.
- Current-market, concept, strategy, authorization, advisory, autonomous and mixed requests select centralized response formats. Strategy requests bypass book-first retrieval unless concept intent is also explicit.
- The existing bounded rule parser now accepts local timeframe tokens with or without `on/at/khung`, preserving multi-indicator and multi-timeframe comparison/crossover bindings.
- Incomplete strategies return `STRATEGY_COMPLETION_REQUIRED_CARD`, remain `NON_EXECUTABLE`, and list missing direction, action, risk, stop, exit, sizing, account or confirmation semantics without candidate generation.
- Browser acceptance completed the two-turn BTCUSDm scenario: H1 EMA(20)/RSI(14) market evidence followed by inherited `BTCUSD/BTCUSDm`, explicit M1, `RSI(14) GREATER_THAN 10`, human-confirmed policy and granular completion blockers. Browser refresh automation was blocked by URL policy; persisted reload behavior passed focused tests.
- Focused contract/routing/reasoning/evidence verification passed 92 tests. The first full run exposed two legacy fake-assembler compatibility failures; the shared call-site fix passed the affected 29-test set. Final full regression passed with 3,256 tests and 156 subtests; two dependency warnings were unchanged.
- Candidate generation, dedicated routing LLM calls, confirmation, mandate changes, pre-submit, controlled-submit, runtime `order_send`, broker mutation and real-account actions remained zero.

# 66. FIELD-AWARE EDITABLE TRADE DRAFTS

- Conversational normalization now distinguishes open BUY/SELL instructions, generic trade intent, exit/management language, questions, hypotheticals, and negation across bounded Vietnamese, English, and mixed-language aliases. Questions and negated instructions do not create a trade draft.
- One protected, immutable `EditableTradeDraft` owns field status, source, evidence, blockers, revisions, and deterministic calculations. Explicit and edited values take precedence over inherited context, policy methods, and approved DEMO defaults; missing symbols fail with `SYMBOL_REQUIRED` and never fall back to XAUUSD.
- The existing strategy, market snapshot, symbol metadata, account evidence, and policy contracts supply authoritative inputs. ATR/structure stops, reward-risk/structure targets, risk distance, broker-normalized volume, and actual risk are calculated in backend code; no LLM calculates final trade parameters.
- Typed patches use optimistic revision checks and recalculate only dependent fields. Risk edits change sizing/risk values, RR edits change the target, direct volume edits change actual risk, and direction edits invalidate/recompute direction-dependent market values while preserving independent fields.
- Streamlit renders one editable `NON_EXECUTABLE` Trade Draft Card with redacted provenance, evidence time, precise blockers, and compact supported controls. Draft changes remain separate from candidate creation, confirmation, approval, pre-submit authority, and execution.
- Browser acceptance covered inherited symbol plus timeframe override, only-stop-missing completion, risk and RR revisions, missing-symbol fail-closed behavior, concept questions, and negated trade language. The exact-source Streamlit process later exited natively with code 139 during unrelated RAG/evaluation work; focused persistence and safety tests cover refresh behavior, and no execution boundary was reached.
- Verification: 107 focused/neighboring tests passed. Full regression passed with 3,285 tests and 156 subtests in 165.48 seconds; two unchanged dependency warnings remained. Compileall, diff, documentation, and static safety checks passed.
- Candidate creation, confirmation, mandate mutation, pre-submit, controlled-submit, runtime `order_send`, broker mutation, management mutation, and real-account actions remained zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero MetaTrader5 imports.

# 67. STRUCTURED SEMANTIC INTERPRETATION BOUNDARY

The application now has one strict, non-authoritative structured semantic boundary for raw meaningful language; it does not yet replace the existing deterministic conversational context or `QueryPlan` path.

- `StructuredSemanticResult` accepts one exact JSON-object schema with a small compositional intent taxonomy, action/direction, generic indicator facts, conditions, references, modes, explicit fields, unresolved fields, negation, and hypothetical state. Unknown fields and every execution-authority field fail closed.
- Structural failures are rejected, while semantic incompleteness is retained. For example, an RSI request without a period can preserve the indicator, timeframe, comparator, and threshold while marking only `indicators[0].parameters.period` unresolved.
- `StructuredSemanticInterpreter` makes one `structured_json=True` call through the existing configured reasoning provider, validates the returned JSON exactly once, does not retry, repair, fan out, or use a fallback provider, and emits only redacted boundary diagnostics.
- The boundary has no broker, freshness, pricing, permission, confirmation, candidate, `QueryPlan`, capability-planning, execution, or MT5 authority. Existing deterministic conversational parsing, retrieval rewrite, context resolution, `QueryPlan`, and capability planners remain unchanged for compatibility.
- The behavior-family harness covers Vietnamese, English and mixed phrasing, word order, missing children, conversational references, negation, hypothetical language, concept/current-data distinction, mixed intent, malformed/authority-bearing output, disabled provider, and provider failure.
- Verification: 21 new boundary tests plus 111 neighboring semantic/query-plan/proposal/runtime tests passed (132 total, 17 subtests). Full regression passed with 3,314 tests and 156 subtests in 128.25 seconds; three pre-existing dependency/UTC warnings remained. Docker Compose configuration passed; app restart and Streamlit health were not verified because the local Docker daemon pipe was unavailable.
- External LLM, MT5, live market data, candidate generation, confirmation, export, pre-submit, controlled-submit, runtime `order_send`, and broker mutation counts were zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` still has zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: deterministic context resolution plus `QueryPlan` semantic-authority cutover, with execution behavior unchanged.

# 68. DETERMINISTIC SEMANTIC RESOLUTION AND QUERYPLAN AUTHORITY

Validated structured semantics can now enter the existing `QueryPlan` without being reinterpreted by legacy raw-language routing.

- `ResolvedSemanticState` is the small deterministic boundary between immutable `StructuredSemanticResult` and `QueryPlan`. It resolves only configured symbol aliases and explicit `previous_symbol`, `previous_indicator`, and `previous_timeframe` references; it records explicit, inherited, policy-default, and unresolved provenance states without inventing missing facts.
- Current structured values override valid prior state. Prior symbol/indicator values are inherited only when the structured result explicitly names the applicable reference. Missing or mismatched references remain unresolved. Partial indicators preserve their identity, timeframe, condition, and missing child path; they do not become a fabricated complete indicator or an execution permission.
- `QueryPlanAssembler.assemble(..., structured_semantics=...)` now returns through a structured path before its legacy router, answer-mode classifier, decomposer, regex symbol extraction, and indicator parser. The resolved projection owns planning fields, ambiguity, constraints, and semantic provenance; legacy raw assembly is unchanged when no structured artifact is supplied.
- Fully specified registry-supported indicators are projected into existing `IndicatorSpec` values and flow into the existing `ContextRequirementPlanner`. Incomplete or unsupported indicator values remain in semantic context and ambiguity rather than receiving policy defaults.
- No universal orchestrator, retrieval, UI, conversational-lifecycle, draft, candidate, approval, execution, bridge, or MT5 cutover occurred. The structured path is an additive, deterministic compatibility route for the next migration step.
- Verification: 11 new semantic-resolution/QueryPlan tests plus 72 neighboring semantic, QueryPlan, context, capability, and interpreter tests passed (83 total, two dependency warnings). Full regression passed with 3,325 tests and 156 subtests in 144.98 seconds; three unchanged dependency/UTC warnings remained. Compileall, documentation integrity, diff, and Docker Compose configuration passed. Docker app restart succeeded and Streamlit health returned HTTP 200.
- External LLM, MT5, live market data, candidate generation, confirmation, export, pre-submit, controlled-submit, runtime `order_send`, and broker mutation counts were zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero `MetaTrader5` imports. Execution controls remain unchanged.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: universal routing into the structured semantic boundary and existing capability stack, retaining the legacy path as an explicit compatibility fallback until migrated.

# 69. UNIVERSAL STRUCTURED SEMANTIC ROUTING

- Normal RAG ingress now attempts the existing `StructuredSemanticInterpreter` once before the legacy router. A valid result drives one resolved `QueryPlan`, then the existing `ContextRequirementPlanner`, `ContextExecutionPlanner`, capability registry, and context-acquisition executor. Invalid or unavailable structured semantics retain the bounded legacy router/query-rewrite/QueryPlan fallback.
- The semantic route maps `SOCIAL`, `SYSTEM`, and `OUT_OF_SCOPE` to the existing cheap early exits without calling the legacy classifier. All other valid structured intents stay non-executable and continue through the existing context stack.
- Retrieval rewrite is now downstream of requirements: it runs only when an `official_report`, `static_knowledge`, or `market_knowledge` capability is required. It remains a retrieval string and never rebuilds or changes the authoritative `QueryPlan`.
- Structured `CPI` and the existing macro-event catalog now project deterministically into the existing macro report/impact plan families. A current macro request with supported indicators reuses the existing market, OHLCV, and technical-snapshot requirements with one parameter set; no capability type or keyword router was added.
- `DecisionContextBuilder` now consumes a supplied authoritative `QueryPlan` without calling its raw router, answer-mode classifier, or decomposer. Legacy fallback behavior remains unchanged when a structured semantic result is absent.
- Verification: 104 focused semantic/query-plan/context/capability/runtime-neighbor tests passed with two unchanged dependency warnings. Full regression passed with 3,335 tests and 156 subtests in 154.39 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose config, Docker app restart, Streamlit health `200 ok`, diff, documentation integrity, and static safety checks passed.
- External LLM, MT5, live market data, candidate generation, confirmation, export, pre-submit, controlled-submit, runtime `order_send`, and broker mutation counts were zero. Exactly one production `.order_send(` call-site remains in the host bridge, `src/` retains zero `MetaTrader5` imports, and semantic/planning constraints retain `execution_allowed=false`.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: Trading Semantic Cutover for the existing trading-language path; thin UI migration and Draft/Candidate lifecycle integration remain later work.

# 70. TRADING SEMANTIC CUTOVER

Valid trading semantics now use the same authoritative path as the rest of the application:

`StructuredSemanticResult -> ResolvedSemanticState -> QueryPlan -> deterministic trading projection -> existing ConversationalTradingRequest / ConversationalStrategyRequest -> existing validation and evidence`.

- `QueryPlan.semantic_context` is the semantic authority. `ConversationalTradingRequest` and `ConversationalStrategyRequest` are non-executable downstream projections and do not reinterpret raw language.
- The Streamlit chat path calls the orchestrator first. When it receives an authoritative semantic QueryPlan, it uses the returned typed projection and persists only the resolved semantic state for the next turn. It invokes the old raw conversational parser only when no valid semantic plan exists.
- The existing legacy parser remains a bounded compatibility fallback. Valid semantic plans bypass `normalize_trade_instruction`, `parse_conversational_strategy`, and `parse_indicator_specs` in the trading projection path.
- Missing semantic children remain explicit: an RSI condition without a period retains RSI, timeframe, comparator, and threshold; it carries a semantic unresolved marker and cannot proceed into evidence as a complete strategy. No default period or execution authority is invented.
- Structured semantics now carry `account_scope` as non-authoritative meaning. Deterministic downstream mode policy still requires DEMO for non-advisory requests and keeps every request non-executable.
- Existing `CLOSE_POSITION` and `MANAGE_POSITION` semantic actions can be represented as non-executable typed lifecycle meaning. Confirm, reject, and status semantics remain unsupported by the current semantic schema and no lifecycle behavior changed.
- Verification: 16 new cutover tests plus 98 neighboring semantic, QueryPlan, conversational, authorization, and reasoning-evidence tests passed (114 total, two dependency warnings). Full regression passed with 3,351 tests and 156 subtests in 134.20 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose config, Docker app restart, Streamlit health `200 ok`, diff, and static safety checks passed.
- No external LLM, MT5, live market data, candidate generation, confirmation, pre-submit, controlled-submit, runtime `order_send`, or broker mutation operation ran. `src/` has zero `MetaTrader5` imports and exactly one production `.order_send(` call-site remains in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Thin UI cleanup, authoritative Draft blocker presentation, and Draft-to-Candidate lifecycle integration remain later work; confirmation, pre-submit, execution, bridge, and permission behavior are unchanged.

# 71. THIN UI AND AUTHORITATIVE DRAFT PRESENTATION

- `tab_chatbot` now has one explicit result-selection boundary: a valid orchestrator `QueryPlan` and typed trading payload are consumed directly, while the legacy conversational resolver/parser is reached only when no authoritative semantic plan exists.
- Open and generic trading requests route straight to the existing `EditableTradeDraft` presentation. The newest persisted Draft revision owns the displayed draft values, revision, warnings, and draft blockers; request-time blockers do not render as current Draft truth.
- Semantic incompleteness remains separate from Draft state. Typed `semantic_unresolved_fields` are displayed as unresolved input facts, so a missing child parameter does not become a missing indicator or a fabricated Draft blocker.
- The UI remains presentation-only: it invokes existing services but does not calculate fields, infer mode, grant permissions, create candidates, confirm, export, submit, or call the bridge write path. Existing Draft calculation, patch/revision, journal integrity, candidate review, confirmation, pre-submit, and execution boundaries remain unchanged.
- Verification: 105 focused UI/Draft/semantic/query-plan/candidate-review neighbors passed with two unchanged dependency warnings. Full regression passed with 3,359 tests and 156 subtests in 140.17 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose config, app restart, Streamlit health, documentation integrity, diff, and static safety checks passed.
- No external LLM, retrieval provider, MT5, market-data, candidate, confirmation, pre-submit, controlled-submit, runtime `order_send`, or broker-mutation operation ran. `src/` retains zero `MetaTrader5` imports; exactly one production `.order_send(` call-site remains in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Draft-to-Candidate DEMO lifecycle wiring is the next separate approved scope.

# 72. EXPLICIT DRAFT-TO-CANDIDATE DEMO LIFECYCLE

An operator can now explicitly create one existing non-executable candidate from the current authoritative Editable Trade Draft revision.

- The lifecycle is `latest protected Draft revision -> explicit Create Candidate action -> existing candidate assembler/orchestrator -> existing candidate journal -> existing read-only Review Card`. It does not enter confirmation, approval, final validation, pre-submit, controlled submission, reconciliation mutation, or broker execution.
- `EditableTradeDraftCandidateService` reloads the Draft from the existing strict Draft store, rejects a missing or stale requested revision before assembly, and checks Draft validity, freshness, DEMO/account binding, authoritative operating mode, and exact strategy identity before using the existing manual-operator assembler path.
- The candidate carries an opaque `EDITABLE_TRADE_DRAFT` provenance reference derived from the complete protected Draft and its revision. This binds all protected Draft values without exposing them in the candidate public projection or Review Card.
- Repeating an explicit action for the same valid Draft revision reuses the existing candidate journal idempotency result. Applying an existing Draft patch creates revision `N+1`, clears the visible current candidate result, and requires a fresh explicit action; the historic candidate for revision `N` remains in the existing candidate journal.
- The UI only passes the Draft ID and revision to the backend service. It reloads authoritative account/mode state, stores only the existing orchestrator result in the current session, and displays the existing non-executable Review Card only when its Draft provenance matches the current revision.
- Verification: 162 focused/neighboring Draft, candidate, review, approval/pre-submit, and thin-UI tests passed. Full regression passed with 3,369 tests and 156 subtests in 139.86 seconds; three unchanged dependency/UTC warnings remained. Compileall and diff checks passed.
- No browser/runtime candidate action, external LLM, MT5 market-data request, confirmation, pre-submit artifact, controlled-submit call, runtime `order_send` call, or broker mutation ran for this sprint. Static source checks retain exactly one production `.order_send(` call-site in the host bridge and zero `MetaTrader5` imports under `src/`.
- Docker Compose configuration passed; the existing `app` service restarted without rebuild, became healthy, and Streamlit health returned `200 ok`. Documentation integrity passed with 11 tests. Final Ponytail review found no unnecessary abstraction or safety regression.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: Explicit Candidate Review + Confirmation Lifecycle Integration.

# 73. EXPLICIT CANDIDATE REVIEW AND CONFIRMATION LIFECYCLE

The existing review controls and protected confirmation journal now form the explicit, non-executing decision boundary for a revision-bound Candidate.

- The lifecycle is `Draft N -> Candidate C(N) -> Review Card -> explicit Confirm or Reject -> persisted review decision`. It stops before approval, final validation, pre-submit, controlled submission, reconciliation mutation, and broker execution.
- The Review Card passes the exact `candidate_reference` to the existing `HumanProposalConfirmationService`; the service reloads and validates the protected Candidate, expected reference, freshness, provenance/source bindings, structured-order hash, and matching protected DEMO account context before persisting a decision.
- Existing `ProposalIntentJournalStore` idempotency owns terminal review decisions. Repeated confirm or reject returns the existing persisted result, and a conflicting terminal action cannot silently replace the first decision.
- The UI reloads the persisted decision for the exact visible Candidate after an action. A prior session-only outcome is not rendered for a later Candidate. Rendering a Draft, creating a Candidate, and rendering the Review Card remain non-mutating.
- A historical Candidate C(N) can retain its original protected Draft-revision provenance after Draft N+1 exists; confirmation of C(N) remains bound to C(N) and never becomes confirmation of N+1. No new candidate is created as a side effect of review.
- Confirmed and rejected proposal intents remain `dry_run_only` and non-executable. The existing pre-submit lifecycle is still a separately invoked later service; this review path does not call it.
- Verification: 104 focused/neighboring lifecycle, Draft, review, idempotency, UI, and pre-submit-safety tests passed. Full regression passed with 3,373 tests and 156 subtests in 145.92 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose configuration, app restart/health, Streamlit health `200 ok`, and diff checks passed.
- No browser/runtime review action, external LLM, MT5 market-data request, pre-submit artifact, controlled-submit, runtime `order_send`, or broker mutation ran. Static source checks retain zero `MetaTrader5` imports under `src/` and exactly one production `.order_send(` call-site in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: Confirmed Candidate -> Deterministic Pre-Submit Readiness Integration.

# 74. CONFIRMED CANDIDATE PRE-SUBMIT READINESS

- The lifecycle now continues explicitly from `Draft N -> Candidate C(N) -> Confirm -> candidate-bound confirmation -> Validate Pre-Submit -> PRE_SUBMIT_READY_NON_EXECUTABLE or BLOCKED`. It stops before controlled submission, reconciliation mutation, and broker execution.
- The existing `ApprovalPreSubmitLifecycleService` remains the sole readiness authority. It reloads the exact Candidate, confirmation, protected market snapshot, and runtime evidence; approval integrity, final validation, freshness, account fingerprint, terminal capability, lifecycle/reconciliation compatibility, and disabled permissions remain independently validated there.
- The Review Card shows `Validate Pre-Submit (Non-Executable)` only after the exact Candidate has a persisted confirmed decision. Confirmation does not invoke readiness automatically. Reloaded readiness display is sourced from the existing strict pre-submit journal by exact Candidate reference, not from Streamlit session state.
- `TradingAuthorityOperatorService` supplies only current read-only DEMO account and lifecycle capability evidence. The existing pre-submit journal keeps its idempotent one-record behavior for identical immutable inputs. Existing mandate capability construction reuses the same terminal-capability helper.
- A ready artifact remains non-executable: submission, execution, `order_send`, broker result, ticket, and deal fields are blocked or absent. The bridge protocol and controlled-submit boundary are unchanged.
- Verification: 131 focused lifecycle/review/Draft/final-validation/pre-submit/disabled-adapter tests passed. Final full regression passed with 3,378 tests and 156 subtests in 138.09 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose configuration, app restart, Streamlit health `200 ok`, diff, and static safety checks passed.
- No external LLM, raw-language parser, broker mutation, controlled-submit, runtime `order_send`, or MT5 write operation ran. `src/` retains zero `MetaTrader5` imports and exactly one production `.order_send(` call-site remains in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: Lifecycle Closure + Legacy Semantic Fallback Cleanup + Release Validation.

# 75. PYDANTIC V2 STRUCTURED SEMANTIC BOUNDARY ALIGNMENT

- The untrusted structured provider boundary now uses strict Pydantic v2 DTOs before explicitly converting to the existing frozen `StructuredSemanticResult`, `SemanticIndicator`, and `SemanticCondition` dataclasses. Resolved semantics, QueryPlan, context/capability planners, trading projection, Draft, Candidate, review, confirmation, pre-submit, bridge, and execution contracts remain unchanged.
- The boundary remains fail-closed for unexpected or authority-bearing fields, malformed JSON, invalid schema/enums, wrong shapes, numeric strings, bool-as-number, and non-finite numbers. JSON integer and float values remain valid where the prior contract accepted them; incomplete semantic children remain explicit unresolved facts without defaulted values.
- Pydantic is declared explicitly with a v2-only requirement and is confined to `src/services/semantic/structured_semantics.py`. The one-call `StructuredSemanticInterpreter -> ProjectLLMReasoningProvider` JSON-mode flow, no-retry behavior, and raw-output redaction behavior remain unchanged.
- Verification: focused semantic/QueryPlan/context/universal-routing/trading-cutover suites passed with `91 passed`, `17 subtests passed`. Final full regression passed with `3,392 passed`, `156 subtests passed` in 138.23 seconds; three unchanged dependency/UTC warnings remained. Compileall, Docker Compose configuration, `git diff --check`, and static safety checks passed.
- Docker runtime: the mounted-source app restarted and Streamlit health returned `200 ok`; the existing image already reports Pydantic `2.13.4`. Two clean dependency-image rebuild attempts timed out after 20 and 10 minutes respectively and were stopped without affecting the healthy app. Clean-image dependency rebuild verification remains `NOT VERIFIED`.
- No external LLM, provider retry/cascade, MT5 write, controlled-submit, runtime `order_send`, broker mutation, or real-account action ran. `src/` retains zero MetaTrader5 imports and exactly one production `.order_send(` call-site remains isolated in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Next approved scope: Legacy Semantic Fallback Cleanup + Architecture Acceptance + Release Validation.

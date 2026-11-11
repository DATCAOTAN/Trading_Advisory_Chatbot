# TRADING_ADVISORY_CHATBOT — FULL CODEBASE, RUNTIME, ROADMAP, AND AGENT HANDOFF

## CURRENT READING GUIDE (2026-11-05)

The historical pre-recovery baseline is `b9e7d83`, containing the Sprint 9/10 checkpoint
in sections 118-120. The local Sprint 11A historical-data foundation is recorded
in section 121; session/coverage reassessment is in section 122. Native MT5 tester
feasibility and its unresolved parity blocker are in section 123. No historical
trade simulator has passed acceptance; Python simulator dependencies remain deferred.
Start with those sections for current state and retained autonomous DEMO acceptance.

Current Git recovery (2026-11-11): Recovery 01 is committed as `51f625c`.
The remaining source/tooling/documentation backlog is recovered in dependency-ordered
commits; see section 160 for the integrated offline verification and exclusions.
This software checkpoint does not renew trading or native-execution acceptance.
Sections 113-116 cover account recovery, human-confirmed execution and position
provenance. Sections 102-109
cover sizing, conversation ownership and Draft workflows; sections 110-112
record earlier cleanup. Source/tests/Git remain authoritative.

The product goal is conversational research and controlled MT5 DEMO operation:
typed semantics -> fresh evidence -> deterministic Draft/Candidate -> exact
human confirmation or bounded Standing Mandate -> independent execution gates
-> broker lifecycle, position/P&L/history reads, management, and reconciliation.
The locked target is `docs/architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md`.

The combined worktree's Sprint 6 regression retained 3,798 tests plus 156
subtests. Its local commits were independently checked on exact staged snapshots:
62 recovery tests and 243 Sprint 6/neighbor/documentation tests. Full-worktree
and isolated-commit evidence are distinct. Neither establishes today's terminal,
feed, permissions, mandate, or Supervisor state.

The remaining cleanup checkpoint and its isolated, configuration-independent
regression are recorded in section 117. Runtime readiness requires a separate
authoritative autonomous DEMO preflight; code verification grants no authority.

Retained Sprint 10 full regression: 3,865 passed and 156 subtests. Current Sprint
11A focused/live evidence is separate in section 121; full regression was not
rerun. Neither result is a new trading session or proof of unattended reliability.

**Historical scope:** sections 1-34 retain the original July snapshot and its
then-current blockers. Sections 35-109 are chronological implementation records.
Statements such as "not implemented" or "manual broker submission not run" in
an older section describe that milestone, not the latest implementation.
Use `README.md` and `docs/PROJECT_CONTEXT_FOR_AI.md` for the concise current map.

### Original snapshot metadata

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

# 76. FINAL LOCKED SEMANTIC ARCHITECTURE CLOSURE

- The normal semantic path is `Streamlit chat -> RAGOrchestrator -> StructuredSemanticInterpreter -> one configured structured provider call -> Pydantic v2 DTO validation -> frozen StructuredSemanticResult -> ResolvedSemanticState -> QueryPlan -> ContextRequirementPlanner -> ContextExecutionPlanner -> CapabilityRegistry`. QueryPlan remains the sole internal semantic and planning authority.
- A valid structured QueryPlan bypasses raw conversational parsing in both the trading projection and the Streamlit result-selection boundary. The trading projection consumes QueryPlan semantic context directly and stays non-executable.
- Remaining raw helpers are named bounded fallbacks only: QueryPlan raw assembly and `parse_indicator_specs` run when a structured result is unavailable or invalid; conversational context, trade-instruction, strategy, and conversational-request parsing are compatibility-only fallbacks when no authoritative semantic plan exists. They cannot overwrite a valid StructuredSemanticResult, ResolvedSemanticState, or QueryPlan.
- Retrieval rewrite remains downstream of capability requirements and is used only for retrieval needs. It is not parsed back into semantic authority. Knowledge, current technical, and mixed requests continue through one capability-driven plan with deduplicated requirements.
- Mode remains a deterministic policy overlay. It does not own another semantic interpreter, QueryPlan, context planner, capability registry, RAG path, market path, or trading-language parser.
- The non-executable lifecycle remains `EditableTradeDraft -> explicit Candidate -> explicit Confirm or Reject -> explicit Pre-Submit -> PRE_SUBMIT_READY_NON_EXECUTABLE or BLOCKED -> STOP`. No step automatically invokes the next one, and ready status is not submission authority.
- Pydantic v2 remains confined to `src/services/semantic/structured_semantics.py`; internal semantic dataclasses and downstream planning, trading, lifecycle, bridge, and execution contracts remain unchanged. No LangGraph, LangChain, PydanticAI, Instructor, Agents SDK, second QueryPlan, or second capability architecture was introduced.
- Final source inspection found no normal-production duplicate arbitrary-language semantic owner. The optional old `conversational_context` parameter has no current non-test caller and remains compatibility-only; its raw path is not used by the Streamlit ingress.
- Verification: 166 focused semantic/routing/context/Draft/review/pre-submit tests passed with two unchanged dependency warnings. Final full regression passed with `3,392 passed`, `156 subtests passed` in 139.59 seconds with three unchanged dependency/UTC warnings. Documentation integrity, compileall, Docker Compose configuration, diff checks, and static safety scans passed.
- Rebuilt-container provenance: the healthy mounted-source app container was recreated at `2026-08-08T14:52:19Z` from image `sha256:93f036dd201697dcaaa7ce72e5ade3e6ddcce631d7847194c00fb9663e829303`, which matches `trading_advisory_chatbot-app:latest` created at `2026-08-08T14:22:14Z` after Sprint 6D. Runtime Pydantic is `2.13.4`, the semantic import is `/app/src/services/semantic/structured_semantics.py`, and Streamlit health returned `200 ok`. No Docker rebuild ran during this verification.
- No external LLM, live market data, MT5 write, candidate creation, confirmation, pre-submit creation, controlled-submit, runtime `order_send`, broker mutation, or reconciliation mutation ran. `src/` retains zero MetaTrader5 imports and exactly one production `.order_send(` call-site remains isolated in the host bridge.
- Verification level: `FULL_REGRESSION_PASS`. Semantic architecture, intelligence architecture, and the non-executable lifecycle satisfy the release-candidate boundary. Controlled submission enablement, broker execution, real-account execution, and MT5 write acceptance remain out of scope.

# 77. STRUCTURED SEMANTIC RUNTIME ROUTING REPAIR

- Runtime evidence after the prior closure found four shared semantic-path defects: the structured-provider prompt illustrated an indicator period, `POSITION_MANAGEMENT` and `TRADE_LIFECYCLE` projected to `unknown`, the immediate structured-trading response bypassed the existing context-acquisition executor for `legacy_heuristic` acquisition, and projection did not derive registry-required missing parameter fields when a provider omitted the corresponding unresolved annotation.
- The strict prompt now illustrates an empty parameter object and requires missing child fields to remain unresolved unless the user or referenced context supplied them. Explicit parameters remain explicit; no conventional indicator period is assigned by the semantic boundary.
- Both structured lifecycle/position-management primary intents now reuse the existing `trade_opportunity_analysis` QueryPlan and its market, OHLCV, economic-event, optional technical, static-framework, and account-state capability requirements. The semantic action remains preserved and execution stays disabled.
- A valid structured trading projection now executes the existing planned context acquisition before DecisionContext construction. It no longer enters the legacy default indicator list, so structured indicator facts cannot be weakened by a secondary acquisition path.
- Trading projection now derives absent registry-required parameters as precise `semantic_unresolved_fields`; it neither fabricates a value nor treats an incomplete typed strategy as malformed. The same rule covers multi-parameter supported indicators, and MACD relational validation runs only when both values being compared exist.
- Verification: focused semantic/interpreter/QueryPlan/trading-cutover tests passed with `70 passed`. Final full regression passed with `3,399 passed`, `156 subtests passed` in 155.36 seconds; three unchanged dependency/UTC warnings remained. Changed-path compileall, diff, and static safety scans passed.
- One browser/runtime acceptance completed after the mounted-source app restart: the structured provider returned a valid `POSITION_MANAGEMENT` result for XAUUSD/XAUUSDm M1, QueryPlan retained `trade_opportunity_analysis`, and the resulting non-executable Draft preserved the RSI condition and threshold while reporting only the missing period as unresolved. No RSI(14) default appeared.
- The structured provider call was the only external provider invocation and owned semantic extraction. The subsequent `[AnswerStream]` entry is UI logging metadata: the structured branch returns `_static_stream(...)`, while the logger labels that bounded stream with the configured provider/model without making a second request. It did not change semantic facts, create a Candidate, or grant authority. The legacy journal detector remained false because it is a safety observation, not the structured-trading authority.
- No candidate generation, confirmation, pre-submit creation, controlled-submit, runtime `order_send`, broker mutation, or MT5 write ran during verification. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero `MetaTrader5` imports.

# 78. TYPED PUBLIC REQUEST ROUND-TRIP GUARD

- A valid complete supported indicator strategy now round-trips losslessly through `ConversationalStrategyRequest.as_dict()/from_dict()` and `ConversationalTradingRequest.to_public_dict()/from_public_dict()`. RSI `period=14` and complete MACD parameters retain normalized numeric meaning, timeframe, unresolved-field state, and strategy identity.
- The trading-request projection no longer publishes an invalid strategy into a public runtime artifact that the strict reloader would reject. It retains the deterministic validation blocker, omits that invalid strategy, keeps the request non-executable, and uses the configured operator profile when no strategy exists.
- Incomplete supported strategies remain publishable as valid incomplete semantics. Missing children remain precise unresolved facts, no value is fabricated, and the existing evidence-staging guard continues to report `NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED` before market/account/tick acquisition.
- Browser acceptance: the explicit BTCUSD/BTCUSDm RSI M1 request no longer crashed during public reload, but its sole provider result was incomplete and invalid (`period` unresolved plus `INDICATOR_PARAMETER_INVALID`), so it did not reach evidence. The raw provider payload was not persisted or logged and is not reconstructed here. A separate partial request preserved the missing period, skipped evidence, remained non-executable, and produced no Candidate.
- Verification: 94 focused semantic/conversational/thin-UI tests passed. Final full regression passed with `3,411 passed`, `156 subtests passed` in 134.56 seconds; three unchanged dependency/UTC warnings remained. Changed-path compileall, app restart, Streamlit health `200 ok`, diff checks, and static safety scans passed.
- No Candidate, confirmation, pre-submit, controlled-submit, runtime `order_send`, broker mutation, or MT5 write occurred. `src/` retains zero `MetaTrader5` imports and the host bridge retains exactly one production `.order_send(` call-site. Execution remains disabled and non-executable.
- Verification level: `FULL_REGRESSION_PASS`. The remaining runtime blocker is upstream structured-provider conformance for the explicit complete request, not public serialization/reload or the partial evidence-staging contract.

# 79. RUNTIME SEMANTIC EVIDENCE STAGING REPAIR

- Typed unresolved strategy fields now stop Draft evidence acquisition before provider construction, strict `plan_strategy_data`, live feature construction, account lookup, or authority-status retrieval. The strict planner remains unchanged: incomplete calculation parameters are valid semantic facts but are not valid inputs for indicator calculation.
- `EditableTradeDraft` retains the precise `SEMANTIC_UNRESOLVED:<path>` blocker and reports `EVIDENCE_NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED`. It no longer derives market, structure, target, account-risk, tick-value, or DEMO-scope failures solely because evidence was deliberately not attempted.
- The UI renders `NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED` as expected state. Genuine validation and acquisition failures remain fail-closed and are rendered as sanitized domain statuses, rather than exposing a Python exception class.
- Verification: 65 focused semantic/Draft/thin-UI tests passed. Final full regression passed with `3,406 passed`, `156 subtests passed` in 137.89 seconds; three unchanged dependency/UTC warnings remained. Changed-path compileall, app restart, Streamlit health `200 ok`, diff, and static safety checks passed.
- Browser acceptance: one fresh partial BTCUSD/BTCUSDm RSI M1 request retained only the unresolved period prerequisite, skipped evidence, and remained non-executable without a Candidate. One fresh explicit-RSI-period request entered the structured semantic provider once but stopped before evidence at deterministic `INDICATOR_PARAMETER_INVALID` during public-request reload. The complete typed request regression confirms that valid complete semantics still enter evidence planning; the runtime provider payload failure is a separate upstream semantic-contract blocker and was not retried.
- Two structured semantic provider calls occurred only for the two browser acceptance inputs. No candidate, confirmation, pre-submit, controlled-submit, runtime `order_send`, broker mutation, or MT5 write occurred. `src/` retains zero `MetaTrader5` imports and the host bridge retains one production `.order_send(` call-site.
- Verification level: `FULL_REGRESSION_PASS`. Any follow-up must diagnose the upstream structured provider/domain strategy payload before evidence staging, without changing the incomplete-semantics policy or execution boundaries.

# 80. COMPLETE SEMANTIC-TO-EVIDENCE RUNTIME ACCEPTANCE

- A fresh single-call BTCUSD/BTCUSDm request passed strict semantic admission with `POSITION_MANAGEMENT`, BUY, RSI period 14 on M1, and `GREATER_THAN 10`; semantic unresolved fields and domain validation issues were empty.
- The typed request passed strict public reload and reached `plan_strategy_data`, `StrategyDataPlan`, `LiveFeatureService`, `MarketSnapshotBundleBuilder`, provider market-data and account lookup, authority status, and `TradeDraftMarketEvidence` creation.
- Draft evidence was attempted and rejected by the existing `SPREAD_TOO_WIDE` policy blocker. `MARKET_EVIDENCE_UNAVAILABLE`, `STRUCTURE_EVIDENCE_UNAVAILABLE`, `TARGET_CALCULATION_DEPENDENCY_MISSING`, and `ACCOUNT_RISK_BASIS_UNAVAILABLE` are downstream cascade blockers, not independent provider or account failures.
- Spread-policy tuning is not part of this repair. The Draft remained non-executable with no execution authority, Candidate, confirmation, pre-submit artifact, controlled-submit, runtime `order_send`, broker mutation, or MT5 write.
- Verification remains `FULL_REGRESSION_PASS`: the final production repair regression passed with `3,416 passed`, `156 subtests passed`, and three existing warnings. The later bounded diagnostic suite passed with 45 focused tests; documentation integrity, changed-path compileall, and diff checks passed.

# 81. SINGLE SEMANTIC AUTHORITY AND DETERMINISTIC MODE CLOSURE

- Valid structured semantics remain the normal ingress and produce one resolved semantic state and one QueryPlan. QueryPlan now stores the authoritative deterministic operating mode separately from the LLM-proposed mode evidence.
- Analysis, questions, negated actions, and hypothetical actions resolve to `advisory_only`; direct OPEN, CLOSE, and MANAGE actions resolve to `human_confirmed_live`; `autonomous_live` requires explicit typed autonomous-mode evidence. None of these modes grants execution authority.
- `ConversationalTradingRequest` consumes the mode from QueryPlan constraints rather than reading the provider field directly. Draft-stage `execution_allowed`, `execution_authority`, and `executable` remain false.
- Any orchestrator runtime result now prevents Streamlit from reparsing the raw user message. Structured-invalid requests therefore produce only the central bounded result or legacy QueryPlan; raw conversational parsing remains compatibility-only when no runtime artifact exists at all.
- Existing partial strategy behavior is unchanged: RSI, comparator, and threshold survive while absent period and semantic timeframe remain unresolved. The operational acquisition profile remains separate from user-requested semantic timeframe.
- Verification: final focused semantic/UI tests passed with `51 passed`; the broader semantic, orchestrator, authorization, UI, and journal group passed with `179 passed`. Full regression passed with `3,426 passed`, `156 subtests passed`, and three unchanged warnings in 136.90 seconds. Compileall, app restart, Streamlit `200 ok`, diff, and static safety checks passed.
- Browser acceptance used one partial direct BTCUSD instruction. The provider returned invalid structured output (`INDICATOR_PARAMETERS_INVALID`), so the central fallback produced one legacy QueryPlan and the UI produced no competing Draft. The request was not retried; live rendering of the deterministic human-confirmed completion card remains unverified for that turn.
- No Candidate, confirmation, pre-submit, controlled-submit, runtime `order_send`, broker mutation, or MT5 write occurred. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero MetaTrader5 imports.
- Verification level: `FULL_REGRESSION_PASS`. Next approved gap is Strategy Completion, field provenance, completion form behavior, and semantic-versus-operational timeframe presentation; upstream provider conformance remains fail-closed.

# 82. STRATEGY COMPLETION, PROVENANCE, AND EDITABLE FORM

- Incomplete typed strategies now produce a non-executable Strategy Completion state and focused Streamlit form. Known action, direction, symbol, indicator, comparator, and threshold remain visible; unresolved indicator parameters and semantic timeframe remain unresolved. Neither a normal Draft nor Candidate controls are available before completion.
- Structured form changes use typed semantic patches. Confirmed suggestions are recorded as `USER_CONFIRMED_SUGGESTION`, manual edits as `USER_EXPLICIT`, inherited context as `CONVERSATION_INHERITED`, and unconfirmed suggestions remain distinct policy/LLM evidence. No raw-language reparse or second semantic-provider call is required.
- Semantic timeframe remains separate from the operational acquisition profile. An unresolved timeframe is displayed as required even when the runtime data profile is M1/H1/H4.
- The strict Pydantic boundary accepts omitted indicator children and provider `null` children only when the exact child or parameter parent is declared unresolved. Unbound nulls, malformed numeric values, conflicting values, extra fields, and untrusted shapes remain fail-closed.
- The Draft service now rejects incomplete semantic prerequisites before store access. A complete typed strategy reuses the existing strategy projection, evidence, and Draft path; evidence remains `NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED` before completion.
- Verification: 61 focused semantic/completion tests and 214 focused/neighboring tests passed. Final full regression passed with `3,442 passed`, `156 subtests passed`, and three unchanged warnings. Container restart, Pydantic 2.13.4 runtime import from `/app/src/services/semantic/structured_semantics.py`, healthy container, and Streamlit `200 ok` were verified.
- Final browser/provider acceptance used one fresh partial BTCUSD RSI request on the final source. One provider call returned `VALID_PARTIAL`: OPEN_POSITION, BUY, BTCUSD/BTCUSDm, RSI GREATER_THAN 10, explicit M1, and unresolved RSI period. Streamlit rendered Strategy Completion instead of a normal Draft, labeled period 14 as a suggestion, preserved `human_confirmed_live` / `CONFIRM_EVERY_TRADE`, and remained `NON_EXECUTABLE`; no retry or competing generic RAG authority occurred.
- Explicit structured acceptance of period 14 recorded completion without another provider call, preserved every semantic sibling, and entered the existing evidence/Draft path. Evidence failed closed with genuine market/structure/account/tick dependency blockers; the resulting Draft remained non-executable and no Candidate was created.
- No Candidate, confirmation, pre-submit, controlled-submit, runtime `order_send`, broker mutation, or MT5 write occurred. The host bridge retains exactly one production `.order_send(` call-site and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Final runtime provenance matched host/container source hashes, the container was healthy, and Streamlit returned `200 ok`. Sprint 2 is complete; Sprints 3 and 4 remain skip-or-closure-only.

# 83. AUTHORITATIVE POSITION READ MODEL, P&L, HISTORY, AND PROVENANCE

- One frozen `PositionReadModel` now projects the existing authenticated host-bridge lifecycle snapshot together with strict protected execution/lifecycle journals and persisted Candidate references. It is read-only and does not supervise, reconcile, authorize, or mutate broker state.
- Current positions and pending orders use broker-authoritative symbol, direction, volume, prices, SL/TP, state, and timestamps. Current unrealized P/L uses the broker position `profit`; closed-trade P/L uses broker deal profit, commission, swap, and fee. Missing broker P/L remains explicitly `UNAVAILABLE`.
- Recent closed trades pair protected opening/closing deal evidence where available. Provenance reports safe references across strategy, Draft, Candidate, authorization, execution, lifecycle, and management; unavailable links remain explicit rather than inferred from chat history.
- Singular targets resolve only by exact protected reference, explicit symbol with one match, or one unique result. Ambiguous, stale, account-mismatched, stale-snapshot, unavailable-journal, unavailable-bridge, and reconciliation-required states fail closed.
- Structured `POSITION_MANAGEMENT` reads with `NONE`/`EXPLAIN` now route through the existing QueryPlan, requirement planner, execution planner, capability registry, and one `position_read` capability. The semantic contract classifies the bounded position/pending/P&L/history/provenance read family without adding raw-language parsing.
- Streamlit stores and renders only the typed public projection in a read-only Trading State card. Runtime acceptance returned `Open positions: none (authoritative broker snapshot)` with zero positions, pending orders, and recent closes; the card remained `NON_EXECUTABLE`.
- Verification: final focused model tests passed with `17 passed`; focused semantic/routing tests passed with `107 passed`; earlier lifecycle/reconciliation/capability/UI neighboring groups passed with `142 passed` and `151 passed`. Final full regression passed with `3,459 passed`, `156 subtests passed`, and three unchanged warnings. Compileall, app/bridge restart, container health, Streamlit `200 ok`, diff, and static safety checks passed.
- No controlled-submit, controlled-management write, runtime `order_send`, broker mutation, or MT5 write occurred. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Next major sprint: S6 `HUMAN_CONFIRMED_POSITION_MANAGEMENT`.

# 84. HUMAN-CONFIRMED POSITION MANAGEMENT

- Direct cancel, protection modification, partial-close, and full-close semantics now route through the existing structured semantic, QueryPlan, position-read, and controlled-management boundaries. Management numbers must be explicitly supplied by the user; LLM-only values cannot become authority.
- Target selection is fail-closed: an exact protected reference is preferred, a symbol must resolve uniquely, and ambiguous, missing, stale, account-mismatched, or reconciliation-blocked targets do not produce a proposal.
- One frozen `HumanConfirmedManagementProposal` wraps the existing `MT5ManagementProposal`. It remains `NON_EXECUTABLE`, binds the protected target, lifecycle observation, account fingerprint, mutation values, and deterministic idempotency key, and exposes only a redacted public projection.
- Protection edits preserve the unchanged SL or TP side. Partial close accepts exactly one explicit fraction, close amount, or resulting volume; broker minimum/step and stop-distance checks remain independently authoritative in the existing app and host-bridge boundaries.
- Streamlit renders one editable review card and requires the existing intent-specific exact confirmation phrase. Cancel/Keep Order performs no mutation. Confirmation reloads the target and revalidates lifecycle, volume, protection, observation, account binding, and the existing controlled-management gates before any bridge write path.
- `RESULT_UNKNOWN` retains retry prohibition and requires reconciliation. No alternate endpoint, adapter, journal, state machine, or `order_send` call-site was added.
- Browser acceptance submitted one human management request for 50% of the current BTCUSD position. With no exact current target, it stopped at `MANAGEMENT_TARGET_REFERENCE_UNRESOLVED` / `POSITION_NOT_FOUND`, rendered no confirmation control, and performed no broker write.
- Verification: 256 focused/neighboring tests passed. Full regression passed with 3,491 tests and 156 subtests; three unchanged dependency/UTC warnings remained. Compileall, Docker app health, Streamlit `200 ok`, bridge health, diff, documentation, and static safety checks passed.
- Controlled-submit, controlled-management write, runtime `order_send`, broker mutation, and MT5 write counts remained zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. S7 `AUTONOMOUS_POST_ENTRY_MANAGEMENT` is documented below.

# 85. AUTONOMOUS POST-ENTRY MANAGEMENT

- The existing completed-bar autonomous coordinator now checks the canonical `PositionReadModel` before considering a new opening candidate. An exact protected position or pending-order target is required; ambiguous, stale, mismatched, or reconciliation-blocked state fails closed.
- Autonomous management reuses the Sprint 6 `MT5ManagementProposal`, deterministic protection and resulting-volume calculations, controlled-management adapter, host-bridge validation, idempotency journal, and single `order_send` boundary. No second supervisor, management backend, endpoint, adapter, or execution state machine was added.
- A protected `MandateManagementAuthorization` binds authoritative `autonomous_live` mode, the current non-revoked Standing Trading Mandate, demo-account fingerprint, strategy and original opening-candidate provenance, symbol, exact management intent, proposal, lifecycle observation, evaluation/policy references, and deterministic idempotency.
- Supported bounded intents are `CANCEL_PENDING_ORDER`, `MODIFY_POSITION_PROTECTION`, `PARTIAL_CLOSE`, and `CLOSE_POSITION`; `OBSERVE` and `NO_ACTION` remain non-mutating. Existing legacy mandate intent aliases remain readable.
- Mode alone and LLM output cannot authorize mutation. Account, strategy, symbol, mandate scope and expiry, position/trade/loss limits, lifecycle, reconciliation, current target state, volume, kill switches, and existing controlled-management permissions remain authoritative and are revalidated immediately before the adapter boundary.
- `RESULT_UNKNOWN` remains retry-prohibited and reconciliation-only. Revocation or target change immediately before the adapter blocks with zero writes. Public projections redact protected references and broker identifiers.
- Deterministic simulation verified all four management families, duplicate-safe authorization, bridge-side independent authority reload, current-state changes, revocation, unknown-result handling, and confirmed PositionReadModel updates. A target with no configured deterministic management evaluator fails closed instead of falling through to opening generation.
- Verification: 243 focused/neighboring tests passed. Full regression passed with 3,516 tests and 156 subtests; three unchanged dependency warnings remained. Compileall, Docker app health, Streamlit `200 ok`, browser acceptance, diff, and static safety checks passed.
- Browser acceptance observed a healthy demo runtime with zero positions and no management action: lifecycle `HEALTHY`, account match true, reconciliation discrepancies and unresolved states zero, all execution/management permissions disabled, and both kill switches engaged.
- Controlled-submit, controlled-management write, runtime `order_send`, broker mutation, and MT5 write counts remained zero. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. S8 is `SKIP_OR_CLOSURE_ONLY`; the next major sprint is S9 `THIN_UI_AND_FULL_CONVERSATIONAL_INTEGRATION`.

# 86. THIN UI AND FULL CONVERSATIONAL INTEGRATION

- Streamlit now selects exactly one primary typed domain presentation per assistant turn: management proposal, position read model, trading request, typed blocker, or plain text. A management result no longer also renders a competing position card.
- Normal UI handling consumes authoritative orchestrator runtime artifacts. The bounded raw conversational parser remains compatibility-only and is not entered when any authoritative runtime artifact dictionary is present.
- The canonical position-read path now persists an exact protected selected-position reference into resolved semantic context only when the broker-authoritative snapshot has one fresh, unambiguous target. Later typed references such as `previous_position` and `previous_order` reuse that binding; missing, stale, ambiguous, or blocked selections remain unbound and fail closed.
- Session state stores typed public request/context and the chosen public presentation payload for rerendering. It does not own operating mode, broker truth, lifecycle/reconciliation state, candidate authority, confirmation, or execution permission.
- Sprint 8 remained closure-only. Existing restart recovery, strict journal reads, duplicate/idempotency handling, reconciliation, lifecycle supervision, and retry-prohibited `RESULT_UNKNOWN` behavior stayed green in focused neighbors and the final regression.
- Verification: the new integration matrix passed with `34 passed`; focused and neighboring semantic/UI/Draft/Candidate/position/management/lifecycle/reconciliation suites passed with `308 passed`. Final full regression passed with `3,550 passed` and `156 subtests passed`; three unchanged dependency/UTC warnings remained. Compileall and diff checks passed.
- Runtime provenance matched the final host files to `/app` for all three changed production modules. The existing app service restarted without rebuild, became healthy, and Streamlit returned `200 ok` at `http://localhost:8501/`.
- Final browser acceptance showed one static-knowledge result, non-executable typed trading presentation, authoritative empty position state, one typed management blocker without confirmation controls, and read-only runtime status: DEMO, `human_confirmed_live`, lifecycle healthy, account match true, zero discrepancies, zero unresolved execution states, disabled write permissions, and engaged kill switches.
- Natural provider classification remains evidence-dependent: one partial request reached the Draft path and one incomplete strategy reached a typed completion blocker; some EMA wording was conservatively handled by RAG rather than forced into trading state. This is a product-acceptance coverage item, not execution authority, and belongs to Sprint 10's case matrix.
- Final Ponytail review removed an overbroad replacement of unrelated protected context references; the final binder puts the verified selected-position reference first while preserving every other reference. Focused coverage and the final regression passed afterward. Final review result: `PONYTAIL_REVIEW_PASS`.
- Browser acceptance produced zero controlled-submit calls, controlled-management writes, runtime `order_send` calls, broker mutations, or MT5 writes. Static checks retain exactly one production `.order_send(` call-site in the host bridge and zero `MetaTrader5` imports under `src/`.
- Verification level: `FULL_REGRESSION_PASS`. Next approved sprint: S10 `60_CASE_PRODUCT_ACCEPTANCE`.

# 87. 60-CASE PRODUCT ACCEPTANCE

- Added one parameterized 60-case acceptance manifest covering social/system, knowledge/RAG, current market, analysis, strategy completion, Draft/Candidate, position reads, history/provenance, human management, autonomous mandate behavior, and failure/recovery.
- Deterministic acceptance is contract-correct for all 60 canonical cases. Five extra high-risk semantic variants and the typed multi-turn sequence also pass. Positive broker-state paths use existing deterministic fixtures; no broker state was created.
- Runtime browser sampling exposed three related structured-provider prompt gaps: indicator concept questions were not explicitly separated from position reads, optional scalar/missing-indicator child output shapes were underspecified, and direct trade instructions were not explicitly separated from advisory questions. All were fixed at the one existing provider prompt boundary without regexes, fallbacks, relaxed schema validation, or new authority.
- Focused final semantic/product tests passed with `150 passed`. Final full regression passed with `3,621 passed`, `156 subtests passed`, and three unchanged dependency/UTC warnings.
- Initial provider sampling used six calls with zero retries. Final closure used one separately authorized Groq call with zero retries and returned `VALID_PARTIAL`: `OPEN_POSITION`, `BUY`, `BTCUSD` / `BTCUSDm`, and `RSI GREATER_THAN 10`, with RSI period and semantic timeframe still unresolved. The canonical mode remained `human_confirmed_live`, confirmation policy remained `CONFIRM_EVERY_TRADE`, and execution remained `NON_EXECUTABLE`.
- After an app restart without rebuild, host/container source hashes matched and Streamlit returned `200 ok`. The browser rendered one Strategy Completion workflow and no competing advisory answer, Draft, Candidate, confirmation, or submission control.
- No Candidate, confirmation, pre-submit, controlled-submit, management write, runtime `order_send`, broker mutation, or MT5 write occurred. Execution remains non-authoritative and fail-closed.
- Verification level: `FULL_REGRESSION_PASS`. Product verdict: `60_CASE_PRODUCT_ACCEPTANCE_COMPLETE`; S11 status: `READY_FOR_FINAL_RELEASE_CLOSURE`.

# 88. SOFTWARE-COMPLETE RELEASE CLOSURE

- Release baseline `f0c0899d734ea890448feeddd072be1684db899f` preserves the completed Sprint 1-10 implementation. Sprint 11 changes release documentation only; no production, test, dependency, configuration, execution, or broker behavior changed.
- The locked production flow remains `user -> structured semantic ingress -> Pydantic v2 -> ResolvedSemanticState -> QueryPlan -> deterministic mode/policy -> capability planning -> domain core`. QueryPlan is the sole downstream semantic authority; Streamlit remains presentation and structured input only.
- Position reads remain broker-authoritative. Human management requires exact per-action confirmation; autonomous management requires a valid bounded Standing Trading Mandate. Both paths retain account, lifecycle, reconciliation, freshness, risk, idempotency, kill-switch, app-side, and independent bridge-side validation.
- Controlled execution remains behind approval, final validation, pre-submit, and the single host-bridge mutation boundary. `RESULT_UNKNOWN` remains retry-prohibited and reconciliation-only. Restart-safe journals, lifecycle supervision, and duplicate protection remain authoritative.
- Release verification retains the Sprint 10 evidence: 60/60 canonical acceptance cases, `150 passed` focused tests, `3,621 passed` full regression tests, and `156 subtests passed`; three unchanged dependency/UTC warnings remained. Sprint 11 did not rerun the full regression because only release documentation changed afterward.
- Sprint 11 static checks found exactly one production `.order_send(` call-site in `tools/mt5_bridge/execution.py` and zero `MetaTrader5` imports under `src/`. No execution, submission, pending-order, management, or autonomous permission was enabled.
- Runtime provenance used the existing image `sha256:93f036dd201697dcaaa7ce72e5ade3e6ddcce631d7847194c00fb9663e829303` with the repository `src/`, `scripts/`, `tools/`, and `data/` bind mounts. The host and `/app` semantic-boundary SHA-256 values matched; runtime Pydantic was `2.13.4` and the import path was `/app/src/services/semantic/structured_semantics.py`.
- The app container was healthy, Streamlit returned `200 ok`, and the authenticated bridge health check reported a connected terminal with redacted account data. A read-only browser smoke showed `DEMO`, `human_confirmed_live`, lifecycle `HEALTHY`, account match true, zero reconciliation discrepancies, zero unresolved execution states, disabled write permissions, and engaged execution and management kill switches.
- No provider call, Candidate, confirmation, mandate change, pre-submit creation, controlled-submit, runtime `order_send`, broker mutation, reconciliation mutation, or MT5 write occurred during Sprint 11 closure.
- Known non-blocking limitations: positive broker mutation acceptance was not performed; positive position/order lifecycle behavior may depend on naturally available demo broker state; explicit operator and account context remain required where the runtime contract requires them; autonomous management requires its configured deterministic strategy evaluator. Real-money approval is explicitly excluded.
- Release tag: `v2.0.0-software-complete` on the Sprint 11 closure commit. Verification level: `FULL_REGRESSION_PASS`. Release verdict: `TRADING_ADVISORY_CHATBOT_SOFTWARE_COMPLETE`.

# 89. POST-RELEASE AUTONOMOUS AND STRATEGY-COMPLETION ALIGNMENT

- The architecture-only clarification commit `21b3489` did not change production source after `v2.0.0-software-complete`. This bugfix keeps that release tag unchanged.
- The structured provider contract now represents explicit autonomous intent generically. Deterministic mode resolution remains authoritative, and mode still grants no execution permission.
- Strategy Completion removes unresolved container paths when concrete leaf children exist. A missing RSI period and timeframe therefore exposes only `indicators[0].parameters.period` and `indicators[0].timeframe`; typed patches preserve known siblings and do not call the provider again.
- Human-confirmed complete strategies continue through fresh deterministic Draft/Candidate construction and exact per-trade confirmation. Autonomous complete strategies route to the existing bounded Standing Mandate setup, never the human per-trade Draft path.
- Autonomous level conditions use previous/current completed-bar evidence as a restart-safe re-arm gate: false arms, false-to-true permits one signal, remaining true blocks duplicates, and a later false state re-arms. Draft, Entry, SL, TP, risk, volume, account evidence, and broker constraints remain fresh per trade instance.
- Browser acceptance used one provider call and zero retries for the original autonomous XAUUSDm RSI family. It returned `autonomous_live`, retained only period/timeframe semantic leaves, accepted both structured leaf suggestions without a second provider call, and displayed the existing non-executable Standing Mandate setup. `DEMO_ACCOUNT_SCOPE_REQUIRED` remained visible until authoritative account binding; Generate stayed disabled and no mandate was granted.
- Verification: focused semantic/completion/autonomous/UI tests passed with `175 passed`; the canonical product acceptance passed with `67 passed` (60 canonical cases plus existing variants/sequence). Final full regression passed with `3,632 passed`, `156 subtests passed`, and three unchanged warnings. Compileall, app restart without rebuild, healthy container, Streamlit `200 ok`, diff, and static safety checks passed.
- Candidate creation, human confirmation, Standing Mandate activation, pre-submit, controlled-submit, controlled-management writes, runtime `order_send`, broker mutation, and MT5 writes remained zero. The host bridge retains one production `.order_send(` call-site and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. This alignment is suitable for a later repository-approved patch release; no tag was created.

# 90. AUTONOMOUS MANDATE PREFILL AND REVIEW UX

- Completed autonomous strategies now project into the existing Standing Mandate authority path as a non-authoritative review setup. Strategy identity/symbol, broker mapping, DEMO account context, current autonomous mode, broker volume constraints, mandate ID/version, and bounded validity timestamps no longer require manual re-entry.
- The projection uses the existing protected account capture, mode journal, mandate store, symbol mapping, and MT5 bridge market metadata. Current account fingerprint binding is verified before the setup is shown; the final grant service still independently revalidates account, mode, scope, limits, timestamps, and explicit operator consent.
- Duration uses bounded 30-minute, 1-hour, or 4-hour presets and generates UTC `active_from`, `active_until`, and `expires_at` values satisfying the existing mandate time contract. Normal operation no longer asks the user to type raw ISO timestamps.
- Broker min/max/step are displayed and maximum-volume edits are validated against those constraints. No deterministic monetary policy currently exists, so maximum volume, position/trade counts, maximum risk per trade, and maximum loss per day remain explicitly unresolved until the operator supplies them. Monetary labels identify account-currency units.
- Management defaults are limited to `OBSERVE` and `NO_ACTION`; other existing canonical capabilities remain editable but are not preselected. Prefill never activates authority: the mandate kill switch stays engaged by default and exact operator confirmation remains mandatory.
- Focused and neighboring mandate/strategy/UI verification passed with `123 passed`. The canonical acceptance suite passed with `67 passed`, including all 60 canonical cases. Final full regression passed with `3,640 passed`, `156 subtests passed`, and three unchanged warnings.
- Runtime verification restarted the app without rebuild; the container became healthy and Streamlit returned `200 ok`. Browser acceptance displayed the authoritative prefilled setup with editable controls, an unchecked confirmation box, and `supervisor_running=false`.
- Provider calls, Candidate generation, mandate activation, pre-submit, controlled-submit, management mutation, runtime `order_send`, broker mutation, and MT5 writes remained zero. Human-confirmed mode retains exact per-trade confirmation and does not render autonomous mandate controls.
- Verification level: `FULL_REGRESSION_PASS`. The historical `v2.0.1-software-complete` tag remains unchanged.

# 91. BOUNDED DEMO MANDATE POLICY AND CONTROL-PLANE ACCEPTANCE

- The existing setup projection now fills all five required limits without creating mandate authority. Maximum volume comes from the current broker symbol's minimum/maximum/step metadata; maximum positions, trades per day, risk per trade, and daily loss come from explicit DEMO-only configuration.
- Monetary limits remain account-currency amounts, never percentages or LLM-derived values. Missing or invalid DEMO policy configuration fails closed. REAL and UNKNOWN account environments cannot inherit these suggestions.
- Streamlit keeps every suggestion editable, labels monetary units, validates the typed `MandateGrantCommand`, leaves confirmation unchecked, and disables grant until the complete form and explicit confirmation are valid. The existing Standing Mandate validator/store remains authoritative.
- Browser acceptance used one narrow XAUUSD/XAUUSDm MARKET mandate with `OBSERVE` and `NO_ACTION`, broker-minimum volume, configured bounded limits, and an engaged mandate kill switch. The protected journal recorded one grant and one revocation; strict reload, integrity validation, account binding, and public redaction passed.
- Reload recovered the same active mandate. Supervisor start required its exact active mandate ID, produced a running process with the expected XAUUSD/M1 profile, then stopped cleanly. After revocation and reload, no active mandate remained and Start Supervisor was disabled.
- Deterministic signal/re-arm behavior remained covered by the focused neighboring coordinator/monitor tests; no live signal was forced and no provider call or Candidate was created during browser acceptance.
- Verification: focused policy/mandate/supervisor neighbors passed with `112 passed`; canonical acceptance passed with `67 passed` including all 60 canonical cases; full regression passed with `3,649 passed`, `156 subtests passed`, and three unchanged warnings.
- The app restarted without rebuild, remained healthy, and Streamlit returned `200 ok`. Controlled-submit, controlled-management writes, runtime `order_send`, broker mutation, and MT5 writes remained zero; execution and management kill switches stayed engaged.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `AUTONOMOUS_DEMO_POLICY_AND_CONTROL_PLANE_COMPLETE`.

# 92. TYPED AUTONOMOUS SUPERVISOR BINDING AND REALTIME OBSERVATION

- The continuous supervisor now receives only the active mandate ID plus its existing symbol/profile admission hints. It reloads the protected Standing Mandate, reconstructs the exact `ConversationalStrategyRequest`, and validates strategy identity/hash, mode, symbol/broker scope, DEMO account fingerprint, active time, and revocation state before startup and every cycle.
- New mandates persist the protected typed strategy together with redacted public identity, direction, and action metadata. Legacy mandates remain readable but fail closed for supervisor admission because they have no authoritative strategy binding.
- `AutonomousTradingCoordinator` passes the recovered typed strategy into the existing authoritative assembler. No raw-language reconstruction, Streamlit session authority, strategy store, endpoint, or execution boundary was added.
- The completed-bar monitor now requests the repository's normal market-history count instead of two bars. This fixes the runtime-only `PARTIAL` quality result caused by the existing 35-bar indicator-quality minimum.
- The existing monitor journal records a safe strategy evaluation projection: completed bar, indicator values, conditions, re-arm state, decision/blocker, safe Candidate reference/proposal summary when present, mandate state, and execution-firewall state. Dashboard rendering only reads that projection and filters it by current strategy reference.
- Live DEMO acceptance loaded bound strategy `BUY XAUUSD`, RSI14 M1 `GREATER_THAN 10`, and observed three consecutive completed bars at `09:00Z`, `09:01Z`, and `09:02Z`. RSI transitions were `51.0876 -> 40.8171`, `40.8171 -> 39.0004`, and `39.0004 -> 54.4070`; all were TRUE-to-TRUE and authoritatively persisted as `WAITING_FOR_REARM` / `NO_ACTION` with zero natural Candidates.
- One controlled supervisor stop/start reloaded the same strategy ID and mandate, did not duplicate the prior bar, and processed the next completed bar. The UI showed the same journal-backed strategy, RSI values, conditions, decision, Candidate `none`, and `BLOCKED_KILL_SWITCH` firewall state.
- Verification: final focused supervisor/monitor/UI/re-arm tests passed with `75 passed`; neighboring autonomous/authority tests passed with `337 passed`; canonical acceptance passed with `67 passed` including all 60 canonical cases. Final full regression passed with `3,670 passed`, `156 subtests passed`, and three unchanged warnings.
- Controlled-submit, controlled-management writes, runtime `order_send`, MT5 writes, broker mutations, and natural Candidate creation remained zero. Execution and management kill switches stayed engaged; the host bridge retains one production `.order_send(` call-site and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Runtime verdict: `REALTIME_AUTONOMOUS_TYPED_STRATEGY_OBSERVATION_COMPLETE`.

# 93. LEVEL AND EDGE AUTONOMOUS TRIGGER SEMANTICS

- Plain comparisons (`GREATER_THAN`, `LESS_THAN`, and `BETWEEN`) are authoritative `LEVEL` triggers. They evaluate the current completed bar and become `ENTRY_ELIGIBLE` whenever the current condition is true; they do not require a prior false state.
- Explicit `CROSSES_ABOVE` and `CROSSES_BELOW` rules remain `EDGE` triggers with `ARMED`, `TRIGGERED`, `WAITING_FOR_REARM`, and `REARMED` transitions. Historical level re-arm descriptions in sections 89 and 92 record the behavior that this fix supersedes.
- Duplicate prevention remains separate from trigger meaning. Existing completed-bar identity suppresses repeat evaluation of the same bar; active Candidate, submission, order, and position state blocks another simultaneous opening with `ENTRY_ALREADY_ACTIVE`.
- Once no opening Candidate/order/position is active and the prior lifecycle is terminal, a later completed bar evaluates a true level condition normally. Mandate, account, lifecycle, reconciliation, position/trade/loss limits, risk, freshness, idempotency, and kill switches remain authoritative.
- The existing monitor projection now exposes trigger mode, current and previous condition, signal state, opening eligibility, decision, blocker, Candidate reference, and execution firewall. Streamlit renders this projection and performs no trigger calculation.
- Verification: final focused trigger/evidence/supervisor/coordinator/UI tests passed with `79 passed`; the broader neighboring strategy, monitor, lifecycle, mandate, and idempotency group passed with `204 passed`; canonical acceptance passed with `67 passed`, including all 60 canonical cases. Final full regression passed with `3,684 passed`, `156 subtests passed`, and three unchanged warnings.
- Bounded live DEMO observation used the persisted typed `BUY XAUUSD`, RSI14 M1 `GREATER_THAN 10` strategy. Consecutive completed bars with true-to-true RSI conditions were recorded as `trigger_mode=LEVEL`, `CONDITION_TRUE`, and `ENTRY_ELIGIBLE`, not `WAITING_FOR_REARM`. No Candidate was created because the first downstream blocker was `STRUCTURED_PROPOSAL_NOT_AVAILABLE`; the execution firewall remained `BLOCKED_KILL_SWITCH`.
- Controlled-submit, controlled-management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero. Exactly one production `.order_send(` call-site remains and `src/` retains zero `MetaTrader5` imports; `RESULT_UNKNOWN` automatic retry remains prohibited.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `LEVEL_AND_EDGE_TRIGGER_SEMANTICS_COMPLETE`.

# 94. REALTIME AUTONOMOUS STRUCTURED PROPOSAL OBSERVABILITY

- The realtime proposal path now preserves the existing provider result instead of collapsing provider, transport, parse, schema, and legitimate no-proposal outcomes into `STRUCTURED_PROPOSAL_NOT_AVAILABLE`.
- `AutonomousOrderProposalResult` exposes only redacted operational telemetry: provider/model identifiers, invocation and retry counts, transport/parse/schema status, proposal status, and one reason code. Prompts, provider responses, credentials, account identifiers, and protected proposal values are not persisted.
- A valid structured `NO_PROPOSAL` is now reported as `VALID_NO_PROPOSAL` with its model reason codes and creates no Candidate. Provider unavailability, timeout/transport failure, invalid JSON, invalid schema, entry-condition blockers, and valid proposals remain distinct fail-closed outcomes.
- The existing reasoning-evidence summary and monitor projection carry this telemetry through the assembler and coordinator. Streamlit only renders the authoritative projection and does not invoke the provider.
- Deterministic focused and neighboring verification passed with `148 passed`, `182 passed`, and `67 passed` for canonical acceptance, including all 60 canonical cases. Final full regression passed with `3,684 passed`, `156 subtests passed`, and three unchanged warnings.
- App restart without rebuild, healthy container, and Streamlit `200 ok` passed. Runtime configuration selected the existing Groq structured-reasoning provider/model with its credential present; no secret value was printed or persisted.
- The bounded live provider observation was not run after restart because the only persisted Standing Trading Mandate expired at `2026-08-10T10:19:26.140980+00:00`. The protected store, mode, and mandate integrity remained valid, but `load_supervisor_strategy` correctly returned `SUPERVISOR_MANDATE_INACTIVE`.
- Controlled-submit, controlled-management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero. Execution and management kill switches remained engaged.
- Verification level: `FULL_REGRESSION_PASS`. Implementation is complete; runtime acceptance remains blocked until the operator explicitly grants a fresh bounded DEMO mandate. Verdict: `REALTIME_AUTONOMOUS_STRUCTURED_PROPOSAL_INCOMPLETE`.

# 95. DETERMINISTIC AUTONOMOUS STRATEGY AUTHORITY

- A complete explicit autonomous strategy no longer asks the structured-reasoning provider to decide whether an already-satisfied deterministic rule may produce a Candidate. Advisory and open-ended requests retain provider-owned `VALID_NO_PROPOSAL` behavior.
- The existing editable-trade Draft calculator now supplies deterministic Entry, SL, TP, risk, and broker-normalized volume from current market, account, and symbol evidence without persisting an intermediate Draft or adding another proposal architecture.
- The MT5 bridge account projection now preserves its authoritative `account_environment`; deterministic strategy assembly requires that value to be exactly `DEMO` and still verifies the redacted account hash against the market bundle before calculation.
- Existing false-condition, EDGE trigger, active-opening, lifecycle, reconciliation, mandate, risk, broker-constraint, idempotency, and execution-firewall checks remain authoritative. Candidates remain non-executable and contain no execution permission.
- Focused calculator/account tests passed with `78 passed`; autonomous/mandate/EDGE neighbors passed with `200 passed`; canonical acceptance passed with `67 passed`, including all 60 canonical cases.
- Final full regression passed with `3,691 passed`, `156 subtests passed`, and three unchanged warnings. Compileall, diff, documentation, static safety, app health, and Streamlit `200 ok` checks passed.
- One natural completed XAUUSDm M1 bar produced `LEVEL`, `CONDITION_TRUE`, `ENTRY_ELIGIBLE`, one deterministic proposal, and one integrity-valid persisted `OPEN_POSITION` Candidate with provider invocations `0`. The later policy boundary remained blocked by account-reference validation and the engaged execution kill switch.
- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero. Exactly one production `.order_send(` call-site remains and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `DETERMINISTIC_AUTONOMOUS_STRATEGY_AUTHORITY_COMPLETE`.

# 96. AUTONOMOUS ACCOUNT-CONTEXT BINDING

- The first post-Candidate mismatch was in `AutonomousTradingCoordinator`: it passed the Candidate's typed `account_context_...` reference to an autonomous-policy input whose established contract requires the current 64-character account fingerprint hash, while also hardcoding the account-match result to true.
- The Candidate contract remains unchanged. Its protected account reference is deterministically derived from the authoritative bridge `account_id_hash`, persisted in the protected Candidate journal, and preserved by strict reload.
- Before autonomous policy evaluation, the coordinator now independently rebuilds that typed reference from the current protected account capture and compares it with the Candidate reference. It separately passes the current fingerprint hash to the policy and leaves the Standing Mandate bound to the same fingerprint hash.
- Missing or invalid protected account hashes, changed fingerprints, mismatched Candidate references, stale context, unknown/non-DEMO context, revoked or expired mandates, and mandate/account mismatches remain fail-closed. Advisory and human-confirmed branches remain unchanged.
- A matching Candidate now passes the account-reference gate and reaches the later Standing Mandate kill switch, which remains engaged and returns `KILL_SWITCH_ENGAGED` without creating Candidate authorization or execution authority.
- Verification: focused Candidate/account/policy/mandate/approval/supervisor tests passed with `171 passed`; post-entry management and multi-symbol neighbors passed with `41 passed`; canonical acceptance passed with `67 passed`, including all 60 canonical cases.
- Final full regression passed with `3,694 passed`, `156 subtests passed`, and three unchanged warnings.
- App, Streamlit, and bridge health checks passed. A new live Candidate cycle was not run because the only persisted DEMO Standing Mandate had expired; no authority was created automatically.
- Controlled-submit, controlled-management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero. Execution and management kill switches remained engaged.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `AUTONOMOUS_ACCOUNT_CONTEXT_BINDING_COMPLETE`.

# 97. AUTONOMOUS EXECUTION PERMISSION CONTRACT

- The app-side autonomous execution chain now uses one permission snapshot projection across mandate pre-submit validation and controlled-adapter admission. The snapshot includes app adapter, controlled execution, autonomous execution, pending-family, global execution, policy-gate, and kill-switch state.
- Standing Mandate pre-submit preserves the historical non-executable acceptance state while also accepting a fully execution-ready state. It does not mutate configuration. Human-confirmed pre-submit behavior is unchanged.
- Final validation continues to hash and protect the permission snapshot. Mandate request construction verifies that hash, and the adapter requires the current snapshot to exactly match the protected snapshot before any controlled client call.
- The execution-ready predicate now matches adapter semantics instead of requiring the opposite values. Pending requests additionally require their existing pending family permission; MARKET requests do not widen pending permissions.
- Bridge authentication, DEMO/account revalidation, mandate integrity, mode validation, idempotency, unknown-result handling, bridge permissions, bridge kill switch, and the isolated `order_send` boundary remain independently enforced.
- Focused permission/pre-submit/adapter/authority/coordinator tests passed with `134 passed`. Canonical acceptance passed with `67 passed`, including all 60 canonical cases. Full regression passed with `3,707 passed`, `156 subtests passed`, and three unchanged warnings.
- No runtime permission or kill switch was changed. Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero; one production `.order_send(` call-site and zero `MetaTrader5` imports under `src/` remain.

# 98. AUTONOMOUS MONITOR EXECUTION PERMISSION CONTRACT

- Root cause: the completed-bar monitor retained an acceptance-era list that rejected every enabled execution flag. After the monitor became the scheduler for the production autonomous coordinator, that stale guard made the execution-ready path unsatisfiable and returned `MONITOR_EXECUTION_PERMISSION_ENABLED` before market acquisition.
- The monitor now consumes the shared execution permission projection and accepts exactly two coherent states: fail-closed observation-only and fully execution-ready autonomous opening. Mixed states return `MONITOR_PERMISSION_STATE_INCOHERENT` before market acquisition.
- Observation-only monitoring retains hard blocks and engaged kill switches. Execution-ready monitoring does not grant authority; policy, Standing Mandate, account binding, final validation, pre-submit, protected permission snapshot, adapter, bridge, and idempotency checks remain independent.
- A deterministic production-path test now reaches completed-bar handling, Candidate creation, policy, mandate, pre-submit, and adapter admission under coherent execution-ready permissions without broker mutation. Existing completed-bar deduplication and restart no-replay behavior remain unchanged.
- Focused monitor/permission/coordinator tests passed with `41 passed`; neighboring autonomous/authority/lifecycle/bridge tests passed with `182 passed`. Canonical acceptance passed with `67 passed`, including all 60 canonical cases. Full regression passed with `3,713 passed`, `156 subtests passed`, and three unchanged warnings.
- Controlled-submit, runtime `order_send`, MT5 writes, broker mutations, and provider calls remained zero. One production `.order_send(` call-site and zero `MetaTrader5` imports under `src/` remain.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `AUTONOMOUS_MONITOR_EXECUTION_CONTRACT_COMPLETE`.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `AUTONOMOUS_EXECUTION_PERMISSION_CONTRACT_COMPLETE`.

# 99. DETERMINISTIC AUTONOMOUS CANDIDATE ELIGIBILITY

- Root cause: Candidate classification reused advisory readiness as its intent authority. A valid deterministic `EDITABLE_TRADE_DRAFT` was therefore downgraded to `NO_ACTION / NOT_ELIGIBLE` when readiness returned `WAIT` or `NO_TRADE`, before the autonomous policy could report its own deterministic blocker.
- A valid deterministic opening Draft now produces `OPEN_POSITION / ELIGIBLE_CANDIDATE`; strict persistence, reload, and completed-bar duplicate protection preserve that result.
- Candidate classification and execution policy remain separate. `WAIT` or `NO_TRADE` still blocks later at policy with `OPEN_POLICY_NOT_READY`, while hard risk blockers remain `RISK_RESULT_BLOCKED`.
- False conditions, advisory `NO_PROPOSAL`, active-entry protection, account binding, mandate authorization, execution permissions, and broker boundaries remain unchanged.
- Focused and neighboring autonomous/policy tests passed with `137 passed`. Canonical acceptance passed with `67 passed`, including all 60 canonical cases.
- Full regression passed with `3,717 passed`, `156 subtests passed`, and three unchanged warnings. Documentation integrity, compileall, diff, and static safety checks passed.
- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero. Exactly one production `.order_send(` call-site remains and `src/` retains zero `MetaTrader5` imports.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `DETERMINISTIC_AUTONOMOUS_CANDIDATE_ELIGIBILITY_COMPLETE`.

# 100. DETERMINISTIC DRAFT AUTONOMOUS POLICY ALIGNMENT

- Root cause: Candidate classification already treated a valid `EDITABLE_TRADE_DRAFT` with advisory readiness `WAIT` or `NO_TRADE` as an eligible deterministic opening, but the later autonomous policy gate still required the advisory-only `REVIEW_READY` value. The same production Candidate therefore stopped at `OPEN_POLICY_NOT_READY`.
- The policy gate now reuses the existing deterministic Draft readiness contract. A valid deterministic Draft may reach `CONTROLLED_OPEN_POSITION`; ordinary non-deterministic `WAIT` remains blocked, and hard risk, lifecycle, account, mandate, freshness, idempotency, permission, and bridge checks remain unchanged.
- Focused autonomous policy/strategy tests passed with `46 passed`. Canonical acceptance passed with `67 passed`, including all 60 canonical cases. Full regression passed with `3,718 passed`, `156 subtests passed`, and three unchanged warnings.
- Bounded DEMO rerun used an operator-approved mandate aligned with the repository's 1% DEMO sizing policy. The earlier volume/risk mismatch and `OPEN_POLICY_NOT_READY` contract defect were resolved without copying Candidate values or widening unrelated scope.
- The final runtime rerun did not receive a new completed XAUUSDm M1 bar during the bounded observation window, so no new Candidate, pre-submit artifact, adapter call, bridge mutation, or `order_send` occurred. The supervisor was stopped, the temporary mandate was revoked, and app/bridge configuration was restored byte-for-byte to fail closed.
- Verification level: `FULL_REGRESSION_PASS`. Runtime verdict remains `DEMO_AUTONOMOUS_ORDER_SEND_END_TO_END_BLOCKED` with first remaining blocker `NO_FRESH_COMPLETED_M1_BAR`.

# 101. EXACT LIFECYCLE EVIDENCE BINDING

- Root cause: lifecycle matching fell back from a missing broker correlation tag to every row with the same symbol and direction. Evidence from a later confirmed BUY execution was therefore assigned to an older rejected BUY execution and produced a false persistent `CONFLICTING_VOLUME_OR_DIRECTION` discrepancy.
- Lifecycle evidence now binds only through the existing correlation tag or protected broker-result references. Same-symbol/direction rows without either binding are not attributed to that execution.
- Strict journal reads, account matching, missing-evidence discrepancies, unmatched-position detection, reconciliation, idempotency, and fail-closed behavior remain unchanged.
- Focused lifecycle/reconciliation tests passed with `46 passed`; lifecycle/reconciliation/coordinator/monitor neighbors passed with `69 passed`. Full regression passed with `3,719 passed`, `156 subtests passed`, and three unchanged warnings.
- A read-only DEMO lifecycle cycle reported `HEALTHY`, account match true, zero discrepancies, one historical `BROKER_REJECTED` record, and one `POSITION_CLOSED` record. No execution permission, controlled-submit, runtime `order_send`, MT5 write, or broker mutation occurred during the repair.
- Verification level: `FULL_REGRESSION_PASS`.

# 102. AUTONOMOUS MANDATE-AWARE DETERMINISTIC SIZING

- Root cause: deterministic autonomous Draft sizing used only configured account-risk policy and broker metadata. Standing Mandate risk and volume limits were first applied after Candidate persistence, so a valid but permanently unauthorized Candidate could be stored.
- The production autonomous assembler now reloads the active account-bound Standing Mandate for every fresh deterministic proposal and passes only its typed maximum-risk, maximum-volume, and authority reference projection into the existing Draft calculator.
- Deterministic sizing uses the lower policy/mandate risk budget, caps volume by the lower mandate/broker maximum, floors to broker step, and recalculates actual risk. A constrained result below broker minimum fails closed and is never rounded upward.
- Policy risk, mandate risk, effective budget, broker volume metadata, mandate volume cap, proposed volume, and actual risk retain separate protected provenance through strict Draft persistence/reload.
- Human-confirmed and unconstrained Draft behavior is unchanged. `TradingAuthorityService` remains the independent final mandate authorization check and still rejects tampered or out-of-limit Candidates.
- Focused mandate-aware sizing tests passed with `68 passed`; neighboring autonomous, mandate, sizing, policy, and lifecycle tests passed with `196 passed`; canonical acceptance passed with `67 passed`, including all 60 canonical cases.
- Final full regression passed with `3,728 passed`, `156 subtests passed`, and three unchanged warnings. No execution configuration, controlled-submit, runtime `order_send`, MT5 write, or broker mutation was changed or invoked.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `AUTONOMOUS_MANDATE_AWARE_SIZING_COMPLETE`.

# 103. CONTINUOUS AUTONOMOUS CHAT RUNTIME CONTINUITY

- Current account trade-state questions are distinguished from conceptual knowledge before the structured semantic provider selects `KNOWLEDGE`. Multilingual P/L, position, pending-order, SL/TP, volume, history, lifecycle, and provenance reads retain the existing `POSITION_MANAGEMENT` read contract.
- The active conversational trading request is reloaded with only the semantic state stored on the same assistant artifact. A later unrelated answer cannot be paired with that older trading request.
- Chat submission now renders the existing persisted mandate/runtime panel in the same Streamlit run. Unrelated chat turns do not hide the controls, replace the strategy, reset mandate limits, or stop the continuous Supervisor.
- Standing Mandate widgets initialize through session defaults and authoritative persisted-mandate synchronization, avoiding conflicting widget defaults while preserving the store as authority.
- Focused position-read, conversational, thin-UI, dashboard, and mandate tests passed with `108 passed` and two unchanged dependency warnings.
- Runtime acceptance passed in one active DEMO conversation: current P/L and SL/TP used `position_state_read` and `position_read`; `ATR là gì?` retained the normal knowledge path. The panel remained visible, Supervisor remained running, lifecycle remained `HEALTHY`, and reconciliation discrepancies/unresolved states remained zero.
- After a natural reload, the persisted mandate limits remained `0.01 / 100 / 5 / 5 / 500` and the selected mandate/Supervisor state remained present. The read-only position queries caused no controlled-submit, `order_send`, MT5 write, or broker mutation.
- Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `AUTONOMOUS_CHAT_RUNTIME_CONTINUITY_COMPLETE`.

# 104. CONVERSATION-SCOPED TRADING OWNERSHIP

- Each conversational trading request now derives one stable protected `trading_scope` from its conversation ID. The scope persists through typed strategy identity, autonomous inputs, protected Candidate provenance, Standing Mandate strategy binding, supervisor ownership, and exact position/history provenance.
- Identical strategy semantics in separate conversations produce distinct strategy and runtime identities. Streamlit lists and controls only the mandate and supervisor bound to the current strategy scope; stopping one scoped supervisor leaves other scoped supervisors running.
- Position and history reads default to the current conversation scope. Explicit account-wide requests retain the existing global read behavior. Raw conversation IDs are never persisted in trading artifacts; public Candidate and position projections do not expose the derived scope reference.
- MT5 account context, broker positions/orders, lifecycle, reconciliation, permission gates, and execution safety remain account-global. A same-symbol active Candidate, order, or position still blocks another opening with `ENTRY_ALREADY_ACTIVE`; conversation scope does not partition broker risk or bypass idempotency.
- Read-only DEMO runtime verification produced two distinct conversation scopes. Each scope returned zero owned positions, orders, and history, while an explicit account-wide read returned the five authoritative broker-history records; all reads retained account match and no blockers.
- Focused and neighboring request, Candidate, authority, supervisor, position-read, policy, and thin-UI tests passed with `279 passed` and unchanged dependency warnings. Changed-path compileall and diff checks passed.
- No full regression was run because the approved task requested focused verification by default. No controlled-submit, runtime `order_send`, MT5 write, or broker mutation was performed.
- Verification level: `FOCUSED_PASS`. Verdict: `CONVERSATION_SCOPED_TRADING_OWNERSHIP_COMPLETE`.

# 105. PROFESSIONAL TRADING WORKSPACE UI

# 106. NOISY TRADE-STATE SEMANTIC ROBUSTNESS

- The existing one-call structured semantic boundary now explicitly interprets meaning through minor spelling mistakes, missing or incorrect diacritics, Unicode normalization differences, informal abbreviations, and noisy multilingual wording. It does not add a spell-correction service, keyword router, regex parser, or second semantic path.
- Obvious current account/trade-state reads continue through `POSITION_MANAGEMENT -> position_state_read -> position_read`; conceptual P/L, indicator, and unrelated financial questions remain `KNOWLEDGE`.
- Focused semantic interpreter, QueryPlan, and position-read tests passed with `92 passed` and two unchanged dependency warnings.
- One new live Streamlit query, `tổng lời lổ hiện tại`, produced one valid `POSITION_MANAGEMENT` interpretation, one `position_state_read` QueryPlan, and one successful authoritative `position_read` acquisition. The public result remained `NON_EXECUTABLE`.
- The old two-message conversation containing the prior RAG blocker remained byte-for-behavior unchanged. Switching back to it reloaded its persisted answer without another provider call.
- No Candidate, confirmation, controlled-submit, runtime `order_send`, MT5 write, or broker mutation occurred. Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `NOISY_TRADE_STATE_SEMANTICS_COMPLETE`.

- The Streamlit shell now uses one shared operational theme with a compact product header, restrained navigation, dense metrics, consistent controls, and responsive desktop/mobile behavior.
- Advisory remains conversation-led. Operations keeps the authoritative market, account, lifecycle, mandate, Supervisor, Candidate, and permission projections while placing legacy execution diagnostics behind one collapsed disclosure.
- Evaluation and Settings use the same visual hierarchy without changing their services, persistence, feature flags, or widget authority.
- Existing widget keys, callbacks, typed requests, trading scope, mandate ownership, Supervisor ownership, Candidate generation, lifecycle, and execution boundaries are unchanged.
- Focused UI and neighboring tests passed with `68 passed` and two unchanged dependency warnings. Live Streamlit verification covered all four tabs plus desktop/mobile overflow and exception checks.
- No candidate generation, confirmation, controlled-submit, `order_send`, MT5 write, or broker mutation was performed.
- Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `TRADING_WORKSPACE_UI_REDESIGN_COMPLETE`.

# 107. EDITABLE DRAFT DEPENDENCY RECALCULATION

- Draft revisions now validate Entry, policy-derived Stop Loss, reward:risk-derived Take Profit, and RR from one coherent revision. Derived target values are recomputed before conflict validation.
- Recalculated revisions retain only unresolved semantic prerequisites from the prior revision; deterministic blockers such as `TARGET_POLICY_CONFLICT` are evaluated again instead of being copied forward.
- Explicit incompatible user TP and RR values still produce `TARGET_POLICY_CONFLICT`. Previous immutable revisions and the existing `NON_EXECUTABLE` Draft boundary remain unchanged.
- Focused Draft tests passed with `32 passed`; neighboring Draft lifecycle, strategy completion, thin-UI, and semantic tests passed with `79 passed` and two unchanged dependency warnings.
- Live Streamlit verification created revision 4 from the affected protected Draft. Fresh ATR evidence produced coherent SL/TP at RR 2 and `VALID_NON_EXECUTABLE`; no Candidate, controlled-submit, `order_send`, MT5 write, or broker mutation occurred.
- No full regression was run for this bounded Draft-only correction. Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `EDITABLE_DRAFT_DEPENDENCY_RECALCULATION_COMPLETE`.

# 108. EDITABLE DRAFT MARKET EVIDENCE REFRESH

- The existing Draft UI now exposes an explicit `Refresh Market Evidence` action beside Candidate creation. It reuses `_load_trade_draft_evidence()` and the existing immutable `apply_patch()` revision path without changing operator parameters.
- Refresh preserves valid `USER_EXPLICIT` and `USER_EDITED` values, recomputes policy/system-derived Entry/SL/TP dependencies from current evidence, revalidates the new revision, and remains `NON_EXECUTABLE`.
- Refresh never creates a Candidate, confirmation, pre-submit artifact, execution authority, or broker mutation. Candidate creation remains a separate explicit action and retains the existing freshness validator.
- Focused Draft, thin-UI, and Candidate lifecycle tests passed with `61 passed` and two unchanged dependency warnings.
- Live DEMO Streamlit verification refreshed the affected stale Draft from revision 4 to 5. Volume `0.03` remained user-owned, ATR-derived SL and RR-derived TP changed coherently, and the UI rendered `VALID_NON_EXECUTABLE` with the new observed timestamp.
- The subsequent explicit Candidate action passed freshness and stopped at the independent pre-existing `DRAFT_MODE_AUTHORITY_MISMATCH` gate. No Candidate was automatically created and no controlled-submit, `order_send`, MT5 write, or broker mutation occurred.
- No full regression was run for this bounded UI/workflow change. Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `EDITABLE_DRAFT_MARKET_REFRESH_COMPLETE`.

# 109. HUMAN-CONFIRMED DEMO CONTROLLED EXECUTION

- The existing human-confirmed workflow now continues from a protected Candidate confirmation through final validation, `PRE_SUBMIT_READY_NON_EXECUTABLE`, a separate exact controlled-submission phrase, the authenticated host bridge, and the single isolated production `order_send` boundary.
- The controlled request is rebuilt only from strict persisted Candidate, confirmation, account-context, and pre-submit artifacts. Exact hashes, bindings, expiry, DEMO environment, protected permission snapshot, and idempotency remain independently validated before submission.
- Human pre-submit accepts either the historical fail-closed permission profile or one coherent controlled-execution-ready profile. The protected pre-submit remains non-executable and a later permission change fails with `PERMISSION_SNAPSHOT_MISMATCH`.
- Draft evidence refresh recalculates market-owned Entry with dependent SL/TP values. An advisory methodology-fit veto no longer overrides an explicit valid human Draft, while deterministic risk, freshness, account, lifecycle, and broker blockers remain authoritative.
- Lifecycle preserves a previously proven terminal close when later broker evidence is absent, while new confirmed executions still bind through exact protected evidence. MARKET requests with semantic price zero resolve to the current broker side at the bridge validation boundary.
- Live DEMO acceptance created one fresh Draft and one `OPEN_POSITION / ELIGIBLE_CANDIDATE`, recorded one explicit confirmation, passed final validation, and performed exactly one controlled submission. The protected result was `RESULT_CONFIRMED` with broker retcode `10009`; lifecycle reported `POSITION_OPEN` with `UNIQUE_POSITION_MATCH`, and the bridge exposed one matching redacted position.
- Focused changed-boundary tests passed with `203 passed`. Final hermetic full regression passed with `3,769 passed`, `156 subtests passed`, and three unchanged warnings. Compileall and runtime health checks passed.
- No retry or duplicate submission occurred. The account remained `DEMO`, authoritative mode remained `human_confirmed_live`, and no protected broker/account identifiers were exposed.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `HUMAN_CONFIRMED_DEMO_ORDER_SEND_COMPLETE`.

# 110. REPOSITORY ORIENTATION AND HOUSEKEEPING

- Reviewed the locked target, latest execution checkpoint, semantic/retrieval ingress, Draft/Candidate and authority wiring, completed-bar coordinator, Supervisor ownership, bridge entrypoint, and repository/configuration inventory against `88f175f`.
- Replaced stale advisory-only README claims and the obsolete June AI context snapshot with a current product overview, production owner map, mode/authority boundaries, retained verification, and supported runbook links. Historical architecture/sprint evidence remains intact.
- Removed only unreferenced root artifacts: the old `diff.txt` patch dump, duplicate `cmd_docker` notes, and empty `log_terminal`. Cleaned regenerable Python/pytest caches and the empty preflight diagnostic directory; retained protected debug records, ZIP backup, credentials, databases, dependencies, and `.agents/`.
- Added explicit Docker build exclusions for local key files, agent configuration, backups, diagnostics, trading journals/protected requests, embedding cache, and knowledge catalog. Existing images were not rebuilt or sanitized; exclusions apply to future builds, while Compose retains the existing data and environment mounts.
- Updated documentation integrity checks to assert current mode/safety semantics, project-map paths/local links, and required sensitive Docker exclusions. Focused documentation tests: `13 passed`; Compose configuration validation passed. Production source and dependency files were not changed; full regression and live acceptance were not repeated.
- Retained implementation verification remains the preceding checkpoint's `3,769 passed` plus `156 subtests passed`. This housekeeping does not establish current runtime health or trading authority.
- Verification level: `FOCUSED_PASS`. No provider, market, candidate, submission, or broker operation was performed.

# 111. COMMIT-INFORMED DEAD-CODE CLEANUP

- Reviewed the implementation history through `88f175f`, including the locked target, autonomous runtime completion, strategy completion, deterministic sizing, conversation ownership, and human-confirmed DEMO execution commits. Added a current reading guide without rewriting historical milestone evidence.
- Deleted 20 orphan `errors.py` modules across calendar, decision, execution preparation, knowledge, market, proposal, reasoning, review, and scoring. Their exception classes had no imports, exports, raises, catches, string references, or dynamic-loading consumers in the current tracked source/tests/config/docs. Active/exported error types remain unchanged.
- Deleted the unused `execution/receipt.py` re-export shim; `DryRunExecutionReceipt` remains in its canonical `models.py` and existing package exports. Deleted the two unreferenced root experiments `run_manual_test.py` and `test_reranker_manual.py`, then removed only their obsolete `collect_ignore` entries from root pytest bootstrap.
- Retained the hermetic provider guards and all supported manual MT5 CLIs, production authority/execution packages, fixtures, and regression coverage. Old sprint/check filenames alone were not treated as deletion evidence.
- Focused affected-family/documentation/hermetic tests: `262 passed`. Default full collection (`.\venv\Scripts\python.exe -m pytest -q`) passed `3,771 tests`, `156 subtests`, and three unchanged warnings in `155.77s`.
- The final preservation check found one existing simulation test had appended a rejected, non-executed simulated receipt to the local simulation journal. The original journal byte prefix remains intact; the extra row was retained. That test now injects the existing temporary journal store. Post-fix simulator/documentation verification passed `78 tests` with no further local-journal change; production code did not change after full regression.
- Offline verification loaded `.env.example` boolean defaults into the test process only; local `.env` and runtime permissions were not edited. Compileall, Compose configuration, and static safety checks passed: one production `.order_send(` call-site, zero `MetaTrader5` imports under `src/`.
- No new trading behavior, dependencies, account authority, runtime restart, provider call, candidate, or broker operation was introduced. Full regression proves repository compatibility; live DEMO behavior was not rerun.
- Verification level: `FULL_REGRESSION_PASS`. Known limit: local backup/private stores and actively exported compatibility contracts remain intentionally preserved.

# 112. TARGET-ALIGNED UNUSED DEFINITION CLEANUP

- Re-read the locked target and traced existing runtime/diagnostic consumers before deleting more source. Shared preflight, permission, bridge, lifecycle, and supported diagnostic workflows remain intact; age and file count are not deletion criteria.
- Removed eight unreferenced definitions in seven existing modules: unused evidence/embedding result containers, OCR metadata helper, coordinator account-context factory, disabled reasoning provider, previous-level wrapper, and two chatbot helpers. Graph inbound references and tracked source/test/config/document references were checked before removal; no replacement abstraction was added.
- Focused affected evidence, parser, embedding, coordinator, trigger, reasoning, conversational UI, simulation, and documentation tests: `341 passed`, two unchanged warnings. Final default full regression: `3,771 passed`, `156 subtests passed`, three unchanged warnings, `135.73s`.
- Offline tests used process-local boolean defaults from `.env.example`; local `.env` and operating permissions were not changed. Compileall and Compose configuration passed; static invariants remain one production `.order_send(` call-site and zero `MetaTrader5` imports under `src/`.
- Preservation checks cover 117 original private/local files. The previously recorded single simulation-only receipt append from section 111 remains retained; this verification introduced no further simulation-journal change. Embedding cache, `.agents/`, credentials, backups, and other protected records remain unchanged by this cleanup.
- No provider, live market, candidate, submission, or broker operation was invoked. Existing running services were not restarted or rebuilt; live behavior was not reaccepted. Verification level: `FULL_REGRESSION_PASS`.

# 113. ACCOUNT-AWARE LIFECYCLE RECOVERY

- Root cause: `MT5PositionLifecycleSupervisor._run_cycle()` classified every account's historical execution against the connected snapshot. Six old-account confirmed executions with integrity-checked, account-bound `POSITION_CLOSED` evidence and one rejected execution therefore caused seven false current-account discrepancies.
- The existing supervisor now excludes only terminal foreign-account history: rejected executions, or confirmed executions with a persisted closed observation bound to the original account. A tag appearing in the current snapshot prevents exclusion. The classifier's account comparison remains unchanged.
- Foreign unresolved/unknown executions, missing or invalid fingerprints, journal failures, current-account conflicting evidence, and current unmatched positions/orders remain blocking. Foreign unresolved records are not rewritten or resolved from the wrong account. Missing/stale snapshot timestamps fail closed. Dashboard projects terminal-history and foreign-recovery counts from the shared lifecycle status.
- Focused lifecycle/read-model/coordinator/management/pre-submit/UI tests passed `136 tests`; final lifecycle/release-closure tests passed `51 tests`. The first full regression exposed an outdated assertion counting only account mismatch, not the additionally detected unmatched current position; that assertion now expects both blockers. Final full regression passed `3,787 tests`, `156 subtests`, three unchanged warnings, `168.05s`.
- Tests used process-local offline boolean defaults, without editing `.env`. An initial neighboring run with execution-enabled local defaults was rejected by the existing offline harness; no live execution occurred. Compileall, diff checks, and static invariants passed: one production `order_send` call-site; no `MetaTrader5` imports under `src/`.
- After an app restart without rebuild, mounted source hashes matched the host. Actual authenticated MT5 DEMO observations reported lifecycle `HEALTHY`, account match true, zero discrepancies, seven terminal historical records excluded, zero foreign unresolved records, and zero new lifecycle observations. Operator status agreed; PositionReadModel was `AVAILABLE`, with zero positions/orders/history and no blockers. App became healthy and Streamlit returned `200 ok`.
- All original execution/lifecycle evidence remains retained, including the earlier account-change and bridge-unavailable observations; current health is a fresh projection, not a rewrite of historical states. Execution permissions, kill switches, authority, and unrelated cleanup were not changed. No Candidate, mandate, controlled-submit, management write, `order_send`, or broker mutation occurred.
- Verification level: `FULL_REGRESSION_PASS`. Verdict: `ACCOUNT_AWARE_LIFECYCLE_RECOVERY_COMPLETE`. This proves read-only account-switch recovery, not a new trade acceptance or autonomous operational readiness.

# 114. FRESH HUMAN-CONFIRMED DEMO DRAFT AND CANDIDATE ACCEPTANCE

- Reused the existing completed human-confirmed conversation strategy: BUY XAUUSD/XAUUSDm, RSI14 M15 greater than 10. No raw chat reinterpretation, invented strategy, mode grant, mandate, or autonomous Supervisor startup was used.
- Fresh authenticated DEMO preflight confirmed the current account/mode binding, lifecycle `HEALTHY`, zero discrepancies/foreign unresolved records, and no open positions. Existing execution permissions and kill switches were inspected and left unchanged.
- One explicit Streamlit `Refresh Market Evidence` created immutable Draft revision 2 from real broker evidence at `2026-11-03T10:53:25.280000+00:00`. Market Entry refreshed to 3904.892, policy SL/TP to 3896.168/3922.34 at RR 2; configured risk fraction stayed 0.01, calculated volume became 0.11, and calculated risk was 95.964 USD. Previous revision remains retained; no operator parameters were changed.
- One `Create Candidate` click produced one protected `OPEN_POSITION / ELIGIBLE_CANDIDATE`, schema v2, mode `human_confirmed_live`. Streamlit showed exactly one `VALID / FRESH / NON_EXECUTABLE` Review Card, with no validation blockers. MARKET Candidate entry price remains unset by contract; bridge-side price resolution is a later execution boundary, not a missing Draft price.
- Independent strict Candidate/market-snapshot/runtime-evidence reload passed, including current account reference, Draft revision source, strategy identity, broker symbol/profile and volume min/max/step checks. All Candidate execution/confirmation flags remained false. Candidate generated at `2026-11-03T10:53:42.914515+00:00`, expires at `2026-11-03T10:58:42.914515+00:00`; it was unexpired at the final integrity check. Expiry remains enforced and acceptance is not permission to confirm a stale Candidate later.
- Protected journal delta was exactly one Draft revision plus one Candidate; all original bytes remained intact. Confirmation, pre-submit, authority, execution, mandate, and management stores were unchanged. No controlled-submit, `order_send`, MT5 write, broker mutation, or simulated fill occurred.
- Existing focused Draft/Candidate/thin-UI tests passed `61 tests`, two unchanged warnings. Production source/tests were not changed for this acceptance; no full regression, rebuild, or restart was required. Verification level: `FOCUSED_AND_LIVE_PASS`. Verdict: `FRESH_HUMAN_CONFIRMED_DEMO_CANDIDATE_ACCEPTANCE_COMPLETE`.

# 115. CURRENT-ACCOUNT HUMAN-CONFIRMED DEMO EXECUTION ACCEPTANCE

- The operator personally confirmed a fresh Candidate and separately authorized controlled submission in Streamlit. No automated consent or submission click, expired Candidate reuse, or retry.
- Protected execution recorded `RESULT_CONFIRMED` at `2026-11-03T11:22:43.427589+00:00`, retcode `10009`, matching the current DEMO account and Candidate. Exactly one `SUBMISSION_STARTED` and one `RESULT_CONFIRMED` exist for this idempotency key.
- Independent broker reads returned one BUY XAUUSDm position, volume 0.11, fill approximately 3904.282, SL 3896.414 and TP 3923.135, zero pending orders. Lifecycle correlated `POSITION_OPEN / UNIQUE_POSITION_MATCH`, current-account health healthy, discrepancies zero.
- PositionReadModel was available and account-matched with no blockers, but position provenance omitted Candidate/execution references. Exact correlation was verified through protected lifecycle evidence instead. No separate explicit reconciliation record was created; unknown-result recovery and position closure were not exercised.
- No production/test/configuration change, management write, second trade, autonomous startup, rebuild or full-regression rerun. Existing unrelated worktree and history retained; no commit or push.
- Verification level: `FOCUSED_AND_LIVE_PASS`; prior focused Draft/Candidate coverage 61 passed is retained, not rerun. Verdict: `HUMAN_CONFIRMED_DEMO_EXECUTION_ACCEPTANCE_COMPLETE`.

# 116. LIVE POSITION READ AND PROVENANCE ACCEPTANCE

- Fixed the existing PositionReadModel correlation boundary: a missing broker comment tag no longer loses execution ownership when exact protected broker-result references or integrity-checked, original-account-bound lifecycle references uniquely identify the execution. No symbol/volume/time-based guessing, new store or execution authority was added. Multiple matching executions or multiple active broker objects claiming one execution remain inconsistent; different-account matches fail closed.
- Preserved strict execution/lifecycle/Candidate reloads and conversation-scope filtering. Strategy, Draft, Candidate, execution and lifecycle provenance now resolve for the actual accepted DEMO trade. Authorization remains explicitly unavailable in this projection because the execution record lacks that field; separate strict reads verified the matching historical human confirmation and protected approval reference. This is a projection limitation, not proof of missing consent. No linked management evidence is projected or fabricated.
- Closed-trade direction now comes from the exact position-linked opening deal, not the opposite closing-deal direction. Missing opening evidence yields UNKNOWN and no invented entry price. Existing historical chat answers are preserved; new reads use corrected projections.
- Real authenticated observation while the position was open verified BUY XAUUSDm, 0.11 volume, fill approximately 3904.282, SL 3896.414, TP 3923.135 and broker-provided floating P/L. Later broker history verified closure at 3923.135, realized net P/L 207.39 USD, no open positions or pending orders. Close price matches the earlier TP, but the snapshot does not expose a closing reason code; TP causation is not claimed.
- Lifecycle now reports POSITION_CLOSED / LINKED_CLOSING_DEAL, HEALTHY, account match true, zero discrepancies and foreign unresolved records. Execution evidence still contains exactly one submission-start and confirmed result for this trade. No explicit unknown-result reconciliation or protected recovery mutation was performed.
- Browser acceptance at localhost:8501 showed the corrected BUY closed history and redacted provenance chain, with explicit unavailable fields. Mounted source hashes matched host source; app healthy and Streamlit 200. Only the app was restarted to load source; bridge/terminal were not restarted, and Docker was not rebuilt.
- Final focused read-model/lifecycle/human-management/autonomous-management/thin-UI/canonical tests: 232 passed, including all 60 canonical cases. Final full regression (`.\venv\Scripts\python.exe -m pytest -q`): 3,798 passed, 156 subtests passed, three unchanged warnings, 156.70s. Tests used process-local offline boolean defaults, not edits to .env; the initial neighboring run inherited local execution flags and was blocked by the offline harness. Earlier runs preceded the browser-proven direction correction and final duplicate-ownership guard; only the result above verifies the final source.
- Compileall and diff checks passed. Static invariants remain one production order_send call-site and zero MetaTrader5 imports under src/. Broker mutations, controlled-submit, order_send and MT5 writes performed by this sprint: zero. No Candidate, mandate, consent, autonomous runtime or management action was created. Original journals, unrelated dirty worktree, cache and .agents/ were not manually edited; no commit or push.
- Final Ponytail review: PASS after adding the duplicate active-owner negative control. Documentation integrity: 13 passed. Verification level: `FULL_REGRESSION_PASS`. Verdict: `LIVE_POSITION_READ_AND_PROVENANCE_ACCEPTANCE_COMPLETE`. Controlled post-entry management, partial-close runtime and unknown-result recovery remain unverified by this sprint.

# 117. REMAINING CLEANUP REVIEW AND SAFE CHECKPOINT

- Reviewed the 44 remaining tracked changes against e377ce7: 43 understood cleanup paths and one runtime embedding-cache change. The untracked .agents/ tree, local .env and protected trading stores remain private and excluded from staging.
- Accepted the existing 26 obsolete-file deletions, eight unused definitions in seven modules, obsolete collection-ignore removal, temporary simulation-test journal injection, Docker/Git context exclusions, and project/retention documentation. Graph callers and current source/test/config references for removed definitions were empty; canonical exports and supported operator workflows remain. Coordinator and reasoning changes remove unused helpers only, not active strategy, mandate, execution or recovery logic.
- Corrected stale current-baseline pointers without rewriting historical cleanup entries. No production refactor, dependency, mode/mandate/permission/kill-switch change, monitor restart, Docker rebuild or broker operation was introduced.
- Isolated full regression initially found one pre-existing observability expectation failure: blank structured provider/model configuration falls back to general provider/model in production, but the old test expected disabled/local metadata. The exact test failed on unmodified e377ce7 as well. Added explicit/fallback parameterized StaticModel fixtures in that test only; no provider was constructed or called externally for this correction.
- Final generated Git-index snapshot, without local .env, passed 3,799 tests and 156 subtests, three unchanged warnings, 135.49s (`.\venv\Scripts\python.exe -m pytest -q`). Focused groups passed 27, 183 and 90 tests; these groups overlap and are not a unique total. The first combined focused collection exposed an unchanged embedding-test Streamlit stub dependency; splitting embedding/parser and UI groups passed without modifying that unrelated test.
- Compileall, Compose configuration, staged diff and added-content secret checks passed. All 681 Python files in the tested snapshot matched the index after Git line-ending normalization. Static invariants remain one production order_send call-site and zero MetaTrader5 imports under src/. Final documentation-only updates are rechecked separately; no production/test changes followed the passing full run.
- Verification level: `FULL_REGRESSION_PASS`. Cleanup is suitable as a code baseline for a separately authorized autonomous DEMO readiness preflight, not evidence of current runtime health or autonomous broker execution. Existing test-order sensitivity, unavailable authorization projection and unverified management/recovery branches remain documented; no safety gate was weakened to obtain PASS.

# 118. SUPERVISOR UI STATE AND DEMO RISK DIAGNOSIS

- Fixed the existing Dashboard Start/Stop handlers to request a Streamlit rerun after a successful process-owner call. Disabled states now reload from the same scope-owned process status; exceptions show a redacted failure type without a success rerun. No process-manager, authority, sizing or execution contract changed.
- Focused Dashboard/runtime/supervisor-binding/mandate tests passed 67 tests, including six new fake-process UI cases for one-click transitions, disabled states, refresh without repeat calls, scope arguments and start/stop failures. Command: `.\venv\Scripts\python.exe -m pytest scripts/test_dashboard_authoritative_runtime_state.py scripts/test_autonomous_runtime_completion.py scripts/test_autonomous_supervisor_strategy_binding.py scripts/test_autonomous_mandate_prefill_review.py -q`. Final run supplied trading/MT5 boolean defaults from `.env.example` only to the test child process; earlier neighboring runs exposed incompatible execution-enabled local flags. Local `.env` and running permissions were not changed. Full regression was not run.
- Read-only DEMO evidence at 2026-11-04T07:10:18Z reproduced the sizing blocker mathematically without creating a Draft/Candidate: M1 ATR 3.5631428571428256, multiplier 1.5, BUY reference 4020.179, tick-rounded SL 4014.834, distance 5.345. Tick size/value 0.001/0.1 imply 534.5 USD risk per lot and 5.345 USD nominal risk at broker minimum 0.01 lot (maximum 200, step 0.01).
- Current mandate caps risk at 1 USD and volume at 0.01; policy risk 102.0739 USD is reduced to the 1 USD authorized budget. Risk-derived volume approximately 0.001870907 floors to 0.00, correctly causing `MANDATE_RISK_BUDGET_BELOW_BROKER_MINIMUM`. The minimum-risk figure is diagnostic, not approved replacement policy or a guarantee against slippage/gaps. No limit or stop policy was widened.
- Protected mode/mandate integrity and DEMO account binding passed. Mode was already autonomous_live; the current unrevoked mandate had its kill switch engaged and expires at 2026-11-04T07:26:17.032193Z. Max positions/trades per day are 1/1. Historical monitor result was BLOCKED at 06:59:08Z with no Candidate; no host/container autonomous worker was running. Current broker positions/orders and daily trades/loss were zero; strict journal reads and read-only lifecycle classification passed with no discrepancy or foreign unresolved execution.
- App-only restart loaded the matching Dashboard source; no Docker rebuild, real Supervisor launch, Candidate generation, LLM call, consent, mandate mutation, controlled-submit, order_send or broker mutation was performed. Compile and diff checks passed. Verification level: `FOCUSED_PASS`; real Start/Stop was intentionally not exercised. Unrelated cache, .agents/ and protected history remain excluded from Git changes. No commit or push.

# 119. SPRINT 9 LEGACY CANDIDATE JOURNAL COMPATIBILITY

- Diagnosed four completed M1 cycles on 2026-11-04 (07:33:55-07:36:14Z): RSI condition true, but active-entry inspection returned `COORDINATOR_CANDIDATE_STATE_UNAVAILABLE` before new Candidate generation. The first failed reload was an expired August protected Candidate containing the four earlier optional strategy fields but lacking only trading_scope; its journal row integrity was valid. This was a schema compatibility failure, not proof of a broker position or failed 20 USD risk sizing.
- The existing deserializer now accepts exactly three field sets: complete current payload, original supported legacy payload without all five optional fields, and the observed pre-scope payload missing only trading_scope. Unknown scope remains empty; no current scope/account/strategy/authority is invented. Other missing-field combinations, extra fields, malformed tuple fields, tampering and reference/provenance/idempotency conflicts remain rejected. No production journal migration, rewrite or re-signing occurred.
- Coordinator projection now reports `NO_ACTION / ENTRY_ALREADY_ACTIVE` only for a genuine active-entry blocker. Candidate-state failure remains `BLOCKED / COORDINATOR_CANDIDATE_STATE_UNAVAILABLE`, with opening eligibility UNAVAILABLE, before generation, policy, authorization or submission. The existing journal scan, active lifecycle checks, expiry check, LEVEL/EDGE semantics and safety gates remain in place.
- Focused orchestrator/coordinator tests: 69 passed. Adjacent monitor/strategy-binding/confirmation/pre-submit/read-model/mandate/Dashboard tests: 153 passed. Full current-worktree regression: 3,827 passed, 156 subtests, three dependency warnings, 130.75s. Commands used `.\venv\Scripts\python.exe -m pytest ...`; full command was `.\venv\Scripts\python.exe -m pytest -q`. Trading/MT5 boolean defaults from .env.example were supplied only to test child environments, preserving live .env/permissions. Prior uncommitted UI changes are included in this verified worktree; no commit was created.
- After app-only restart without rebuild, read-only production checks loaded 67 protected Candidates without exceptions; one pre-existing summary-only row still has no protected payload and returns None. Decision journal bytes remained identical. The active-entry guard, evaluated read-only against current broker/lifecycle evidence, returned no blocker. This did not create a Draft/Candidate or exercise execution. Final preservation checks found only a normal app-generated lifecycle append; all original lifecycle bytes remain an exact prefix, and decision/authority/execution records, .env, cache and .agents/ remain unchanged.
- Current DEMO account/mode binding and authority integrity passed; lifecycle POSITION_CLOSED, zero discrepancies/foreign unresolved, positions/orders/trades today/loss today zero, no host/container autonomous worker. The only current-account execution remains yesterday's confirmed human trade. Mandate v3 expired at 2026-11-04T07:56:46.690149Z and must not be reused.
- Compileall and diff checks passed; production order_send call-sites remain one, with zero MetaTrader5 imports under src/. No LLM call, real monitor startup, Candidate generation, mandate/mode/kill-switch change, controlled-submit or broker mutation. Existing cache, .agents/, .env and historical records preserved; no commit/push. Verification level: `FULL_REGRESSION_PASS`. Verdict: `LEGACY_CANDIDATE_RELOAD_FIXED`. Autonomous broker E2E remains unverified; a separately approved fresh mandate and preflight are required before another acceptance.

# 120. SPRINT 10 RUNTIME RELIABILITY AND OBSERVABILITY

- Retained Sprint 9 acceptance subsequently proved autonomous Candidate-to-broker correlation, mandate v4 authorization, one BUY and a linked closing deal with raw reason 4 / DEAL_REASON_SL. This historical evidence establishes AUTONOMOUS_DEMO_E2E_PASS, not profitability or 24/7 reliability; Sprint 10 performed no trading acceptance.
- Read-only preflight found no host/container autonomous workers, one protected DEMO BUY position and no pending orders, discrepancies or unknown current-account results. The distinct latest mandate was v5 (two trades/day, risk/daily-loss 20 USD, volume 0.01), expired at 2026-11-04T17:20:31.118764Z. Protected submission records for v4/v5 were before their respective expiry; no later submission was found. Existing position protection was left untouched.
- Closed history now joins closing deal -> unique position-linked opening deal -> exact opening-order reference and position reference. Historical broker order SL/TP is projected; absent evidence remains unavailable. Duplicate orders/openings, conflicting position references, foreign-account and ambiguous execution evidence fail closed. No symbol/time/volume matching or journal rewrite was added.
- The existing scope-owned process owner retains one atomic sanitized diagnostic record per scope under data/cache/supervisor_status/: launch, redacted references, observed exit code, stop request/completion and STOPPED/RUNNING/EXITED/FAILED states. Refresh only observes. Loss of an owned handle after app restart is UNKNOWN and blocks duplicate startup, not proof that a worker stopped; no automatic restart or PID-based adoption was added. Diagnostic-write failure blocks launch but never prevents operator stop. stdout/stderr remain DEVNULL; raw tracebacks and secrets are not collected.
- Streamlit independently displays process state and CURRENT/HISTORICAL/UNAVAILABLE monitor evidence with evaluation time/blocker. Setup diagnostics distinguish ACCOUNT_CONTEXT from BROKER_MARKET_EVIDENCE and bounded DNS/timeout/network/refusal/HTTP/TLS categories without raw URLs or exception payloads. Tick reads retain the existing fail-closed empty-evidence behavior. No authority mutation retry was introduced.
- Setup currently depends on app -> authenticated bridge account capture -> protected mode/account binding -> bridge tick/metadata, not an external LLM or market API. Host/terminal and Docker/bridge checks were healthy; the old network incident is HISTORICAL_CAUSE_UNCONFIRMED. Source tests exercise transient failures and successful recovery without granting authority.
- Expiry/revocation behavior was preserved, not rewritten: supervisor strategy reload and fresh authorization reject inactive mandates; exact Candidate authorization expires no later than mandate/Candidate validity. Later fake-clock attempts cannot append authorization. Read-only positions/protection remain available without active authority; expiry does not liquidate a position. Existing management, daily-limit, duplicate-entry and unknown-result protections remain independent.
- Final focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_position_read_model.py scripts/test_autonomous_runtime_completion.py scripts/test_autonomous_mandate_prefill_review.py scripts/test_standing_trading_mandate_authority.py scripts/test_dashboard_authoritative_runtime_state.py -q`: 129 passed. Neighboring strategy/coordinator/approval/lifecycle/management/provider/canonical group: 253 passed, including all 60 canonical cases. Earlier test-only failures corrected an expiry-code expectation and a fake selectbox/import; no production authority rule was weakened.
- One final full regression `.\venv\Scripts\python.exe -m pytest -q`: 3,865 passed, 156 subtests, three unchanged dependency warnings, 154.49s. Test child processes alone received trading/MT5 boolean defaults from .env.example; .env and running execution settings were not edited. Documentation integrity: 13 passed. Affected compileall, diff check, static safety and final Ponytail review passed.
- App-only restart, no rebuild: all five changed production modules matched mounted container source; container healthy, Streamlit HTTP 200 / ok. Browser localhost:8501 visibly showed SUPERVISOR_STOPPED and HISTORICAL monitor evidence. The live read model reloaded the exact retained closed trade with SL 4047.491, TP 4058.669, BUY and -3.10 USD net P/L, preserving Candidate/execution provenance. Old persisted chat answers were not reprocessed or overwritten.
- Safety: no real Supervisor start, Candidate/mandate/mode/permission/kill-switch change, provider call, controlled-submit, management write, order_send or broker mutation. Final 114-file check found only normal lifecycle observations appended by the running app; all 3,683 original lifecycle rows remain an exact byte prefix. Other protected stores, .env, embedding cache, .agents/ and earlier work were unchanged; no commit/push. One standalone read-model import diagnostic exposed an import-order cycle; the production lifecycle-first bootstrap and real read succeeded. That import cleanup was not added to this bounded sprint. Verification level: FULL_REGRESSION_PASS. Verdict: SPRINT_10_RELIABILITY_PASS. Not verified: long-duration operation, real worker launch/stop in this sprint, historical network root cause, or post-entry management/recovery mutation.

# 121. SPRINT 11A HISTORICAL MT5 RESEARCH DATA FOUNDATION

- Operator explicitly chose data foundation only, without adding a simulator dependency. No simulator, experiment, strategy signal, risk sizing, train/test split, benchmark or performance statistics were implemented. BacktestEvaluationAgent remains an observation evaluator that prohibits trade simulation.
- Added an isolated research dataset boundary and host-only export CLI. Reused OHLCVBar, pure market OHLC validation, timeframe durations/mapping and existing MT5Client/_call_mt5. Live bridge/API/schema, strategy, indicators, Draft/Candidate, authorization and execution paths were not changed. No dependency was installed.
- Explicit UTC date-range bars/ticks are captured from the connected DEMO terminal, with before/after account match and bounded requests. All eight bar fields and six tick fields retain source values. Only identical inter-chunk overlap is removed; conflicting/duplicate/non-monotonic input fails closed. No timestamps, prices, spread or volumes are synthesized.
- Content-addressed local data/research/mt5 artifacts include deterministic JSONL, request/provenance/coverage/current contract metadata, source Git revision and exporter checksum, data/manifest integrity and quality. Re-export is idempotent; old datasets are not overwritten. Current contract metadata is not claimed to be historical. Git/Docker exclusions were installed before any export; protected stores/cache/agent state are separate.
- Shared coverage gate reports VERIFIED/PARTIAL/INVALID/INSUFFICIENT_HISTORY, enforces warmup and rejects invalid OHLC/quote/spread/timestamp fields. Loader recomputes quality and checksums; non-VERIFIED data is rejected by default. Session policy is explicitly a conservative UTC-weekday assumption; unknown maintenance/holidays and actual Sunday bars remain flagged, not silently excluded or interpolated. Tick completeness is unverified.
- Real export: research_dataset_e81f53d087563a5c1c128979, 2026-11-04 15:00-16:00Z, 60 M1 bars, VERIFIED, no missing slots. Strict reload and repeated real export retained its identity/count. One week 2026-10-26 to 2026-11-02 returned 6,829 M1 bars, PARTIAL: 430 missing expected weekday slots plus Sunday/calendar mismatch. This is not proof of broker data loss; historical session evidence is still needed. One minute of real ticks returned 338 rows, PARTIAL, not certified complete.
- Fresh verification: `.\venv\Scripts\python.exe -m pytest scripts/test_historical_research_dataset.py -q`: 42 passed. Neighbors `.\venv\Scripts\python.exe -m pytest scripts/test_live_ohlcv_feature_engine.py scripts/test_market_data_provider_mt5_bridge_real_boundary.py scripts/test_backtest_evaluation.py -q`: 40 passed. Documentation integrity: 13 passed. Affected compileall/diff and final Ponytail safety review passed. Full regression was not rerun: existing shared production code, execution and indicator formulas are unchanged.
- No app restart/rebuild was applicable to this new offline-only boundary. Existing app, bridge and positions were not restarted or changed. Final read-only checks: DEMO, positions/orders zero, lifecycle discrepancies and RESULT_UNKNOWN zero, no real autonomous workers. 114 protected/private files were unchanged, including .env, embedding cache, authority/Candidate/execution history and .agents/. No commit/push or broker mutation occurred.
- Verification level: FOCUSED_AND_LIVE_PASS for 11A data acquisition, not trading performance. Full Sprint 11 delivery remains SPRINT_11_VERIFICATION_INCOMPLETE because 11B-11D and simulator acceptance were deliberately deferred. Next: verify the broker's historical session/calendar policy before promoting broad intervals to VERIFIED, then obtain a separate simulator/dependency decision. No strategy may be promoted to live authority from these datasets.

# 122. SPRINT 11A.1 HISTORICAL SESSION AND DATA COVERAGE

- Baseline remains b9e7d83 with the prior uncommitted 11A work preserved. Reused the isolated research module; no trading/indicator/live provider changes. Added session_coverage.py and focused fixtures; exporter v2 supports distinct ticks sharing a millisecond and compares complete ordered overlap groups. Identical within-chunk duplicates and conflicts fail closed. Loader retains v1 quality semantics for all original manifests; no export was rewritten or promoted.
- Separate versioned reassessment records internal consistency versus coverage, explicit aware UTC historical session evidence and source, quoting versus trading, full-slot closure/no-quote coverage, unknown and contradictory evidence. No weekly/DST/holiday inference framework or fabricated bar/tick values. It is diagnostic and does not bypass the primary dataset loader.
- The independent Exness November 2026 DST notice supports a daily/Friday/Sunday trading-boundary explanation, not exact quote-session history for this server/suffix. Python MT5 5.0.5735 has no session APIs; documented MQL5 session functions accept weekdays, not historical dates. No MQL5 exporter added solely to obtain a current snapshot. Native quote-session snapshot, historical server offsets and holiday exceptions remain unverified.
- Original 430 absent weekday slots: Oct 26-29 20:58-22:00Z (62 each), Oct 30 20:58-24:00Z (182). All five remain SESSION_HISTORY_UNAVAILABLE with low confidence in exact cause. Adjacent raw bars are retained in the evidence report. The full final absent interval extends to Nov 1 23:01Z without an assumed weekend calendar. There are 59 actual Sunday bars through 23:59Z; quote availability is not opening permission.
- Strict original reload/checksums pass. Hour: internally VALID, VERIFIED_BAR_SLOTS; week: internally VALID, PARTIAL; ticks: internally VALID, PARTIAL. Two real repeated tick reads return the same 338 records; a half-minute overlap matches 147. No same-ms/identical duplicates in this real sample. Flags 134 preserve known BID/ASK bits and uninterpreted bit 128. Repetition is not independent tick-completeness certification.
- Local ignored evidence: data/research/sprint_11a1_coverage_evidence.json. Existing storage/runbook document contains sources, session limitations and the four-option engine assessment. Recommendation is a separately approved pinned backtesting.py OHLC baseline, with explicit lot/cost/SL-TP ambiguity assumptions and AGPL review; it is not a tick-accurate MT5 engine. Backtrader/vectorbt trade-offs are documented. No engine installed, simulator implemented or performance result produced.
- Verification level FOCUSED_AND_LIVE_PASS: focused research/session plus market/bridge/observation-evaluator neighbors 98 passed (58 research + 40 neighbors). Documentation integrity 13 passed; affected compileall/diff and Ponytail review pass. No full regression: isolated offline boundary only. No app restart/rebuild required; no shared live behavior changed. Private/protected/original research files preserved; no authority writes, Supervisor, provider calls, Candidate, controlled-submit or broker mutation. No commit/push.
- Verdict SPRINT_11A_PARTIAL_EVIDENCE. Not verified: exact historical quote sessions, full tick completeness, historical contract changes, engine compatibility or profitability. Next: obtain dated server/symbol-specific quoting coverage evidence before promoting broad historical data; Sprint 11B remains separately approved work.

## Recovery 01 - Historical foundation checkpoint candidate (2026-11-11)

- Candidate isolated from b9e7d83 with only the 11A/11A.1 research dataset, session coverage, host exporter, offline tests, ignore rules and relevant documentation. No later research, semantic, Bridge, native parity or Trading Core changes are required.
- Verification level FOCUSED_PASS: 98 focused/neighbor tests and 13 documentation integrity tests passed in the isolated candidate. Historical live evidence above was not rerun; this checkpoint does not certify historical broker sessions or tick completeness.
- No acquisition, network-dependent operation, MT5 invocation, authority change, Supervisor, order, Docker/WSL operation, commit or push. Original dirty worktree and index preserved; commit approval remains separate.

# 123. SPRINT 11B NATIVE MT5 TESTER FEASIBILITY AND PARITY

- Baseline remains b9e7d83 with all uncommitted 11A/11A.1 work retained. Research-only StrategyParity.mq5, Python reference-vector helper and focused tests were added; no live execution, authority, indicator, strategy, Draft or sizing implementation was changed. No dependency installed, Docker restart/rebuild, commit or push.
- Installed terminal/MetaEditor/MetaTester build 6230 was verified. Copied installed vendor executables/license into ignored data/research/mt5_tester/s11b, without account credentials, operational configuration or profiles. Separate portable process used Experts Enabled=0, AllowLiveTrading=0, AllowDllImport=0; cloud/remote agents disabled. The connected DEMO terminal stayed on its original process and configuration. Both isolated math sessions terminated, with no remaining isolated terminal/agent.
- Research EA refuses initialization outside MQL_TESTER or in optimization. SimulateOrders defaults false; guarded virtual-order code was not exercised. No EA was attached to a normal chart. Completed M1 input uses CopyRates shift 1 and duplicate-bar protection; research-only caps/one-attempt restriction are not production Mandate or journal emulation.
- Native MetaEditor final compile: 0 errors/0 warnings, 512 ms; compiler process returned 1, so executable and log were checked rather than inferring failure/success from exit code. Two Model=3 Math-calculations sessions ran with OnTester=1 and agent mathematical-pass evidence. Final terminal wrapper still reports 'some error after pass finished'; cause unresolved. Math reports exist, but are not historical trading or broker-result evidence.
- Independent MQL results cover 12 synthetic fixtures plus 46 rolling 15-bar vectors from the checksum-verified real 60-bar dataset. RSI/ATR, completed-bar timestamps, LEVEL/EDGE, warmup, active-entry flags and volume agree in all 58 vectors within explicit checks. Full numeric parity is 57/58: real_16 differs at half-tick price rounding; Python SL/TP/risk 4027.783/4042.072/4.763 versus MQL 4027.784/4042.070/4.762. These are reference-vector calculations, not real order prices/results.
- First mismatch is Decimal(str(ATR)) price arithmetic versus double arithmetic before tick rounding: ATR repr 3.1750000000000194 and entry 4032.546 yield Decimal raw SL 4027.78349999999997090 versus double 4027.7835. No tolerance was widened or live Python formula changed. Bundled vendor RSI example uses recursive smoothing and flat=50, unlike Python's window average/flat=100; vendor ATR example uses an SMA-equivalent rolling recurrence. Native indicator bit-parity was not assumed.
- Historical trade pilot count zero: stopped at numeric-parity failure. XAUUSDm availability/history/real-tick quality, historical costs/contract/margin, fills, SL/TP execution and MTF trading inside the isolated tester remain NOT VERIFIED. The active terminal's bars/ticks and the successful Math test do not prove these. The broker DST notice remains general trading evidence, not exact suffix/server historical quote evidence; week/ticks remain PARTIAL.
- Verification level FOCUSED_PASS: 135 Python tests passed with two existing protobuf warnings; documentation integrity 13 passed; affected compileall and diff checks passed. Pytest validates the reference/audit/safety contracts, not full MQL parity. An initial collection failure exposed the existing proposal-package import cycle; the research helper uses existing decision-first bootstrap only, without changing production packages. Ponytail review: prototype is isolated, but promotion is blocked by recorded rounding mismatch and untested broker simulation. No full regression required for this research-only boundary.
- Provenance/inputs/outputs, source and report checksums are in ignored data/research/mt5_tester/s11b/feasibility_evidence.json. Source matches the compiled EA copy. Original private/protected files, cache, .agents and research exports are unchanged. Live provider/Candidate/authority/Supervisor/controlled-submit/bridge order_send/broker mutations zero; DEMO positions/orders remain zero.
- Verdict SPRINT_11B_PARITY_INCOMPLETE. Recommended primary engine direction is a narrow hybrid: native MT5 fills plus Python authoritative reference/audit, conditional on numeric parity and genuine tester data/cost evidence. Not an approved engine adoption or performance claim. Next bounded work: resolve research-only quantization parity without altering live strategy, then provision/verify XAUUSDm tester history before the one historical pilot. No second simulator or optimization.

# 124. M0 UNIFIED ADAPTIVE TRADING ARCHITECTURE AUDIT

- `STATIC_ONLY`: see [M0 capability matrix and roadmap](docs/architecture/M0_UNIFIED_ADAPTIVE_TRADING_AUDIT.md). Existing semantic and execution layers remain authoritative; workflows, origin, authorization and adaptation are not interchangeable. No change to the locked architecture or runtime.
- First proposed M1 family: goal with user constraints but no defined strategy, projected through canonical semantics to an advisory research brief or missing-leaf clarification. No Draft/Candidate, activation or permission. Existing Advisory and Strategy-Driven behavior must remain unchanged.
- Existing Mandate binds the exact strategy identity; a different revision cannot inherit it. Data quality/parity and genuine isolated tester evidence gate quantitative ranking, not M1 intake. Prior Sprint 11B parity remains 57/58 and no historical fills are established. No M1–M11 implementation was started.

# 125. M1 GOAL-ONLY SEMANTIC ROUTING

- On local `b9e7d83`, canonical `STRATEGY_RESEARCH` projects a bounded `RESEARCH_REQUIRED / STRATEGY_NOT_ESTABLISHED` brief. Explicit objective, horizon, percentage constraints, symbol, account preference and sources remain user facts with provenance. Referenced research goals can inherit established facts, with current overrides and unresolved values respected.
- Explicit requested autonomy is retained as intent; effective mode remains `advisory_only`, with no strategy, execution permission or actionable Mandate. The orchestrator returns before capability execution or trading projection. The existing projector also blocks autonomous requests with no strategy; the chat does not resurface an older trade card at a research turn.
- `FULL_REGRESSION_PASS`: 222 focused, 3,954 full tests and 156 subtests passed. Tests used scripted provider output and offline fixtures, not a live provider, terminal, or restarted app. Execution authority, protected files and Sprint 11 artifacts were not modified; no commit/push.
- Next: M2 proposal/revision provenance and a separate research approval state. Do not treat the brief as a strategy or authority. Quantitative ranking still depends on verified coverage, native parity and a genuine historical tester pilot.

# 126. R1 RESEARCH PROPOSAL AND REVISION CONTRACT

- R1 delivers the proposal/revision portion of the M0 audit planning row M2. The previous M1 next-step label used that planning convention; original roadmap M2 remains Autonomous Reliability and is unchanged.
- `ResearchProposal` consumes the canonical M1 QueryPlan brief without reparsing or executing it. It preserves goal, user constraints, requested mode, unresolved facts and provenance. A hypothesis may be absent; an optional typed strategy keeps the existing canonical identity and must be advisory-only with no execution.
- Immutable scoped revisions record UTC, parent, author and canonical content fingerprint. Replay requires trusted scope; identical updates are idempotent, stale forks are rejected, and a changed revision does not inherit review. Evidence stores references only, and VALIDATED requires an evidence-owner check bound to scope and hypothesis. MT5 Tester validation remains blocked at 57/58 parity.
- Research acceptance is revision-specific and only permits the next research stage. Both proposal and revisions remain non-executable. R1 adds no runtime caller, storage, broker integration or authority. Future durable writes need protected provenance and atomic head comparison; content fingerprints are not signatures.
- `FOCUSED_PASS`: 281 focused/neighbor tests including canonical 60-case acceptance; documentation integrity 13 passed. No new full regression (isolated module), live provider, tester run, app restart, trading writes, stage, commit or push. Next dependency: a trusted evidence-owner integration for scoped references, with historical Tester evidence still gated on parity and a real pilot.

# 127. R2 TRUSTED RESEARCH EVIDENCE VERIFICATION

- Historical evidence uses the Sprint 11 read-only loader plus an explicitly approved source path, independently retained manifest checksum and exact conversation/account scope. Manifest and data integrity, approved provenance, bar-window coverage, claim support and strategy performance remain distinct. Only the declared aligned bar window can be verified; partial data stays limited and no bars are interpolated.
- Verification reports bind proposal, revision and fingerprint, reference, scope, symbol/timeframe, UTC window and check time. R1 can record validated evidence in a new immutable revision only through the revision-aware owner; replay rechecks source contents. No prior review is inherited and evidence verification never accepts a review or grants trading authority.
- Read-only replay of the three retained 11A/11A.1 artifacts against the recorded manifest pins: one bar window verified, other bars and ticks limited. The verified source produced an in-memory R1 revision at READY_FOR_REVIEW with zero review decisions and execution disabled.
- `FULL_REGRESSION_PASS`: 299 focused/neighbor tests, 1 architecture check on rerun, 3,976 full tests and 156 subtests. Documentation integrity 13 passed. No live providers, broker activity, app restart, or protected writes. Current-market and private knowledge references remain pending in R2. Native Tester remains 57/58 with no accepted historical fills.
- No UI or durable verification store is wired; pin and scope provisioning are trusted caller responsibilities. R2 is a research work package, not original M2 Autonomous Reliability. Next dependency: trusted source provisioning at any future product integration; current-market and knowledge verification need their own provenance/freshness or access checks.

# 128. M2 AUTONOMOUS RELIABILITY AND RECOVERY

- Baseline `main@b9e7d83`, existing M0/M1/R1/R2/Sprint 11 work preserved. Scope is Strategy-Driven reliability, not Goal-Driven adaptation. Semantic, strategy, authorization, policy and reconciliation owners remain unchanged.
- GAP_CONFIRMED and fixed: competing Supervisor starts now serialize by trading scope on the shared data path and reread persisted diagnostics before launch; failed stop retains the live handle and a redacted failure category. No auto-restart or ownership adoption. Older/replayed bars cannot claim new work; unclosed bars fail quality and changed bars between claim and input assembly fail before Candidate creation.
- GAP_CONFIRMED and fixed: an exception after the durable submission or management start is reported as RESULT_UNKNOWN, not a pre-submission block. The existing journal identity remains reserved; autonomous watch stops on uncertainty. Reconciliation remains the sole owner of broker-result recovery, never of order retries.
- ALREADY_VERIFIED offline: expired/revoked/wrong-scope authority and changed account block; duplicate submission is rejected; no/multiple broker matches stay inconclusive; stale/unavailable lifecycle, foreign unresolved and ambiguous exposure fail closed. PARTIALLY_VERIFIED: broker-specific partial fills and end-to-end cross-process behavior have isolated coverage, not deployed acceptance. BLOCKED_BY_EXTERNAL_ENVIRONMENT for this offline evidence level: current DEMO timebase, closed-session/disconnect and restart behavior with real broker data; no live evidence collected.
- `FULL_REGRESSION_PASS`: 545 focused/neighbor tests plus one targeted watch test, 3,986 full tests and 158 subtests; docs 13 passed. Read-only DEMO NOT_RUN; unattended soak NOT_RUN. Follow the [local runbook](docs/operations/local_runbook.md) for the separately approved read-only gate before any soak. No app/bridge restart or broker operation in M2.

# 129. G0 SEMANTIC-TO-EXECUTION CORRECTNESS FOUNDATION

- Conditional Human-Confirmed Candidate admission now requires current, strategy-bound completed-bar evidence. False, unknown, stale or unbound evidence cannot produce an eligible Candidate. Draft preview remains non-executable; direct BUY/SELL does not require a condition. Autonomous LEVEL/EDGE, re-arm and deduplication retain their existing owners.
- Canonical typed SL/TP, risk and volume retain raw value, unit and source into immutable Draft revisions. Explicit invalid or unresolved input blocks instead of falling back to policy; omitted input can still use policy. Only explicit, compatible canonical references inherit prior parameters, not an old Draft. Candidate retains the exact Draft reference and validates explicit risk against its current quote.
- A requested technical computation requires matching symbol/timeframe OHLCV, a fresh completed bar and the requested indicator outputs. Unavailable computation has no fallback result. Default indicators are labeled as a generic summary when no computation was requested.
- `FULL_REGRESSION_PASS` (offline): 392 focused tests including the canonical 60-case suite; 4,009 full tests and 158 subtests. See the [G0 changelog entry](docs/engineering/SPRINT_CHANGELOG.md#g0---semantic-to-execution-correctness-foundation) for commands. No deployment, live provider/MT5 checks, authority changes or broker operations.
- Future signal admission belongs before proposal construction in `AuthoritativeAutonomousInputAssembler.build`, using the existing strategy identity, timeframe and `expected_closed_bar_time` binding. A generated signal must first be attested by a separately approved trusted owner; a hash alone gives no authority. G1 is a separate approval; [platform decisions](docs/ai_platform/DECISIONS.md) remain pending where recorded.

# 130. G1 OPEN-ENDED COMPUTATIONAL SPECIFICATION

- The existing one-call structured semantic path accepts an optional `computational-specification/v1` with a deterministic content ID. It preserves inert formulas, steps, temporal/state requirements, parameters and units, multi-timeframe data requirements, output validity, and entry/exit/re-entry/management text. It round-trips in the existing resolved semantic record; the original query remains in the QueryPlan and conversation.
- Strategy Origin, Authorization Mode and Adaptation Policy are independent. Mode maps only to existing requested-mode labels, not authority. Explicit, inherited, suggested and trusted-confirmed values retain distinct provenance. Missing/conflicting fields are surfaced; older semantic payloads, strategy hashes and mandate binding are unchanged.
- QueryPlan projects a non-executable specification before capability acquisition or legacy strategy projection. Data availability, freshness and completeness are `NOT_CHECKED`; no feed, worker, artifact promotion or Candidate is involved. An explicit reference with missing prior state stays blocked. Formula text is not interpreted or evaluated.
- `FULL_REGRESSION_PASS` (offline): 437 focused, 4,039 full tests and 158 subtests. One scripted semantic call, no rewrite or extra provider call; output cap unchanged. No deployment, live provider token measurement, MT5 Tester, generated-code run or broker operation. See the [G1 changelog](docs/engineering/SPRINT_CHANGELOG.md#g1---open-ended-computational-specification).
- G1 can be handed off for G2 design. Generated execution is not approved: G2 still needs an isolation and immutable provenance decision; G3 needs separate Windows Tester isolation and data/parity approval. See [platform decisions](docs/ai_platform/DECISIONS.md).

# 131. G2 TRUSTED-HOST PILOT, ISOLATION GATE OPEN

- `G2_PARTIAL / G2_ISOLATION_APPROVAL_REQUIRED`. The offline pilot accepts one pinned, contiguous historical bar window via R2 and the strict Sprint 11A loader. It binds the specification, research revision, manifest and minimal input bytes. A source reply can only be held as inert, hashed, unverified text. No provider caller, worker, verified artifact or promotion path is wired.
- The selected research-only indicator is volume-weighted close location over a trailing window. A trusted rational-arithmetic oracle checks output shape/timestamps, warm-up, values, exact replay and all prefixes. Tests check claimed vectors; they do not attest actual execution or profitability.
- Read-only preparation replayed the separately retained pin for XAUUSD M1, 2026-11-04 15:00-16:00 UTC: 60 closed bars, `VERIFIED_FOR_DECLARED_SCOPE`. The job remains at the isolation gate. No generated source or new historical dataset was persisted.
- Windows hypervisor, WSL2 and Docker are present. Hyper-V inventory is inaccessible to this session; the running app has writable secret/code/data mounts and a network. No environment was verified or approved for generated execution. See the [G2 changelog](docs/engineering/SPRINT_CHANGELOG.md#g2---trusted-host-pilot-isolation-approval-required) for the proposed next gate and exact offline checks. G3 is not ready.

# 132. G2.1 HYPER-V BENIGN ACCEPTANCE HANDOFF

- **Final disposition: G2_1_PARTIAL, operator workflow closed.** A/C/D/E/F retain prior runtime PASS; G is **OPERATOR_ATTESTED**, with independent machine-readable guest evidence **not captured** and formal independent G PASS not claimed. B/H remain **INCONCLUSIVE** for independent host/guest exposure attestation and installed-image lineage. Not eligible for formal full acceptance; `READY_FOR_G2_2: NO`. See the [final acceptance report](docs/operations/g2_1_sandbox_acceptance_report.md).
- Existing Stage3 Closeout completed at **16:07:49Z**, exit code 0, using the operator's explicit attestation through its unchanged exact-phrase gate. `stage3_closeout.json` and `g21_operator_attested_closeout_20261109.txt` record the scope. Original and clone are **Off**; original incident pin, sealed baseline, old runtime and restored disk are preserved. Normal guest-OS shutdown is host-evidenced at 15:53:26Z. No replay or VM state change occurred during Closeout.
- No further screenshots, guest checks or G2.1 investigations are scheduled. G2.2 generated execution, isolation changes and live trading remain unauthorized.
- The proposed read-only Computational Specification Review is now implemented independently of G2.1; see section 133. No sandbox work was reopened.
- Closeout checkpoint verification: `FOCUSED_PASS` for documentation and host Verify only; `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **13 passed**; selected Stage3 script parser: **0 errors**. No new guest acceptance or full regression is claimed.
- [Host Verify](scripts/g2_1_hyperv_worker.ps1) and the [guest harness](scripts/g2_1_guest_probes.py) are separate. The harness does not provision, install, boot, transfer media, change settings, or accept external commands or trading input. It creates and removes only its own temporary guest fixture, and runs bounded transient units. It emits `PASS`, `FAIL`, or `INCONCLUSIVE` per check; exit 1 is a failure, exit 2 is incomplete evidence (even with all guest checks passing).

## Operator Run Order

The [offline operator runbook](docs/operations/g2_1_offline_probe_runbook.md) describes the earlier A-E/H media workflow; do not repeat completed probes or use it for F/G. Continue only from the existing RestoreG checkpoint using the incident-pinned Stage3 procedure identified in the acceptance report. The operator-attested Closeout is complete. Do not collect more guest evidence or replay any phase. B/H remain formal acceptance limitations; continue product work that has no sandbox execution dependency.

| Original probe | Required evidence and current scope |
| --- | --- |
| A: No network | PASS from prior operator-supplied runtime evidence; current host Verify still requires zero NICs. Guest loopback-only/no default routes and numeric IPv4 `ENETUNREACH` belong to the completed probe, not a new run. |
| B: No host resources or secrets | Check Basic Session/no integrations, exact attached media, clean install and operator-reviewed guest inventory without displaying secrets. Missing known mounts/Docker socket alone is inconclusive; finding one fails. |
| C: Input read-only | Worker reads the matching synthetic bytes and a write-open on the mode-0666 fixture fails with `EROFS`. No real data used. |
| D: Non-privileged worker | Correct UID/GID and groups, zero capabilities, `NoNewPrivs=1`, and actual `EACCES` reading a private root marker. This covers the probe service, not arbitrary future execution. |
| E: CPU/RAM/process/time | CPU cgroup throttles at 25%; a 64 MiB/no-swap cgroup kills a bounded memory child; task limit 6 actually rejects a fork; a separate 2s service ends with systemd result `timeout`, without completion. No host-side teardown claimed. |
| F: Host can stop the correct VM | Separate operator approval: on a disposable target only, record ownership/VM ID and `Running`, launch a benign bounded 60s sleep with a visible start marker, then confirm `Stop-VM -VM $verifiedVm -TurnOff -Confirm` against that exact object while the sleep is active. Require `Off` on that ID. Hard power-off can corrupt the guest disk; do not use an irreplaceable disk. |
| G: Clean recovery | Separate approval for the restore path and disposable storage. Pin a clean powered-off guest image; create a benign marker in a disposable copy; restore from the pin and prove the marker is absent. Preserve the current disk and do not use destructive rollback as a substitute. |
| H: Host provenance and checksums | Host Verify authenticates the installer ISO; record the script's host/guest hash match and compare C's input SHA-256 with `7e2c9737f9df3c7fe5a26752772db0e2d4381e4b6bf0bd6543139546483c6ab2` for `G2.1 benign input v1` plus LF. Installed baseline provenance and real G2 input/output workflow are not proven by a synthetic fixture. |

Guest probe safety evidence is not permission to run generated code, and does not remove the previously recorded Windows patch-level risk. Operator-attested Closeout is complete; independent G proof, B/H proof and an approved persistent output boundary remain limitations. G2.2 is not authorized.

# 133. READ-ONLY COMPUTATIONAL SPECIFICATION REVIEW

- The existing orchestrator early exit renders the resolved G1 specification and QueryPlan findings: confirmed requirements with provenance, unconfirmed values, missing fields with questions, conflicting values, unsupported requirements, and separate specification/runtime readiness. Empty requests remain incomplete; ordinary requests do not pick up a prior spec without an explicit same-conversation reference.
- Streamlit labels the response as a specification review, not RAG or a trade card. When a selected conversation disappears, the shell reloads the replacement history with its ID before rendering. Historical messages are not rewritten. Computational review still returns no trading request, uses no additional provider call or data acquisition, and leaves `execution_allowed=False` and data `NOT_CHECKED`.
- `FOCUSED_PASS`: 298 passed, including 37 computational specification cases, 60 canonical cases and 13 documentation tests, with process-local offline safety overrides. Streamlit AppTest submitted a scripted request after switching away from a stale spec or trade history. App-only restart, matching source hashes and Streamlit HTTP 200 verified. No live provider prompt, full regression, MT5 action or sandbox work.
- The typed single-field clarification loop is now implemented; see section 134.

# 134. TYPED COMPUTATIONAL SPECIFICATION CLARIFICATION

- Advisory offers one explicit answer at a time on the latest review: objective, algorithm, formula, configuration enum, a named parameter value, or an identified OHLCV timeframe. The existing semantic patch and strict specification schema validate the leaf, including recorded bounds and mode conflicts. Missing or unsupported leaves are not defaulted or overwritten.
- QueryPlan rebuilds from the updated resolved state without rerunning semantics; the new review preserves sibling values and provenance. MongoDB appends only if the exact review is still the persisted tail of that conversation, without upsert. A stale, duplicate or deleted review cannot change stored state; no vector memory is written for the clarification.
- The review remains advisory-only, with data `NOT_CHECKED` and execution disabled. No new LLM, research/data execution, strategy deployment, generated code, sandbox or broker operation.
- `FOCUSED_PASS`: 322 passed (61 specification/history, 60 canonical, 13 documentation), with offline execution flags overridden in pytest only. Streamlit AppTest covered apply, rerun, switching, stale and deleted conversations. An isolated MongoDB collection confirmed only one of two concurrent submissions could append; newer, changed and missing tails rejected. No live prompts or full regression.
- OHLCV lookback and warm-up clarification is now implemented; see section 135.

# 135. OHLCV INTEGER CLARIFICATION

- The existing single-field form supports missing `lookback_bars` and explicitly unresolved `warmup_bars` for an identified OHLCV requirement. Omitted optional warm-up is not made mandatory. Confirmed values and other datasets are not editable through this addition.
- Whole-number input is checked before storage. Existing strict schema bounds are lookback greater than zero and warm-up at least zero; signed 64-bit is a BSON storage bound, not a trading/data limit. The specification has no lookback/warm-up ordering invariant. The pilot's separate dataset-coverage checks remain unchanged and are not run by the form.
- The review preserves requirement position, sibling values and provenance. It still uses the same conditional conversation append and deterministic QueryPlan review, with data `NOT_CHECKED`, no LLM, and no execution authority.
- `FOCUSED_PASS`: 371 passed, including 87 specification/history, 60 canonical and 13 documentation tests. Streamlit AppTest verified both fields, invalid input, rerun, stale/deleted reviews and conversation switching. BSON round-trip and a concurrent-submit regression against an atomic storage test double passed. No new collection or live conversation write.
- The final OHLCV widget slice adds explicitly unresolved `max_age_seconds`; see section 136.

# 136. OHLCV FRESHNESS-TOLERANCE CLARIFICATION

- An identified OHLCV requirement offers `max_age_seconds` only when its exact field is unresolved. An omitted optional value or a confirmed value is not editable. The shared typed form accepts a positive integer that fits signed 64-bit BSON; it records seconds, not a data freshness verdict.
- Single-leaf provenance and the conditional conversation append are unchanged. No data or provider call, and execution stays disabled. Stop adding individual OHLCV widgets here.
- `FOCUSED_PASS`: 392 passed, including 108 specification/history cases, 60 canonical cases and 13 documentation tests. AppTest covered successful apply/rerun, invalid input, stale review and conversation switching; BSON boundary and concurrent/duplicate tests passed without a live conversation write.
- The read-only Research Readiness view is implemented; see section 137.

# 137. READ-ONLY RESEARCH READINESS

- In Advisory, **Research readiness → Inspect existing research revision** checks one existing proposal head and one explicitly approved local historical source. The displayed proposal decision and the current R2 outcome/reason, artifact quality, integrity, provenance, symbol/timeframe and requested window are independent. Results are not stored or reused on rerun.
- Operator provisioning only: place the current trusted R1 export at `data/research/readiness/proposal.json` and supply one server-side `RESEARCH_READINESS_BINDING` JSON object with `trading_scope`, optional `account_ref`, `proposal_id`, `revision_id`, `proposal_sha256`, `dataset_id`, and `manifest_sha256`. The scope is the existing conversation scope and the account reference is opaque, not a login. `proposal_sha256` is the independently retained SHA-256 of the exact trusted export bytes; `manifest_sha256` is the approved canonical manifest checksum, not the file hash including its trailing newline. The dataset must already be under `data/research/mt5/<dataset_id>`. No browser-supplied paths or pins, no scan, no auto-approval. Keep the server binding and current export under operator control; do not point to an obsolete copy. Changed snapshots fail closed until the binding is explicitly refreshed.
- Pinned replay validates scope, identity, chain and recorded review without rechecking all historical evidence. Normal proposal replay/approval still requires its verifier. The current single-source check uses R2 separately; a mismatched manifest pin stops before row reads. A verified artifact can still have inadequate coverage for the requested window.
- `FOCUSED_PASS`: 469 passed, including 13 readiness cases, two readiness AppTests, 60 canonical cases and 13 documentation cases. AppTest verified click/rerun, limited coverage and conversation isolation. Existing app health HTTP 200; no app restart because loaded live execution flags were enabled. No trusted readiness binding/snapshot was configured on this host; live readiness inspection not run.
- The subsequent operator-approved R1 revision and historical input preparation are verified in section 138. This does not authorize research execution, generated code or G2.2.

# 138. R1 IMMUTABLE RESEARCH INPUT PACKAGE

- Implemented [input preparation](src/services/trading/research/input_package.py) within the existing research package. Exact operator-pinned binding, R1 export checksum, revision/scope and recorded `ACCEPTED_FOR_NEXT_RESEARCH_STAGE` are checked before historical rows. Existing R2 inspection and pinned dataset loading must independently return `VERIFIED_FOR_DECLARED_SCOPE`.
- Real local acceptance: approved proposal `proposal_4c4012c99819ef06f79efa3a722210381ff86b500bbd4054cb9a7cce118d1e3a`, revision `revision_32d3da1129490e2faa0cf08427f35c62ea401be5885264591b83c51a013686d0`, scope `trading_scope_56f9811d7d14d191e8aa5025`, dataset `research_dataset_e81f53d087563a5c1c128979`. Approval and source bytes remain unchanged.
- Exactly 60 consecutive closed XAUUSD/XAUUSDm M1 bars from 2026-11-04 15:00 inclusive to 16:00 exclusive UTC. Fields are only `time`, `high`, `low`; UTC Unix seconds and source numeric values are preserved. No range calculation, interpolation, resampling or live acquisition.
- Schema `r1-research-input/v1` binds proposal/revision/export, dataset/manifest/data hashes, revision fingerprint, scope, provenance, window and projected row checksum. DEMO provenance is `MT5_AUTHENTICATED_LOCAL_TERMINAL`; `execution_allowed=false`.
- The single ignored local artifact is `data/research/inputs/research_input_c2f1fc8a424eec05338d19f05f2abb0bddae006edb2ae1ee59a492f4ea8d68e8.json`. Its full-byte SHA-256 is the filename suffix. Canonical JSON and complete-byte no-replace publication give reproducible, content-addressed output; conflicting existing bytes fail closed. This is not OS-enforced immutability or a signature against a privileged host attacker.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **128 passed**, two existing dependency deprecation warnings. Real local replay preserved exact bytes and mtime with one output; all four protected source files remained byte-identical.
- Not verified/implemented: research calculations or execution, backtesting, G2.2, generated code and OS-level write protection. No provider/MT5 access, broker mutation, app restart, commit or push. Pre-existing worktree changes remain preserved.
- The deterministic descriptive implementation is verified with fixtures in section 139; real computation remains gated by a separate exact operator approval.

# 139. R1 CONTROLLED DESCRIPTIVE COMPUTATION

- Implemented [one trusted operation](src/services/trading/research/descriptive_computation.py): per-bar `high - low`. UTC timestamp and original High/Low are preserved; `range` uses an exact decimal string in the source price unit. Decimal precision is derived from each pair, independent of ambient context. No statistics, trading signal, backtest or generated code.
- The existing R1 stage decision is not computation approval. `run_descriptive_computation` rejects missing explicit `DescriptiveComputationApproval` before file reads or arithmetic. A trusted caller must supply the separately obtained operator decision for the exact proposal, revision, scope, input SHA-256, `HIGH_MINUS_LOW_V1` and absolute `data/research/results` destination. This typed projection records a trusted caller's decision; it is not an authentication service or permission derived from R1 status.
- Before calculation, recheck the current approved binding/export pin and accepted head, package bytes/hash, metadata, provenance binding, exact UTC window, contiguous timestamps and row checksum. Missing/invalid/nonfinite prices or negative ranges fail closed. Recheck package, binding and export bytes before publishing.
- Reused complete-byte, no-replace publication from input preparation with a filename prefix; input behavior is unchanged. Results use `r1-descriptive-result/v1`, `research_result_<full-byte-SHA256>.json`, bind the exact input/proposal/revision/dataset/algorithm and record a separate row checksum. Existing different content is rejected, not overwritten. No OS-level immutability claim.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **174 passed**, two existing dependency deprecation warnings. Includes 46 new controlled-fixture cases for approval gating, exact decimal subtraction, malformed/tampered input, provenance, timestamps, replay, no-overwrite and source preservation. Syntax checks pass.
- Real local historical acceptance **PASS**, following the operator's separate explicit approval for this exact revision/input/operation/output. Revalidated the current approved binding/export, accepted revision/scope and input hash before one production entry-point call. Runtime call tracing counted exactly one entry-point and one calculator invocation. Input SHA-256 remains `c2f1fc8a424eec05338d19f05f2abb0bddae006edb2ae1ee59a492f4ea8d68e8`.
- Actual result: `data/research/results/research_result_cbe3c90bb56aba8230a8843765e110c94e8742a21db04dfbc2a1f901a41cf0a1.json`, 5,992 bytes, full-byte SHA-256 matching its filename. Row SHA-256 `1e65a031346e440fb5fd437c2effb939292bc03136c279ec37fc76a76d4f89a7`; exactly 60 source-bound rows in the approved 2026-11-04 15:00-16:00 UTC end-exclusive window.
- All 60 ranges passed an independent exact rational oracle. Independently reconstructed result bytes and canonical reserialization matched the artifact exactly; the real production computation was not repeated. Existing fixture tests separately verify repeated production calls return identical bytes/mtime. Original proposal, approved binding, manifest, historical data, input package and Git index remained unchanged.
- No provider/live MT5 access, trading authority, broker mutation, app restart, commit or push. G2.1 remains CLOSED/PARTIAL and G2.2 unauthorized.
- Acceptance verification remains `FOCUSED_PASS` plus real offline historical execution evidence, not live broker or full-regression evidence. Current-task focused computation/documentation checks: **59 passed**; the earlier 174-case family result is retained, not rerun. No source changes were needed for this acceptance.
- The read-only result review is now implemented; see section 140. No automatic new computation or research promotion.

# 140. R1 VERIFIED RESEARCH RESULT REVIEW

- Existing Advisory **Research readiness** now includes **Inspect verified result**. The orchestrator delegates to `review_research_result` in the existing descriptive research module. No new engine, store, semantic call or research execution. Existing revision readiness inspection remains independent and unchanged.
- Trusted host configuration: reuse `RESEARCH_READINESS_BINDING` for the exact approved R1 binding and add `RESEARCH_RESULT_BINDING` containing only `input_sha256` and `result_sha256`. Paths are fixed under `data/research/inputs` and `results`; no browser path or discovery scan. Missing configuration returns `NOT_CHECKED / RESEARCH_RESULT_NOT_CONFIGURED`. Do not silently provision or refresh pins from chat or artifact content.
- Verify the result full-byte SHA-256 before parsing, then schema/algorithm, recorded bounded approval, and exact input/proposal/revision/dataset/scope/window binding. Computation and review share the extracted read-only input validator and pinned proposal replay. Rows retain exact timestamps/High/Low; ranges must be finite nonnegative decimal strings. No range subtraction or extra statistics during inspection; mathematical correctness remains evidence from the prior acceptance, not a new oracle run.
- Recheck source bytes before returning a verified view. Results are local to the click, not cached/persisted in session or history; rerun, conversation switch and unavailable conversation do not reuse a previous table. Failed checks expose a reason and no result rows.
- UI shows objective, identity, algorithm, market/window, dataset provenance, input/result SHA-256 and a 60-row table of UTC/High/Low/Range. Prices and ranges are displayed as text to avoid float formatting artifacts. The limitations explicitly distinguish historical observations from strategy, signal, forecast, backtest or profitability evidence.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_research_result_review.py scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **256 passed**, two existing dependency deprecation warnings. Includes 29 result review cases and AppTest click/rerun/tamper/scope/deletion checks. Initial AppTest exposed an incompatible dataframe width argument; changed to the installed Streamlit API and final regression passed.
- One real local read-only inspection verified result `cbe3c90bb56aba8230a8843765e110c94e8742a21db04dfbc2a1f901a41cf0a1` and input `c2f1fc8a424eec05338d19f05f2abb0bddae006edb2ae1ee59a492f4ea8d68e8`, with the accepted R1 revision and 60 observations. Runtime tracing recorded zero calls to calculator/execution. Protected proposal, binding, manifest, historical source, input and result hashes remained unchanged.
- **Deployment/UI limitation:** running app is healthy (HTTP 200) but its current live execution/order-send/controlled flags are true and execution kill switch false. No restart, persistent configuration change or browser trading workflow was authorized or performed. New UI is verified by host AppTest, not claimed deployed/browser-accepted in that live-configured process. Result pins were supplied to the host-only acceptance call, not installed in the running app.
- No MT5/provider access, new computation, broker mutation, authority write, generated code/G2.2, full regression, commit or push. G2.1 stays CLOSED/PARTIAL; unrelated local work is preserved.
- Expanded historical coverage assessment is recorded in section 141; no acquisition or additional computation is authorized.

# 141. EXTENDED HISTORICAL RESEARCH COVERAGE

- **PROPOSED objective, not an approved revision:** inspect per-bar High/Low observations over three consecutive UTC hour blocks surrounding the original hour. Scope: XAUUSD/XAUUSDm, M1, 2026-11-04 **14:00 inclusive to 17:00 exclusive UTC**, exactly **180** unique, ordered, finite, closed bars without gaps. This is the smallest window for this chosen three-block observation objective, not a statistical sample-size claim, strategy evaluation or profitability finding. No indicator warm-up or extra research computation is implied.
- Existing `HistoricalDataRequest` validates the explicit request: `canonical_symbol=XAUUSD`, `broker_symbol=XAUUSDm`, `timeframe=M1`, `kind=bars`, the above UTC boundaries, `warmup_records=35`, `session_policy=UTC_WEEKDAYS_CONSERVATIVE_V1`. The 35-record value preserves the existing exporter/loader quality floor; it does not discard 35 observations or add another 35 bars. Broker mapping matches current repository configuration. Calendar policy is a declared assumption, not a certified broker schedule.
- Read-only discovery was restricted to `data/research/mt5/research_dataset_*/manifest.json`; all three artifacts passed existing loader manifest/data/identity/count/quality checks. No scanning of trading journals, external folders or live MT5.
- `research_dataset_e81f53d087563a5c1c128979`: XAUUSD/XAUUSDm M1 bars, **60**, quality `VERIFIED`, 2026-11-04 15:00-16:00 UTC end-exclusive (last observation 15:59), no missing slots inside its own window. It is the only source in the current protected research binding. Manifest/data pins remain unchanged.
- `research_dataset_9474120dbe23938a9b8ffaad`: same symbol/M1 bars, **6,829**, 2026-10-26 to 2026-11-02 UTC end-exclusive, quality `PARTIAL`; **430** absent expected weekday slots, four intervals Oct 26-29 20:58-22:00 UTC and Oct 30 20:58-24:00 UTC, plus `SESSION_POLICY_MISMATCH`. No overlap with the proposed Nov 4 window; source is not approved by the current R1 binding. Do not relabel gaps as broker closure or promote the dataset using a subset/schedule guess.
- `research_dataset_9095667fb029de365258239c`: **338 ticks**, 2026-11-04 15:00-15:01 UTC, quality `PARTIAL` due to uncertified tick completeness. Not a bar source; no resampling or substitution. It is not approved by the current R1 binding. All three artifacts record `MT5_AUTHENTICATED_LOCAL_TERMINAL`, DEMO, execution authority false; integrity/provenance metadata alone is not scope approval.
- Applying existing `assess_quality` to the proposed interval and real 60-bar source yields **120 missing bars**, precisely 14:00-15:00 and 16:00-17:00 UTC. This means unavailable in the inspected local source, not proven absence from broker history. No price values/ranges were recalculated.
- Canonical revision mechanism: `ResearchProposal.revise` with exact current parent and scope, `ResearchContent` plus a new `EvidenceReference` window, initially `PENDING/UNKNOWN`, not copied `VALIDATED` claims. An in-memory diagnostic branch produced `revision_002f4d5a6913090a344e3d42d64e2092d4f85c4334fedeec5ce3d69ff1bd936e`, status `EVIDENCE_PENDING`. Existing `HistoricalEvidenceVerifier.inspect` returned `PARTIAL_OR_LIMITED / RESEARCH_COVERAGE_INSUFFICIENT` against the independently pinned source. This branch was **not persisted**, is not the canonical head or an approval target, and adding a new dataset reference later changes revision identity. The accepted proposal/export, binding, input and result remain unchanged.
- **Acquisition request prepared, NOT EXECUTED; explicit operator approval required** for only the one read-only DEMO export below. It re-exports the whole contiguous scope through the existing content-addressed exporter rather than stitching/altering the original artifact. Broker/account/mapping checks remain mandatory and partial export is not acceptance. Approval of acquisition does not approve the future proposal, evidence promotion or computation.

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.export_research_history --symbol XAUUSD --broker-symbol XAUUSDm --timeframe M1 --kind bars --start 2026-11-04T14:00:00Z --end 2026-11-04T17:00:00Z --warmup-records 35 --session-policy UTC_WEEKDAYS_CONSERVATIVE_V1
```

- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_historical_research_dataset.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_session_coverage.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **93 passed**, two existing deprecation warnings. Covers missing/partial/sufficient evidence, UTC, symbol/timeframe mismatch, pins, approvals and immutable history. An additional bounded mocked export-contract check rejected wrong broker mapping before any MT5 initialization. No production/test source gap found; no source or test files changed.
- Not verified: broker availability for the two missing local periods and the proposed 180-bar dataset. No acquisition, proposal approval, research calculation, app restart, G2.2/Hyper-V activity, MT5 order, commit or push.
- The operator subsequently approved and completed only that acquisition; see section 142. Source admission, revision approval and computation remain separate gates.

# 142. AUTHORIZED THREE-HOUR MT5 HISTORICAL EXPORT

- Operator explicitly approved one read-only DEMO export with the exact section 141 request. Preflight confirmed running/connected terminal, DEMO environment, available stable protected fingerprint, repository XAUUSD/XAUUSDm mapping and valid broker contract metadata. No identifiers were printed; no terminal settings or execution authority changed.
- Ran `tools.mt5_bridge.export_research_history` **once**, using all explicit approved CLI arguments. Exit code 0; no retry. The existing exporter independently checks DEMO/fingerprint before and after its historical read and preserves its normal no-overwrite content-addressed persistence.
- Actual new dataset: `data/research/mt5/research_dataset_46c26e4f381b5e5a0cda010c`. Exactly **180** closed M1 bars in **2026-11-04 14:00 inclusive to 17:00 exclusive UTC**; first 14:00, last 16:59. Mapping XAUUSD/XAUUSDm; provenance `MT5_AUTHENTICATED_LOCAL_TERMINAL`, DEMO, `execution_authority=false`.
- Canonical manifest SHA-256: `c7d1e743204a111f48e1978593d758c5fafd2a982d3e5d5ae13d3a734cf3a76f`. Data SHA-256: `785175291491edb92129ecce470a69b4c67d9c52dbd60f956e75c9f302afdff4`. Manifest checksum is the existing canonical checksum contract, not the file hash including its newline.
- Existing `load_dataset(..., expected_manifest_checksum=...)` and recomputed quality passed: `VERIFIED`, no issues/acquisition failures/gaps, strictly ordered unique UTC minute timestamps and no out-of-window rows. Independent exact-window timestamp comparison confirmed all 180 slots. `warmup_records=35` is the existing quality minimum; all 180 rows are research-window observations, **zero additional warm-up bars** were fetched or counted.
- **Source approval NOT GRANTED.** R2 inspection of a temporary in-memory pending revision using only the previously authorized source owner returned `SOURCE_UNAVAILABLE / RESEARCH_SOURCE_NOT_APPROVED`. This is expected authorization enforcement, not a quality defect. The new dataset was not registered as approved; no `VERIFIED_FOR_DECLARED_SCOPE` admission or expanded revision approval is claimed. The temporary diagnostic revision was not persisted.
- Verification level: `FOCUSED_AND_LIVE_PASS` for read-only acquisition/loader evidence only, not trading or research execution. Prior unchanged-source 93-case coverage family PASS retained; current documentation integrity: **13 passed**. No source/test edits, full regression or rerun acquisition.
- Original 60-bar dataset, all earlier local datasets, approved proposal/export, binding, input/result, `.env`, Git index and unrelated source changes remain unchanged. No Streamlit restart, order, research computation, backtest, optimizer, generated code/G2.2, commit or push.
- The operator subsequently approved this exact source; admission and pending expanded revision are recorded in section 143. Computation remains unauthorized.

# 143. EXTENDED SOURCE APPROVED; THREE-HOUR REVISION AWAITS REVIEW

- Operator explicitly approved only dataset `research_dataset_46c26e4f381b5e5a0cda010c`, manifest `c7d1e743204a111f48e1978593d758c5fafd2a982d3e5d5ae13d3a734cf3a76f`, data `785175291491edb92129ecce470a69b4c67d9c52dbd60f956e75c9f302afdff4` as an eligible read-only source for XAUUSD/XAUUSDm M1, 2026-11-04 14:00-17:00 UTC end-exclusive. Existing pinned loader revalidated integrity, DEMO/authenticated provenance, execution authority false, exact 180 unique ordered closed-bar slots and no gaps before approval was recorded.
- Scope `trading_scope_56f9811d7d14d191e8aa5025` remains valid: `conversation_trading_scope` hashes conversation identity, not timestamps. A read-only MongoDB metadata check through the existing HistoryService found exactly one matching conversation. The window belongs to revision evidence, not the scope ID; no replacement conversation scope was invented.
- Reused `ApprovedHistoricalSource` and `HistoricalEvidenceVerifier`, including both historical source pins so the accepted predecessor chain validates normally. No new approval mechanism or source registry was introduced. `ResearchProposal.revise` appended one validated-evidence revision; `ResearchProposal.review` was **not called**.
- Same proposal `proposal_4c4012c99819ef06f79efa3a722210381ff86b500bbd4054cb9a7cce118d1e3a`; new revision `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5`. Objective: descriptive per-bar High/Low observations over the three consecutive hours surrounding the original hour, without trading/performance claims. Timeframe M1; exact 180-bar window and new dataset reference are immutable revision content. Any computation needs separate authorization.
- Persisted through the existing R1 `to_json` export and trusted readiness binding at `data/research/readiness/proposal.json` and `binding.approved.json`. Export SHA-256 `d28a2347ef10ec530c4a518f04bb26d2301bc84fe74e650f0d1e8ef123e9998b`. The binding's approval is **source eligibility only**, not acceptance of this proposal revision. The new head is `READY_FOR_REVIEW`, reason `RESEARCH_REVISION_NOT_ACCEPTED`; zero new review records. R2 independently returns `VERIFIED_FOR_DECLARED_SCOPE / RESEARCH_HISTORICAL_BAR_WINDOW_VERIFIED`.
- The repository has one current export/binding, so previous byte-exact files were archived before updating the current head: `data/research/readiness/archive/proposal_7257882d40f474d7313079dfa6bf6ec85ff82006854b3dbaafcf045577cba6d3.json` and `binding_c0f37f99b044402902cb5c86a42063d76b11e55b833afe10a8b6058ca191ddf8.json`. Archives are historical evidence, not a second approval store. The original revision content and its acceptance review remain unchanged inside the new chain and accepted archived snapshot. In the expanded chain its derived current-head status is `SUPERSEDED`, not revoked. All original datasets, input and computed result bytes remain unchanged.
- Strict normal R1 replay with both source owners passed; existing readiness inspection confirmed separate pending proposal and verified evidence states. Old server pins are not silently refreshed: no app/environment update or restart occurred; an old pinned view must fail closed against a changed current export rather than relabel its historical result as current.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_research_readiness.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **48 passed**, two existing dependency deprecation warnings. No production/test source changes, full regression or new browser acceptance.
- Not approved/implemented: acceptance of the expanded revision, new input preparation, computation, backtest, optimizer, generated code/G2.2 or trading. No MT5 acquisition/access, Streamlit restart, trading authority change, commit or push in this task.
- The operator subsequently accepted that exact revision and authorized input preparation; see section 144. Computation remains a separate authorization.

# 144. THREE-HOUR R1 ACCEPTED; VERIFIED INPUT PREPARED

- Revalidated operator-pinned pre-review export SHA-256 `d28a2347ef10ec530c4a518f04bb26d2301bc84fe74e650f0d1e8ef123e9998b`, exact proposal/revision/scope, existing source approval, dataset/manifest/data pins, DEMO/authenticated provenance and 180 ordered unique closed M1 bars. No acquisition or recomputation.
- Called existing `ResearchProposal.review` for only `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5`, decision `ACCEPTED_FOR_NEXT_RESEARCH_STAGE`, reviewed_at `2026-11-09T18:32:39.384102Z`. Exactly one review appended; all revision contents and prior review records unchanged. Proposal remains `proposal_4c4012c99819ef06f79efa3a722210381ff86b500bbd4054cb9a7cce118d1e3a`, scope `trading_scope_56f9811d7d14d191e8aa5025`.
- Archived pending export/binding byte-for-byte using the existing archive convention, then persisted accepted R1 export and refreshed only its checksum in the current research binding. Accepted export SHA-256 is now `e9afb513179a06b421aee2b9c020e0a5d785ebd66e82dbe2a3edb2c4d67df1f4`. Normal strict R1 reload passed. Existing readiness inspection separately returned proposal `ACCEPTED_FOR_NEXT_RESEARCH_STAGE` and historical evidence `VERIFIED_FOR_DECLARED_SCOPE`.
- Existing `prepare_research_input` requires accepted R1 and verified historical evidence, but does not evaluate the hypothesis or require computation authorization. Reused it unchanged to project only `time/high/low` from source `research_dataset_46c26e4f381b5e5a0cda010c`; no Trading Core or G2.2 gate was altered.
- Actual artifact: `data/research/inputs/research_input_f4e4fa840ccfa8f87394d41cd3525366fcebf5b200e9aadc3021aeb1c8c50741.json`, schema `r1-research-input/v1`, 10,370 bytes. Full-byte SHA-256 is its filename suffix; projected rows SHA-256 `72d4ff3649962c5f1bd9ab6bb1686674918dacd0202b53e47cbe7ffe58670d11`. It binds the exact accepted export, revision, scope, manifest/data pins and authenticated local MT5 DEMO provenance; `execution_allowed=false`.
- Exactly 180 source-identical observations, Nov 4 14:00 inclusive to 17:00 exclusive UTC. UTC ordering and numeric precision preserved. Repeated preparation returned identical bytes/checksum and unchanged mtime; exactly one new input package, no overwrite. Source/proposal/binding unchanged throughout preparation. No new result artifact; runtime tracing recorded zero calculator/execution calls.
- Original one-hour accepted snapshot, old binding archives, all datasets, original 60-bar input and result remain byte-identical. Pending three-hour snapshot is preserved at `data/research/readiness/archive/proposal_d28a2347ef10ec530c4a518f04bb26d2301bc84fe74e650f0d1e8ef123e9998b.json`; its old binding is `binding_36175ca85c47324b63b66d32bcc3fc5593297961d7e48a4d61c2ab68145dffa6.json` in that same archive directory.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_research_readiness.py scripts/test_research_input_package.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **63 passed**, two existing dependency deprecation warnings. No production/test source changes or full regression.
- The operator subsequently issued a separate exact 180-bar computation approval; its one bounded execution is recorded in section 145. Prior one-hour authority was not reused.
- No MT5 access/acquisition/order, research computation, backtest/optimizer, generated code/G2.2, Streamlit restart, environment/trading authority change, commit or push occurred during input preparation. Current app pins are not automatically refreshed.

# 145. AUTHORIZED 180-BAR DESCRIPTIVE COMPUTATION COMPLETE

- Operator explicitly authorized one `HIGH_MINUS_LOW_V1` run, `range = high - low`, for revision `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5`, unchanged proposal/scope, accepted export `e9afb513179a06b421aee2b9c020e0a5d785ebd66e82dbe2a3edb2c4d67df1f4` and input `f4e4fa840ccfa8f87394d41cd3525366fcebf5b200e9aadc3021aeb1c8c50741`. Approval is exhausted by this bounded task, not continuing research/trading authority.
- Before execution, checked exact current binding, normal strict R1 history/acceptance replay with both approved source pins, dataset integrity and exact 180 source rows, input bytes/hash, scope/window and algorithm. No result already existed for that input. No acquisition or preparation was repeated.
- Invoked existing production `run_descriptive_computation` **once**, with separately supplied `DescriptiveComputationApproval`. Runtime tracing recorded one entry-point call and one calculator call; no retry. Only per-bar ranges were computed; all UTC timestamps and High/Low observations were preserved.
- Result: `data/research/results/research_result_6323aff52d368d6f97ba9aec21dbcfa953df48bb1b245eb295739acf2ed0f842.json`, **14,002 bytes**, schema `r1-descriptive-result/v1`, full-byte SHA-256 matching filename. Row SHA-256 `a7368c41eee95b449bcdf7f4e7bbdfabd4e55eb51014da0302e8f03d1cd169d7`. Exact 180 XAUUSDm M1 observations, 2026-11-04 14:00 inclusive to 17:00 exclusive UTC; research-only provenance and execution/generated-code flags false.
- Independent oracle decoded JSON numeric lexemes as Decimal and subtracted with 100-digit precision and rounding/inexact traps enabled: **180/180 matched**. Independently rebuilt the complete expected artifact; exact byte comparison and canonical reserialization passed. Reusing only no-overwrite publication for those same bytes preserved result mtime/content; no production recomputation or different result. Existing result-review verifier separately returned `VERIFIED` for the pinned input/result and current proposal provenance without arithmetic.
- First observation: 14:00 UTC, High 4046.795, Low 4043.852, Range 2.943. Last: 16:59 UTC, High 4067.144, Low 4064.607, Range 2.537. No additional statistics or trading conclusions.
- All pre-existing datasets, inputs, results (including the 60-bar result), accepted proposal, binding and archives remained byte-identical. `.env`, Git index and unrelated worktree changes were preserved. One new ignored result; no source/test modification or persistent app pin update.
- `FOCUSED_PASS` plus real local historical computation evidence: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_research_computation.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **59 passed**, two existing dependency deprecation warnings. No full regression or live market test.
- No MT5 access/order, live trading, strategy execution, backtest, optimizer, generated code/G2.2, Streamlit restart, execution-authority change, commit or push. Content-addressed/no-overwrite storage is not OS-level immutability. Task complete; do not automatically request or start another acquisition, revision or computation.

# 146. CROSS-WINDOW CONSISTENCY AND HOURLY SUMMARY IMPLEMENTATION

- Actual read-only comparison independently verified old result `cbe3c90bb56aba8230a8843765e110c94e8742a21db04dfbc2a1f901a41cf0a1` against its archived accepted export/binding and current result `6323aff52d368d6f97ba9aec21dbcfa953df48bb1b245eb295739acf2ed0f842` against the current accepted revision/input. **60/60 observations matched** exactly in Decimal High, Low and Range over Nov 4 15:00-16:00 UTC end-exclusive; discrepancy list empty. No source edits or high-minus-low reruns.
- Extended the existing result verifier with optional, explicitly supplied `archive_binding_sha256`. It verifies the archived binding's actual full-byte hash and exact archived proposal pin through the same input/provenance validator. No scan or automatic fallback. Current default validation and all execution paths still require current authority; the archive parameter is not exposed through the UI. Historical verification is not current execution authorization.
- Added [descriptive summary](src/services/trading/research/descriptive_summary.py) in the existing research package: exact overlap comparison, pure three-hour M1 summary and separately gated execution. Reuses the existing typed computation approval and no-overwrite publisher; no engine, service, UI or second approval system.
- Summary contract `r1-hourly-range-summary/v1`, algorithm `HOURLY_RANGE_SUMMARY_V1`: exactly three complete consecutive UTC hourly groups of 60 existing range observations. For the real source these are 14:00-15:00, 15:00-16:00 and 16:00-17:00 UTC. No high-minus-low recalculation or other statistics.
- Explicit numeric policy: count integer; arithmetic mean of 60 Decimal ranges serialized as a fixed 12-place decimal string, `ROUND_HALF_EVEN`; median is the exact midpoint of sorted positions 30/31; min/max preserve exact source Decimal values. Working precision accommodates exact sums/midpoints before final mean rounding; no binary-float arithmetic. No additional dispersion metrics, predictive, profitability or significance claim.
- Summary output is separately content-addressed `data/research/results/research_summary_<full-byte-SHA256>.json`, binding source result SHA-256, original input package, proposal/revision, scope, dataset/window, algorithm and precision policy, group checksum and research-only flags. Source verification is repeated before publication to reject changes; no stale or cross-scope report reuse.
- Scope assessment: existing R1 content binds the same descriptive High/Low objective, market, three-hour window and evidence, with no per-operation algorithm allowlist in the revision schema. No new revision is mandated by that contract for this derived descriptive summary; **separate exact operator approval of the new computation and its descriptive scope is still required**. Stage acceptance and `HIGH_MINUS_LOW_V1` approval are not reused as summary authority.
- `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_summary.py scripts/test_research_result_review.py scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **226 passed**, two existing dependency deprecation warnings. Includes 23 new cases for grouping/boundaries, half-even ties, context independence, archive pins, discrepancy reporting, exact approval, stale/tampered source, idempotency and no-overwrite. Syntax/diff checks pass; no full regression.
- Real comparison tracing confirmed zero high-minus-low and summary execution calls during implementation; fixture tests were not real computation evidence. The operator subsequently authorized exactly one real summary; execution and independent verification are recorded in section 147.
- That exact approval targets revision `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5`, source result SHA-256 `6323aff52d368d6f97ba9aec21dbcfa953df48bb1b245eb295739acf2ed0f842`, original input `f4e4fa840ccfa8f87394d41cd3525366fcebf5b200e9aadc3021aeb1c8c50741` and only the declared five statistics. The existing approval projection's `input_sha256` binds the source result hash for this operation, not the original raw-input hash.
- No MT5/acquisition, real summary/new production computation, backtest/optimizer, generated code/G2.2, app restart, authority change, commit or push occurred during implementation. Do not infer continuing research authority from the subsequent bounded acceptance.

# 147. AUTHORIZED HOURLY RANGE SUMMARY COMPLETE

- Explicit operator approval covered one `HOURLY_RANGE_SUMMARY_V1` computation for the exact accepted three-hour revision/source result and `data/research/results/research_summary_<SHA256>.json`. Preflight revalidated current binding/revision acceptance, source result hash, original input/proposal provenance, XAUUSDm M1 window/180 rows and exact precision policy; no prior summary existed.
- Invoked existing production `run_hourly_summary` **once**. Runtime tracing recorded one entry-point and one aggregator call, zero high-minus-low calls; retries zero. Only count, arithmetic mean, exact median, minimum and maximum were computed for each of the three 60-observation groups.
- Actual artifact: `data/research/results/research_summary_10c783572d3f834945f8efb799af9137150d56eceb9f0ed7b60851beaa3c0645.json`, **2,817 bytes**, `r1-hourly-range-summary/v1`. Full-byte SHA-256 matches filename; groups SHA-256 `fc84b6caaee789677c16669c29f99137d347e589e4e51a181fe87931bfd0638f`. Provenance binds source result, original input, accepted proposal/revision, dataset/window and explicit approval. Execution/generated-code authority remains false.
- Actual statistics, source price units, 2026-11-04 UTC end-exclusive groups:

| UTC group | Count | Mean (12 places, half-even) | Median (exact) | Minimum | Maximum |
| --- | --- | --- | --- | --- | --- |
| 14:00-15:00 | 60 | 2.681033333333 | 2.4035 | 1.153 | 7.755 |
| 15:00-16:00 | 60 | 2.673366666667 | 2.5615 | 1.326 | 5.248 |
| 16:00-17:00 | 60 | 2.539250000000 | 2.386 | 1.284 | 5.623 |

- Independent reference selected observations by UTC timestamp predicates rather than production slicing, confirmed 60 unique observations per group, and verified all five statistics using 100-digit Decimal arithmetic plus standard-library Decimal median. **3/3 groups and 15/15 reported statistic values matched**. No production rerun.
- Independently reconstructed the complete artifact, obtaining identical bytes/checksum; canonical reserialization also identical. Republishing those exact bytes through the existing no-overwrite publisher preserved content and mtime and produced no second summary file. Original datasets, proposals, bindings, input packages, archive and both source results remained unchanged.
- `FOCUSED_PASS` plus real local aggregation evidence: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_summary.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **36 passed**, two existing dependency deprecation warnings. No source/test edits or full regression; only new ignored summary plus current documentation changed.
- No MT5 access/acquisition/order, trading, strategy execution, backtest/optimizer, extra statistics, forecasts/signals, generated code/G2.2, Streamlit restart, trading-authority/configuration change, commit or push. Descriptive observations do not establish prediction, profitability or significance; no OS-level immutability claim. Task complete; STOP without another acquisition or computation request.

# 148. STRATEGY EVALUATION READINESS; NUMERIC PARITY OPEN

- Assessed `main@b9e7d83b3ed5046fa02effba1508ceb69f505fdd` and the preserved dirty worktree. Closed descriptive research is not strategy-performance acceptance. The actual accepted proposal has `strategy=None`; its approval does not authorize backtesting.

| Capability | Status and limit | Source / focused tests |
| --- | --- | --- |
| Typed strategies and deterministic rules | IMPLEMENTED_AND_VERIFIED, unit level | `strategy_evidence.py`: `validate_strategy`, `plan_strategy_data`, `evaluate_strategy_rule`; `test_reasoning_evidence_v2.py` |
| Scenario replay | IMPLEMENTED_AND_VERIFIED, not chronological fills | `scripts/evaluate_reasoning_v2_replay.py`; `test_reasoning_evidence_v2.py` |
| Deterministic SL/TP/risk/volume | IMPLEMENTED_AND_VERIFIED, not portfolio accounting | `editable_trade_draft.py`; `test_field_aware_editable_trade_draft.py` |
| Historical orders/fills | PARTIAL | Research `StrategyParity.mq5` optional Tester-only simulation branch; one-attempt cap, no retained successful historical simulation |
| Python/MQL parity | PARTIAL | `tester_parity.py`, `test_mt5_tester_parity.py`; historical native evidence 57/58 math vectors |
| Costs / spread / slippage | PARTIAL | Quote/spread/deviation inputs exist; historical commission, swap, margin and per-fill cost accounting not verified |
| Look-ahead prevention | PARTIAL | Previous-bar prefixes, Tester shift=1 and duplicate-bar guards; end-to-end causality, next-event fills and intrabar SL/TP ordering unverified |
| IS/OOS and walk-forward | MISSING | No research split/walk-forward evaluation implementation identified in inspected owners |
| Research approval/data/artifacts | IMPLEMENTED_AND_VERIFIED, descriptive scope only | R1/R2 contracts and historical loader/verifier tests; no strategy authority implied |
| Native research isolation/feed | IMPLEMENTED_UNVERIFIED, approval pending | Existing Tester prototype/guards; pre-G3 Windows isolation/provenance decisions remain pending in `docs/ai_platform/DECISIONS.md` |

- Owners above are under `src/services/trading/reasoning/`, `proposal/`, and `research/`; focused tests are under `scripts/`. `src/services/agents/backtest_evaluation.py` and `paper_trading_evaluation.py` enforce `no_trade_simulation=True`; they evaluate observations, not simulated trade P/L. Host venv has MetaTrader5 5.0.5735, pandas 2.3.3 and numpy 1.26.4; backtesting/backtrader/vectorbt distributions were not installed. No dependency installed or engine adopted.
- Narrow safe fix: `tools/mt5_bridge/research/StrategyParity.mq5::RunFixtures` calculated native RSI but emitted LEVEL/EDGE/eligibility flags from Python-expected current RSI. Flags now use native RSI; legacy CSV column is consumed but ignored. Supplied previous-RSI test context remains; this is not fully independent previous-RSI recomputation. CSV format and Tester-only/optimizer/default-no-orders guards unchanged. One static-source regression added.
- Retained `data/research/mt5_tester/s11b/feasibility_evidence.json` reports 57/58 vectors and zero historical simulations/submissions. `real_16`: Python SL 4027.783 vs MQL 4027.784, from Decimal/binary-double half-tick behavior. Strict comparator still rejects it; tolerance unchanged. Retained native source/binary/report preserved. Patched EA NOT compiled/run; 57/58 describes only the historical checkpoint, not current patched native acceptance.
- Minimum viable future evaluation: one approved fixed typed strategy, explicit exits/re-entry/sizing/costs, current Python rules/calculations and native research Tester simulated fills with independent audit. Prototype RSI14 M1 LEVEL >10 is a plumbing control, not alpha or an approved performance strategy; do not promote prototype risk defaults to operator facts. Recurring trade/equity-ledger support needs later explicit scope; existing one-attempt prototype is insufficient.
- Required data: approved full OHLCV and spread units, verified session/calendar, ordered unique closed UTC bars, preceding past-only warmup from `plan_strategy_data`, pinned native Tester history/tick source and explicit historical Bid/Ask/commission/swap/slippage/margin assumptions. The `time/high/low` input projection cannot supply RSI/ATR or simulated fills. 180 M1 bars are only a plumbing sample. Existing 6,829-bar local export remains PARTIAL, with 430 missing weekday slots/session issues; never guess that gaps are legitimate closures.
- PROPOSED planning horizon, not approved or statistically sufficient minimum: eight complete trading weeks, chronologically four development, two validation, two untouched holdout, with past-only warmup. Counts must follow verified sessions, not 24-hour weekday arithmetic; regime/trade counts and costs determine adequacy. No acquisition requested/executed.
- Single next milestone: **RESEARCH_NUMERIC_PARITY_CLOSURE**. Reuse `tester_parity.py` and the EA, specify exact numeric representation/serialization/tick rounding without epsilon tricks or copied expected decisions. Acceptance: all retained 58 vectors plus BUY/SELL half-tick and volume-step boundaries match strictly; independently derived native decisions; source/binary/toolchain/input/report pins; no simulated orders. Native compile/math-only execution requires separate approved Windows research isolation/provenance scope. G2.1 remains closed PARTIAL; G2.2 unauthorized. Strategy/backtest approval remains a later independent boundary.
- Verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_field_aware_editable_trade_draft.py scripts/test_backtest_evaluation.py scripts/test_paper_trading_evaluation.py scripts/test_historical_research_dataset.py scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **177 passed**, two protobuf deprecation warnings. Isolated parity suite **17 passed**. Python/static checks are not native Tester or performance verification.
- Not verified/implemented: patched native compile/runtime, accurate fills/costs, portfolio accounting, IS/OOS/walk-forward or profitable strategy. No new research engine, UI, semantic authority, live MT5, acquisition, actual backtest, generated code/G2.2, restart, trading authority/config change, commit or push. Prior artifacts and unrelated changes preserved.

# 149. NUMERIC PARITY IMPLEMENTED; NATIVE APPROVAL PENDING

- At unchanged `main@b9e7d83b3ed5046fa02effba1508ceb69f505fdd`, reloaded the retained fixture by SHA-256 `b83232054545190a93a9252ec884947bb23001a245c7a3b165d39e717e8c14f3`. All 58 current Python reference rows match the archived Python reference exactly. Re-comparison of the OLD native CSV still fails only `real_16` columns 4/5/7: SL 4027.784 vs 4027.783, TP 4042.070 vs 4042.072, risk 4.762 vs 4.763. This is historical evidence rechecked, NOT execution of updated MQL.
- First mismatch boundary: native double arithmetic collapses raw stop to 4027.7835; canonical Python computes 4027.78349999999997090 from `Decimal(str(ATR))`, ATR 3.1750000000000194. Price tick rounding is ROUND_HALF_UP; volume is capped then ROUND_DOWN to step; ordinary Decimal operations use precision 28, ROUND_HALF_EVEN. Canonical production formulas and strict comparison tolerances remain unchanged.
- Existing research `tester_parity.py` now supports explicit BUY/SELL, validates input/fixture identity, policy fields, finite values and bar ordering, pins reference Decimal context, and reports exact case/column/expected/observed failures. Legacy fixture expected-RSI column is not an input authority. Its loader accepts retained v1 and side-aware v2; prepared output is v2. RSI/ATR still use canonical production functions.
- Research EA preserves numeric input text and uses `ParityDecimal.mqh` for decimal arithmetic/tick/volume boundaries, converting to double only after calculation. This helper exists because MQL has no existing repository Decimal boundary; it is research-local, not a new sizing/strategy engine. It implements bounded string-coefficient arithmetic (128 digits, exponent -64..64; unsupported/invalid values propagate failure), 28-significant-digit half-even operations, half-up tick rounding, truncating volume quantization and shortest round-trip native ATR conversion. Native correctness/compile is still NOT_VERIFIED.
- Native RSI uses separately averaged gains/losses in canonical order, Neumaier float sums matching the current CPython 3.12 family, and independently computed RSI for flags. Previous RSI remains an explicit fixture control, not a claimed independent previous-series computation. Algorithm reference: [CPython 3.12.5 sum](https://github.com/python/cpython/blob/v3.12.5/Python/bltinmodule.c); native formatting follows [MQL StringFormat](https://www.mql5.com/en/docs/convert/stringformat). Neither reference substitutes for native tests.
- Added `MathOnly=true` default: rejects simultaneous simulated-order request; initialization runs fixture math and returns before market ledger; OnTick returns before acquisition or order logic. Existing Tester-only and optimizer guards remain. New numeric fixtures exercise exact half-ticks, adjacent representable doubles, SELL symmetry, non-decimal tick/volume steps, half-even ties, recurring division and invalid input. No expected indicator is supplied to native calculation.
- Prepared ONE content-addressed JSON package through existing no-overwrite publisher: `data/research/mt5_tester/numeric_parity_preparation_e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5.json`, 91,201 bytes; full-byte SHA-256 is filename suffix. Contains 58 original BUY vectors, 58 SELL counterparts and 30 scalar checks, fixture strings/hashes, Python expected rows, source pins and CPython 3.12.5 identity. Does not represent R1 execution approval or a strategy experiment. Native binary/toolchain/output hashes are null, `native_status=NOT_VERIFIED`, execution/simulated-order authority false.
- Prepared `s11b_parity.csv` SHA-256 `d6dd035b40cf21ed472fb4f5a927a30eb35fe62bd4b64bc121c5569132f86e6b`; `s11b_numeric.csv` SHA-256 `08fcdf27bc3da6d9cafcc234697d9d656c773c3dcc76a4a765f0c2c49e3f1524`. Current EA SHA-256 `84751e398039fd7e0ce27e8001db4567c46b463b6075af27e0f8ea860b174e0a`; include `e6d4857eb68286c56b3a369fda5e78fe3f78d5a31e0776c289f3a6a8244c9d72`; Python harness `7e40867f792b746c62a177042de32f6c64f36da4f73cc7e77134d5b0d435dac6`. Full remaining source pins are in the package.
- Verification level `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_field_aware_editable_trade_draft.py scripts/test_backtest_evaluation.py scripts/test_paper_trading_evaluation.py scripts/test_historical_research_dataset.py scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **306 passed**, two existing protobuf deprecation warnings. Includes all 58 retained vectors and Python/static tests; no MQL execution. Python syntax and normal Git diff check pass. No full regression or app restart (explicit task prohibition).

## Pending One Native Math-Only Approval

- Verdict **INCONCLUSIVE**, blocker `NATIVE_MATH_ONLY_AUTHORIZATION_REQUIRED`. No native executable is pinned to these sources yet. Do not reuse old .ex5/report as current evidence or assume 57/58 survives current native changes.
- Approval request is limited to the exact package/source/fixture pins above, one compile and one Model=3 math-calculations session, no automatic retries, `MathOnly=true`, `SimulateOrders=false`. Reuse vendor tools in a NEW isolated portable research directory such as `data/research/mt5_tester/numeric_e05805d67cd2`; never overwrite `s11b` historical evidence, active terminal files or account profiles. Pre-existing path/conflicting process/source drift must stop preparation.
- BEFORE invocation: approve and verify Windows research isolation under `docs/ai_platform/DECISIONS.md`; separate process/profile from bridge; no credentials/account login copied; DLL/live trading/optimization/remote/cloud disabled; verify OS-enforced research executable/agent network denial or stop for operator-assisted isolation. Portable mode and Experts flags alone do not prove network isolation. No Administrator action or active terminal restart is authorized by this preparation.
- After that separate approval only: extract and checksum the two CSVs from the pinned package into the new portable `MQL5/Files`; copy the two pinned research sources together to `MQL5/Experts`. Compile with that directory's vendor MetaEditor using `/portable /compile:<absolute EA path> /log:<new compile log>`. Verify compiler log (zero errors/warnings) and new EX5 hash, not process exit alone. Then invoke only the separate portable terminal with `/portable /config:<new math.ini>`.
- Config must retain `[Experts] Enabled=0, AllowLiveTrading=0, AllowDllImport=0`; `[Tester] Expert=StrategyParity.ex5, Symbol=EURUSD, Period=M1, Model=3, Optimization=0, ForwardMode=0, UseLocal=1, UseRemote=0, UseCloud=0, Visual=0, ReplaceReport=0, ShutdownTerminal=1`. The source-pinned defaults MathOnly=true/SimulateOrders=false are mandatory. No broker feed/history download is required/approved for math mode; do not switch to a tick/bar model to resolve a startup problem.
- Expected new evidence: `MQL5/Experts/StrategyParity.ex5`, compile log, Tester log/report, local-agent `MQL5/Files/s11b_parity_result.csv` (116 rows) and `s11b_numeric_result.csv` (30 rows). Record actual terminal/compiler builds, EX5/output/config hashes. Use `load_fixture_csv` plus `compare_results` on the exact prepared fixture and `compare_numeric_results(numeric_cases(), ...)` for scalars; save both machine-readable reports with exact failing IDs/values. Any mismatch/schema/count/initialization issue is FAIL or INCONCLUSIVE, never a tolerance change or dropped vector.
- No native compile/session/MT5 access, historical acquisition, actual backtest/fill, research strategy/generated-code/G2.2 execution, trading authority change, commit or push occurred. Prior datasets/results/approvals, journals, `.env`, index and unrelated user work remain protected. Native parity closure is the next step; meaningful strategy performance still additionally needs an approved fixed strategy, cost/feed/causality validation, recurring trade accounting and independent holdout data.

# 150. NATIVE ISOLATION AUDIT PREPARED; NO NATIVE EXECUTION

- Operator conditionally approved ONE math-only native verification for the exact section-149 package. Initial read-only preflight found default outbound Allow on all enabled firewall profiles; effective rule access denied. No compile/session invoked. Blocker `NETWORK_ISOLATION_NOT_PROVEN` supersedes the missing-approval blocker, not the isolation requirement.
- Added `scripts/audit_native_math_isolation.ps1`: operator-owned elevated READ-ONLY audit, no self-elevation or policy/process changes. ActiveStore profiles/outbound rules/application and associated filters, intended executable applicability, vendor hashes/versions, Sandbox feature and explicit errors are saved to one CreateNew JSON report. Candidate program rules never imply whole-tree/credential isolation or overall PASS.
- Exact planned paths are under `data/research/mt5_tester/numeric_e05805d67cd2`: MetaEditor64.exe, terminal64.exe and metatester64.exe. No directory created. Additional helper/relocated-agent paths remain unproven. Static vendor inventory under old s11b found these three files at version 5.0.0.6230, without launching any.
- Non-elevated smoke audit produced `data/research/mt5_tester/isolation_audit_20261109T194653004Z_957f17be78b74dd3b2a4d03356dac28f.json`: INCONCLUSIVE, three preserved access/elevation errors, zero native invocations. Report timestamp is the observed host clock, not independent time verification. Windows Professional build 19045; Sandbox launcher absent, feature state UNKNOWN because inspection requires elevation.
- `docs/operations/native_math_isolation.md` provides the one operator command, evidence checklist and proposed disposable Sandbox with networking/clipboard disabled and only sanitized read-only input mapping. No Sandbox configuration launched/provisioned. Offline startup/compiler/Tester compatibility for pinned vendor build remains NOT_VERIFIED; math-mode documentation does not prove clean-guest compatibility. Artifact extraction without writable host mapping/network/clipboard remains unresolved.
- Verification is limited to new audit tests, syntax/read-only behavior and documentation, not repeated parity tests. No numeric source/package changes, native execution, feature/firewall change, G2.1 reopening, G2.2, MT5 mutation, app restart, commit or push. Next action: operator runs elevated read-only audit; native invocation remains blocked until containment and compatibility are proven.
- `FOCUSED_PASS` for audit tooling only: `.\venv\Scripts\python.exe -m pytest scripts/test_native_math_isolation_audit.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **25 passed** (12 audit, 13 documentation). PowerShell AST parsing and normal Git diff check pass. Isolation readiness remains INCONCLUSIVE, not upgraded by these tests.

# 151. DISPOSABLE OFFLINE SANDBOX INPUT PREPARED

- Continued only Sandbox preparation, not Firewall audits or numeric implementation. Elevated operator audit has zero errors but does not prove whole-environment isolation. Sandbox feature Disabled is now corroborated by read-only Win32_OptionalFeature InstallState=2; launcher absent. Windows 10 Pro x64 19045.3086, 12 logical CPUs, 15.39 GiB physical RAM, around 75.55 GiB free D:. Hypervisor/firmware virtualization true; SLAT/VMMonitor WMI flags false under the running hypervisor are inconclusive. Available RAM fluctuated 3.47-4.75 GiB; recheck headroom before any launch. No CBS/WU reboot-pending keys observed; feature enable can still require reboot.
- Created `docs/operations/native_math_offline.wsb`: Networking/ClipboardRedirection/vGPU/audio/video/printer disabled, 2048 MiB planned guest memory, one read-only input mapping, no LogonCommand or writable mapping. WSB SHA-256 `67c43042588bced99e76e74c598f91eccfdc20aaa370e6dc092de82205f22f71`. This is prepared configuration, not an instantiated Sandbox or approved RAM adequacy claim.
- Prepared `data/research/mt5_tester/native_sandbox_e05805d67cd2/input`, exactly 11 flat allowlisted files, about 249 MiB: vendor MetaEditor64/terminal64/metatester64, pinned StrategyParity.mq5/ParityDecimal.mqh, two pinned CSVs, original numeric_package.json, math.ini, guest_preflight.ps1 and manifest.json. Manifest SHA-256 `f20b2dff06dd6f4c288a4a32bd91605089a17c46e7f585b671750b7659534651`. Package `e05805d6...f3cf9b5`, 58 original/58 SELL/30 numeric checks and all numeric source pins preserved. No credentials/account profiles/Config/.env/private journals, installed DLLs, directories or reparse points copied.
- Added `scripts/native_math_guest_preflight.ps1`, staged manually executable only in a future fresh guest. Checks hashes/allowlist, package/source/fixture pins, active adapters/default routes, vendor processes and MetaQuotes profile presence; reports pending mapping/read-only checks and output authorization. No native launches; report stays INCONCLUSIVE until external containment gates reviewed. Uses .NET SHA-256 to avoid an implicit PowerShell Security module dependency exposed by focused tests.
- Static objdump import inspection (not vendor execution) found Windows-system libraries only across the three vendor EXEs. Section-flag warnings recorded; dynamic/packed dependencies, guest library presence, offline bootstrap/compiler/Tester compatibility remain NOT_VERIFIED. No missing dependency installed or proprietary license/profile copied speculatively.
- Practical extraction proposal is a dedicated `.../native_sandbox_e05805d67cd2/outbox` -> C:\ResearchOut writable projection, operator/SYSTEM-only host access and a six-file log/CSV/receipt allowlist. NOT created, NOT mapped, ACLs NOT changed. Requires separate consent to host-write/disk-exhaustion risks. Proposed admission limits (8 MiB total/4 MiB each) are not an enforced quota. Current input-only WSB has no result egress; do not consume the one Tester session before this gate is settled.
- `docs/operations/native_math_isolation.md` contains operator-only feature-enable command with -NoRestart, restart scheduling conditions, dependency limitations, guest checks and exact extraction approval scope. No feature enable, Sandbox creation/launch, compiler/MT5/Tester, G2.1/G2.2, app restart, authority change, commit or push. Overall readiness INCONCLUSIVE: feature enable/resources, guest containment, extraction approval and offline runtime compatibility remain pending.
- Tooling verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_native_math_isolation_audit.py -k sandbox -q -p no:cacheprovider --tb=short`: **6 passed, 12 deselected**; new XML/manifest/guest syntax tests only, no repeated Firewall/parity suites. Documentation integrity is run separately after documentation changes. No native parity PASS claimed.
- Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **13 passed**. Actual staged allowlist/hash validation passed via the read-only helper on the host; this is not guest runtime evidence. Normal Git diff check PASS.

# 152. DEVELOPMENT-ONLY GITHUB ISSUE TO CODEX BRIDGE

- Added independent `tools/codex_issue_bridge.py`, not a Trading Core path or authority. Fixed repository/owner DATCAOTAN/Trading_Advisory_Chatbot, label codex-dev-task, UUIDv4 task and immutable owner approval hash. PENDING receipt supplies the exact owner comment so ChatGPT can read/approve it without manual human copying. API identity is verified; PRs/other authors/edited approvals/unsupported schemas and paths are refused.
- Supports smoke, review, one-file development edit only; default read-only dry-run. Writes limited to docs/development/bridge_tasks or scripts/dev_tasks (.md/.py), after local --allow-edits AND a delivered actual smoke PASS. Dirty/untracked targets, context changes, bad hashes, sensitive content, symlinks/junctions/hardlinks, malformed code and whitespace errors block. No Issue-supplied shell/test/config commands execute; AST/whitespace checks do not claim unit tests ran. Development Python files are not executed.
- Dedicated Codex CLI 0.167.0 ephemeral tool-disabled turn over explicitly selected local-source snapshots; temporary cwd outside live repo, private CODEX_HOME/keyring. No Desktop thread resume/fork/daemon handover or inherited approvals. Installed official app-server supports thread/resume, but safe active-Desktop ownership transfer was not established. Repository context is explicit, not full historical Desktop chat. CLI feature validation confirmed shell_tool/apps/hooks false without provider call; built-in provider overrides were rejected by this CLI and removed, not bypassed.
- Windows Credential Manager holds operator-supplied fine-grained GitHub PAT (Issues RW and metadata, one repo); Codex uses separate OS-keyring login. No token files/env exports or connector credential extraction. Broker/API/GitHub/proxy env is excluded from worker. No Administrator runtime allowed. Local bridge credential currently unavailable and dedicated Codex home not initialized; ChatGPT connector repository access does not supply local auth or prove its Issue-write capability.
- Durable local SQLite task lifecycle PENDING/RUNNING/PASS/BLOCKED/FAILED, unique Issue/task claims, global Windows mutex and process lock, exclusive target-write handle and private before-image backups. Interrupted tasks become BLOCKED without rerun; uncertain comment delivery reconciles exact existing comment before anything else and never blindly reposts. Ambiguous writes require manual inspection, no automatic restore/reset. Desktop unsaved buffers cannot be detected; operator must pause edits to selected files. No claim of VM-grade containment.
- Added `scripts/test_codex_issue_bridge.py` and `docs/operations/codex_issue_bridge.md` with credentials/label setup, one activation command, owner Issue JSON/hash workflow, read-only smoke, result reading and strict recovery rules. No background listener/service/task-scheduler started. No GitHub Issue/comment mutation or authenticated Codex task was performed in implementation. ChatGPT must explicitly read result comments; no automatic conversation wake/injection is provided.
- Verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **73 passed** (60 bridge, 13 documentation). Includes offline component integrations with fake GitHub/worker, real SQLite and Windows locks/writes in temporary directories; not live GitHub/provider E2E evidence. Targeted compileall and normal Git diff check PASS; no full regression needed for isolated development tooling.
- Remaining operational gate: operator provisions label, least-privilege PAT and dedicated Codex login, activates watch in dry-run, then completes ONE non-trading owner-approved smoke Issue. Real smoke unlock is not populated by tests. No production Trading Core/source, permissions, broker/MT5/research/native Tester/G2.2, Docker/WSL/app restart, Git commit/push/merge or destructive worktree operation changed. Existing unrelated dirty files preserved. Do not start trading or native verification through this bridge.

# 153. ISSUE BRIDGE CREDENTIAL FAILURE DIAGNOSED

- Operator ran credential/login/watch; watch failed before any task receipt. Bounded GET-only diagnosis reproduced the FIRST failed request: GET `https://api.github.com/repos/DATCAOTAN/Trading_Advisory_Chatbot`, HTTP **401**, GitHub message **Bad credentials**. No GET Issue #1 or comments reached in that attempt. Network/TLS reached GitHub and error JSON was readable; Issue permissions remain untested, not proven denied. Existing local bridge task count is zero.
- Credential Manager loading succeeded; safe format checks confirmed U+0016 (Ctrl+V) inside the stored opaque value. Previous whitespace-only storage validation accepted this control character. Do not infer token expiry/revocation or expose/strip the secret. Stored credential was NOT changed by diagnosis. Codex login success is unrelated to GitHub PAT validity.
- Shared credential validation now rejects controls/non-ASCII/whitespace before both storage and request. The credential CLI verifies GitHub owner identity and repository/Issue read access before writing; rejection preserves the old entry. Existing credential requires operator replacement with an actual valid fine-grained PAT, using real terminal paste rather than a literal Ctrl+V marker. No authentication/permission bypass.
- Added safe GitHubFailure diagnostics distinguishing HTTP authentication, permission/policy, rate limits, missing/invisible resources, request validation, service errors, network/TLS/DNS/timeout/connection, request format and response JSON errors. HTTPError is handled before its URLError base class. No headers, raw errors/bodies or credential contents enter logs/comments; only allowlisted reason codes. POST ambiguity/no-repost receipts and no automatic retries remain unchanged.
- New `check` subcommand reads repository/owner/labelled Issues/Issue #1/comments only. It short-circuits before Codex/locks/database initialization and never posts comments, authorizes tasks or runs a worker. With current malformed credential it correctly stops locally at GITHUB_CREDENTIAL_FORMAT_INVALID; no new HTTP request is sent. Authentication is still BLOCKED until operator replacement; no live worker/smoke PASS is claimed.
- Verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **97 passed** (84 bridge, 13 docs). Added controlled transport error/redaction and POST no-retry cases, Ctrl+V storage rejection, rejected-token non-overwrite and GET-only command isolation. No full regression; compile/diff checks run separately. Runbook updated with exact safe check/replacement guidance.
- No listener/worker or GitHub write, credential change, Trading Core/MT5/Docker/WSL/authority operation, commit or push. Existing bridge database and unrelated local state preserved. Next action: operator securely replaces invalid PAT, then runs check before any owner-approved smoke.

# 154. ISSUE BRIDGE WINDOWS GUI CREDENTIAL INPUT

- Added operator-only `credential --gui` using installed Tkinter 8.6: masked entry, explicit Paste from Clipboard, Verify and Save, and Cancel/window close. No keyboard shortcut required, no automatic clipboard read, token reveal, normalization or alternate credential store. Invalid/non-text/control-character clipboard content leaves the input unchanged.
- GUI and console reuse one validate -> GitHub owner/repository/Issue read verification -> Windows Credential Manager write path. Failed validation/verification cannot reach storage. GUI callbacks suppress raw exceptions and provide sanitized feedback; no automatic retries. Cancel clears the input; system clipboard/history is intentionally not changed. Bounded synchronous verification may temporarily block the window.
- Verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **119 passed** (106 bridge, 13 documentation). Tests cover clipboard/manual invalid input, cancellation, verify-before-store ordering, failure redaction, CLI isolation and actual Tk widgets with a withdrawn window. No real clipboard/token, GitHub verification or vault write was used. Targeted syntax and diff validation performed separately; no full regression.
- Runbook now recommends GUI entry, with console fallback and existing GET-only `check`. No listener/worker, GitHub writes, Trading Core/MT5, Docker/WSL restart, authority change, commit or push. Unrelated dirty files remain untouched. Live authentication and Issue-write permission remain NOT_VERIFIED until the operator supplies and verifies the actual PAT.

# 155. ISSUE BRIDGE NATIVE WINDOWS TLS VERIFICATION

- Existing urllib GitHub client now uses an explicit per-client HTTPSHandler with `truststore.SSLContext(PROTOCOL_TLS_CLIENT)` on Windows, CERT_REQUIRED and hostname checks enabled. No global injection/monkeypatch, verification bypass, alternate networking client, untrusted CA file or retries. Missing dependency fails closed. Non-Windows uses standard verified SSL. Host development dependency `truststore==0.10.5` is pinned separately in `tools/requirements-codex-issue-bridge.txt` and installed in the project venv only; application/Docker requirements unchanged.
- Read-only diagnosis: Python 3.12.5/OpenSSL 3.0.13, no process proxy or SSL CA override detected. Standard Python GET already returned HTTP 200 BEFORE this change; historical unable-to-get-issuer error could not be reproduced. Verified peer `*.github.com` issuer Sectigo Public Server Authentication CA DV E36; native Windows chain Build succeeded to Sectigo Public Server Authentication Root E46 with no chain errors. No interception observed on these connections. Missing intermediate/cache behavior is plausible but NOT VERIFIED as the historical root cause; prior shell environment/chain state is unavailable.
- Acceptance: unauthenticated public GET with the exact bridge context returned HTTP 200 with certificate and hostname verification enabled. Then ONE existing read-only `check` returned read_only_access=PASS, task_contract=VALID, labelled_issue_count=1, comment_count=0, owner_hash_approval_present=false, issue_write_permission=NOT_TESTED. Authenticated owner/repository/Issue reads are now proven; no Issues write capability or live Codex worker acceptance is claimed.
- Verification `FOCUSED_AND_LIVE_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **128 passed** (115 bridge + 13 docs). Covers explicit native context/no global SSL mutation, missing dependency, verified non-Windows fallback, certificate-error redaction and GET/POST no-retry outcomes, alongside existing auth/permission/network/parsing and GUI protections. Negative certificate errors use controlled transport failures, not claims of hostile-endpoint live tests. Targeted compileall/diff checks run separately; no full regression.
- Only development bridge, focused tests, host-only dependency pin, runbook and current docs changed. No credential/Firewall/authority change, Issue write, worker/listener, Trading Core/MT5, Docker/WSL restart, commit or push. Existing dirty local state preserved. Next optional operator step remains owner-approved non-trading smoke, not automatic listener activation.

# 156. ISSUE BRIDGE UNCERTAIN PENDING RECEIPT - BLOCKED

- GET-only diagnosis of Issue #1 and SQLite read-only inspection identified smoke task `645c7e08-b6c6-4d05-a78a-6b50cc71da0e`: durable state=PENDING, attempted=1, delivered=0. The uncertain operation is POST /repos/DATCAOTAN/Trading_Advisory_Chatbot/issues/1/comments for its initial PENDING/hash-approval receipt, not a worker result. Expected body SHA-256 `92e4d612e836fe4005a8d274e317608e378e44985b339c58362e1de25cac2fc9`. Remote owner, open/labelled Issue, task ID/operation/hash all match; comments=0, matching receipts=0. No active bridge once/watch process observed.
- `COMMENT_DELIVERY_UNCERTAIN_NO_REPOST` is emitted only by the previously-attempted reconciliation branch. Therefore the reported once invocation stopped on the older unresolved receipt; that error does not indicate another POST. Reproduced the delivery method against a read-only database and GET-only remote evidence: same blocker, zero POST/worker calls, journal bytes unchanged. No listener/worker or full once run invoked in diagnosis.
- Exact original transport failure remains UNKNOWN: this schema persists no HTTP diagnostic, attempt timestamp or server request ID. Current empty comments prove no visible receipt at inspection, not authoritative non-delivery of an older request. Cannot infer prior TLS failure, HTTP 403 or permission grant from this row. Issues Write remains NOT_DEMONSTRATED; successful authenticated reads do not prove it. No safe rejection-based retry transition can be authorized from the available evidence. Operationally BLOCKED; original PENDING/attempt flags preserved exactly.
- No production source/state-machine change or new retry mechanism. Added focused regression for repeated absent comments, delayed exact delivery, wrong body/task/state/author, duplicate prevention, explicit HTTP 403 and durable restart reconciliation. Exact matching delayed owner receipt is acknowledged without repost; lost historical rejection diagnostics remain insufficient. Require operation-bound original non-acceptance evidence or a genuinely published matching receipt, never a fabricated comment/reset/ID change.
- Verification `FOCUSED_AND_LIVE_PASS` for read-only diagnosis and protections, NOT smoke execution: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **137 passed** (124 bridge + 13 docs). Targeted compileall/diff checks separate; no full regression. Updated runbook/current docs only. No Issue/credential/trading/MT5/Docker/WSL mutation, commit or push. Actual smoke remains BLOCKED pending authoritative delivery evidence.

# 157. ISSUE BRIDGE TASK-SCOPED UNCERTAIN RECEIPT ISOLATION

- Verified global-blocking defect in Bridge.tick: the unconditional sweep of every undelivered receipt called deliver before discovering current labelled Issues. Its first old unresolved write raised NO_REPOST and aborted the entire poll. Offending row is Issue #1 smoke task `645c7e08-b6c6-4d05-a78a-6b50cc71da0e`, state=PENDING, attempted=1/delivered=0, receipt operation SHA-256 `92e4d612e836fe4005a8d274e317608e378e44985b339c58362e1de25cac2fc9`. Original HTTP outcome still UNKNOWN. Current GitHub #1 is closed/unlabelled with zero comments; no receipt or state was fabricated/reset.
- Current #2 is open/labelled, task `c5d27b9a-4f32-47b8-a2d1-9a3e635f0e74`, operation=smoke, valid task hash `25e36f1f47b308272a7a5be75ea395646d92691d0e8feba9c0e7575a3b6fe52e`, zero comments. No durable row exists for #2. Because the existing production path commits its row and attempted flag before POST, no #2 POST was reached/recorded by that path; no Issues Write permission is inferred.
- Minimal existing-loop fix: re-admit receipt task against current Issue owner/state/label/ID/hash before delivery. Withdrawn or changed tasks are deferred unchanged; active uncertain receipts block only their own task while independent tasks may proceed. No retry/reset, receipt deletion, worker replay, new store or process owner. At most one new task per poll retained. When no independent work proceeds, active uncertainty remains observable. Inactive delayed comments do not change a row until the original task is admitted again.
- Added structured task/Issue/operation/comment-hash/stage diagnostics for deferral, reconciliation and new POST transport failures. Diagnostic bodies use fixed reason codes/hashes, not Issue payloads or credentials. Historical missing HTTP evidence remains unavailable; no recovery authority is invented.
- Verification `FOCUSED_AND_LIVE_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **146 passed** (133 bridge + 13 docs). New multi-Issue tests cover withdrawal, independent authorized work, each Issue's uncertainty, duplicate identity, delayed receipt and crash recovery. One pre-existing recovery fixture's placeholder pin was replaced with its actual canonical hash to exercise the newly enforced admission contract.
- Live acceptance used authenticated GET only and a read-only persistent DB copied to memory. New tick deferred #1 and reached #2's initial PENDING receipt in memory; a hard guard stopped BEFORE network POST or worker invocation. Persistent journal bytes/#1 row unchanged, #2 persistent rows=0. This proves task discovery/isolation, NOT live smoke delivery or worker success. Compile/diff checks separate; no full regression.
- Updated bridge, tests, runbook and current docs only. No listener, real GitHub POST, credential/security/trading/MT5/Docker/WSL change, commit or push. Next smallest operator action: run ONE normal once to attempt #2's first PENDING receipt; #1 remains preserved and isolated. Stop on any new POST failure and use its task-specific diagnostic, never blindly retry.

# 158. ISSUE BRIDGE WINDOWS WORKER CLEANUP FAILURE

- Issue #2 task `c5d27b9a-4f32-47b8-a2d1-9a3e635f0e74` is durably FAILED with delivered=1, LOCAL_FAILURE_NO_RETRY, worker_started=true/write_attempted=false. Its row and the entire task journal were preserved. Original traceback/stderr was discarded by the old worker, so exact historical stack cannot be recovered. No remote task was rerun or new GitHub comment posted here.
- Local diagnosis reproduced the concrete failure on the existing worker path: Codex CLI 0.167.0 returned 0, valid JSON was parsed, then TemporaryDirectory cleanup raised PermissionError/errno 13/WinError 32 (sharing violation) deleting the process cwd. This exception was outside the old worker's internal try and became generic LOCAL_FAILURE_NO_RETRY in Bridge.tick. The handle owner was not established. One early local probe happened to pass; instrumentation reproduced the cleanup failure, and a short bounded cleanup wait still failed. That retry experiment was removed, not shipped.
- Minimal confirmed fix separates one stable, empty, private worker-cwd outside the repository from per-turn disposable schema/result artifacts. Nonempty/reparse workspaces fail closed. Existing tool-free/read-only/never-approval/keyring/ephemeral CLI configuration, context snapshots and result/authority/idempotency gates remain unchanged. Old scratch leftovers are intentionally preserved. No ignore_cleanup_errors, permission change or silent cleanup bypass.
- Added CodexWorkerFailure diagnostics for home/workspace/temp/schema, subprocess exit/startup/timeout, result-file/JSON and cleanup stages. Preserve exception class, return code, errno/WinError and fixed-vocabulary stderr markers; bounded private stderr tail only, no raw task/context/auth output. A secondary cleanup failure cannot mask the primary failure. Existing FAILED receipt persists these fields; terminal task is never retried. Other unexpected local failures retain existing fail-closed behavior.
- Verification `FOCUSED_AND_LIVE_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **166 passed** (153 bridge + 13 docs). Includes startup/preparation/timeout/nonzero/missing/oversized/invalid JSON/encoding, cleanup masking, cwd handle separation, nonempty workspace rejection, result protocol, stderr redaction and FAILED-task no-repeat. No full regression.
- Four independent local diagnostic CLI invocations total, not retries of #2: initial PASS; instrumented cleanup failure; unsuccessful cleanup-wait experiment; separated-cwd smoke PASS. Final worker-path smoke used one CLI invocation, exit=0, status=PASS/summary=BRIDGE_SMOKE_OK/edits=[], no new scratch leftovers, journal bytes unchanged. A final stderr-marker refinement was verified by focused tests without repeating the provider smoke. Built-in Codex transport retries are not asserted to be zero; bridge task/worker auto-retry remains zero.
- Bridge/test/runbook/current docs updated only. No Issue write, listener, credential change, live repo worker context, Trading Core/MT5, Docker/WSL restart, commit or push. Local smoke does NOT set durable live_smoke_pass and does not establish fresh GitHub E2E completion. Ready for one separately owner-approved fresh smoke task; never reset/reuse terminal #2. Targeted compile/diff checks separate.

# 159. ISSUE #5 - WATCH DEFERRED DIAGNOSTIC DEDUPLICATION

- Baseline: operator confirmed E2E/watch smoke completion; read-only journal inspection in this task shows #3/#4 PASS/delivered=1, #2 terminal FAILED and #1 unresolved PENDING/attempted=1/delivered=0. No smoke/provider/listener/GitHub activity was repeated here. Existing local source, research changes, cache and .agents preserved.
- Root cause: each tick re-admitted the same inactive receipt and unconditionally printed TASK_RECEIPT_DEFERRED/ISSUE_NOT_AUTHORIZED/RECEIPT_TASK_ADMISSION. Task-scoped isolation already worked; only output repeated.
- Minimal change in existing Bridge: per-instance in-memory diagnostics keyed by task_id, comment-hash operation_id, reason and stage. Canonical event also includes safe Issue state/locked/task-label flags, so meaningful changes re-emit even when the reason remains unchanged. Only the latest poll's observations are retained; recovery/recurrence, state reversion and fresh process observations log again. No new database, state machine, service or CLI setting.
- Dedup is applied only after normal GET/admission and before printing; it never skips receipt reconciliation, task discovery, approval, worker/idempotency or no-repost decisions. Uncertain-write and other new API errors retain their existing behavior. No row or attempted/delivered field is changed merely to suppress logs.
- Verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **178 passed** (165 bridge + 13 docs). New tests count per-poll admission/discovery, repeated events, key and Issue-state changes, state reversion, independent approved fake task, fresh Bridge/reopened temporary DB, recurring deferral, delayed receipt and new TLS error propagation. One initial new-test assertion was corrected to account for the existing visible uncertainty event; final suite passed.
- Changed bridge, focused tests, runbook and current handoff/changelog only. Targeted compileall/diff checks separate; no full regression or live watch acceptance. No real worker, GitHub request/write, trading/MT5, credential/Firewall, Docker/WSL restart, commit or push. Next operator step: Ctrl+C the old listener, then restart plain watch; no edit permission expansion required. Original uncertain #1 outcome remains unknown.

# 160. FINAL GIT RECOVERY - INTEGRATED OFFLINE CHECKPOINT

- Recovery 01 (`51f625c`) was fast-forwarded to origin/main. Remaining legitimate changes were copied into an isolated recovery worktree; the original dirty main checkout, index, cache, personal rules and raw evidence were not edited.
- Shared semantic, Draft/Candidate, research review/completion and M2 safety changes form one dependency-closed functional checkpoint. Offline G2 contracts/tooling, native parity preparation, development Issue Bridge and documentation are separate subsequent groups. No new production feature or trading authority was added during recovery.
- The first integrated full regression found one stale architectural test allowlist: the existing strict R1 computation-approval model also uses Pydantic. Updated that exact allowlist; semantic authority assertions and production validation remain intact. Redacted three user-profile paths in the G2 acceptance report only in the recovered copy.
- Verification level FULL_REGRESSION_PASS: final isolated `python -m pytest -q -p no:cacheprovider --tb=short -rs` through the original Windows venv passed 4,529 tests and 158 subtests, with 60 skips and three deprecation warnings. The skips all require retained private native historical evidence that was deliberately not copied; they do not establish native parity. Initial run: one failure, 4,528 passed, 60 skipped, 158 subtests; focused fix/research regression: 341 passed; G2/native/Bridge/documentation group: 317 passed, 60 skipped.
- Test children alone received boolean defaults from .env.example, as in prior hermetic verification. No .env, process authority or running application configuration changed. Compileall for src/scripts/tools and parsing of four PowerShell scripts passed; static safety retained one production order_send call-site and zero MetaTrader5 imports under src. Scoped secret/private-profile and diff checks passed.
- Excluded locally: embedding_cache.sqlite, .agents personal rules, six raw G2 transcripts and edit_smoke.md. Raw datasets, vendor binaries, credentials and protected journals are not included. No MT5 operations, native compilation/Tester, research acquisition/computation, VM action, Bridge worker/listener or Docker/WSL restart was performed.
- Not verified here: live deployment, unattended Supervisor reliability, native numeric parity, G2 full isolation or strategy performance. G2.1 remains closed PARTIAL; G2.2 remains unauthorized. Git publication is not execution authorization.

# 161. GOAL-DRIVEN RESEARCH - CONNECTED PROPOSAL WORKFLOW

- Implemented on the recovered 5a6eca8 baseline: canonical Research Brief -> explicit Generate testable hypothesis -> one existing structured LLM transport call -> strict ResearchContent -> AI_RESEARCHED ResearchProposal -> persisted immutable revisions -> Advisory review/editor. The canonical semantic pipeline and QueryPlan are reused without a new parser, service, collection or execution engine.
- HistoryService stores proposal JSON and generation status inside the existing MongoDB conversation document. Atomic conditional writes bind the exact persisted brief, message count, conversation scope and expected record/head. One durable generation claim prevents duplicate provider calls; deleted/stale conversations and concurrent edits fail closed. Read-only reload bypasses stale Redis views; UI additionally checks the displayed brief against MongoDB. Follow-up goals receive a new brief-bound proposal, preserving prior proposals rather than changing their immutable goal identity.
- Proposed hypotheses and timeframes are AI suggestions, not user facts or observed market results. Unknown risk/constraints stay in the canonical brief; missing/ambiguous prerequisites block generation rather than acquiring invented values. Users can edit/save hypotheses as USER_AUTHORED revisions while retaining AI_RESEARCHED origin and prior history. The UI displays proposal/revision identity, constraints/provenance, limitations, revision history and EVIDENCE_PENDING.
- Explicit Attach/check approved historical evidence reuses the existing trusted readiness binding and R2 verifier; no source discovery or approval is added. Only same-scope approved sources can supply a pending reference. Data verification is recomputed for the exact new revision and displayed independently; it never grants research review approval, claim support or execution authority. Missing, tampered or incompatible sources remain pending/blocked.
- Final verification level FULL_REGRESSION_PASS: original Windows venv `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,555 passed, 158 subtests, 60 retained-private-native-evidence skips, three existing deprecation warnings. Final focused workflow/goal/R1/readiness/computational regression: 168 passed, including 26 new workflow cases and Streamlit AppTest. Compileall, documentation and diff checks pass; static safety remains one production order_send call-site and zero MetaTrader5 imports under src.
- Not verified: real provider inference, live MongoDB failover or deployed-browser acceptance. Tests use bounded synthetic provider/data and a locked Mongo CAS fixture, not real broker results. The original live-configured dirty checkout was not restarted or changed. No live MT5, research computation, native Tester, G2.2, Hyper-V or Issue Bridge runtime was invoked.
- Known limit: an interrupted/failed generation is not automatically retried; its durable claim/status remains visible, and a new explicit goal request is required for a fresh generation. Existing R1 approval/export and research execution gates remain separate; this slice supplies no approval or computation control. Original worktree/cache/personal rules/journals are preserved.

# 162. GOAL-DRIVEN LIVE INTEGRATION AND EXPLICIT RECOVERY

- Implemented from 5350261 in an isolated worktree. The configured real Groq openai/gpt-oss-120b semantic path produced a canonical Vietnamese Research Brief. Real MongoDB sessions persisted the goal and R1 AI_RESEARCHED proposal; strict reload confirmed the original AI_SUGGESTED revision plus a USER_AUTHORED edit, preserved 1%/5% research constraints and no research review/trading authority. Conversation switching hid foreign research state and restored the exact proposal/head.
- Runtime defect: actual generation failed the existing timeframes schema. The prior prompt omitted the authoritative supported enum/field schema. Added the existing ResearchContent schema and supported-timeframe enum to the provider prompt, without normalizing/truncating invalid output or relaxing validation. Schema-only failure codes expose field/type, never raw values. Two invalid responses were rejected; two explicit UI recovery actions were used after the initial Generate, and the final response passed. No automatic retry or provider fallback was added.
- Recovery supersedes section 161's new-brief limitation: explicit confirmation + Retry/recover reuses the same brief/slot. A crash-releasing OS lock covers the provider call; Mongo CAS, per-attempt identity and a snapshot token prevent concurrent generation and stale completion. Active workers block recovery. Foreign-host ownership fails closed and requires the owning instance; legacy claims require operator confirmation that no old instance is running. No timer, listener, queue, collection or execution authority was added.
- Runtime defect: hard refresh after switching chose the most recently updated conversation, not the selected one. Existing app navigation now carries the selected conversation in the URL, admitting only IDs returned by existing session discovery. Live refresh retained the exact edited revision even with a newer empty conversation. Deleted/unknown IDs still follow the existing safe fallback.
- Live R2 check returned EVIDENCE_PENDING / RESEARCH_REVISION_NOT_VERIFIED with no approved binding for this new conversation. No dataset or evidence result was fabricated and no approval was written. Existing R1/R2 authorization and research execution gates remain unchanged.
- Verification level FULL_REGRESSION_PASS plus real application acceptance: final full Windows-venv pytest command passed 4,565 tests and 158 subtests, with 60 retained-private-native-evidence skips and three existing warnings. Final focused workflow/computational/history tests: 144 passed, including 36 workflow cases and real-app Streamlit AppTest. Compileall, documentation/diff and scoped secret checks passed. OS-lock tests proved active-process exclusion and lock release after abrupt child exit; those tests are not live broker evidence.
- Acceptance used a separate real Streamlit process on 127.0.0.1:8503 with execution/management kill switches true, submission/order-send/autonomous flags false and bridge URL deliberately unreachable. Runtime environment, source worktree marker and HTTP 200/ok were verified. Existing trading-configured app on 8501 was not restarted; no global .env, account, mandate, broker, Hyper-V, Tester, G2.2 or Issue Bridge runtime was changed. The safe research instance remains available separately.
- AGENTS Git policy now reflects standing authorization for verified fast-forward development pushes to main, preserving task-specific prohibitions and dirty checkout safety. Original dirty checkout/data remain preserved. Not verified: cross-host forced takeover, Mongo failover, hypothesis quality/performance or any trading/research computation; none is implied by this live UI acceptance.

# 163. GOAL-DRIVEN STRATEGY SPECIFICATION AND TEST PLAN

- Implemented from 804fc8d: saved hypothesis -> explicit Develop testable strategy -> one existing provider call -> strict G1 ComputationalSpecification inside optional R1 ResearchDevelopment -> immutable AI_SUGGESTED revision -> structured JSON editor -> USER_AUTHORED revision -> persistent reload. No new semantic resolver, storage collection, research engine or executable strategy is created. Canonical brief constraints remain authoritative and unchanged.
- G1 formula/steps/parameters and entry/exit/reentry/management retain open-ended inert expressions. Research-design fields record IS/OOS scope, transaction-cost definitions, evaluation/rejection criteria and missing information. Existing QueryPlan completeness/range checks are reused; missing/conflicting requirements remain visible. These are reviewable proposals, not validated algorithms or automatically approved risk budgets. Free-text rule timing, cost realism and IS/OOS disjointness still require review; schema validity cannot prove them.
- Reuses the existing same-host OS generation lock and Mongo CAS against the exact brief/scope/head. Stale, concurrent and cross-conversation writes fail closed; failed development leaves the saved hypothesis intact and requires another explicit action. Changing the hypothesis invalidates its dependent specification. New specification revisions retain evidence references as PENDING, never old validation. Optional-field serialization preserves pre-existing R1 hashes when development is absent.
- R2 additionally checks the current developed data requirements rather than stale hypothesis timeframe metadata: fields, symbol/timeframe, lookback and contiguous pre-window warmup. Insufficient or unsupported data stays pending/limited, independently of proposal approval, claim support, strategy performance and execution authority. No source discovery/acquisition/approval was added.
- Verification FULL_REGRESSION_PASS: final focused Windows-venv command covering goal strategy/workflow/brief, computational specification, R1, R2 and readiness: 210 passed, including 21 new cases and Streamlit AppTest. Final full `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,586 passed, 158 subtests, 60 retained-private-native-evidence skips, three existing warnings. Documentation, compileall, diff and scoped secret/static safety checks separate.
- Real Groq openai/gpt-oss-120b and MongoDB/UI acceptance on isolated trading-disabled port 8504: three explicit development attempts, two invalid responses rejected, then one typed specification saved after schema-aligned prompt correction; no automatic retry. Subsequent structured edit persisted a fourth proposal revision, preserving original hypothesis revisions and 1%/5% canonical research constraints. Refresh/switch restored the correct head; empty conversation exposed no foreign card. R2 remained EVIDENCE_PENDING / RESEARCH_REVISION_NOT_VERIFIED without an approved source binding.
- Test instance source/process/hash/health and fail-closed permissions verified; Windows UTF-8 was set only in its child environment. Existing live-configured app, authority, mandates, broker state and original dirty checkout were untouched. No MT5, research computation/backtest, generated-code execution, G2.2, Hyper-V, native Tester or Issue Bridge activity. Known limitations: no distributed-host development lock/Mongo failover acceptance, no strategy-quality/performance claim; real data, costs and exact test windows remain prerequisites for further research.

# 164. HISTORICAL RESEARCH DATA INTEGRATION

- Implemented from 2150e64: optional typed UTC start/end/split and explicit session policy in R1 development revisions; Streamlit edits these directly. Enforces start < split < end when a split is supplied, aware UTC normalization and timeframe-aligned boundaries. Missing split or costs do not prevent a fully specified read-only acquisition; missing acquisition dates remain unresolved. No dates, policy, risk or cost values are selected automatically.
- Frozen request projections reuse G1 requirements, configured broker mapping and Sprint 11A HistoricalDataRequest. The authenticated broker-read-only POST /research/history/export delegates to the existing host exporter, which independently checks DEMO identity, stable account, symbol mapping and closed history. No src MetaTrader5 import, new acquisition engine or trading authority. Exported manifest/data bytes are locally verified through load_dataset and mirrored without overwriting approved artifacts; warmup is fetched explicitly before the evaluation window, never invented or counted as scored research bars.
- Existing Mongo conversation records/CAS and OS exclusion retain acquisition claims, explicit retry state, exact dataset/checksum source approvals and R2 attachment. Source approval constructs the existing ApprovedHistoricalSource; R2 validation, R1 review and preparation remain separate. Every required timeframe needs its own compatible verified source. Cost/split-only revisions reuse unchanged raw exports, require current-revision R2 revalidation/review, and cannot display an obsolete revision's input package as current. Historical approvals and immutable artifacts remain preserved.
- Four editable cost assumptions retain value, unit, source/assumption note and per-entry revision authorship. AI suggestions cannot become user-confirmed merely through unrelated edits. Historical spread is exposed in broker points when present; commission/swap are not exported and slippage is not observable from OHLCV. Declared assumptions are explicitly NOT broker-verified, even when their value is an explicit zero. No automatic conversion or cost fabrication.
- After exact source validation and explicit R1 acceptance, the existing no-overwrite publisher prepares r1-evaluation-input/v1 with pinned proposal/spec/dataset identity, disjoint half-open IS/OOS partitions and past-only warmup_context_not_scored. Missing source, fields, coverage, warmup, split or costs blocks preparation; computation/trading authorization stays false. Existing high-low input/computation contracts are unchanged and not invoked for an unrelated strategy.
- Verification FULL_REGRESSION_PASS: final focused Windows-venv pytest across historical integration, goal strategy/workflow, R1/R2/input, historical/session and bridge/semantic boundaries: 270 passed, including 35 new cases and Streamlit AppTest. Final full `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,621 passed, 158 subtests, 60 retained-private-native-evidence skips, three existing warnings. An initial static-boundary failure was fixed by moving editor validation into the existing R1 contract, not weakening its architecture test. Compilation, documentation, diff and scoped security checks separate.
- Real Streamlit/Mongo read-only acceptance on isolated port 8505 confirmed editable blank UTC/split/cost inputs and HISTORICAL_ACQUISITION_PENDING_USER_INPUT. Existing proposal remained four revisions with zero acquisition records or review approvals. Operator explicitly withheld date/split selection; no acquisition, source approval, evaluation or new LLM inference was performed. Software fixtures/HTTP tests are not real historical coverage evidence. Existing trading-enabled processes/configuration, account/mandates/positions and original dirty checkout were untouched.
- Remaining real prerequisites: operator-confirmed UTC/split/session policy, supported raw data requirements (current dataset field is unresolved; derived indicators are not raw OHLCV fields), sourced cost assumptions, then separately requested acquisition/source review. Live MT5 endpoint acceptance, research performance, cross-host exclusion and Mongo failover remain unverified. No G2.2, native Tester, generated code, backtest, Hyper-V or Issue Bridge activity; no implicit trading/research execution permission.

# 165. OPEN-ENDED DATA DEPENDENCY RESOLUTION

- Extended existing G1 data requirements with optional typed computations: exact output name, indicator ID/parameters/output component, or inert custom definition with typed RAW_MT5/DERIVED inputs and declared total lookback/warmup. FLOAT64, INT64 and UTC_SECONDS are explicit data types. No name/period parsing, formula evaluation, new semantic resolver, research engine or LLM call. Existing canonical/research prompts describe the same schema for future explicit requests.
- Existing registry definitions and parameter validation supply supported raw dependencies, formula version, minimum bars, warmup and timeframe compatibility. Defaults are not substituted for missing indicator parameters. Explicit inadequate counts or conflicting input/output types remain blockers; original specification values/provenance are not overwritten. Custom declarations can resolve raw inputs but remain DECLARED_UNVERIFIED without a verified implementation.
- The shared metadata resolver serves historical_requests and independent R2 checks. Same-market/timeframe raw requirements are deduplicated and combined at their largest compatible requirements; different timeframes remain separate. Cycles, undeclared fields, duplicate/shadowing aliases, missing inputs and conflicts block the affected group. Only raw schema fields enter historical requests/input projections; derived outputs are never requested from MT5. Existing source approval and revision-specific review/computation gates remain independent.
- Empty optional computation lists are omitted during serialization, preserving legacy G1/R1 identity hashes. No stored proposal, dataset, binding, cost assumption, IS/OOS or approval was migrated or rewritten. Streamlit displays supported raw types, derived/unsupported computations, explicit versus required counts and exact blockers without acquisition.
- Verification FULL_REGRESSION_PASS: final focused Windows-venv pytest across dependencies, historical/goal workflows, G1, R1/R2 input and semantic boundaries: 322 passed, including 41 new cases and Streamlit AppTest. Final full `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,662 passed, 158 subtests, 60 retained-private-native-evidence skips, three existing warnings. Compilation, documentation/diff and scoped security checks separate. Fixtures prove software contracts, not actual market or numerical-parity results.
- Safe port-8506 Streamlit/Mongo read-only acceptance confirmed current bare derived names need declarations instead of inferred periods. Existing proposal stayed four revisions with no acquisition records/review approvals; UTC/cost inputs and HISTORICAL_ACQUISITION_PENDING_USER_INPUT remain unchanged. Source/process/hash/health and fail-closed environment verified; original dirty checkout and trading-enabled instances were untouched.
- Not verified or authorized: indicator execution on actual data, custom implementation correctness, research/backtest performance, live acquisition, generated code, native Tester or G2.2. Next necessary product input is an explicit typed dependency declaration and the already-required research scope; this milestone does not grant any execution or data-source authority.

# 166. HISTORICAL FEATURE COMPUTATION

- Implemented from cf80fe1: explicit Compute research features uses existing G1 declarations, INDICATOR_REGISTRY and calculate_indicator_snapshot. EMA/SMA/RSI/ATR/MACD/BOLLINGER_BANDS use exact supported parameters, selected output component and production formula versions. No new indicator engine, expression evaluator, LLM call or execution authority. Custom declarations remain DECLARED_UNVERIFIED, displayed separately; invalid parameters/components do not acquire defaults.
- Approved r1-evaluation-input/v1 packages are strictly reconstituted from the current accepted R1 revision, R2 source approval, manifest/data pins and typed historical request before computation. Feature-only preparation bypasses only missing trading-cost assumptions, explicitly marks FEATURE_INPUT_ONLY and retains unknown costs. Full evaluation-input preparation still requires costs; UTC/split, coverage, warmup, source and approval gates remain enforced. Existing default preparation bytes are unchanged.
- Replay uses continuous approved prefixes, never future bars. IS history is past context for OOS, not a reset seed. Each value records original open timestamp, completed_at, partition, parameters and formula; warmup is unscored with explicit unavailable statuses. Multi-timeframe alignment admits only source bars completed at or before evaluation time. Shared calculations reuse identical parameter/formula prefixes while respecting separate declared warmup requirements.
- Existing DescriptiveComputationApproval now admits HISTORICAL_FEATURES_V1 only as an explicitly approved operation. Its input_sha256 pins the displayed canonical multi-input request descriptor, including every package/source checksum, current proposal/specification/scope and calculation-source/Python hash. It is not a substitute for individual input hashes. Existing publisher writes reproducible content-addressed r1-research-features/v1 results without overwriting different content; production float64 semantics are recorded, not represented as exact Decimal math.
- Mongo conversation CAS plus existing OS exclusion claims a RUNNING attempt before calculation. Reload never computes; duplicate PASS returns the pinned verified artifact, FAILED needs a fresh explicit click, RUNNING cannot automatically retry. Stale/concurrent revisions cannot publish as current; historical immutable artifacts remain preserved. Research acceptance, source approval, feature-computation consent and trading authorization remain distinct.
- Streamlit shows available/blocked computations, explicit input preparation, pinned request approval, series values and completed-bar-aligned IS/OOS results. AppTest found and fixed a nested-expander incompatibility. No backtest, signal, simulated fill, profitability or live-trade claim is made.
- Verification FULL_REGRESSION_PASS: focused Windows-venv pytest on historical_features, goal_historical_data_integration, research_data_dependencies, research_input_package and descriptive_research_computation: 173 passed, including 36 new cases and AppTest. Final full pytest with .env.example child-only boolean defaults: 4,698 passed, 158 subtests passed, 60 private-native-evidence skips, four warnings (two protobuf deprecations, an unrelated Tkinter finalizer warning and existing utcnow deprecation). Compileall, documentation and diff checks separate; scoped safety scan retains one production order_send call-site and zero src MetaTrader5 imports.
- Real safe port-8507 browser/Mongo read-only acceptance showed RESEARCH_FEATURE_DEPENDENCIES_UNRESOLVED and unresolved UTC/data requirements. Existing conversation remained four revisions with zero historical acquisition, review or feature-run records. Process cwd/source hashes, health and fail-closed child configuration verified. No real historical feature computation or acquisition occurred; fixture calculations are not real market evidence. Trading-enabled processes/configuration and original 95-path dirty checkout/index were untouched.
- Known limits: bounded prefix replay fails closed above 5,000,000 prefix-bar operations or 100,000 result/alignment cells; no truncation or unverified batch substitute. An interrupted RUNNING claim remains blocked rather than guessed completed/retried. Distributed execution/Mongo failover, custom formula correctness and actual strategy performance remain unverified. No G2.2, Hyper-V, native Tester, generated code, Bridge automation or broker mutation.

# 167. HISTORICAL STRATEGY SIGNAL EVALUATION

- Goal-Driven research revisions now carry optional typed ENTRY/EXIT rule groups, explicit ALL/ANY composition, exact G1 feature output references and a user-selected completed-bar evaluation timeframe. Free-text strategy descriptions remain inert and unchanged. Missing/unsupported timing, inputs and operators stay UNRESOLVED, not guessed. Empty optional rules preserve legacy R1 identity.
- Streamlit saves and confirms the rule contract separately from R1/R2 acceptance and computation consent. Unchanged rule confirmation preserves the accepted revision and its evidence; changed research content requires reconfirmation. Evidence-only descendants retain rule review. No implicit approval of rules from a generic edit or LLM suggestion.
- Historical replay adapts verified features to existing StrategyRule/evaluate_strategy_rule. LEVEL and EDGE/re-arm use completed clocks only; previous observations can use past IS at the OOS boundary but cannot bridge missing clock/source bars. Unknown required operands block the group. Signals are condition observations, not orders, fills, positions or performance.
- Explicit HISTORICAL_SIGNALS_V1 consent pins the proposal/revision/specification, R1/R2 sources and input checksums, exact feature artifact, rule review, IS/OOS window and evaluator code. The existing publisher creates immutable-by-contract content-addressed r1-research-signals/v1 results. Existing Mongo CAS and OS lock prevent automatic/duplicate reruns and stale result attachment. UI displays UTC entry/exit observations, IS/OOS counts, operand provenance and unresolved rules.
- FULL_REGRESSION_PASS: 4,735 passed, 158 subtests passed, 60 skipped (private native evidence), three warnings. Focused Windows-venv signal/feature/historical/specification/core/R1 regression: 169 passed, including Streamlit AppTest. Compileall, documentation integrity and diff checks passed.
- Separate local Streamlit 8508 read-only acceptance verified current real conversation shows RESEARCH_SIGNAL_RULES_UNRESOLVED and HISTORICAL_ACQUISITION_PENDING_USER_INPUT. Source/process/health and child-only disabled trading flags verified; Mongo showed zero signal runs or acquisitions. No real data computation, broker or authority mutation. Original dirty checkout preserved.
- Limits: completed-bar-close only; unverified custom formulas stay inert, and over 100,000 condition observations block instead of truncating. No generated code, trading, G2.2 or backtest. Next: confirm typed dependencies and rules, select UTC/IS-OOS, approve and compute exact inputs before authorizing real signal evaluation.

# 168. NATIVE TESTER REPORT ADMISSION AND PERFORMANCE REVIEW

- Goal-Driven now shows native Tester readiness after Historical Signals. Missing UTC/IS-OOS, confirmed costs and current complete signal evidence are distinct from native mapping, parity, isolation and operator run-approval blockers. The app does not launch Tester or authorize a run.
- Existing StrategyParity is a fixed M1 RSI/ATR14 math probe and at most one virtual BUY, not a typed-strategy executor. No conversion from prose, unsupported rule mapping or substitute fill model was added. Rechecked the retained, checksum-pinned old CSV read-only: 57/58 vectors match, with real_16 still mismatching SL, TP and risk. This is not current-native parity evidence.
- The read-only consumer is enabled only by a deployment-owned RESEARCH_NATIVE_TESTER_RECEIPT_SHA256 pin for an independently reviewed receipt. It looks up canonical native_tester_receipt_<sha>.json, native_tester_result_<sha>.json and opaque native_tester_raw_<sha>.bin in the existing research results directory. It checks bytes, exact current R1 revision and signal identity (including R2 inputs), native build/model and the attested strategy/binary/report/isolation/parity/run-approval hashes. There is no UI pin entry or automatic receipt creation. Host review is the trust anchor; hashes are not independent proof that Tester ran or that a raw report was normalized correctly.
- The bounded ledger comparison requires every native signal (including non-triggers) to agree in both partitions. Validates strictly post-signal fill times in UTC milliseconds, flat partition boundaries, single non-overlapping full-volume entry/exit, SL/TP direction, observed costs, native net P&L and equity endpoints. Partial fills, carry across splits, unknown cost evidence, optimization and other fill models are not admitted. Drawdown is based on the supplied native equity curve; monetary metrics use Decimal. No Python fill simulator.
- UI shows separate IS/OOS counts, gross/net P&L, costs, win rate, profit factor, expectancy, equity/drawdown and provenance only for admitted reports. Undefined ratios remain absent. Review remains INCONCLUSIVE until explicit research criteria and review exist; no implicit strategy acceptance or promotion.
- FOCUSED_PASS: 216 passed, 60 archived-evidence skips in the isolated worktree, including Streamlit AppTest. The historical CSV check above separately used read-only original retained evidence. Documentation integrity, compileall and diff check run separately. No shared calculation, broker or execution core changed; no full regression or running app restart.
- Remaining gates: verified native strategy mapping and result producer, whole-environment isolation, new math parity, exact approved data/costs/rules, and separate native run approval. No genuine Tester run, current parity PASS, performance result or broker mutation in this sprint.

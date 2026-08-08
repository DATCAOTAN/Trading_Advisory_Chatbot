# Trading Advisory Chatbot - Sprint Changelog

This file contains concise, append-only sprint history.

## Documentation roles

- `TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md`
  - Current architecture and current verified state.

- `docs/engineering/SPRINT_CHANGELOG.md`
  - Concise historical sprint records.

- Git commits and diffs
  - Detailed source-level implementation history.

## Verification levels

Use exactly one:

- `IMPLEMENTED_NOT_VERIFIED`
- `STATIC_ONLY`
- `FOCUSED_PASS`
- `FOCUSED_AND_LIVE_PASS`
- `FULL_REGRESSION_PASS`

Never claim full-regression success unless the full regression was actually executed.

---

## Current Baseline - MT5 Live Adapter Disabled + Pre-Submit Gate

Date recorded: 2026-07-21
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: `10107f0`

### Implemented

- Added the disabled app-side MT5 live adapter shape.
- Added the pre-submit safety gate for disabled execution checks.
- Added kill switch reporting with the default state engaged.
- Added check-only idempotency registration and duplicate blocking.
- Added pre-submit journal records with hashed idempotency data.
- Confirmed the app can reach the MT5 bridge write skeleton endpoint.
- Confirmed the bridge write skeleton remains blocked and non-submitting.
- Preserved the current no-order, no-ticket, no-deal execution state.

### Verification

- Focused tests: `scripts/test_mt5_live_adapter_disabled_pre_submit_gate.py -q` -> 12 passed.
- Neighboring tests: `scripts/test_mt5_request_dict_final_validation_and_bridge_skeleton.py -q` -> 24 passed.
- Neighboring tests: `scripts/test_mt5_request_dict_dry_run_builder.py -q` -> 75 passed.
- Compileall: passed.
- Docker Compose config: passed.
- Docker restart: passed.
- Application health: healthy; Streamlit health reported ok.
- Live check: latest pre-submit live check passed.
- Static scan: handoff reports no `MetaTrader5` import under `src/`, no real `order_send` call, and no forbidden bridge order endpoint.
- Full regression for this sprint: NOT RUN.
- Historical regression reference only: 2461 passed, 156 subtests passed, 3 warnings.
- The historical result predates the current pre-submit sprint and does not verify the current sprint.

### Current state

- Latest completed boundary: MT5 Live Adapter Disabled + Pre-Submit Gate.
- Bridge status: write skeleton reachable and `BLOCKED`.
- Adapter status: `BLOCKED_BY_DISABLED_ADAPTER`.
- Pre-submit status: `PASSED_DISABLED_PRE_SUBMIT_CHECK`.
- Controlled demo integration workflow: allowed.
- Live submission: blocked.
- `order_send`: blocked.
- Kill switch: engaged.
- Idempotency: `CHECK_REGISTERED`.
- Order sent: false.
- Ticket/deal: none.
- Next planned sprint: Controlled Demo `order_send` Integration.

### Not implemented

- Controlled demo submission.
- Real broker-submittable MT5 request dictionary.
- Real MT5 payload or order constants in an active submit path.
- Order/position reconciliation and failure recovery.
- Runtime supervision or autonomous execution.

---

## Sprint Entry Template

Use this only for sprint-level or architecture-changing work.

### Sprint <number> - <name>

Date:
Verification:
Commit:

#### Implemented

- ...

#### Verification

- Focused tests:
- Neighboring tests:
- Compileall:
- Static scan:
- Docker/live check:
- Full regression:

#### Current state

- ...

#### Not verified / not implemented

- ...

#### Known limitations

- ...

#### Next step

- ...

---

### Sprint 34A - Immutable Approved Semantic Execution Parameters

Date: 2026-07-21
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: included in this commit

#### Implemented

- Added one frozen, typed approved semantic execution-parameter contract to the existing approval/lock module.
- Canonicalized 12 allow-listed semantic fields and bound them to approval, lock, source, and timestamps with SHA-256.
- Made value mutation, reference mutation, missing fields, extra fields, unsupported semantics, and non-finite numerics fail closed.
- Propagated and verified the same hash through parameterization, final review, dry-run request-dict, and final validation.
- Kept legacy schema-only behavior compatible; the explicit approved-value path must opt in and fails closed when values are absent.
- Kept exact values out of general serialization, formatters, journals, logs, and documentation.

#### Verification

- New focused tests: 19 passed.
- Neighboring focused tests: 198 + 129 + 188 = 515 passed; total focused tests: 534 passed.
- Compileall on changed paths: passed.
- Static scan: 0 `MetaTrader5` imports under `src`; 0 real `order_send` calls under `src`/`tools`; bridge code unchanged.
- Docker Compose config and app restart: passed; Streamlit health returned HTTP 200 `ok`.
- Disabled pre-submit live check: passed with bridge reachable and `BLOCKED`, kill switch engaged, and no order sent.
- Full regression: NOT RUN.

#### Current state

- Approved semantic values can be integrity-bound without granting execution permission.
- Live submission, execution, and `order_send` remain disabled; ticket/deal remain none.

#### Known limitations / next step

- No protected persisted value store, bridge submission schema, account classification, idempotency reservation, result classification, or reconciliation exists yet.
- Next: Controlled Demo Bridge Submission Prerequisites.

---

### Sprint 34B - Controlled MT5 Execution Integration

Date: 2026-07-21
Verification: `FOCUSED_PASS`
Commit: included in this commit

#### Implemented

- Added one shared account-agnostic protected execution path to the existing adapter and host bridge.
- Added authenticated bridge validation for semantic integrity, references, freshness, confirmation, permissions, terminal capability, and account fingerprint.
- Added atomic restart-safe idempotency states and protected result classification with no automatic retry.
- Added one isolated production `order_send` call-site and a disabled-by-default manual entry point.
- Kept ticket/deal values out of responses and retained exact values only in the protected execution journal.

#### Verification

- New focused tests: 16 passed using fake MT5 only.
- Direct neighboring execution/bridge tests: 130 passed.
- Changed-path compileall, Docker Compose config, app restart, and Streamlit HTTP 200 `ok`: passed.
- Static scan: 0 `MetaTrader5` imports under `src`; exactly 1 production `order_send` call-site.
- Automated broker submission: NOT RUN. Manual broker submission: NOT RUN. Full regression: NOT RUN.

#### Current state

- Controlled execution exists but remains disabled by default; kill switch remains engaged.
- Default live submission, execution, and order-send flags remain false; no order was sent during verification.

#### Known limitations / next step

- Broker-state reconciliation and recovery for unknown outcomes are not implemented.
- Next: Sprint 35 - Order/Position Reconciliation and Failure Recovery.

---

### Sprint 35 - MT5 Reconciliation and Failure Recovery

Date: 2026-07-21
Verification: `FOCUSED_PASS`
Commit: included in this commit

#### Implemented

- Extended the existing protected execution journal with stable correlation metadata and restart-safe reconciliation records.
- Added authenticated read-only bridge reconciliation for bounded MT5 order, deal, and position evidence.
- Added stale `RESERVED` abandonment and stale `SUBMISSION_STARTED` recovery to `RESULT_UNKNOWN`.
- Confirmed unknown results only from one unique correlated evidence group; ambiguity, no match, and query failure remain non-retryable.
- Kept exact broker identifiers in the protected journal and exposed only redacted presence flags.
- Added one app-side reconciliation contract and reused the existing adapter and bridge client.

#### Verification

- New focused tests: 20 passed.
- Direct neighboring tests: controlled execution 16, disabled pre-submit 12, final validation/bridge skeleton 24, request-dict dry-run builder 75; focused total 147 passed.
- Compileall for `src`, `scripts`, and `tools`: passed.
- Static scan: 0 `MetaTrader5` imports under `src`; exactly 1 production `.order_send(` call-site; 0 forbidden bridge endpoints.
- Docker Compose config, app restart, and container health: passed (`healthy`).
- Manual reconciliation, terminal-backed reconciliation, broker submission, live check, and full regression: NOT RUN.

#### Current state

- Reconciliation is read-only and enabled; submission, execution, order-send, and automatic retry remain disabled by default.
- Kill switch remains engaged; no order was sent during verification.

#### Known limitations / next step

- Existing pre-Sprint-35 journal entries without correlation metadata cannot use the new reconciliation endpoint.
- Correlation currently relies on protected metadata plus broker relationships unless an approved comment already carries the stable tag.
- Next: Sprint 36 - End-to-End Runtime Testing and Simplification.

---

### Sprint 36 - End-to-End Verification, Hardening and MVP Closure

Date: 2026-07-22
Verification: `FULL_REGRESSION_AND_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added one 21-test fake-MT5 milestone suite for blocked, submit-once, duplicate, account-change, unknown-result, reconciliation, restart, corruption, auth, integrity, and redaction paths.
- Made protected execution-journal corruption and conflicting transitions fail closed.
- Updated legacy preflight scans to enforce one host-bridge call-site and zero app/reconciliation call-sites.
- Reused the existing protected POST helper in the bridge client; no new boundary or framework was added.

#### Verification

- Milestone tests: 21 passed; neighboring controlled/reconciliation tests: 72 passed.
- Preflight and permission regression: 205 passed.
- Full scripts regression: 2577 passed, 156 subtests passed, 3 dependency warnings.
- Compileall, `docker-compose config --quiet`, app restart, and Streamlit HTTP 200 health: passed.
- Static scan: 1 production `.order_send(` in `tools/mt5_bridge/execution.py`; 0 under `src/` and reconciliation; 0 MetaTrader5 imports under `src/`.
- Bridge runtime: health OK; write skeleton BLOCKED; missing/invalid reconciliation auth rejected with HTTP 401; no execution journal created.
- Fake latency, 20 samples: controlled median 58.546 ms, p95 63.871 ms; reconciliation median 55.941 ms, p95 60.812 ms; controlled execution was slowest.

#### Current state

- Live submission, execution, order-send, executable, order-sent, and automatic-retry flags remain false; kill switch remains engaged.
- Controlled MT5 execution MVP is complete for automated fake-MT5 and non-submitting bridge verification.

#### Not verified / known limitations

- No controlled-submit request, manual broker submission, or terminal-backed reconciliation of an actual order was performed.
- Position lifecycle management, runtime supervision, autonomous operation, and live-account promotion remain unimplemented.

#### Next step

- Operator decision on separately authorized manual demo-account submission and terminal-backed reconciliation; do not infer execution authority from MVP completion.

---

### Post-MVP Operator Tooling - Protected Artifact Capture

Date: 2026-07-22
Verification: `PROTECTED_ARTIFACT_CAPTURE_PASS`
Commit: included in this commit

#### Implemented

- Added one CLI and one orchestration module that create the nine protected artifacts required by the existing controlled-request exporter.
- Reused the existing proposal, approval-lock, final-validation, disabled pre-submit, and read-only account-context services.
- Added typed account-context and standalone confirmation artifacts bound to proposal, lock, final-validation, semantic-hash, and account-fingerprint references.
- Added exclusive protected persistence, final-manifest integrity verification, exporter compatibility checking, and failed-bundle cleanup.
- Kept runtime journals isolated and temporary; no controlled submission or reconciliation path is called.

#### Verification

- New focused capture tests: 13 passed.
- Focused plus neighboring approval-lock, exporter, final-validation, pre-submit, and controlled-execution tests: 135 passed.
- Changed-path compileall and static execution-boundary scans: passed.
- Real terminal artifact capture and export-only operator acceptance: NOT RUN.

#### Current state / next step

- All execution defaults remain blocked and the kill switch remains engaged.
- Run one export-only acceptance with operator-approved semantic input and a testing-account terminal before any manual controlled submission.

---

### Phase 2 - Read-Only Position Lifecycle and Runtime Supervisor

Date: 2026-07-22
Verification: `FOCUSED_AND_READ_ONLY_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added one read-only lifecycle supervisor inside the existing MT5 execution ownership and one operator CLI.
- Reused the protected execution journal and bridge client; added bounded authenticated lifecycle snapshots with broker identifiers hashed host-side.
- Added deterministic lifecycle states, redacted discrepancy reporting, append-only restart recovery, stable idempotency, overlap prevention, and single-instance locking.
- Kept submission, reconciliation, order mutation, execution flags, and automatic retry outside this workflow.

#### Verification

- Focused supervisor tests: 25 passed; neighboring reconciliation, journal, and controlled-execution tests: 57 passed.
- Changed-path compileall, static scans, `docker-compose config --quiet`, app restart, and Streamlit HTTP 200 health: passed.
- Non-submitting terminal runtime cycle: `HEALTHY`, 0 protected records inspected, 0 discrepancies, 26.296 ms.
- Static state: exactly 1 production `.order_send(` call-site; 0 `MetaTrader5` imports under `src`; 0 lifecycle submission, reconciliation, or mutation calls.
- Full regression: NOT RUN for this task; prior post-confirmation-split regression remains 2612 tests and 156 subtests passed.

#### Current state / limitations / next step

- Live submission, execution, order-send, executable, and order-sent remain false; the kill switch remains engaged.
- No broker submission or lifecycle reconciliation was performed; real-record lifecycle tracking and long-duration polling remain unverified.
- Next: collect bounded read-only lifecycle evidence from future protected execution records and run a soak before changing architecture.
---

### Sprint 38 - Controlled MT5 Position Management

Date: 2026-07-22
Verification: `FOCUSED_AND_BLOCKED_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added immutable proposal/request/receipt contracts for cancel, protection modification, and full/partial close of one existing MT5 target.
- Bound each request to a fresh lifecycle observation, account fingerprint, protected broker-reference hash, intent-specific confirmation, mutation hash, and idempotency key.
- Reused the shared adapter, protected execution/lifecycle journals, bridge authentication, account context, lifecycle snapshots, and isolated submission function.
- Added independent host-bridge target resolution, policy/capability checks, management idempotency states, redacted receipts, and one manual operator CLI.
- Preserved unrequested protection fields and prohibited volume increase, unrelated position creation, automatic retry, and autonomous mutation.

#### Verification

- Focused controlled-management tests: 33 passed; neighboring lifecycle, reconciliation, idempotency/pre-submit, controlled-execution, and MVP tests: 94 passed.
- Changed-path compileall, `docker-compose config --quiet`, app restart, and Streamlit HTTP 200 health: passed.
- Blocked runtime: bridge `OK`; missing/invalid auth returned HTTP 401; all three valid intents returned `MANAGEMENT_DISABLED`; no runtime journal was created.
- Static scan: exactly 1 production `.order_send(` call-site, 0 `MetaTrader5` imports under `src`, and 0 management retry markers.
- Full regression and manual broker mutation: NOT RUN.

#### Current state / limitations / next step

- Controlled management, all intent permissions, live execution, and order-send remain disabled; hard block and kill switches remain engaged.
- Fake-MT5 mutation/reconciliation paths are verified, but no real pending order or position was changed.
- Next: Sprint 39 - Autonomous Decision Orchestrator; it must produce decisions only and must not grant execution authority.
---

### Sprint 39 - Autonomous Decision Orchestrator

Date: 2026-07-23
Verification: `FOCUSED_AND_NON_EXECUTING_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added one frozen, versioned, non-executable candidate contract and one deterministic orchestrator under existing trading decision ownership.
- Reused structured context, method-selection, score, readiness/risk, lifecycle, and reconciliation artifacts; no free-text output grants authority.
- Added fail-closed classification for stale, incomplete, conflicting, risk-blocked, account-mismatched, ambiguous lifecycle, unresolved reconciliation, and unsafe journal state.
- Added canonical provenance/idempotency hashing, restart-safe append-only journaling, duplicate suppression, redacted public output, and one non-executing CLI.

#### Verification

- Focused orchestrator tests: 33 passed; neighboring decision-policy, scoring, lifecycle, and reconciliation tests: 93 passed.
- Changed-path compileall, `docker-compose config --quiet`, app restart, and Streamlit HTTP 200 health: passed.
- Non-executing runtime: `NO_ACTION`, `VALID`, one decision journal record, `execution_authority=false`, 973.165 ms.
- Static scan: exactly 1 production `.order_send(` call-site; 0 `MetaTrader5` imports under `src`; 0 orchestrator/CLI mutation calls; 0 execution-authority-true markers.
- Full regression and broker execution: NOT RUN.

#### Current state / limitations / next step

- All candidates and runtime outputs remain non-executable; autonomous execution, live execution, order-send, and broker mutation remain disabled.
- Sprint 39 is one-shot only; it does not schedule decisions or authorize/submit/manage broker actions.
- Next: Sprint 40 - Autonomous Execution Policy Gate, independently deterministic and blocked by default.

---

### Sprint 40 - Autonomous Execution Policy Gate

Date: 2026-07-23
Verification: `FOCUSED_AND_POLICY_BLOCKED_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added one deterministic, frozen, versioned policy result and gate under existing decision ownership.
- Mapped candidates only to block, human review, or eligibility for an existing controlled open/management boundary.
- Added fail-closed provenance, freshness, risk, account, lifecycle, reconciliation, exposure, close-volume, and persistence checks.
- Added canonical policy/idempotency hashing, protected append-only journaling, redacted serialization, and one non-executing CLI.
- Kept policy/open/management eligibility disabled and the policy hard block enabled by default.

#### Verification

- Focused policy tests: 34 passed; neighboring orchestrator, decision-policy, lifecycle, reconciliation, and management tests: 133 passed; controlled-execution integration tests: 16 passed.
- Changed-path compileall, `docker-compose config --quiet`, app restart, and Streamlit HTTP 200 health: passed.
- Blocked runtime: `BLOCK`, target `NONE`, validation `VALID`, journal appended; execution authority and executable remained false.
- Static scan: exactly 1 production `.order_send(` call-site; 0 `MetaTrader5` imports under `src`; 0 policy/CLI mutation calls or authority-true defaults.
- Full regression and broker mutation: NOT RUN.

#### Current state / limitations / next step

- Policy eligibility is not approval or execution authority; every submission/execution/order flag remains false.
- No scheduler, continuous loop, autonomous confirmation, controlled endpoint call, or broker operation was added.
- Next: Sprint 41 - Soak Test, Hardening, and Release Closure.

---

### Sprint 41 - Soak Test, Hardening, and Release Closure

Date: 2026-07-23
Verification: `FULL_REGRESSION_SOAK_AND_RUNTIME_PASS`
Commit: included in this commit

#### Implemented

- Added one integrated release-closure test file; no production feature, boundary, adapter, endpoint, scheduler, or permission was added.
- Covered non-mutating decision/policy flow, default blockers, restart/idempotency, bridge loss, auth failure, timeout, overlap, unknown-result retry prohibition, corruption, redaction, and static invariants.
- No production defect or evidence-supported Sprint 37-40 simplification was found.

#### Verification

- Closure tests: 7 passed; full scripts regression: 2,744 passed, 156 subtests passed, 3 dependency warnings, 132.69 seconds.
- Fake soak: 300 decision, 300 policy, 200 lifecycle, and 50 reconciliation-read samples; 11 bounded journal records totaling 15,248 bytes.
- Fake soak after warm-up: RSS +24,576 bytes; threads 15 to 15; no crash, deadlock, conflict, or authority leak.
- Terminal read-only soak: 620.2 seconds, 60 health checks, 60 lifecycle snapshots, and 10 blocked decision/policy checks.
- Runtime measurement: health median/p95 3.393/10.948 ms; lifecycle 6.265/13.133 ms; bridge RSS +12,288 bytes; threads 13 to 13.
- Docker config/app restart/HTTP 200, bridge restart/health/market data, HTTP 401 auth rejection, write-skeleton block, management blockers, and one healthy lifecycle cycle passed.
- Static state: exactly 1 production `.order_send(` call-site; 0 `MetaTrader5` imports under `src`; 0 autonomous/runtime mutation markers.

#### Current state / limitations / completion

- All execution, management, retry, and autonomous policy permissions remain blocked by default; broker mutation was NOT RUN.
- Three regression warnings are upstream dependency deprecations; actual broker submission and position mutation remain operator-only and unverified in this closure.
- The planned sprint roadmap is complete. No Sprint 42 is planned; future work is operational acceptance or evidence-driven maintenance only.

---

### Post-release Maintenance - Structured Market and Pending Order Intent Candidate

Date: 2026-07-23
Verification: `FOCUSED_AND_RUNTIME_PASS`
Commit: NOT COMMITTED

#### Implemented

- Extended the existing autonomous candidate and structured-input parser for BUY, SELL, LIMIT, STOP, and STOP_LIMIT proposals; no parallel candidate or execution boundary was added.
- Added deterministic action resolution, Bid/Ask and optional symbol-metadata checks, separate stop-limit trigger/limit fields, integrity hashing, and redacted public output.
- Preserved legacy decision/management behavior and all non-executable safety flags.

#### Verification

- Focused structured-order candidate tests: 29 passed.
- Neighboring orchestrator and autonomous policy tests: 67 passed.
- Changed-path compileall and static scans passed: 0 `MetaTrader5` imports under `src/`, exactly 1 existing production `.order_send(` call-site.
- Docker Compose config, app restart/healthy status, Streamlit HTTP 200 (`ok`), and a valid non-broker candidate v2 smoke passed.
- Full regression, bridge runtime, controlled endpoints, and broker mutation: NOT RUN.

#### Current state / limitations

- Structured proposals remain advisory and non-executable; LLM-supplied action cannot override deterministic resolution.
- Symbol metadata is consumed only when supplied by the structured snapshot; no universal distance constant is assumed.
- This is post-release maintenance, not Sprint 42.

---

### Post-release Maintenance - Read-only Streamlit Market/Pending Order Review Card

Date: 2026-07-23
Verification: `FOCUSED_AND_LIVE_PASS` (Streamlit runtime scope)
Commit: NOT COMMITTED

#### Implemented

- Added typed session ownership for one already-produced `AutonomousDecisionRunResult`; replacement and clearing remain explicit and rendering never generates a candidate.
- Added a bounded operator-review projection with proposal values required for local review while preserving the existing redacted public serialization and journals unchanged.
- Reused the existing presenter, Review Card, resolver output, and validation result for conditional MARKET, LIMIT, STOP, and separate STOP_LIMIT trigger/limit display.
- Preserved v1, NO_ACTION, human-review, management, missing-state, freshness, deterministic blocker order, and non-executable safety behavior.
- Added no button, scheduler, duplicate validator, candidate producer, LLM call, journal access, bridge call, confirmation, permission, or broker mutation path.

#### Verification

- Focused Review Card tests: 20 passed; neighboring candidate/orchestrator/policy/dashboard tests: 132 passed.
- Changed-path compileall and static scans passed: 0 `MetaTrader5` imports under `src/`, exactly 1 unchanged production `.order_send(` call-site.
- Docker Compose config, app restart, healthy status, and Streamlit HTTP 200 (`ok`) passed.
- Streamlit AppTest rendered a typed v2 stop-limit result through the session owner twice with 0 exceptions, 0 buttons, exact bounded proposal values, `NON_EXECUTABLE` safety, and journal count unchanged at 1.
- Full regression, MT5 bridge runtime, controlled endpoints, and broker mutation: NOT RUN.

#### Current state / limitations

- A producer must explicitly store its already-produced typed run result; page load and refresh intentionally do not run the autonomous orchestrator or LLM.
- This is post-release maintenance, not a new execution, permission, or approval boundary.

---

### Post-release Maintenance - Controlled Pending Order Contract and Dry-Run Mapping

Date: 2026-07-24
Verification: `FOCUSED_AND_PENDING_DRY_RUN_PASS`
Commit: NOT COMMITTED

#### Implemented

- Added one typed pending-order contract and semantic dry-run mapper inside existing controlled execution ownership; no new package, endpoint, permission boundary, or UI flow was added.
- Supports all six LIMIT, STOP, and STOP_LIMIT types while preserving separate stop-limit trigger/limit fields.
- Reuses candidate validation and canonical snapshot hashing; requires symbol metadata, fresh matching protected account context, and existing review/confirmation references bound to candidate provenance and structured-order integrity.
- Produces a redacted public contract and request draft only for valid reviewed inputs; all execution flags remain false.

#### Verification

- Focused pending-contract tests: 35 passed.
- Neighboring candidate, policy, approval, semantic-contract, request-draft, and dry-run-validator tests: 319 passed.
- Changed-path compileall and static safety scans: passed.
- Fixture `BUY_STOP_LIMIT` dry-run: `VALID`; trigger/limit separate; no bridge request, execution journal, or broker mutation.
- Full regression, Docker/runtime checks, MT5 bridge pending execution, controlled submission, and broker mutation: NOT RUN.

#### Current state / limitations

- Bridge pending-order execution is not implemented; this boundary is reviewed dry-run preparation only.
- Exactly one existing production `.order_send(` call-site remains; `src/` has zero `MetaTrader5` imports.
- Next task, only if explicitly approved: Controlled Pending Order Submission.
---

### Post-release Maintenance - Controlled Pending Order Submission

Date: 2026-07-24
Verification: `FULL_REGRESSION_PASS`
Commit: `67844f9`; regression fix: `02c3298`

#### Implemented

- Extended the existing protected request, shared adapter, authenticated controlled-submit endpoint, execution journal, reconciliation, and lifecycle ownership; no parallel endpoint, adapter, journal, or approval framework was added.
- Supports all six LIMIT, STOP, and STOP_LIMIT types with independent app/bridge validation and exact stop-limit trigger-to-`price`, limit-to-`stoplimit` mapping.
- Added terminal Bid/Ask, tick/digits/stops, volume-step, GTC, pending-family, account, reference, freshness, and integrity checks.
- Preserved one isolated production `order_send` call-site, protected result redaction, completed-result replay, conflicting duplicate blocking, and retry-prohibited `RESULT_UNKNOWN`.

#### Verification

- Focused pending-submission tests: 28 passed; neighboring pending dry-run, market controlled-submit, management, reconciliation, and lifecycle tests: 129 passed.
- Changed-path compileall and `git diff --check`: passed.
- Docker Compose config/app restart: passed; app healthy and Streamlit HTTP 200 (`ok`).
- Host bridge health: `OK`; protected pending runtime attempt: HTTP 403 `EXECUTION_DISABLED`, no order sent, identifiers null.
- Read-only lifecycle snapshot: `OK`; reconciliation read: `NOT_REQUIRED`, `RETRY_PROHIBITED`, identifiers null.
- Static scan: exactly 1 production `.order_send(` call-site, 0 `MetaTrader5` imports under `src/`, 1 existing controlled-submit endpoint, and 0 autonomous submission calls.
- Full scripts regression: 2,865 passed and 156 subtests passed in 155.84 seconds; 3 dependency warnings. Broker mutation: NOT RUN.

#### Current state / limitations

- App and bridge pending submission plus LIMIT, STOP, and STOP_LIMIT family flags remain disabled/hard-blocked by default.
- Runtime reconciliation used an existing non-reconcilable protected record, so no broker-history match was required.
- Next: pending-order operational acceptance with explicit operator enablement on a testing account; no autonomous submission.

---

### Post-release Maintenance - Pending Artifact Capture and Validation-Only Export

Date: 2026-07-24
Verification: `PASS_WITH_RUNTIME_CANDIDATE_LIMITATION`
Commit: NOT COMMITTED

#### Implemented

- Added explicit protected handoff for an existing typed reviewed pending candidate and its typed market snapshot.
- Reused the existing pending dry-run mapper and controlled pending request builder to export `controlled-mt5-pending-execution/v1`.
- Added one path-only CLI, atomic/idempotent protected bundle writes, integrity validation, and an explicit non-submitting Streamlit action.
- Kept public serialization redacted and every execution, submission, executable, and order-send flag false.

#### Verification

- Focused pending artifact tests: 30 passed; neighboring export, capture, candidate, Review Card, pending dry-run, and controlled-submission tests: 150 passed with 2 dependency warnings.
- Changed-path compileall and `git diff --check`: passed.
- Docker app restart/healthy and Streamlit HTTP 200 (`ok`): passed; execution journals changed: 0.
- Static scan: exactly 1 production `.order_send(` call-site, 0 `MetaTrader5` imports under `src/`, protected output path Git-ignored, pending defaults disabled/hard-blocked.

#### Current state / limitations / next step

- Runtime had no authoritative typed reviewed pending candidate; no fixture was substituted and no runtime pending artifact was exported.
- Full regression, controlled submission, reconciliation, and broker mutation: NOT RUN.
- Next: pending-order operational acceptance after a real runtime candidate is explicitly reviewed and handed off.
---

### Verification Follow-up - Pending Artifact Capture Full Regression

Date: 2026-07-24
Verification: `FULL_REGRESSION_PASS`
Commit verified: `8de0d94`

- Full scripts regression: 2,895 passed and 156 subtests passed in 132.11 seconds.
- Warnings: 3 dependency deprecations; no test failures.
- Controlled submission, reconciliation, runtime candidate export, and broker mutation: NOT RUN.
- Operational status remains `PASS_WITH_RUNTIME_CANDIDATE_LIMITATION` until a real typed reviewed runtime candidate is explicitly handed off and exported.

---

### Post-release Maintenance - Operator-Triggered Autonomous Candidate Generation

Date: 2026-07-24
Verification: `PASS_WITH_RUNTIME_INPUT_LIMITATION`
Commit: NOT COMMITTED

#### Implemented

- Added one concrete authoritative input assembler over the existing feature, calendar, regime, knowledge, reasoning, scoring, readiness, and read-only lifecycle services.
- Added one explicit Streamlit generation action and a session-guarded controller that calls the existing orchestrator once and stores only a valid persistence-safe typed result through the existing owner.
- Preserved read-only Review Card ownership, explicit replacement/clear semantics, duplicate/rerun protection, deterministic validation, and all non-executable safety flags.
- Added no scheduler, background worker, alternate candidate model, execution boundary, automatic export, permission control, bridge mutation, or fallback trading value.

#### Verification

- Focused generation tests: 34 passed; neighboring orchestrator/candidate/review/policy/export tests: 146 passed; dashboard safety tests: 36 passed.
- Changed-path compileall, `git diff --check`, ignore checks, and static safety scans: passed.
- Docker Compose config/app restart: passed; app healthy; Streamlit HTTP 200 (`ok`); bridge `OK`, terminal connected.
- Streamlit runtime: action rendered and initial session had no candidate; generation failed closed before orchestration with `LIFECYCLE_UNAVAILABLE` because the runtime lifecycle auth token was unavailable.
- Execution journal hash/size and protected artifact count remained unchanged; autonomous decision journal remained absent.

#### Current state / limitations / next step

- Implementation and focused verification are complete; a real typed runtime result remains blocked by missing read-only lifecycle authentication.
- Automatic export, controlled submission, reconciliation mutation, broker mutation, and order submission: NOT RUN.
- Next: provide the existing lifecycle endpoint authentication to the runtime, click generation once, then use validation-only pending export only if the authoritative result is a valid PENDING candidate.


---

### Post-release Maintenance - Authoritative Non-Executable Proposal Owner

Date: 2026-07-25
Verification: `FOCUSED_PASS`
Commit: NOT COMMITTED

#### Implemented

- Added one upstream typed owner for non-executable autonomous order proposals; no execution, approval, export, bridge, or UI boundary was added.
- Reused the existing project model router, typed feature/context/method/score/readiness artifacts, autonomous order contracts, resolver, and lifecycle-gated operator assembler.
- Strict JSON output is accepted once per explicit generation request; prose, extra or missing fields, incomplete values, stale evidence, malformed or mismatched bindings, symbol conflicts, invalid price relations, and model failures return ordered blockers before orchestration.
- Raw model output, hidden reasoning, credentials, and full provider responses are not persisted. Normalized proposal fields may appear in the bounded operator Review Card; approved references and integrity hashes may appear in redacted/public candidate serialization. All execution flags remain unchanged.

#### Verification

- Focused proposal-provider tests: 30 passed.
- Focused operator-generation tests: 36 passed with 2 dependency warnings.
- Existing method-selector adapter tests: 18 passed; mapping, plain-string, malformed-response, and provider-metadata compatibility are also covered by the provider suite.
- Changed-path compileall and `git diff --check`: passed.
- Docker/Streamlit health passed before the binding-only correction; it was not rerun for this focused review-gap pass.
- Static scan: exactly 1 production `.order_send(` call-site and 0 `MetaTrader5` imports under `src/`.

#### Current state / limitations / next step

- No runtime candidate, live LLM call, artifact export, controlled submission, reconciliation mutation, or broker mutation was run.
- Current app market ownership provides authoritative tick/bid/ask and source bindings but not point/tick-size/digits/stops-level; downstream pending validation remains fail-closed when those fields are required.
- Next: review and commit, then perform one explicit post-commit runtime generation with fresh data.

---

### Post-release Maintenance - Isolated Offline Candidate Acceptance

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one offline-only CLI with eight deterministic scenarios and an injected fixed clock.
- Reused the authoritative proposal parser/normalizer, market/input validators, candidate orchestrator, readiness classification, and reason ordering.
- Marked fixture-derived candidates with integrity-bound offline provenance and blocked protected handoff/pending mapping with `OFFLINE_PROVENANCE_NOT_EXECUTABLE`.
- Added no UI, network adapter, candidate schema, live path, approval artifact, export, submission, retry, or broker mutation.

#### Verification

- Focused offline harness tests: 29 passed.
- Neighboring proposal/candidate/pending/export/submission/reconciliation/lifecycle tests: 238 passed with 2 dependency warnings.
- Changed-path compileall and eight scenario smoke runs: passed.
- Full regression: 2,990 passed and 156 subtests passed with 3 dependency warnings; compileall passed. Ponytail full-mode review passed; no duplicated policy, network boundary, retry, or speculative abstraction was found.

#### Current state / limitations / next step

- Offline MARKET/PENDING results are non-exportable and non-submittable engineering evidence only.
- Live acceptance remains `DEFERRED_UNTIL_FRESH_XAUUSDM_MARKET_DATA`.
- Next: complete full regression/static review, retain the harness, then wait for genuinely fresh XAUUSDm tick and M15/H1/H4 data for a separately approved one-attempt live acceptance.
---

### Post-release Maintenance - Hermetic Offline and Regression LLM Isolation

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added a root process-local pytest bootstrap that disables structured external reasoning before dotenv-backed settings load and excludes two manual root runners from default discovery.
- Added a constructor-level fail-closed guard for known external reasoning providers in hermetic tests and all project LLM clients in offline acceptance mode.
- Kept the offline harness deterministic with a restored process-local marker; production runtime and every execution/export/submission gate remain unchanged.

#### Verification

- Focused hermetic and offline suites: 37 passed.
- Default full regression without a shell LLM override: 2,998 passed and 156 subtests passed with 3 dependency warnings.
- Changed-path compileall and `git diff --check`: passed; external provider constructors/requests: 0; `.env`: unchanged and untracked.

#### Current state / next step

- No external LLM, bridge, export, submission, reconciliation mutation, or broker mutation was run.
- Live acceptance remains `DEFERRED_UNTIL_FRESH_XAUUSDM_MARKET_DATA`; next is the separately authorized one-attempt live acceptance after fresh XAUUSDm tick and M15/H1/H4 bars are available.

---

### Post-release Maintenance - Broker-Aligned Multi-Symbol Candidate Flow

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reused the shared symbol resolver for canonical and broker identities across operator generation, market data, candidate integrity, pending dry-run, bridge validation, and reconciliation.
- Added `BTCUSD -> BTCUSDm`, preserved the existing XAUUSD mapping, and preserved the no-symbol XAUUSD default.
- Propagated existing broker symbol metadata required for deterministic freshness, spread, volume, pending-order, and terminal checks.
- Removed XAUUSD/gold fallback leakage from BTCUSD calendar and knowledge selection; BTC spread configuration fails closed by default.

#### Verification

- BTCUSD-focused tests: 10 passed.
- Focused and neighboring symbol/market/candidate/pending/reconciliation tests: 398 passed.
- Full regression: 3,008 passed and 156 subtests passed with 3 dependency warnings.
- External LLM, candidate generation, bridge runtime, export, submission, reconciliation mutation, `order_send`, and broker mutation: NOT RUN.

#### Current state / limitations / next step

- All execution, submission, autonomous execution, and management defaults remain disabled and hard-blocked.
- BTCUSDm runtime freshness, account/lifecycle health, and one natural candidate result remain unverified.
- Next: separately authorize one BTCUSDm live-acceptance attempt while execution, export, and submission remain disabled.

---

### Post-release Maintenance - Task-Scoped BTCUSD M1 Acceptance Profile

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reused the existing request-scoped timeframe input and added M1 to the supported timeframe normalizer with a 300-second freshness threshold.
- Added one explicit BTCUSD-only UI checkbox that requests `M1,H1,H4`; ordinary requests still use `M15,H1,H4`.
- Preserved XAUUSD as the permanent default and preserved all operating-mode, approval, execution, export, submission, and broker-mutation gates.

#### Verification

- Focused M1/multi-symbol tests: 16 passed.
- Neighboring market/operator/provider/orchestrator/Review Card tests: 164 passed.
- Full regression: 3,014 passed and 156 subtests passed with 3 dependency warnings.
- Live candidate generation, export, submission, reconciliation mutation, `order_send`, and broker mutation: NOT RUN before commit.

#### Current state / next step

- Implementation and regression verification are complete; runtime acceptance is pending.
- Next: run the separately authorized BTCUSDm M1/H1/H4 preflight and make at most one natural candidate-generation attempt.

---

### Post-release Maintenance - MT5 Completed-Bar Normalization

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Corrected the existing host bridge OHLCV read to start at MT5 position `1`, the latest completed bar, instead of position `0`, the currently forming bar.
- Applied the same existing bridge path to M1, M15, H1, H4, and other supported timeframes without adding a market-data pipeline or changing freshness thresholds.
- Preserved the BTCUSD `M1,H1,H4` acceptance profile and the default XAUUSD `M15,H1,H4` profile.

#### Verification

- Raw read-only MT5 evidence confirmed position `0` is current and position `1` is completed for M1, H1, and H4; epoch timestamps normalized to UTC once.
- Focused and neighboring market-data tests: 45 passed with 2 dependency warnings.
- Full regression: 3,016 passed and 156 subtests passed with 3 dependency warnings.
- Live bridge/provider comparison exposed completed bars only; the current H4 bar was no longer incorrectly classified as complete.

#### Current state / next step

- The earlier stale M1/H1 terminal history synchronized before the final comparison; no timestamp conversion defect was found.
- External LLM calls, candidate generation, export, submission, reconciliation mutation, `order_send`, and broker mutation: 0.
- Next: wait until the completed M1/H1/H4 set passes existing freshness gates, then authorize a separate one-attempt candidate acceptance.

---

### Post-release Maintenance - Completed-Bar Close-Time Freshness

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one shared duration mapping for the existing supported timeframes.
- Changed the existing quality gate to measure completed-bar age from close time, not open time.
- Preserved MT5 current-bar exclusion, freshness thresholds, timeframe profiles, and ordered stale reason behavior.

#### Verification

- Focused freshness/provider/candidate-readiness tests: 130 passed with 2 dependency warnings.
- Full regression: 3,017 passed and 156 subtests passed with 3 dependency warnings.
- Documentation, compile, diff, safety, and Ponytail checks passed.

#### Current state / next step

- External LLM, candidate generation, export, submission, reconciliation mutation, `order_send`, and broker mutation: 0.
- Next: run a new read-only BTCUSDm M1/H1/H4 preflight; authorize one generation attempt only if completed bars are fresh.

---

### Post-release Maintenance - Structured Proposal JSON Compatibility

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reproduced the structured proposal failure offline across plain, fenced, prose-wrapped, double-encoded, malformed, empty, non-finite, schema-invalid, and split reasoning/content responses.
- Requested Groq JSON-object mode for the autonomous proposal through the existing LLM client, bounded tokens, and disabled fallback for that structured call.
- Added minimal strict normalization for one exact outer JSON fence and one double-encoded JSON string while preserving rejection of prose and malformed or schema-invalid output.
- Kept response extraction on final `message.content`; proposal schema, candidate authority, execution flags, and all broker boundaries are unchanged.

#### Verification

- Focused proposal/provider tests: 42 passed.
- Neighboring adapter/orchestrator/offline/hermetic tests: 153 passed with 2 dependency warnings.
- Full regression: 3,029 passed and 156 subtests passed with 3 dependency warnings.
- External LLM calls, generation, export, submission, reconciliation mutation, `order_send`, and broker mutation: 0.

#### Current state / next step

- The previous live raw response was not persisted, so its exact wrapper remains unknown; repository compatibility defects are fixed and covered offline.
- Next: separately authorize one new BTCUSDm candidate-generation attempt after the normal fresh-data preflight.

---

### Post-release Maintenance - Groq Windows-Safe Structured Transport

Date: 2026-07-26
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Diagnosed `STRUCTURED_PROPOSAL_MODEL_UNAVAILABLE` as a Windows console `UnicodeEncodeError` before Groq HTTP transport.
- Replaced the structured Groq route log with ASCII-safe output.
- Applied the configured timeout and `max_retries=0` to structured JSON calls while preserving no fallback.
- Added fixed, redacted provider failure categories and fail-fast missing-credential handling.

#### Verification

- Focused provider/hermetic/operator tests: 96 passed.
- Full regression: 3,039 passed and 156 subtests passed with 3 dependency warnings.
- Direct non-trading probe: 1; HTTP response: none; candidate generation and all MT5/broker operations: 0.

#### Current state / next step

- Production defaults, proposal schema, execution boundaries, and disabled permissions are unchanged.
- Next: separately authorize one minimal post-fix Groq JSON transport probe before any candidate generation.

---

### Post-release Maintenance - Structured Proposal Field Contract

Date: 2026-07-27
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Kept the exact ten-field proposal schema and made the complete `NO_PROPOSAL` shape explicit in the existing structured prompt.
- Required null order/trade fields and a non-empty reason-code list for natural no-proposal output, with field-specific redacted blockers.
- Preserved strict rejection of missing/extra fields, unsupported statuses, malformed values, invalid relationships, retries, fallback, and field repair.

#### Verification

- Focused provider/contract tests: 63 passed.
- Neighboring operator/candidate/multi-symbol/offline/hermetic tests: 118 passed with 2 dependency warnings.
- Full regression: 3,050 passed and 156 subtests passed with 3 dependency warnings.
- External LLM, generation, MT5, market data, retries, fallback, export, submission, controlled-submit, `order_send`, and broker mutation: 0.

#### Current state / next step

- The earlier live key set was not persisted; the three-field no-proposal fixture is only the minimal deterministic reproducer.
- A valid no-proposal response stops before candidate creation as `STRUCTURED_PROPOSAL_NOT_AVAILABLE`.
- Next: separately authorize one fresh BTCUSD acceptance attempt; do not retry within this maintenance task.

---

### Post-release Maintenance - Runtime Input Handoff Reference Clock

Date: 2026-07-27
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reproduced `STRUCTURED_RUNTIME_INPUT_STALE` hermetically with fresh structured artifacts created ten seconds after the pre-reasoning reference time.
- Confirmed no Streamlit session/cache reuse and no snapshot-reference loss in the authoritative assembler path.
- Kept the market-preflight clock and captured a current post-reasoning handoff clock for structured-input and proposal validation.
- Preserved the 300-second TTL, five-second skew allowance, snapshot/provenance bindings, completed-bar rules, profiles, provider contract, and disabled execution gates.

#### Verification

- Focused and neighboring runtime-input, proposal, snapshot, session, hermetic, and offline tests: 177 passed with 2 dependency warnings.
- Full regression: 3,055 passed and 156 subtests passed with 3 dependency warnings.
- MT5, market data, Streamlit generation, external LLM, candidate generation, retry, fallback, export, submission, controlled-submit, `order_send`, and broker mutation: 0.

#### Current state / next step

- Fresh structured inputs remain valid after normal reasoning latency; genuinely stale inputs and mismatched proposal snapshot bindings still fail closed.
- Next: separately authorize one fresh BTCUSD acceptance attempt. No live acceptance was run in this maintenance task.

---

### Post-release Maintenance - Offline Actionable Candidate Lifecycle

Date: 2026-07-28
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Extended the existing deterministic harness through authoritative proposal validation, candidate admission, journal persistence, integrity/provenance checks, and idempotent duplicate rejection.
- Added valid natural no-proposal, MARKET, and PENDING outcomes plus price, volume, freshness, source, account, lifecycle, malformed JSON, and schema-invalid failures.
- Classified valid `NO_PROPOSAL` as operator `NO_ACTION` before orchestration; no candidate or journal record is created.
- Preserved offline provenance, non-executable candidates, protected-handoff rejection, and every disabled execution boundary.

#### Verification

- Focused offline/operator tests: 95 passed.
- Combined neighboring suites: 327 passed with 2 dependency warnings.
- Full regression: 3,080 passed and 156 subtests passed in 220.78 seconds with 3 dependency warnings.
- External LLM, MT5, export, submission, reconciliation mutation, `order_send`, and broker mutation: 0.

#### Current state / next step

- Offline actionable candidate lifecycle: verified complete through authoritative persistence and duplicate-safe admission.
- Next: offline operator review and human-confirmation lifecycle acceptance using the persisted actionable candidate; execution remains disabled.

---

### Post-release Maintenance - Operator Review and Human Confirmation Lifecycle

Date: 2026-07-28
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reused the existing autonomous decision and proposal-intent journals to reload protected actionable candidates and persist one confirm/reject transition.
- Expanded the existing Review Card with candidate, broker symbol, timeframe, method, market, account-binding, expiry, and integrity details.
- Bound confirmation to the exact candidate/proposal hashes and references, protected account context and fingerprint hash, symbol/order/timeframes, phrase, nonce, timestamps, and disabled permissions.
- Added fail-closed duplicate, tamper, switching, wrong-account, expiry, partial-journal, and Streamlit rerun handling without a parallel approval path.

#### Verification

- Focused lifecycle tests: 24 passed; focused Review Card/confirmation group: 98 passed.
- Full regression: 3,105 passed and 156 subtests passed in 175.47 seconds with 3 dependency warnings.
- External LLM, MT5, market data, live generation, export, submission, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- MARKET and PENDING candidate review, explicit confirmation/rejection, protected persistence, and idempotent reload are complete while candidates remain non-executable.
- Next: approval integrity, final validation, and pre-submit gate verification as a separate milestone; execution remains disabled.

---

### Post-release Maintenance - Approval Integrity and Pre-Submit Lifecycle

Date: 2026-07-28
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Extended the existing protected candidate and confirmation journals with the market/runtime evidence and confirmation timestamp required for authoritative reload.
- Added exact candidate-confirmation-source binding, independent account/order/metadata/capability/lifecycle/reconciliation/permission validation, and protected intent construction in the existing pre-submit package.
- Reused the existing pre-submit report, journal record, store, and controller; exact duplicates are idempotent and confirmation reuse or journal corruption fails closed.
- MARKET and `BUY_LIMIT` PENDING reach `PRE_SUBMIT_READY_NON_EXECUTABLE`; all execution and submission permissions remain disabled.

#### Verification

- Focused milestone tests: 24 passed; directly affected confirmation/proposal tests: 100 passed.
- Full regression: 3,129 passed and 156 subtests passed in 215.32 seconds with 3 dependency warnings.
- Compileall passed. External LLM, MT5, market data, live generation, export, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- Approval integrity, final validation, persistent idempotency, and non-submitting pre-submit readiness are complete for authoritative MARKET and PENDING candidates.
- Next: a separately authorized controlled demo submission acceptance. No submission permission was enabled in this milestone.

---

### Post-release Maintenance - Protected Manual Operator Candidate Entry

Date: 2026-07-29
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added explicit `MANUAL_OPERATOR` proposal provenance to the existing candidate schema, journal, Review Card, confirmation bindings, and protected pre-submit intent.
- Reused authoritative market/account metadata, deterministic method selection, scoring, risk, lifecycle, reconciliation, order validation, and candidate admission.
- Added one dashboard form with no prefilled trade values and no automatic confirmation, export, pre-submit, or execution action.
- Prevented invalid manual proposals from being journaled and preserved deterministic duplicate admission across equivalent decimal text.
- Fixed false duplicate journal conflicts caused by tuple/list differences after JSON reload.

#### Verification

- Focused manual/operator/review/confirmation/pre-submit tests: 123 passed.
- Neighboring candidate/policy/pending tests: 229 passed.
- Full regression: 3,142 passed and 156 subtests passed with 3 unchanged dependency warnings.
- External LLM, controlled-submit, runtime `order_send`, retries, fallback, and broker mutation: 0.

#### Current state / next step

- Manual candidate implementation is complete and non-executable; no runtime manual candidate, confirmation, pre-submit artifact, or submission was created in this task.
- Next: operator enters one exact demo proposal through the dashboard form; subsequent confirmation and submission still require separate explicit actions.

---

### Post-release Maintenance - Read-only Completed-Bar Candidate Monitor

Date: 2026-08-02
Verification: `FOCUSED_PASS`
Commit: 04479e5

#### Implemented

- Added one CLI monitor around the existing live feature, authoritative input, proposal, orchestrator, and protected candidate journal path.
- Claimed each symbol/timeframe/completed-bar key before generation and prohibited automatic retry after an interrupted attempt.
- Persisted only redacted monitor status; Streamlit reads status and existing protected candidates without starting work on rerun.
- Preserved disabled execution, export, submission, management, reconciliation mutation, and broker permissions.

#### Verification

- Focused monitor tests: 8 passed.
- Neighboring candidate/provider/orchestrator/review/manual/policy tests: 206 passed with 2 dependency warnings.
- Changed-path compileall, CLI help, diff check, journal-ignore check, and static safety scans passed.
- Production `order_send` call-sites: 1; MetaTrader5 imports under `src/`: 0.

#### Current state / next step

- Monitor implementation is verified; the watch loop and external LLM were not started automatically.
- Next: operator starts the BTCUSD M1/H1/H4 monitor explicitly and observes the first natural new-bar result while execution remains disabled.

---

### Production Completion - Standing Mandate and Mode Authority

Date: 2026-08-02
Verification: `FOCUSED_PASS`
Commit: this commit

#### Implemented

- Added one protected hash-chained authority journal for `advisory_only`, `human_confirmed_live`, and `autonomous_live` mode changes, standing-mandate grant/update/revocation, and exact-candidate mandate authorization.
- Bound mandates to a demo account fingerprint, symbols, MARKET/PENDING and management families, volume/risk/position/trade/loss limits, active window, expiry, nonce, idempotency, operator grant, and kill-switch state.
- Extended the existing approval/pre-submit lifecycle with an explicit `HUMAN_CONFIRMATION` versus `STANDING_MANDATE` source discriminator; the two record types cannot substitute for each other.
- Autonomous mode reloads and revalidates the current mode, mandate version/revocation, exact candidate/order parameters, account, expiry, and kill switch before the existing non-executable pre-submit journal is appended.
- Advisory candidates cannot create approval authority, real-account inputs fail closed, and all submission/execution flags remain disabled.

#### Verification

- Standing mandate/mode/authorization and neighboring approval/confirmation/permission tests: 153 passed with 2 unchanged dependency warnings.
- Changed-package compileall and diff check passed.
- External LLM, MT5, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- Stage 1 authority ownership is complete at focused verification level.
- Next: integrate the completed-bar monitor into one bounded coordinator; no autonomous execution authority is enabled by default.

---

### Production Completion - Bounded Coordinator and Monitor Integration

Date: 2026-08-02
Verification: `FOCUSED_PASS`
Commit: this commit

#### Implemented

- Reduced the completed-bar monitor to an account-scoped trigger/checkpoint and moved proposal assembly, candidate admission, runtime-state checks, mode authority, mandate authorization, and optional pre-submit transition into one `AutonomousTradingCoordinator`.
- Added persisted account+symbol+timeframe claims, cross-account isolation, unresolved-STARTED hard blocking, next-bar duplicate protection, and backward-compatible strict reads for the previous monitor journal schema.
- Reconciliation/lifecycle conflict blocks before orchestration; advisory and human modes stop at their proper non-executing boundaries; autonomous mode requires current mandate context before exact-candidate authorization.
- The CLI now constructs the coordinator and closes the bridge client on normal exit or interruption. Streamlit remains read-only and does not start the coordinator on rerun.

#### Verification

- Coordinator/monitor/mandate focused tests: 29 passed; focused and neighboring candidate/proposal/policy/review/manual/pre-submit suites: 307 passed.
- Changed-path compileall passed. External LLM, MT5, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- Stage 2 bounded coordination is complete at focused verification level; the monitor is no longer an independent business-logic owner.
- Next: attach the existing controlled execution/result/reconciliation/lifecycle/management services to the coordinator using deterministic fake boundaries.

---

### Production Completion - Mandate-Controlled Execution Integration

Date: 2026-08-02
Verification: `FOCUSED_PASS`
Commit: this commit

#### Implemented

- Added a `STANDING_MANDATE` discriminator to the existing controlled-submit request without changing the human-confirmation contract or endpoint.
- The host bridge reloads the shared protected authority journal, current mode, mandate and exact-candidate authorization before idempotency reservation or MT5 mapping.
- Autonomous requests are demo-only, exact-candidate/order/account/mandate bound, and independently hard-blocked by a new default-false bridge flag.
- The existing coordinator can pass a pre-submit-ready mandate request through the existing adapter; accepted, rejected and unknown receipts retain the existing protected journal and state machine.
- Current host market price is selected only inside the bridge for MARKET execution when the approved candidate intentionally has no fixed entry price.

#### Verification

- Autonomous mandate bridge/coordinator and execution/reconciliation/lifecycle/management neighbors: 157 passed with 2 unchanged dependency warnings.
- Fake controlled-submit attempts exercised accepted, rejected, unknown, duplicate, revoked-mandate and non-demo account paths. Real external operations: 0.
- Production `order_send` call-sites remain 1; MetaTrader5 imports under `src/` remain 0.

#### Current state / next step

- Stage 3 controlled execution integration is complete at focused verification level; management and reconciliation continue through their existing services and remain disabled by default.
- Next: expose authoritative mode/mandate/supervisor state through existing Streamlit controllers and complete restart/readiness verification.

---

### Production Completion - Runtime, Observability, and Readiness Closure

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Wired the existing authority, approval/pre-submit, policy, coordinator, disabled adapter, and completed-bar monitor into one production CLI path.
- Added authoritative lifecycle aggregate/capability evidence for standing-mandate limits and fail-closed mandate risk evaluation from broker metadata.
- Required the autonomous policy gate before mandate authorization and preserved all default execution, submission, management, and kill-switch blocks.
- Added service-owned Streamlit mode/mandate/supervisor controls plus redacted lifecycle, permission, execution, reconciliation, and unknown-result observability.

#### Verification

- Focused/neighboring completion tests: 243 passed; final coordinator/runtime tests: 14 passed.
- Full regression: 3,186 passed and 156 subtests passed in 160.55 seconds with 3 unchanged dependency warnings.
- Compileall and diff checks passed. Production `order_send` call-sites: 1; MetaTrader5 imports under `src/`: 0.
- Real external LLM, MT5, controlled-submit HTTP, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- `AUTONOMOUS_TRADING_SOFTWARE_IMPLEMENTATION_COMPLETE`; working permissions remain disabled and hard-blocked by default.
- `OPERATIONAL_ACCEPTANCE_PENDING`; next work is one separately authorized demo-account operational acceptance, not another implementation sprint.

---

### Software Release Finalization

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS` (preserved evidence)
Commit: this release documentation commit

#### Implemented

- Corrected the existing local and host-bridge runbooks to document authenticated read-only and controlled endpoints, default hard blocks, startup, shutdown, and redaction.
- Recorded software commit `e8f516d`, release tag `v1.0.0-software-complete`, completed lifecycle, safety invariants, and the separation between implementation completion and operational acceptance.

#### Verification

- Preserved verified evidence: 3,186 regression tests and 156 subtests passed; Ponytail review passed.
- Documentation integrity, path/config validation, and Git diff checks passed for release finalization.
- Real LLM, MT5, controlled-submit HTTP, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- Software release is complete locally with no production blocker.
- Operational acceptance remains pending and requires a separately authorized demo-account procedure. No push was performed.

---

### Maintenance - Authoritative Dashboard Runtime State

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Made the existing Dashboard reload and display authoritative account, mode, lifecycle, reconciliation, unresolved-state, permission, and kill-switch state through the existing operator service.
- Made BTCUSD selection resolve to BTCUSDm and activate the existing M1/H1/H4 profile; XAUUSD keeps configured defaults.
- Reloaded market freshness, completed bars, capability, features, calendar, regime, and live-price labels for the selected symbol without silent fallback.
- Replaced one stale bridge-documentation assertion exposed by regression with the current controlled-endpoint hard-block invariants.

#### Verification

- Focused Dashboard/runtime/multi-symbol/operator tests: 70 passed.
- Browser: DEMO, human-confirmed mode, healthy lifecycle, zero discrepancies/unresolved states, BTCUSDm M1/H1/H4 and complete freshness/capability visibly rendered.
- Full regression: 3,192 passed; 156 subtests passed; 3 unchanged dependency warnings.
- Candidate generation, LLM, confirmation, pre-submit, controlled-submit, `order_send`, management and broker mutation: 0.

#### Current state / next step

- Dashboard/backend state alignment is complete; software execution permissions remain disabled and kill switches engaged.
- Next: operator reviews the corrected Dashboard before separately authorizing any operational candidate-generation acceptance.

---

### Maintenance - Streamlit Mode Authorization Demo

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Bound candidate assembly and mode-specific controls to the authoritative persisted operating mode.
- Limited Confirm/Reject to `human_confirmed_live` and Standing Trading Mandate controls to `autonomous_live`; `advisory_only` exposes neither authority path.
- Fixed the existing mode form so an explicit initial selection can reach backend validation.

#### Verification

- Focused Dashboard/authority tests: 48 passed.
- Browser: all three modes persisted and rendered distinct controls; one human-mode generation attempt stopped at `METHOD_BAD_REGIME` with no candidate.
- Full regression: 3,194 passed; 156 subtests passed; 3 unchanged dependency warnings.
- Confirmation, mandate grant/revoke, export, pre-submit, controlled-submit, `order_send`, management mutation, and broker mutation: 0.

#### Current state / next step

- Streamlit mode authorization presentation is complete; execution permissions remain disabled and kill switches engaged.
- A human operator may later perform a separately authorized demo acceptance when a natural actionable candidate exists.

---

### Maintenance - Conversational Trading Authorization

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one typed, redacted and non-executable conversational trading request for advisory, human-confirmed and autonomous mode intent.
- Reused the existing protected mode/mandate service, candidate generation, Review Card and confirmation controls directly beside the conversation.
- Added caller-scoped Streamlit widget keys so Dashboard and chat controls coexist without duplicate actions.
- Kept configured symbol/profile resolution authoritative and added no dedicated intent-classification LLM call.

#### Verification

- Focused/neighboring tests: 83 passed with 2 dependency warnings.
- Full regression: 3,205 passed and 156 subtests passed in 172.16 seconds with 3 unchanged dependency warnings.
- Browser: one BTCUSD demo request rendered the human-confirmed MT5 Access Card; one refresh preserved the same request and no action repeated.
- Candidate generation, confirmation, mandate, export, pre-submit, controlled-submit, `order_send`, management and broker mutation: 0.

#### Current state / next step

- Conversational authorization is waiting at the genuine human `Grant MT5 Demo Access` boundary.
- The operator may grant that mode explicitly, then authorize at most one candidate-generation action. Submission remains separate and disabled.

---

### Maintenance - Conversational MT5 Access Grant Idempotency

Date: 2026-08-02
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Verified one real human Grant reached the existing controller and persisted `human_confirmed_live` for the matching DEMO account fingerprint.
- Reused the stable typed conversational request ID as the existing mode nonce/idempotency key.
- Made duplicate delivery return the original protected mode record and conflicting reuse fail closed.
- Rerun Streamlit after a successful write so the visible mode is reloaded from backend authority immediately.

#### Verification

- Focused authority/Dashboard/conversation tests: 39 passed with 2 unchanged dependency warnings.
- Full regression: 3,206 passed and 156 subtests passed with 3 unchanged dependency warnings.
- Fresh authority reload and Streamlit refresh both showed `human_confirmed_live`; the protected journal grew by exactly one record from the human click.
- LLM, candidate generation, controlled-submit, runtime `order_send`, and broker mutation counts: 0.

#### Current state / next step

- Execution permissions remain disabled and execution/management kill switches remain engaged.
- Next: complete full regression, then the operator may separately authorize one candidate-generation action.

---

### Reasoning Engine v2 - Configurable Strategy Evidence

Date: 2026-08-03
Verification: `FULL_REGRESSION_PASS` with browser-policy limitation
Commit: this commit

#### Implemented

- Extended the existing conversational request with a validated typed strategy specification and stable strategy identity.
- Reused the six supported indicator implementations through one bounded registry and rule engine.
- Added per-timeframe completed-bar planning plus deterministic feature, regime, score and granular reason evidence.
- Bound strategy identity through proposal provenance and the existing protected candidate lifecycle.
- Added compact LLM context, existing Streamlit Review Card rendering and deterministic V1/V2 replay evaluation.

#### Verification

- Focused reasoning, conversation, proposal, candidate, review, market, multi-symbol and scoring suites: 267 passed.
- Initial full regression: 3 failed and 3,221 passed; it identified a backward-compatibility defect in legacy feature-service calls.
- Final full regression after the shared fix: 3,224 passed, 156 subtests passed, 3 unchanged dependency warnings.
- Frozen replay: 12 scenarios, deterministic rate 100%, mean compact-context/raw-history ratio 4.04%, provider calls 0, broker mutations 0.
- Compileall and diff checks passed. Streamlit and bridge health returned HTTP 200.
- Browser-visible localhost acceptance was blocked by browser URL policy before interaction; candidate generation and provider calls remained 0.
- Controlled-submit, runtime `order_send`, broker mutation, confirmation and authority changes: 0.

#### Current state / next step

- Reasoning v2 is integrated and regression-verified; browser-visible acceptance remains limited by external browser URL policy.
- Execution and submission permissions remain disabled; no release tag moves are planned.

---

### Maintenance - Current Market Indicator Routing

Date: 2026-08-03
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Routed current indicator questions to authoritative market-state evidence before generic book preference.
- Resolved configured broker aliases to canonical symbols without suffix guessing or UI-local mappings.
- Reused the indicator registry and completed-bar evidence engine for deterministic values and freshness checks.
- Kept conceptual indicator questions book-first and preserved market evidence for mixed questions.

#### Verification

- Focused routing/evidence compatibility: 65 passed; affected post-regression matrix: 25 passed and 9 subtests passed.
- Browser: one BTCUSDm H1 request rendered deterministic EMA(20), RSI(14), completed-bar timestamp and current technical evidence.
- The single full run reported 3,237 passed, 156 subtests passed and one stale fixed-date test-fixture failure; the corrected fixture passed in the affected focused set.
- Candidate generation, confirmation, mandate changes, pre-submit, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- Current market indicator routing is live-verified; full-regression PASS was not claimed because the required single full run preceded the test-fixture correction.

---

### Maintenance - Conversational Intent and Strategy Routing

Date: 2026-08-03
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one typed, non-executable conversational context shared by parser, query/evidence planning and Streamlit persistence.
- Centralized intent-to-response formats for current market, concept, strategy, authorization, advisory, autonomous and mixed requests.
- Preserved configured symbol aliases and per-field conversation precedence without silent XAUUSD or timeframe fallback.
- Routed incomplete strategy requests to granular completion blockers before retrieval/provider/candidate paths.
- Preserved local timeframe bindings for multi-indicator numeric and crossover rules.

#### Verification

- Focused contract/routing/reasoning/evidence tests: 92 passed with 2 unchanged dependency warnings.
- Affected compatibility rerun after the full-suite finding: 29 passed.
- Final full regression: 3,256 passed and 156 subtests passed with 2 unchanged dependency warnings.
- Browser: the two-turn BTCUSDm H1 to inherited BTCUSD/M1 strategy scenario rendered the expected non-executable completion card; automated refresh was URL-policy blocked and persistence was verified by focused tests.
- Candidate generation, routing LLM, confirmation, mandate, pre-submit, controlled-submit, runtime `order_send`, and broker mutation: 0.

#### Current state / next step

- The conversational contract is complete and fail-closed for incomplete strategies.
- Integrate the isolated branch only after separately preserving the overlapping local changes in the main working tree.

---

### Maintenance - Field-Aware Editable Trade Drafts

Date: 2026-08-03
Verification: `FULL_REGRESSION_PASS` with safe browser-runtime limitation
Commit: this commit

#### Implemented

- Centralized bounded BUY/SELL/generic/exit/question/hypothetical/negation semantics across Vietnamese, English, and mixed input.
- Added one immutable protected draft with field status, provenance, exact blockers, deterministic risk calculations, integrity, and optimistic revisions.
- Preserved explicit and inherited values field by field; proposed only missing methods and never silently supplied a symbol.
- Added dependency-aware typed edits and one Streamlit `NON_EXECUTABLE` Trade Draft Card.

#### Verification

- Focused conversational, draft, authorization, persistence, and generation neighbors: 107 passed.
- Full regression: 3,285 passed and 156 subtests passed in 165.48 seconds with 2 unchanged dependency warnings.
- Browser matrix covered inherited context, partial completion, risk/RR edits, missing symbol, concept, and negation behavior.
- The exact-source Streamlit process later exited with native code 139 during unrelated RAG/evaluation work; no draft Python traceback or safety-boundary change was observed.
- Candidate, confirmation, mandate, pre-submit, controlled-submit, runtime `order_send`, management, broker, and real-account mutation counts: 0.

#### Current state / next step

- Editable trade proposals are validated and revision-safe but remain non-executable.
- Integrate the isolated commit only after the unrelated dirty main tree is preserved or resolved.

---

### Architecture - Structured Semantic Interpretation Boundary

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one strict, non-authoritative typed semantic result contract and one interpreter over the existing structured reasoning provider.
- Rejected malformed, extra, authority-bearing, or non-numeric structured output while retaining valid incomplete facts through `unresolved_fields`.
- Kept existing conversational context, QueryPlan, capability planners, retrieval rewrite, UI, lifecycle, bridge, and execution paths unchanged.
- Added compact fake-provider behavior-family coverage without live LLM calls.

#### Verification

- New structured semantic boundary tests: 21 passed.
- Neighboring semantic/query-plan/proposal/runtime tests: 111 passed and 17 subtests passed.
- Full regression: 3,314 passed and 156 subtests passed in 128.25 seconds; 3 unchanged dependency/UTC warnings.
- Docker Compose config passed. App restart and Streamlit health were not run because `dockerDesktopLinuxEngine` was unavailable locally.
- No LLM, MT5, market-data, candidate, confirmation, export, pre-submit, submission, `order_send`, or broker-mutation operation ran.

#### Current state / next step

- The boundary validates semantic facts only and cannot express execution authority.
- Deterministic context-resolution and QueryPlan-authority cutover remain the next sprint; execution behavior is unchanged.

---

### Architecture - Deterministic Semantic Resolution and QueryPlan Authority

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added deterministic resolution of configured symbols and explicit structured conversation references with field provenance and fail-closed unresolved state.
- Added a structured-semantics path to the existing `QueryPlanAssembler` that skips legacy raw semantic parsing when a validated artifact is supplied.
- Reused the existing indicator registry and context-requirement planner; incomplete indicators remain semantic ambiguity rather than receiving defaults.
- Preserved legacy QueryPlan assembly unchanged when structured semantics are absent.

#### Verification

- Semantic-resolution, QueryPlan, interpreter, conversational, context, execution-planner, and capability neighbors: 83 passed with 2 dependency warnings.
- Full regression: 3,325 passed and 156 subtests passed in 144.98 seconds with 3 unchanged dependency/UTC warnings.
- Compileall `src`/`scripts`, documentation integrity (11 passed), diff, Docker Compose configuration, and static safety checks passed. Docker app restart succeeded; the container became healthy and Streamlit health returned HTTP 200.
- No external LLM, MT5, market data, candidate, confirmation, export, pre-submit, submission, `order_send`, or broker-mutation operation ran.

#### Current state / next step

- Valid structured semantics now project deterministically into the existing QueryPlan without weaker raw-language reinterpretation; raw assembly remains the compatibility fallback.
- Universal orchestrator/capability routing, retrieval rewrite separation, trading-language, UI, lifecycle, and execution migration remain out of scope.

---

### Architecture - Universal Structured Semantic Routing

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Routed normal meaningful RAG requests through one valid structured semantic result and one authoritative QueryPlan before existing context planning/execution.
- Kept legacy routing only as the bounded invalid/unavailable-semantic fallback and preserved existing social/system/out-of-scope exits.
- Moved retrieval rewriting downstream so it runs only for knowledge capabilities and cannot overwrite QueryPlan semantics.
- Projected existing macro events and technical indicators into the existing capability requirements without a new capability or execution path.
- Prevented DecisionContextBuilder from raw reparsing an authoritative supplied QueryPlan.

#### Verification

- Focused semantic/query-plan/context/capability/runtime-neighbor tests: 104 passed with 2 unchanged dependency warnings.
- Full regression: 3,335 passed and 156 subtests passed in 154.39 seconds with 3 unchanged dependency/UTC warnings.
- Compileall, Docker Compose config, Docker restart, Streamlit health `200 ok`, diff, documentation integrity, and static safety checks passed.
- External LLM, MT5, market data, candidate, confirmation, pre-submit, submission, `order_send`, and broker mutation operations: 0.

#### Current state / next step

- Structured semantic routing and existing capability planning are universal for valid semantic artifacts; execution remains disabled and unchanged.
- Trading raw-language cutover is next; thin UI migration and Draft/Candidate lifecycle integration remain later.

---

### Sprint 4 - Trading Semantic Cutover

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Projected valid resolved `QueryPlan` facts into the existing typed trading and strategy contracts without raw re-parsing.
- Moved the chat ingress to orchestrator-first; the UI consumes the authoritative returned projection and retains resolved state for explicit next-turn inheritance.
- Preserved incomplete indicator siblings and marked only unresolved semantic fields; domain validation remains responsible for complete-strategy evidence admission.
- Added non-authoritative semantic account scope and projected existing close/manage lifecycle meaning without lifecycle mutation.
- Retained the legacy conversational parser only for invalid/unavailable semantic-plan compatibility fallback.

#### Verification

- Focused cutover plus semantic, QueryPlan, conversation, authorization, and reasoning-evidence suites: 114 passed, 2 unchanged dependency warnings.
- Full regression: 3,351 passed, 156 subtests passed in 134.20 seconds, 3 unchanged dependency/UTC warnings.
- Compileall, Docker Compose configuration, app restart, Streamlit health `200 ok`, and diff checks passed.

#### Current state

- Valid QueryPlan semantics are authoritative for migrated trading ingress; all projections remain `NON_EXECUTABLE`.
- Execution, confirmation, pre-submit, controlled submission, bridge behavior, and permissions are unchanged and blocked by default.

#### Not verified / not implemented

- Full thin-UI cleanup, authoritative Draft blocker presentation, Draft-to-Candidate lifecycle wiring, and legacy parser removal remain later work.

#### Next step

- Thin UI + Authoritative Draft/Lifecycle Presentation Integration.

---

### Sprint 5 - Thin UI and Authoritative Draft Presentation

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Made the valid orchestrator result the explicit UI selection boundary before legacy conversational fallback.
- Routed actionable request presentation directly to the latest persisted `EditableTradeDraft` revision.
- Kept semantic unresolved input fields distinct from current Draft blockers and warnings.
- Preserved existing Draft calculation, patch/revision, candidate review, confirmation, pre-submit, and execution contracts.

#### Verification

- Focused UI/Draft/semantic/query-plan/candidate-review neighbors: 105 passed with 2 unchanged dependency warnings.
- Full regression: 3,359 passed and 156 subtests passed in 140.17 seconds with 3 unchanged dependency/UTC warnings.
- Compileall, Docker Compose config, app restart, Streamlit health `200 ok`, documentation integrity, diff, Ponytail, and static safety checks passed.

#### Current state

- Valid QueryPlan results bypass UI raw trading parsing; legacy parsing remains only for absent/invalid-plan compatibility fallback.
- Latest Draft state owns current Draft presentation; all outputs remain non-executable.

#### Not verified / not implemented

- Draft-to-Candidate DEMO lifecycle wiring, candidate lifecycle changes, confirmation, pre-submit, execution, and legacy fallback cleanup remain separate work.

#### Next step

- Explicit Draft-to-Candidate DEMO Lifecycle Integration.

---

### Sprint 6A - Explicit Draft-to-Candidate DEMO Lifecycle Integration

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one explicit, revision-bound Draft-to-Candidate action using the existing Draft store, candidate assembler/orchestrator, candidate journal, and Review Card.
- Bound the candidate to an opaque protected-Draft provenance reference; Draft values are not re-parsed from chat text or exposed publicly.
- Reused candidate-journal idempotency for a repeated action and reject stale Draft revisions before assembly.
- Cleared only the current UI result after a Draft edit; the historic candidate remains in the existing journal and confirmation is still absent.

#### Verification

- Focused and neighboring Draft/candidate/review/approval/pre-submit/thin-UI tests: 162 passed with 2 dependency warnings.
- Full regression: 3,369 passed and 156 subtests passed in 139.86 seconds with 3 unchanged dependency/UTC warnings.
- Compileall, documentation integrity (11 passed), `git diff --check`, Docker Compose configuration, app restart/healthy state, and Streamlit health `200 ok` passed. Static safety checks and final Ponytail review passed.

#### Current state

- Candidate creation is explicit, DEMO-bound, duplicate-safe, and non-executable.
- Confirmation, approval, final validation, pre-submit, controlled submission, reconciliation mutation, and broker execution remain unchanged and blocked.

#### Not verified / not implemented

- Browser/runtime creation from a live Draft, human candidate confirmation, pre-submit authority, and broker submission were not run.

#### Next step

- Explicit Candidate Review + Confirmation Lifecycle Integration.

---

### Sprint 6B - Explicit Candidate Review + Confirmation Lifecycle Integration

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Connected the existing Candidate Review Card to the existing protected Confirm/Reject service only when the visible Candidate exactly matches the current Draft provenance.
- Reloaded persisted review status by exact candidate reference so a Streamlit session outcome cannot appear on another Candidate after a rerun or Draft edit.
- Reused the existing confirmation intent journal and its one-decision-per-candidate idempotency; conflicting terminal actions return the original immutable decision.
- Proved historical C(N) review remains bound to C(N)'s protected Draft-revision source after Draft N+1 is created.

#### Verification

- Focused/neighboring Draft, Candidate, confirmation, idempotency, Review Card, UI, and pre-submit-safety tests: 104 passed with 2 unchanged dependency warnings.
- Full regression: 3,373 passed and 156 subtests passed in 145.92 seconds with 3 unchanged dependency/UTC warnings.
- Compileall, Docker Compose configuration, app restart/healthy state, Streamlit health `200 ok`, and diff checks passed.

#### Current state

- Confirm and Reject are explicit, candidate-bound, duplicate-safe, auditable, non-executable review decisions.
- Rendering and Candidate creation do not create review authority; confirmation does not invoke pre-submit.

#### Not verified / not implemented

- Browser/runtime review action, pre-submit readiness, controlled submission, reconciliation mutation, and broker execution were not run.

#### Next step

- Confirmed Candidate -> Deterministic Pre-Submit Readiness Integration.

---

### Sprint 6C - Confirmed Candidate Pre-Submit Readiness Integration

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: 17d1065

#### Implemented

- Connected the exact persisted Candidate confirmation to the existing `ApprovalPreSubmitLifecycleService` through one explicit Review Card action.
- Reused strict Candidate-bound confirmation, approval integrity, final validation, current lifecycle capability evidence, and the existing idempotent pre-submit journal.
- Reloaded readiness by exact Candidate reference from the protected journal; a session-only result cannot appear on a different Candidate.
- Kept Confirm and Validate Pre-Submit separate actions. Ready remains `PRE_SUBMIT_READY_NON_EXECUTABLE` and does not call controlled submission.

#### Verification

- Focused pre-submit, confirmation, Draft/Candidate lifecycle, Review Card, Dashboard/runtime, disabled-adapter, and bridge-skeleton tests: 131 passed with 2 dependency warnings.
- Final full regression: 3,378 passed and 156 subtests passed in 138.09 seconds with 3 unchanged dependency/UTC warnings.
- Compileall, Docker Compose config, app restart, Streamlit health `200 ok`, `git diff --check`, and static safety scans passed.

#### Current state

- `Draft N -> Candidate C(N) -> Confirm -> explicit Validate Pre-Submit -> PRE_SUBMIT_READY_NON_EXECUTABLE or BLOCKED` is deterministic, exact-artifact-bound, idempotent, and non-executable.
- Execution, controlled submission, bridge behavior, reconciliation mutation, permissions, and kill switches remain unchanged.

#### Not verified / not implemented

- Browser/runtime confirmation and readiness action, controlled submission, broker execution, and reconciliation mutation were not run.

#### Next step

- Lifecycle Closure + Legacy Semantic Fallback Cleanup + Release Validation.

---

### Sprint 6D - Pydantic V2 Structured Semantic Boundary Alignment

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Replaced manual untrusted structured-semantic validation with strict Pydantic v2 DTOs and an explicit conversion into the existing frozen semantic dataclasses.
- Kept the one-call JSON-mode provider flow, existing semantic error contract, strict numeric behavior, partial unresolved facts, and downstream QueryPlan/context/trading contracts unchanged.
- Added an explicit v2-only Pydantic dependency and compact boundary coverage for invalid shape/enum/authority/numeric inputs plus integer, float, partial, round-trip, and confinement behavior.

#### Verification

- Focused semantic, QueryPlan, context, universal-routing, and trading-cutover suites: 91 passed, 17 subtests passed.
- Full regression: 3,392 passed and 156 subtests passed in 138.23 seconds with three unchanged dependency/UTC warnings.
- Compileall, Docker Compose configuration, `git diff --check`, and static safety scans passed.
- Docker app restart and Streamlit health: passed (`200 ok`). Clean dependency-image rebuild: NOT VERIFIED; two bounded rebuild attempts timed out without affecting the healthy existing app.

#### Current state

- Pydantic v2 is confined to the untrusted semantic boundary; frozen internal semantic, QueryPlan, context, trading, lifecycle, bridge, and execution contracts remain unchanged.
- No external LLM, provider retry, MT5 write, controlled submission, runtime `order_send`, or broker mutation ran.

#### Not verified / not implemented

- Clean-image dependency rebuild remains unverified after the local Docker build timeouts.
- Legacy semantic fallback cleanup and final closure remain separate work.

#### Next step

- Legacy Semantic Fallback Cleanup + Architecture Acceptance + Release Validation.

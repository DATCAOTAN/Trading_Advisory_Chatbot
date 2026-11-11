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

---

### Sprint 6E - Final Locked Semantic Architecture Closure

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Verified the one-call structured semantic path through Pydantic v2, frozen semantic facts, deterministic resolution, QueryPlan, context planning, and existing capabilities.
- Classified remaining raw semantic helpers as bounded unavailable/invalid-provider fallbacks or compatibility-only paths; no normal Streamlit path reparses a valid structured plan.
- Confirmed retrieval rewrite is retrieval-only, mode is a policy overlay, and the Draft/Candidate/Review/Pre-Submit lifecycle remains explicit and non-executable.

#### Verification

- Focused semantic, routing, context, Draft, Review, and Pre-Submit tests: 166 passed with 2 unchanged dependency warnings.
- Full regression: 3,392 passed and 156 subtests passed in 139.59 seconds with 3 unchanged dependency/UTC warnings.
- Docker Compose config, runtime Pydantic `2.13.4`, semantic import path, Streamlit health `200 ok`, compileall, documentation integrity, diff checks, and static safety scans passed. The container was recreated from the current named app image after Sprint 6D; provenance is verified without another rebuild.

#### Current state

- QueryPlan is the sole internal semantic/planning authority; valid structured semantics cannot be overwritten by raw fallback parsers.
- The app remains non-executing. Exactly one production `.order_send(` call-site remains in the host bridge and `src/` has zero MetaTrader5 imports.

#### Not verified / not implemented

- Controlled submission enablement, broker execution, real-account execution, MT5 write acceptance, and reconciliation mutation remain out of scope.

#### Known limitations

- Remaining raw parsers are deliberately bounded fallbacks for unavailable/invalid structured semantics or compatibility callers; they are not normal structured-path authority.

#### Next step

- Semantic architecture closure is release-candidate complete. Execution enablement remains a separate explicitly authorized scope.

---

### Sprint 6F - Structured Semantic Runtime Routing Repair

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: pending review

#### Implemented

- Removed the conventional indicator-period example from the structured semantic prompt; incomplete child fields remain explicitly unresolved.
- Routed structured `POSITION_MANAGEMENT` and `TRADE_LIFECYCLE` through the existing `trade_opportunity_analysis` QueryPlan and capability requirements.
- Routed the immediate valid structured-trading response through the existing context-acquisition executor, avoiding `legacy_heuristic` default indicator acquisition.
- Derived missing registry-required indicator fields into the typed strategy's unresolved set without fabricating a value; relation checks run only when their required operands exist.

#### Verification

- Focused semantic/interpreter/QueryPlan/trading-cutover tests: 70 passed.
- Full regression: 3,399 passed and 156 subtests passed in 155.36 seconds with 3 unchanged dependency/UTC warnings.
- Changed-path compileall, `git diff --check`, and static safety scans passed.
- Browser/runtime acceptance: one valid structured provider call produced a non-executable XAUUSD/XAUUSDm M1 Draft with the missing indicator period precisely unresolved; no RSI(14) default was created. The subsequent AnswerStream provider/model label was UI logging for a static bounded response, not a second provider request.

#### Current state

- Structured semantic facts retain explicit siblings and unresolved child fields; no semantic-path default period is assigned.
- Execution remains disabled and non-executable; no execution or broker behavior changed.

#### Not verified / not implemented

- Candidate, confirmation, pre-submit, submission, broker execution, and MT5 write acceptance remain out of scope.

#### Next step

- Review the documentation/code diff and create a focused local checkpoint if approved.

---

### Runtime Semantic Evidence-Staging Repair

Date: 2026-08-08
Verification: `FULL_REGRESSION_PASS`
Commit: pending review

#### Implemented

- Kept incomplete typed strategy facts valid and non-executable while skipping evidence work that requires their unresolved calculation parameters.
- Preserved precise semantic blockers and removed market/account/tick cascade blockers caused only by deliberate evidence non-attempt.
- Replaced the user-facing Python exception-class warning with explicit not-attempted or sanitized evidence-failure statuses.

#### Verification

- Focused semantic, Draft, and thin-UI tests: 65 passed.
- Full regression: 3,406 passed and 156 subtests passed in 137.89 seconds with 3 unchanged dependency/UTC warnings.
- Changed-path compileall, app restart, Streamlit health `200 ok`, static safety checks, and diff checks passed.
- Browser partial acceptance passed for BTCUSD/BTCUSDm RSI M1 with period unresolved: evidence was not attempted, cascade blockers were absent, and no Candidate was created.
- A single explicit-period browser request stopped before evidence at `INDICATOR_PARAMETER_INVALID` during strict public-request reload. Valid complete typed semantics enter evidence planning in focused coverage; the upstream runtime provider payload was not retried.

#### Current state

- Partial semantics remain visible, precise, and non-executable; strict calculation remains deferred until semantic prerequisites are complete.
- Candidate, confirmation, pre-submit, controlled submission, broker mutation, and MT5 writes remain untouched.

#### Next step

- Diagnose the upstream structured provider/domain strategy payload only if separately authorized; do not change evidence staging or retry the failed runtime input.

---

### Typed Public Request Round-Trip Guard

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: pending review

#### Implemented

- Preserved valid complete typed indicator strategies across strict public serialization and reload, including RSI and MACD parameter families.
- Prevented a strategy with deterministic validation errors from being published into a runtime artifact the strict reloader would reject; the request remains blocked and non-executable.
- Preserved incomplete semantics and the existing no-evidence staging behavior unchanged.

#### Verification

- Focused semantic/conversational/thin-UI tests: 94 passed.
- Full regression: 3,411 passed and 156 subtests passed in 134.56 seconds with 3 unchanged dependency/UTC warnings.
- Changed-path compileall, app restart, Streamlit health `200 ok`, static scans, and diff checks passed.
- Browser partial acceptance passed: RSI period remained unresolved and evidence status was `NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED` without a Candidate.
- Browser explicit-period acceptance no longer crashed on public reload, but its single provider payload was incomplete/invalid, so evidence was not reached; it was not retried.

#### Current state

- Complete typed round-trip validation is clean; incomplete typed semantics remain precise and non-executable.
- The remaining runtime blocker is upstream structured-provider conformance for the explicit complete request.

#### Not verified / not implemented

- Runtime evidence acquisition from a complete browser-produced RSI request remains blocked by that upstream payload.
- Candidate, confirmation, pre-submit, submission, broker execution, and MT5 writes remain out of scope.

#### Next step

- Diagnose the structured-provider/domain-strategy payload only under a separate approved scope; do not weaken strict reload or fabricate parameters.

---

### Complete Semantic-to-Evidence Runtime Acceptance

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: pending review

#### Implemented

- Closed the coherent runtime repair covering structured intent routing, typed/public round-trip validation, partial semantic staging, and bounded invalid-semantic diagnostics.
- Preserved incomplete semantic children without fabricating values and kept evidence acquisition behind complete typed prerequisites.

#### Verification

- Final production repair regression: 3,416 passed and 156 subtests passed with 3 existing warnings.
- Bounded diagnostic tests: 45 passed.
- One single-call runtime request passed semantic/domain validation and reached the complete Draft evidence boundary.
- Existing evidence policy returned the genuine blocker `SPREAD_TOO_WIDE`; spread-policy tuning was not part of this repair.

#### Current state

- Semantic/domain runtime path: PASS; evidence boundary: REACHED.
- Draft remains non-executable. Candidate, confirmation, pre-submit, controlled submission, broker mutation, and MT5 writes remain unchanged at zero.

#### Next step

- Treat any spread-policy adjustment as a separate explicitly approved policy task.

---

### Sprint 1 - Single Semantic Authority and Deterministic Mode Closure

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Made QueryPlan the authoritative owner of deterministic operating mode while retaining provider mode only as semantic evidence.
- Mapped analysis to advisory, direct OPEN/CLOSE/MANAGE to human-confirmed, and explicit autonomous evidence to autonomous mode.
- Stopped Streamlit raw-language reparsing whenever an orchestrator runtime result exists; raw fallback remains only for compatibility callers without runtime artifacts.

#### Verification

- Focused semantic/UI tests: 51 passed; neighboring semantic/orchestrator/authorization/UI/journal tests: 179 passed.
- Full regression: 3,426 passed and 156 subtests passed with 3 unchanged warnings.
- Compileall, app restart/health, Streamlit `200 ok`, `git diff --check`, and static safety scans passed.
- Browser: one invalid provider payload failed closed into one central fallback result with no competing UI Draft and no retry.

#### Current state

- QueryPlan is the sole downstream semantic authority; all Draft-stage execution authority remains false.
- One production `order_send` call-site remains isolated in the host bridge; `src/` has zero MetaTrader5 imports.

#### Known limitations / next step

- The single browser turn did not render the human-confirmed completion card because provider output failed strict validation.
- Next: Strategy Completion, field provenance, completion form, and semantic-versus-operational timeframe presentation.

---

### Sprint 2 - Strategy Completion Provenance and Editable Form

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one typed non-executable completion state and structured semantic patch transaction.
- Preserved known strategy siblings while keeping missing indicator parameters/timeframe unresolved.
- Added explicit provenance for user values, confirmed suggestions, LLM suggestions, inherited context, and calculated/policy sources.
- Routed incomplete strategies to a focused Streamlit completion form, not a normal Draft or Candidate control.
- Kept semantic timeframe distinct from the M1/H1/H4 operational acquisition profile.
- Accepted only declared missing provider children while retaining strict malformed/conflicting-value rejection.
- Added a domain-level Draft guard before journal/store access.

#### Verification

- Focused semantic/completion tests: 61 passed.
- Focused and neighboring transition tests: 214 passed.
- Full regression: 3,442 passed and 156 subtests passed with 3 unchanged warnings.
- Container restart/runtime import, Streamlit `200 ok`, compile, documentation, diff, and static safety checks completed.

#### Current state / limitations

- Completion, provenance, UI gating, and complete-strategy reprojection are verified; execution remains disabled and non-executable.
- Final browser acceptance used one provider call and zero retries. A valid partial BTCUSD/BTCUSDm RSI strategy rendered Strategy Completion with unresolved period, explicit M1, labeled suggestion, `human_confirmed_live`, and no Draft or Candidate before completion.
- Accepting period 14 through the structured form preserved all siblings and entered the existing evidence/Draft path. Genuine evidence blockers remained fail-closed; no Candidate or execution authority was created.
- Host/container source hashes matched, the container was healthy, and Streamlit returned `200 ok`. Sprints 3 and 4 are skip-or-closure-only; the next major implementation sprint is Sprint 5 Position Read Model, PnL History, and Provenance.

---

### Sprint 5 - Position Read Model, P&L History, and Provenance

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one canonical read-only model over the authenticated lifecycle snapshot and existing protected journals.
- Separated open positions, pending orders, and recent closed trades; used broker P/L fields without approximation.
- Added deterministic target resolution, freshness/account/reconciliation blockers, and safe provenance references.
- Routed the bounded existing-trade read family through the current semantic/QueryPlan/capability chain.
- Rendered the typed public projection in one non-executable Streamlit Trading State card.

#### Verification

- Position model: 17 passed; focused semantic/routing: 107 passed.
- Neighboring lifecycle/reconciliation/capability/UI groups: 142 passed and 151 passed.
- Full regression: 3,459 passed and 156 subtests passed with 3 unchanged warnings.
- Compileall, app and bridge restart, container health, Streamlit `200 ok`, browser acceptance, diff, and static safety checks passed.

#### Current state / next step

- Browser acceptance returned an authoritative empty open-position result; no trade was created for testing.
- Broker mutation, controlled-submit, management writes, and MT5 writes remained zero.
- Stored management/close reasons remain explicitly unavailable when no authoritative management reference exists.
- Next: S6 `HUMAN_CONFIRMED_POSITION_MANAGEMENT`.

---

### Sprint 6 - Human-Confirmed Position Management

Date: 2026-08-09
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Routed cancel pending order, modify protection, partial close, and full close through the existing semantic, PositionReadModel, and controlled-management boundaries.
- Added one non-executable typed proposal with explicit-value provenance, protected target/account/lifecycle binding, deterministic idempotency, and redacted public output.
- Added editable Streamlit review controls and exact human confirmation without creating another execution endpoint, adapter, journal, or state machine.
- Preserved unchanged SL/TP values and represented partial close as a deterministic resulting volume for existing broker validation.

#### Verification

- Focused and neighboring management/semantic/UI tests: 256 passed.
- Full regression: 3,491 passed and 156 subtests passed with 3 unchanged warnings.
- Compileall, app/container health, Streamlit `200 ok`, bridge health, diff, documentation, and static safety checks passed.
- Browser acceptance failed closed at `MANAGEMENT_TARGET_REFERENCE_UNRESOLVED` / `POSITION_NOT_FOUND`; no confirmation control or broker mutation was available.

#### Current state / next step

- All proposals remain `NON_EXECUTABLE`; exact confirmation and the existing final app/bridge validations remain mandatory.
- Controlled-submit, controlled-management write, runtime `order_send`, broker mutation, and MT5 writes remained zero.
- `RESULT_UNKNOWN` remains retry-prohibited and reconciliation-only.
- Next: S7 `AUTONOMOUS_POST_ENTRY_MANAGEMENT`.

---

### Sprint 7 - Autonomous Post-Entry Management

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added protected Standing Mandate authorization for bounded cancel, protection modification, partial close, and full close intents.
- Reused the PositionReadModel, Sprint 6 proposal/calculation path, controlled-management adapter, bridge validation, and existing journals.
- Added same-cycle target lookup and immediate pre-adapter revalidation of mandate, account, lifecycle, target, volume, limits, and provenance.
- Kept mode and LLM output non-authoritative; missing deterministic management evaluation, stale state, revocation, mismatch, and reconciliation requirements fail closed.
- Preserved no-retry `RESULT_UNKNOWN`, redacted public output, and one production `order_send` boundary.

#### Verification

- Focused and neighboring autonomous/management/lifecycle/UI tests: 243 passed.
- Full regression: 3,516 passed and 156 subtests passed with 3 unchanged warnings.
- Compileall, app health, Streamlit `200 ok`, browser acceptance, diff, documentation, and static safety checks passed.

#### Current state / next step

- Browser runtime had no current position or pending order, so no autonomous mutation was attempted; permissions remained disabled and kill switches engaged.
- Controlled-submit, controlled-management writes, runtime `order_send`, broker mutation, and MT5 writes remained zero.
- S8 is skip-or-closure-only; next major sprint is S9 `THIN_UI_AND_FULL_CONVERSATIONAL_INTEGRATION`.

---

### Sprint 9 - Thin UI and Full Conversational Integration

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one deterministic presentation dispatch over existing typed runtime artifacts.
- Prevented management turns from also rendering a competing position interpretation.
- Bound one fresh, unambiguous broker-selected position reference into canonical semantic context for typed cross-turn continuation.
- Kept raw UI parsing compatibility-only when no authoritative runtime artifacts exist.
- Preserved backend authority for mode, account, lifecycle, reconciliation, candidates, confirmation, and execution.

#### Verification

- New integration matrix: 34 passed; focused and neighboring suites: 308 passed.
- Full regression: 3,550 passed and 156 subtests passed with 3 unchanged warnings.
- Compileall, app restart without rebuild, host/container source hashes, container health, Streamlit `200 ok`, diff, documentation, browser, and static safety checks passed.
- Browser acceptance returned authoritative empty positions and a single typed management blocker; no confirmation or mutation control was exposed.
- Final Ponytail review narrowed selected-position binding so unrelated protected context references remain intact; rereview passed.

#### Current state / next step

- Sprint 8 lifecycle/recovery closure remains green.
- Controlled-submit, management writes, runtime `order_send`, broker mutation, and MT5 writes remained zero.
- Natural provider/RAG classification variations remain fail-closed and are coverage input for S10 `60_CASE_PRODUCT_ACCEPTANCE`.

---

### Sprint 10 - 60-Case Product Acceptance

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added one data-driven 60-case product acceptance suite and concise acceptance evidence report.
- Covered all twelve product families plus five semantic variants and one typed multi-turn sequence.
- Fixed three shared structured-provider prompt-contract gaps without regexes, schema relaxation, new fallback paths, or new authority.

#### Verification

- Canonical matrix: 60/60 contract-correct; final focused semantic/product group: 150 passed.
- Full regression: 3,621 passed and 156 subtests passed with 3 unchanged warnings.
- Provider/browser sample used 6 calls and zero retries; knowledge and mixed advisory/current results were contract-correct.
- Final closure used one additional Groq call with zero retries and classified the natural direct request as `VALID_PARTIAL`; Streamlit rendered the non-executable Strategy Completion workflow with period and semantic timeframe unresolved.
- Candidate, confirmation, pre-submit, controlled-submit, management write, runtime `order_send`, broker mutation, and MT5 write counts remained zero.

#### Current state / next step

- Host/container source hashes matched after restart without rebuild; Streamlit health was `200 ok` and no competing advisory, Draft, Candidate, confirmation, or submission artifact appeared.
- Verdict: `60_CASE_PRODUCT_ACCEPTANCE_COMPLETE`.
- Next: `READY_FOR_FINAL_RELEASE_CLOSURE`.

---

### Sprint 11 - Final Release Closure

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Closed the software release from the completed Sprint 1-10 implementation without changing production, tests, dependencies, configuration, or broker behavior.
- Recorded one authoritative release closure in the existing handoff and selected the new annotated tag `v2.0.0-software-complete` without moving earlier release tags.

#### Verification

- Retained Sprint 10 evidence: 60/60 canonical cases, 150 focused tests, 3,621 full-regression tests, and 156 subtests passed.
- Documentation integrity, compileall, diff, and release static-safety checks passed.
- Runtime host/container semantic hashes matched; Pydantic 2.13.4 loaded from the mounted `/app` semantic boundary; app, Streamlit, terminal bridge, and read-only Dashboard smoke were healthy.
- Static invariants remained one production `order_send` call-site and zero `MetaTrader5` imports under `src/`.

#### Current state / limitations

- Software implementation and the locked target architecture are complete; real-money approval remains excluded.
- Positive broker mutation acceptance was not performed and is not claimed. Demo-state-dependent positive lifecycle checks remain operational acceptance, not a software release blocker.
- Provider calls, controlled-submit, runtime `order_send`, broker mutations, reconciliation mutations, and MT5 writes remained zero during closure.

---

### Post-release fix - Autonomous and Strategy Completion Alignment

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Corrected generic structured autonomous-mode guidance without raw-text keyword routing or execution authority.
- Projected only concrete unresolved strategy leaves and preserved typed completion provenance without a second provider call.
- Kept human mode trade-centric and routed autonomous completion to the existing Standing Mandate controls.
- Added a generic completed-bar false-to-true re-arm gate using existing prior/current evidence; no new state store or execution boundary was added.

#### Verification

- Focused semantic/completion/autonomous/UI group: 175 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,632 passed and 156 subtests passed with 3 unchanged warnings.
- One browser/provider call, zero retries: `autonomous_live`, leaf-only completion, no completion error, and non-executable Standing Mandate setup rendered.
- Compileall, app restart without rebuild, container/Streamlit health, diff, and static safety checks passed.

#### Current state / limitations

- Authoritative demo-account binding remains required and fail-closed; the browser did not grant a mandate or create a Candidate.
- Candidate, confirmation, mandate activation, pre-submit, controlled-submit, management write, runtime `order_send`, broker mutation, and MT5 write counts remained zero.
- Historical `v2.0.0-software-complete` remains unchanged; a patch tag is recommended only after explicit release authorization.

---

### Post-release UX - Autonomous Mandate Prefill and Review

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reused the existing strategy, protected account, bridge metadata, mode authority, mandate store, validator, and grant command to build one non-authoritative setup projection.
- Replaced backend-centric symbol, version, and raw timestamp entry with read-only facts and bounded duration presets.
- Added editable broker-constrained volume and bounded management controls; monetary risk/loss remain unresolved when no configured policy exists.
- Preserved explicit operator grant, engaged kill switch, human per-trade confirmation, and all execution boundaries.

#### Verification

- Focused and neighboring mandate/strategy/UI group: 123 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,640 passed and 156 subtests passed with 3 unchanged warnings.
- App restart without rebuild, healthy container, Streamlit `200 ok`, and browser-visible prefill acceptance passed.

#### Current state / limitations

- Browser acceptance left confirmation unchecked and supervisor stopped; no mandate, Candidate, submission, or broker mutation was created.
- Maximum volume, positions, trades/day, monetary risk, and monetary daily loss require explicit operator values because no deterministic product policy defines those limits.

---

### Post-release UX - Bounded DEMO Mandate Policy and Control Plane

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Prefilled maximum volume from current broker metadata and the four remaining limits from explicit DEMO-only configuration.
- Kept all suggestions editable and non-authoritative until typed validation plus exact operator confirmation.
- Failed closed for missing/invalid DEMO policy and for REAL or UNKNOWN account environments.

#### Verification

- Focused policy/mandate/supervisor neighbors: 112 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,649 passed and 156 subtests passed with 3 unchanged warnings.
- Browser acceptance: one protected grant, strict reload/integrity/redaction pass, supervisor start/stop, one revoke, and revoked mandate blocked after reload.

#### Current state / limitations

- Execution and management kill switches remained engaged; controlled-submit, management writes, runtime `order_send`, broker mutation, and MT5 writes were zero.
- The acceptance did not force a live market signal or create a Candidate; deterministic signal/re-arm neighbors remained green.
- Verdict: `AUTONOMOUS_DEMO_POLICY_AND_CONTROL_PLANE_COMPLETE`.

---

### Post-release fix - Typed Autonomous Supervisor Binding

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Bound each new autonomous mandate to the exact protected typed strategy, identity/hash, direction, and opening action.
- Made supervisor startup and every observation cycle reload and validate that binding through the existing authority store.
- Passed the recovered strategy into the existing assembler/coordinator and kept legacy unbound mandates fail-closed.
- Reused the normal market-history count so the completed-bar quality gate can evaluate indicator-ready data.
- Extended the existing monitor journal and Dashboard with a redacted, strategy-filtered condition/re-arm projection.

#### Verification

- Final focused supervisor/monitor/UI/re-arm group: 75 passed.
- Neighboring autonomous/authority group: 337 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,670 passed and 156 subtests passed with 3 unchanged warnings.
- Live DEMO supervisor persisted three advancing XAUUSDm M1 completed bars; TRUE-to-TRUE RSI14 remained `WAITING_FOR_REARM` with no Candidate.
- A controlled process restart reloaded the same strategy/mandate, preserved deduplication, and processed the next bar.

#### Current state / limitations

- Supervisor remains read-only with execution and management kill switches engaged.
- Natural false-to-true Candidate creation was not observed during the bounded live window; deterministic re-arm and Candidate freshness contracts remain covered by tests.
- Controlled-submit, management writes, runtime `order_send`, broker mutation, and MT5 writes remained zero.
- Verdict: `REALTIME_AUTONOMOUS_TYPED_STRATEGY_OBSERVATION_COMPLETE`.

---

### Post-release fix - Level and Edge Trigger Semantics

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Made plain comparison rules current-bar `LEVEL` triggers and retained explicit crossing rules as re-arming `EDGE` triggers.
- Kept duplicate suppression in completed-bar identity, Candidate state, lifecycle, and idempotency instead of using false-to-true re-arm for level rules.
- Added trigger mode and opening eligibility to the existing monitor projection and read-only Dashboard status.

#### Verification

- Final focused trigger/evidence/supervisor/coordinator/UI group: 79 passed.
- Broader neighboring strategy/monitor/lifecycle/mandate/idempotency group: 204 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,684 passed and 156 subtests passed with 3 unchanged warnings.
- Live DEMO completed bars showed true-to-true RSI14 as `LEVEL`, `CONDITION_TRUE`, and `ENTRY_ELIGIBLE`; the first downstream blocker was `STRUCTURED_PROPOSAL_NOT_AVAILABLE`.

#### Current state / limitations

- No natural Candidate was created during the bounded observation; execution remained blocked by the kill switch.
- Controlled-submit, management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `LEVEL_AND_EDGE_TRIGGER_SEMANTICS_COMPLETE`.

---

### Post-release fix - Realtime Structured Proposal Observability

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Replaced the generic realtime proposal blocker with precise provider, transport, parse, schema, no-proposal, and valid-proposal outcomes.
- Added redacted provider telemetry to the existing reasoning evidence, monitor projection, and Dashboard status.
- Preserved valid `NO_PROPOSAL` as a legitimate no-Candidate result and kept every failure fail-closed with zero retries.

#### Verification

- Focused proposal/coordinator/monitor/UI group: 148 passed.
- Neighboring autonomous/strategy group: 182 passed.
- Canonical product acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,684 passed and 156 subtests passed with 3 unchanged warnings.

#### Current state / limitations

- App and Streamlit health passed after restart; structured-reasoning configuration was available without exposing credentials.
- Live provider observation was blocked because the persisted DEMO mandate had expired; no replacement authority was created automatically.
- Controlled-submit, management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `REALTIME_AUTONOMOUS_STRUCTURED_PROPOSAL_INCOMPLETE` pending an explicit fresh bounded DEMO mandate.

---

### Post-release fix - Deterministic Autonomous Strategy Authority

Date: 2026-08-10
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Bypassed provider proposal authority only for complete explicit deterministic autonomous strategies after deterministic entry eligibility.
- Reused the existing Draft calculator for Entry, SL, TP, risk, and volume, and preserved authoritative DEMO account evidence through the MT5 market account projection.
- Retained provider-owned `NO_PROPOSAL` for advisory/open-ended flows and all downstream safety boundaries.

#### Verification

- Focused calculator/account tests: 78 passed; autonomous/mandate/EDGE neighbors: 200 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,691 passed and 156 subtests passed with 3 unchanged warnings.
- One natural XAUUSDm M1 bar created one integrity-valid, non-executable deterministic Candidate with provider invocations 0.

#### Current state / limitations

- The post-Candidate policy boundary remained blocked by account-reference validation and the engaged execution kill switch; no execution authority was widened.
- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `DETERMINISTIC_AUTONOMOUS_STRATEGY_AUTHORITY_COMPLETE`.

---

### Post-release fix - Autonomous Account-Context Binding

Date: 2026-08-11
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Preserved the Candidate's existing protected `account_context_...` reference through strict journal reload.
- Compared that reference with one rebuilt from the current authoritative `account_id_hash`, then passed the separate current fingerprint hash to autonomous policy and Standing Mandate validation.
- Removed the coordinator's hardcoded account-match result without adding a store, reference type, adapter, or execution boundary.

#### Verification

- Focused account/Candidate/policy/mandate/approval/supervisor group: 171 passed; management and multi-symbol neighbors: 41 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,694 passed and 156 subtests passed with 3 unchanged warnings.
- Matching account binding reached the later engaged kill switch; changed and tampered account bindings remained fail-closed.

#### Current state / limitations

- App, Streamlit, and bridge health passed. Live Candidate observation was not repeated because the persisted DEMO mandate had expired; no replacement mandate was granted automatically.
- Controlled-submit, management writes, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `AUTONOMOUS_ACCOUNT_CONTEXT_BINDING_COMPLETE`.

---

### Post-release fix - Autonomous Execution Permission Contract

Date: 2026-08-11
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Replaced contradictory mandate pre-submit and adapter permission predicates with one shared authoritative permission snapshot contract.
- Preserved non-executable acceptance, bound the snapshot hash into the protected request, and required exact adapter-time snapshot compatibility.
- Kept bridge authorization and every broker-side safety boundary independent and unchanged.

#### Verification

- Focused permission/pre-submit/adapter/authority/coordinator group: 134 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,707 passed and 156 subtests passed with 3 unchanged warnings.
- Documentation integrity, compileall, diff, and static safety checks passed.

#### Current state / limitations

- No runtime permission or kill switch was changed; controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Logical app-side satisfiability is proven with a deterministic fake boundary; no broker-mutation acceptance was performed.
- Verdict: `AUTONOMOUS_EXECUTION_PERMISSION_CONTRACT_COMPLETE`.

---

### Post-release fix - Autonomous Monitor Execution Permission Contract

Date: 2026-08-11
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Replaced the monitor's acceptance-era enabled-flag prohibition with the shared permission projection.
- Allowed coherent observation-only and execution-ready states while blocking mixed permission states before market acquisition.
- Preserved downstream policy, mandate, account, pre-submit, adapter, bridge, idempotency, deduplication, and restart protections.

#### Verification

- Focused monitor/permission/coordinator group: 41 passed.
- Autonomous/authority/lifecycle/bridge neighbors: 182 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,713 passed and 156 subtests passed with 3 unchanged warnings.

#### Safety

- Provider calls, controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `AUTONOMOUS_MONITOR_EXECUTION_CONTRACT_COMPLETE`.

---

### Post-release fix - Deterministic Autonomous Candidate Eligibility

Date: 2026-08-11
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Preserved `OPEN_POSITION / ELIGIBLE_CANDIDATE` when an explicit deterministic strategy has already produced a valid `EDITABLE_TRADE_DRAFT`.
- Kept policy authority independent: advisory readiness may still block execution with `OPEN_POLICY_NOT_READY`, and hard risk failures remain `RISK_RESULT_BLOCKED`.
- Preserved false-condition, advisory no-proposal, active-entry, persistence, reload, and duplicate-bar behavior.

#### Verification

- Focused and neighboring autonomous/policy group: 137 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,717 passed and 156 subtests passed with 3 unchanged warnings.
- Documentation integrity, compileall, diff, and static safety checks passed.

#### Safety

- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `DETERMINISTIC_AUTONOMOUS_CANDIDATE_ELIGIBILITY_COMPLETE`.

---

### Post-release fix - Deterministic Draft Policy Alignment

Date: 2026-08-12
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Reused the existing deterministic Draft readiness contract at the autonomous policy boundary.
- Allowed valid `EDITABLE_TRADE_DRAFT` openings with non-blocking advisory readiness to reach controlled-boundary eligibility.
- Kept ordinary non-deterministic `WAIT`, hard risk blockers, mandate/account validation, permissions, idempotency, and bridge checks fail closed.

#### Verification

- Focused policy/strategy tests: 46 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,718 passed and 156 subtests passed with 3 unchanged warnings.

#### Runtime limitation and safety

- The bounded DEMO rerun received no new completed M1 bar, so no fresh Candidate or downstream submission artifact was created.
- Supervisor stopped, temporary mandate revoked, original fail-closed app/bridge configuration restored, and health checks passed.
- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Verdict: `DEMO_AUTONOMOUS_ORDER_SEND_END_TO_END_BLOCKED`; first remaining blocker: `NO_FRESH_COMPLETED_M1_BAR`.

---

### Post-release fix - Exact Lifecycle Evidence Binding

Date: 2026-08-12
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Removed the lifecycle fallback that assigned untagged broker rows to every execution with the same symbol and direction.
- Broker evidence now binds by the existing correlation tag or protected broker-result references.
- Unbound evidence remains fail-closed instead of contaminating another execution lifecycle.

#### Verification

- Focused lifecycle/reconciliation tests: 46 passed.
- Lifecycle/reconciliation/coordinator/monitor neighbors: 69 passed.
- Full regression: 3,719 passed and 156 subtests passed with 3 unchanged warnings.
- A read-only DEMO lifecycle cycle reported `HEALTHY`, account match true, zero discrepancies, one broker-rejected historical record, and one closed-position record.

#### Safety

- No execution permission was enabled and no controlled-submit, runtime `order_send`, MT5 write, or broker mutation occurred during the repair.

---

### Post-release fix - Autonomous Mandate-Aware Sizing

Date: 2026-08-12
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Added a minimal typed projection of the active Standing Mandate risk and volume caps to deterministic autonomous Draft sizing.
- Applied the lower policy/mandate risk budget and mandate/broker volume cap before Candidate persistence, with broker-step flooring and no upward broker-minimum clamp.
- Preserved separate policy, mandate, broker, proposed-volume, and actual-risk provenance; kept final `TradingAuthorityService` enforcement unchanged.
- Kept human-confirmed sizing behavior unchanged and failed closed for inactive, mismatched, expired, revoked, or below-minimum mandate constraints.

#### Verification

- Focused sizing tests: 68 passed.
- Autonomous/mandate/sizing neighbors: 196 passed.
- Canonical acceptance: 67 passed, including all 60 canonical cases.
- Full regression: 3,728 passed and 156 subtests passed with 3 unchanged warnings.

#### Safety

- No execution flag, controlled-submit path, bridge permission, `order_send`, MT5 write, or broker state was changed.

---

### Post-release fix - Continuous Autonomous Chat Runtime Continuity

Date: 2026-08-12
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Clarified the structured semantic contract so multilingual current trade/account-state reads use the existing authoritative position-read path rather than conceptual knowledge retrieval.
- Kept each persisted trading request bound only to its own semantic-state artifact and rendered the active runtime panel after unrelated chat responses in the same Streamlit run.
- Preserved persisted Standing Mandate form values without conflicting Streamlit widget defaults.

#### Verification and safety

- Focused position-read, conversational, thin-UI, dashboard, and mandate tests: 108 passed with two unchanged dependency warnings.
- Live DEMO P/L and SL/TP queries used `position_state_read`/`position_read`; an unrelated ATR question used the normal knowledge path.
- The mandate, controls, running Supervisor, healthy lifecycle, and zero reconciliation discrepancies/unresolved states survived the chat sequence and a natural reload.
- Read-only queries caused zero controlled-submit, runtime `order_send`, MT5 writes, or broker mutations.

---

### Post-release feature - Conversation-Scoped Trading Ownership

Date: 2026-08-12
Verification: `FOCUSED_PASS`
Commit: this commit

#### Implemented

- Added one stable protected conversation trading scope to the existing typed request, strategy, Candidate, mandate-binding, supervisor, and exact position/history provenance contracts.
- Scoped mandate and supervisor controls to the current strategy while preserving account-global lifecycle, reconciliation, broker state, permissions, and opening safety.
- Made position/history reads scope-local by default and retained explicit account-wide reads without exposing protected scope identifiers publicly.
- Kept same-symbol concurrent openings fail closed through the existing `ENTRY_ALREADY_ACTIVE` predicate.

#### Verification and safety

- Focused and neighboring ownership, request, Candidate, authority, supervisor, position-read, policy, and thin-UI tests: 279 passed with unchanged dependency warnings.
- Read-only DEMO verification produced two distinct scopes with no cross-attributed trades; explicit account-wide history returned five authoritative records with account match true.
- Changed-path compileall and diff checks passed; full regression was not run for this focused task.
- Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.

---

### Post-release UI - Professional Trading Workspace

Date: 2026-08-12
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Added one shared Streamlit workspace theme and replaced the oversized banner with a compact operational shell.
- Clarified Advisory, Operations, Evaluation, and Settings hierarchy while retaining every existing controller, widget key, and authoritative runtime projection.
- Collapsed legacy execution diagnostics into progressive disclosure and added responsive desktop/mobile styling without introducing a frontend dependency.

#### Verification and safety

- Focused UI and neighboring tests: 68 passed with two unchanged dependency warnings.
- Actual Streamlit checks covered all four tabs, desktop/mobile overflow, and rendered exception state.
- Candidate generation, confirmation, controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.

---

### Post-release fix - Noisy Trade-State Semantics

Date: 2026-08-13
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Clarified the existing structured semantic provider contract so spelling errors, accent/diacritic noise, Unicode normalization differences, abbreviations, and multilingual noise do not change an otherwise clear trade-state read into conceptual knowledge.
- Kept the single Pydantic v2 semantic boundary and existing `POSITION_MANAGEMENT -> position_state_read -> position_read` flow; no parser, keyword table, regex, history rewrite, or execution change was added.

#### Verification and safety

- Focused semantic/routing tests passed with `92 passed` and two unchanged dependency warnings; conceptual P/L, ATR, and unrelated financial questions remained `KNOWLEDGE`.
- One live typo query produced one provider call and a successful authoritative `PositionReadModel`; switching to the old conversation reloaded its unchanged persisted RAG response without another provider call.
- Candidate generation, confirmation, controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.

---

### Post-release fix - Editable Draft Dependency Recalculation

Date: 2026-08-14
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Validated derived target policy against the final Entry/SL/TP/RR values belonging to the same immutable Draft revision.
- Recomputed deterministic blockers per revision while preserving unresolved semantic prerequisites and explicit user-value conflicts.

#### Verification and safety

- Focused Draft tests: `32 passed`; neighboring Draft lifecycle, completion, UI, and semantic tests: `79 passed` with two unchanged dependency warnings.
- Live Streamlit revision 4 rendered `VALID_NON_EXECUTABLE` with coherent ATR-derived SL and RR-derived TP; prior revisions remained unchanged.
- Candidate creation, controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero. Full regression was not run for this bounded Draft-only correction.

---

### Post-release UX - Editable Draft Market Evidence Refresh

Date: 2026-08-14
Verification: `FOCUSED_AND_LIVE_PASS`
Commit: this commit

#### Implemented

- Added an explicit `Refresh Market Evidence` Draft action using the existing authoritative evidence loader and immutable Draft revision calculation path.
- Preserved user-owned parameters, recalculated policy-derived dependencies, and kept refresh separate from Candidate creation and all execution authority.

#### Verification and safety

- Focused Draft, thin-UI, and Candidate lifecycle tests passed with `61 passed` and two unchanged dependency warnings.
- Live DEMO UI refresh created revision 5 from stale revision 4, preserved user-edited volume, recomputed SL/TP coherently, and rendered `VALID_NON_EXECUTABLE` with fresh evidence.
- One subsequent explicit Candidate action no longer returned `MARKET_DATA_STALE`; it stopped at independent mode authority validation. Controlled-submit, runtime `order_send`, MT5 writes, and broker mutations remained zero.
- Full regression was not run for this bounded UI/workflow change.

---

### Post-release fix - Human-Confirmed DEMO Controlled Execution

Date: 2026-08-14
Verification: `FULL_REGRESSION_PASS`
Commit: this commit

#### Implemented

- Completed the existing protected human-confirmed path from Candidate confirmation and final validation to one separately authorized controlled DEMO submission.
- Reused strict persisted Candidate, confirmation, account-context, pre-submit, permission-snapshot, idempotency, adapter, bridge, and lifecycle contracts; no parallel authority or broker path was added.
- Preserved deterministic Draft recalculation and explicit-human authority when advisory methodology scoring is the only non-deterministic veto.
- Kept independent bridge MARKET-price resolution and exact lifecycle evidence binding at their existing trust boundaries.

#### Verification and safety

- Focused Draft, Candidate, policy, approval, controlled-execution, bridge, and lifecycle tests passed with `203 passed` and two unchanged dependency warnings.
- Final hermetic full regression passed with `3,769 passed`, `156 subtests passed`, and three unchanged warnings; compileall passed.
- Live DEMO acceptance reached the single production `order_send` boundary exactly once and returned protected `RESULT_CONFIRMED` / retcode `10009`; lifecycle reported `POSITION_OPEN` with a unique evidence match.
- Duplicate submissions and retries were zero. Protected broker/account identifiers remain excluded from public output and documentation.

---

### Maintenance - Repository Orientation and Housekeeping

Date: 2026-11-01
Verification: `FOCUSED_PASS`

#### Implemented

- Replaced the stale README and June AI context snapshot with the current product/mode overview, production owner map, retained evidence, and links to the existing runbooks.
- Removed unreferenced root patch/terminal/command-note artifacts and regenerable caches; preserved source contracts, tests, knowledge, runtime journals, credentials, backups, virtual environment, embedding cache, and `.agents/`.
- Excluded host secrets, agent settings, backup/diagnostic output, and protected runtime stores from future Docker build contexts; no image rebuild or runtime restart was performed.
- Kept historical sprint/architecture records and active compatibility modules instead of treating age or naming as proof of dead code.

#### Verification

- Documentation, local-link/source-path, and Docker exclusion checks: `13 passed`; Compose configuration validated.
- Production source/dependencies unchanged; no full regression, live provider, market query, candidate creation, or broker operation.
- The prior implementation checkpoint retains `3,769 passed` and `156 subtests passed`; those results were not rerun or reclassified as current runtime evidence.

---

### Maintenance - Commit-Informed Dead-Code Cleanup

Date: 2026-11-01
Verification: `FULL_REGRESSION_PASS`

#### Implemented

- Reviewed milestone commits and distinguished the July handoff snapshot from current implementation with a front-of-document reading guide.
- Removed 20 unreferenced exception-only modules, the unused execution receipt re-export, and two obsolete root manual experiments. Removed only their now-unnecessary pytest collection exclusions.
- Kept canonical receipt exports, all active error handling, hermetic provider guards, supported operational CLIs, and production safety/authority contracts.

#### Verification

- Focused affected-family/hermetic/documentation tests: `262 passed`.
- Full default pytest collection with process-local `.env.example` boolean defaults: `3,771 passed`, `156 subtests passed`, three unchanged warnings, `155.77s`.
- A legacy simulation test appended one rejected/non-executed receipt to the local simulation journal; all original bytes remain intact and the row was retained. Injected a temporary store into that test; simulator/documentation tests then passed `78 tests` without further journal changes. No production change followed the full regression.
- Compileall and Compose configuration passed. Production `order_send` call-sites: one; `MetaTrader5` imports under `src/`: zero.
- No runtime process, provider, market, candidate, submission, or broker operation; private local state and user changes preserved.

---

### Maintenance - Target-Aligned Unused Definition Cleanup

Date: 2026-11-01
Verification: `FULL_REGRESSION_PASS`

#### Implemented

- Re-read the locked target and checked graph callers plus tracked references before removing eight unused definitions across evidence, parser, embedding, coordinator, reasoning, and chatbot modules.
- Retained all active/exported contracts and supported diagnostic/preflight workflows. Added no replacement layer and changed no trading policy or permission behavior.

#### Verification

- Focused affected-family tests: `341 passed`, two unchanged warnings.
- Final default pytest collection with process-local offline boolean defaults: `3,771 passed`, `156 subtests passed`, three unchanged warnings, `135.73s`.
- Compileall and Compose configuration passed; one production `order_send` call-site and zero `MetaTrader5` imports under `src/` remain.
- Private/local preservation checks passed except for the already-recorded retained simulation-only append from the preceding cleanup; no new simulation-journal change. No runtime restart, rebuild, provider call, market query, candidate, or broker operation.

---

### Fix - Account-Aware Lifecycle Recovery

Date: 2026-11-03
Verification: `FULL_REGRESSION_PASS`

#### Implemented

- Fixed cross-account historical executions contaminating current-account lifecycle health at the existing supervisor, without loosening `_classify_record` or rewriting journals.
- Exclude only rejected foreign executions or confirmed foreign executions with original-account-bound closed proof; current correlation collisions and unresolved foreign executions still block.
- Retained invalid binding, unknown-result, journal-integrity, current exposure and reconciliation safety. Detect unmatched current orders as well as positions, reject missing/stale snapshot timestamps, and expose historical/recovery counts in the existing Dashboard.

#### Verified

- Focused neighbors: `136 passed`; final lifecycle/release-closure tests: `51 passed`.
- Final full regression: `3,787 passed`, `156 subtests passed`, three unchanged warnings, `168.05s`. Updated one obsolete release-closure assertion to count both account conflict and unmatched exposure after the initial regression identified it.
- Process-local offline defaults were required; `.env` was not edited. Compileall/diff/static checks passed; one production `order_send` call-site, zero `MetaTrader5` imports under `src/`.
- Real authenticated DEMO read-only observation: `HEALTHY`, account match true, discrepancies zero, seven terminal foreign history records, foreign unresolved zero, observations appended zero. Operator status agreed; PositionReadModel available with no positions/orders/blockers. App restart without rebuild, mounted-source verification and Streamlit `200 ok` passed.
- No new authority, Candidate, mandate, submission, management, MT5 write or broker mutation. Historical evidence and unrelated worktree changes preserved; no push.

---

### Acceptance - Fresh Human-Confirmed DEMO Draft and Candidate

Date: 2026-11-03
Verification: `FOCUSED_AND_LIVE_PASS`

- Used the existing completed BUY XAUUSD/XAUUSDm RSI14 M15 > 10 strategy and current DEMO account-bound human-confirmed mode; no new strategy or authority was created.
- Real authenticated preflight passed: lifecycle healthy, account/mode match, discrepancies/foreign unresolved zero, no open positions. Permissions and kill switches were unchanged.
- One UI market refresh created immutable Draft revision 2 with coherent Entry/ATR SL/RR TP and deterministic volume/risk. One Create Candidate action persisted one eligible opening and displayed one valid non-executable Review Card.
- Strict reload verified account, Draft revision, strategy, symbol/profile, snapshot and volume constraints. Candidate generated at 10:53:42 UTC with expiry 10:58:42 UTC; later confirmation still requires a fresh valid Candidate.
- Journal delta: one Draft revision and one Candidate only; historical bytes and confirmation/pre-submit/authority/execution stores preserved. No confirmation, submission, `order_send`, management, broker mutation or simulated fill.
- Focused existing Draft/Candidate/UI tests: `61 passed`, two unchanged warnings. No production/test change, full regression, rebuild, restart or push. Order execution remains a separate operator-authorized task.

---

### Acceptance - Current-Account Human-Confirmed DEMO Execution

Date: 2026-11-03
Verification: `FOCUSED_AND_LIVE_PASS`

- Operator personally confirmed a fresh Candidate and separately authorized controlled submission in Streamlit; no automated consent or repeated submission.
- Protected execution: current DEMO binding matches, result confirmed, retcode 10009; one submission-start and one confirmation for the idempotency key.
- Independent broker read: one BUY XAUUSDm position, volume 0.11, fill approximately 3904.282, SL 3896.414, TP 3923.135, no pending orders. Lifecycle uniquely matches the open position; current-account health healthy, discrepancies zero.
- PositionReadModel available/account-matched but position provenance lacks Candidate/execution references; protected lifecycle evidence provides correlation. No separate reconciliation record; recovery and closure not exercised.
- No production/test/config change or new full regression; prior focused coverage 61 passed retained. No management action, second trade, autonomous startup, rebuild, commit or push. Unrelated user state preserved.
- Verdict: `HUMAN_CONFIRMED_DEMO_EXECUTION_ACCEPTANCE_COMPLETE`.

---

### Sprint 6 - Live Position Read and Provenance Acceptance

Date: 2026-11-04
Verification: `FULL_REGRESSION_PASS`

- Reused PositionReadModel and protected execution/lifecycle stores to link missing-tag broker rows through unique exact protected references with account binding. Ambiguous/foreign matches and duplicate active-object ownership remain fail-closed; no heuristic ownership or new authority/store.
- Corrected closed-position direction using the position-linked opening deal; missing opening evidence remains UNKNOWN. Existing immutable conversations and trading history were not rewritten.
- Live DEMO open-position evidence and later closed history matched the read model: BUY XAUUSDm 0.11, entry approximately 3904.282, close 3923.135, realized net P/L 207.39 USD. No current positions/orders; lifecycle POSITION_CLOSED / LINKED_CLOSING_DEAL, HEALTHY, zero discrepancies/foreign unresolved.
- Streamlit visibly rendered corrected closed history and strategy/Draft/Candidate/execution/lifecycle provenance. Authorization reference is not joined by this execution projection, although separate reads verified historical confirmation and protected approval; management evidence is not linked. These remain explicitly unavailable, not evidence of absent consent. Closing reason code was unavailable; matching the old TP is not proof of TP causation.
- Final focused neighbors: 232 passed, including all 60 canonical cases. Final full regression (`.\venv\Scripts\python.exe -m pytest -q`): 3,798 passed, 156 subtests passed, three unchanged warnings, 156.70s. Process-local offline defaults only; initial local execution flags were correctly rejected by the offline harness. Earlier runs preceded the browser-proven direction correction and final duplicate-ownership guard; the result above covers final source.
- Host/container source hashes matched, app healthy, Streamlit 200; app-only source reload, no rebuild or bridge/terminal restart. Compileall/diff passed; one production order_send call-site, zero MetaTrader5 imports under src/.
- No Candidate, confirmation, mandate, submission, management action, broker mutation or MT5 write. Protected history and unrelated worktree/cache/.agents/ retained; no commit or push. Management and unknown-result recovery are not live-accepted here.
- Documentation integrity: 13 passed; final Ponytail review PASS after the duplicate active-owner negative control. Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_position_read_model.py scripts/test_mt5_position_lifecycle_supervisor.py scripts/test_human_confirmed_position_management.py scripts/test_autonomous_post_entry_management.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_60_case_product_acceptance.py -q`.
- Verdict: `LIVE_POSITION_READ_AND_PROVENANCE_ACCEPTANCE_COMPLETE`.

---

### Maintenance - Remaining Cleanup Review and Safe Checkpoint

Date: 2026-11-04
Verification: `FULL_REGRESSION_PASS`

- Reviewed remaining work against e377ce7; accepted 43 existing cleanup paths, excluded embedding cache, .agents/, .env and protected stores. Retained historical evidence and corrected current-baseline reading pointers.
- Confirmed 26 obsolete-file deletions and eight unused definitions have no active callers/imports/config references. Retained canonical exports, supported CLIs and all active execution/authority/strategy/lifecycle contracts.
- Accepted temporary unit-test journal isolation and Docker context secret/private-data exclusions; existing images were not rebuilt or declared sanitized.
- Initial isolated full run: 1 failed, 3,797 passed, 156 subtests. The observability expectation also failed on unmodified HEAD with blank structured reasoning config. Added two deterministic explicit/fallback metadata cases using StaticModel; no production behavior or external provider call changed.
- Actual focused groups: 27 passed (embedding/parser), 183 passed (UI/docs/hermetic/evidence/coordinator/trigger/reasoning/unit-simulation/completion), 90 passed (provider metadata/neighbors). Counts overlap. Initial combined focused collection exposed an unchanged Streamlit stub order dependency; separate processes passed, with no unrelated fix.
- Final isolated staged-source full regression: 3,799 passed, 156 subtests, three unchanged warnings, 135.49s. Command: `.\venv\Scripts\python.exe -m pytest -q`. No ignored local .env was present in the snapshot; no local runtime permissions were changed.
- Compileall, Compose configuration, staged diff and secret checks passed; 681 Python files matched staged source with Git CRLF normalization. One production order_send call-site; zero MetaTrader5 imports under src/. Final docs are checked separately after recording results.
- No runtime restart, new Candidate/mandate, autonomous launch, controlled-submit, management write, order_send, MT5 write or broker mutation. Unit fixtures are not operational trading evidence; current runtime health and autonomous E2E remain unverified here.
- Code checkpoint is suitable for the next read-only autonomous DEMO readiness preflight. No push; runtime cache and unrelated agent state remain outside Git staging.

---

### Sprint 9 Maintenance - Supervisor UI State and Risk Diagnosis

Date: 2026-11-04
Verification: `FOCUSED_PASS`

- Added rerun after successful existing Start/Stop process-owner calls; refreshed disabled states use the same trading scope. Process exceptions display redacted failure types and do not trigger a success rerun. No runtime owner or authorization path was changed.
- Six new fake-process UI cases verify one-click transitions, no repeat calls on rerun/refresh, start/stop disabled states, scope propagation and exceptions. Focused Dashboard/runtime/strategy-binding/mandate suite: 67 passed, two dependency warnings. Final child test environment used `.env.example` trading/MT5 boolean defaults; initial runs inherited incompatible local execution flags. No runtime or `.env` change.
- Command: `.\venv\Scripts\python.exe -m pytest scripts/test_dashboard_authoritative_runtime_state.py scripts/test_autonomous_runtime_completion.py scripts/test_autonomous_supervisor_strategy_binding.py scripts/test_autonomous_mandate_prefill_review.py -q`. No full regression.
- Actual read-only M1 evidence: ATR approximately 3.563143, SL distance 5.345, tick size/value 0.001/0.1. Risk per lot 534.5 USD; minimum 0.01 lot requires 5.345 USD nominal stop risk. A 1 USD mandate budget yields approximately 0.001870907 lot, rounded down to 0.00: `MANDATE_RISK_BUDGET_BELOW_BROKER_MINIMUM` is correct. No financial limit was changed or approved.
- DEMO mode/mandate account binding and integrity valid; mandate kill switch engaged, expiry 07:26:17Z. No real autonomous workers, positions/orders, current discrepancies or foreign unresolved executions. Historical BLOCKED monitor status is not a running-process status.
- App-only restart, matching mounted Dashboard hash, Streamlit HTTP 200, compile and diff checks passed. No broker mutation, order_send, controlled-submit, Candidate, mandate mutation or real process transition. Protected/unrelated work preserved; no commit/push.
- Remaining: operator-owned risk/mandate decision and separate Gate B startup/kill-switch authorization. A successful UI test and mathematical risk diagnosis do not establish autonomous broker execution.

---

### Sprint 9 Maintenance - Legacy Candidate Journal Compatibility

Date: 2026-11-04
Verification: `FULL_REGRESSION_PASS`

- Confirmed first blocker in four real M1 evaluations: an integrity-valid expired August Candidate lacked only trading_scope, but the deserializer accepted only the complete current set or the original all-optional-fields-absent legacy set.
- Added exactly the observed pre-scope shape. Missing scope stays empty; no arbitrary subset acceptance, scope inheritance, journal migration, re-signing or safety bypass.
- Unavailable Candidate state now projects BLOCKED/UNAVAILABLE with its exact blocker, not NO_ACTION/ENTRY_ALREADY_ACTIVE. Real active positions/orders/pending submissions and eligible unexpired Candidates still block duplicate entries; expired valid history no longer fails deserialization.
- Added 12 journal cases and 10 coordinator cases using isolated files and fake runtime dependencies. Covered current/original/pre-scope shapes, immutable reads, unknown scope, malformed fields, tampering, all three correlation conflicts, expiry, active-entry protection and stopping before generation/authorization/submission.
- Focused: 69 passed; neighboring monitor/strategy-binding/confirmation/pre-submit/read-model/mandate/Dashboard: 153 passed. Full regression: 3,827 passed, 156 subtests, three dependency warnings, 130.75s. No failing test run in this maintenance task.
- Commands: `.\venv\Scripts\python.exe -m pytest scripts/test_autonomous_decision_orchestrator.py scripts/test_autonomous_trading_coordinator.py -q`; full `.\venv\Scripts\python.exe -m pytest -q`. Test child environments alone received .env.example trading/MT5 boolean defaults. Current worktree includes the prior uncommitted UI fix.
- Read-only real journal reload: 67 protected Candidates loaded, one unchanged summary-only row returns None, no exceptions or decision-file byte change. Existing active-entry guard returns no blocker against current healthy closed-position evidence; no new Candidate was produced.
- App-only restart, no rebuild. DEMO account binding valid, lifecycle POSITION_CLOSED, no discrepancies/foreign unresolved, positions/orders/trades/loss today zero; no host/container autonomous workers. Mandate v3 is expired and not reused. Final 114-file preservation check found only a normal app-generated lifecycle append with the original bytes preserved as an exact prefix; decision/authority/execution files and private environment/cache/agent files are unchanged.
- Compileall/diff passed. One production order_send call-site; no MetaTrader5 imports under src/. No provider, trading, authority, kill-switch or protected-history mutation. Cache/.agents/.env and earlier work preserved. No commit/push.
- Verdict: `LEGACY_CANDIDATE_RELOAD_FIXED`. Remaining: separately authorized fresh mandate/preflight and autonomous broker E2E; this maintenance is not live execution acceptance.

---

### Sprint 10 - Trading Runtime Reliability and Observability

Date: 2026-11-05
Verification: `FULL_REGRESSION_PASS`

- Preserved the uncommitted Sprint 9 fixes. Retained later audit evidence establishes autonomous DEMO opening and DEAL_REASON_SL closure; no new trading was performed for Sprint 10.
- Read-only baseline: no autonomous workers, one DEMO protected position, no pending orders/discrepancies/unknown results. Latest mandate v5 allowed two trades/day and expired 2026-11-04T17:20:31.118764Z; v4 and v5 were not merged. Protected submissions were before expiry.
- Closed history projects broker SL/TP only through a unique position-linked opening deal and exact historical order reference. Missing protection stays unavailable; ambiguous/foreign-account/conflicting references fail closed. Direction, closing price, P/L and protected provenance remain intact.
- Existing scope-owned process owner retains bounded per-scope sanitized launch/exit/stop diagnostics, without capturing raw stdout/stderr. Unexpected exits never restart. An unowned historical RUNNING/STARTING record is UNKNOWN and blocks duplicate startup, not automatically adopted authority.
- Streamlit separates actual process state from current/historical monitor evidence. Stop remains available even if diagnostic persistence fails; launch fails closed when initial diagnostics cannot be saved.
- Mandate setup reports bounded account-context versus broker-market failure categories. Mocked transient network failures recover on a later read without retrying authority mutation. Original incident remains HISTORICAL_CAUSE_UNCONFIRMED; current dependencies are bridge account/tick reads, not an external market/LLM service.
- Fake-clock tests preserve expiry/revocation rejection at admission and authorization reload; later bars append no new authorization. Position/protection reads remain non-mutating after expiry. No automatic liquidation or permission change.
- Focused: 129 passed across read-model/runtime/mandate/authority/Dashboard tests. Neighbors: 253 passed across strategy/coordinator/approval/lifecycle/management/provider/canonical tests, including all 60 canonical cases.
- Full command `.\venv\Scripts\python.exe -m pytest -q`: 3,865 passed, 156 subtests, three unchanged warnings, 154.49s. Only test child environments received .env.example trading/MT5 boolean defaults. Initial focused failures were corrected test setup/expectations, not bypassed production checks.
- Documentation integrity: 13 passed. Affected compileall, diff check, one production order_send call-site, zero MetaTrader5 imports under src/ and final Ponytail review passed.
- App-only restart, no rebuild. All five changed production modules match container source; container healthy; Streamlit 200 / ok. Browser showed SUPERVISOR_STOPPED/HISTORICAL; exact closed DEMO read projected broker SL/TP and retained provenance.
- No real Supervisor launch, Candidate creation, mandate/mode/kill-switch/permission change, provider call, controlled-submit, management write or broker mutation. Protected history/private state and prior work preserved; no commit/push.
- Final preservation: 114 original files checked; only the app's normal lifecycle append changed, with all 3,683 original rows retained as an exact byte prefix. A standalone read-model import diagnostic hit an import-order cycle; production lifecycle-first initialization/read passed. No unrelated import refactor.
- Verdict: SPRINT_10_RELIABILITY_PASS. Not verified: long-term unattended runtime, a real process transition in this sprint, historical network cause, or management/recovery mutation. Historical chat responses remain unchanged.

---

### Sprint 11A - Genuine MT5 Historical Data Foundation

Date: 2026-11-05
Verification: `FOCUSED_AND_LIVE_PASS`

- Baseline b9e7d83. Operator narrowed the sprint to 11A only and declined a new simulator dependency. No simulation, strategy research results, optimization, UI or live execution change.
- Added src/services/trading/research/historical_dataset.py and host tools/mt5_bridge/export_research_history.py. Reused existing market models/OHLC checks/timeframes and host MT5Client/_call_mt5; retrospective BacktestEvaluationAgent contract unchanged.
- Explicit UTC, completed intervals, verified canonical/broker mapping, connected DEMO identity before/after, bounded native rates/tick reads. No symbol selection, authority or broker write operation.
- Deterministic JSONL/checksums/content IDs and safe manifests retain raw field precision, coverage, Git/exporter provenance, current-only contract metadata and quality. Exact inter-chunk overlap is reported/deduplicated; invalid or conflicting data rejected. Existing artifacts never silently overwritten.
- Git/Docker exclude data/research/ before acquisition. Quality/loader enforce schema, monotonicity, prices, OHLC, volume/spread, warmup and declared session coverage; primary reads reject non-VERIFIED datasets. No interpolation or fabricated prices/ticks.
- Real hour: 2026-11-04 15:00-16:00Z, 60/60 M1 bars VERIFIED, same ID on repeat. Real week: 6,829 bars PARTIAL, 430 absent declared weekday slots and Sunday/calendar mismatch. Actual closure/session cause remains unverified. Real one-minute ticks: 338 rows PARTIAL; completeness not certified.
- New focused command `.\venv\Scripts\python.exe -m pytest scripts/test_historical_research_dataset.py -q`: 42 passed. Market/bridge/retrospective-evaluator neighbors: 40 passed. Documentation integrity: 13 passed. Affected compileall, diff check and final Ponytail safety review passed.
- No full regression rerun: isolated new boundary; existing shared production/indicator/execution source unchanged. No application restart/rebuild needed, no dependency installed.
- Current read-only DEMO positions/orders, lifecycle discrepancies and RESULT_UNKNOWN zero; no autonomous workers. 114 private/protected files unchanged. Broker mutation, Candidate/authority writes and LLM calls zero. No commit/push.
- 11A data foundation verified; full delivery verdict SPRINT_11_VERIFICATION_INCOMPLETE reflects explicitly deferred simulator/research phases. No P/L, monthly-return, drawdown or profitability claim. Next: authoritative historical session/calendar evidence before broad primary datasets; simulator requires a separate approval.

---

### Sprint 11A.1 - Historical Session and Data Coverage Verification

Date: 2026-11-05
Verification: `FOCUSED_AND_LIVE_PASS`

- Preserved b9e7d83 and prior local 11A changes. Strictly reloaded all three original exports; raw data/manifests never changed. No simulator, dependency installation, bridge endpoint, shared live behavior change or trading operation.
- Added read-only mt5-session-coverage/v2 reassessment using explicit aware UTC evidence intervals/source/historical validity. Internal consistency is separate from coverage. Trading schedules never substitute for quoting evidence; missing slots stay unresolved unless independent historical evidence supports closure/no quotes. No inferred holidays/DST schedule or interpolation.
- Exporter v2 retains distinct same-millisecond ticks; identical within-chunk duplicates and conflicting ordered overlap groups fail closed. Manifest v1 reload remains byte/quality compatible. Existing bar corruption, Bid/Ask, timestamp, checksum and primary-loader gates remain intact.
- Official dated broker DST trading notice is compatible with daily/Friday/Sunday boundaries, but does not certify this server's historical quote sessions. All five original weekday gaps (4x62+182=430 slots) remain SESSION_HISTORY_UNAVAILABLE. Week has 59 genuine Sunday bars starting 23:01Z; current schedule is not historical proof. No native quote-session snapshot acquired or MQL5 script added.
- Real DEMO tick repeats returned 338/338 identical rows; overlapping 30 seconds matched 147. No exact/same-ms duplicates in original sample. Completeness remains PARTIAL. All three datasets internally VALID; hour retains verified slots, week/ticks remain PARTIAL. Local ignored JSON evidence includes original checksums, intervals, neighbors, sources and confidence.
- Focused+neighbor command: `.\venv\Scripts\python.exe -m pytest scripts/test_historical_research_dataset.py scripts/test_historical_session_coverage.py scripts/test_live_ohlcv_feature_engine.py scripts/test_market_data_provider_mt5_bridge_real_boundary.py scripts/test_backtest_evaluation.py -q`: 98 passed (58 research + 40 neighbors).
- Documentation `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q`: 13 passed. Affected compileall, git diff --check and final Ponytail safety review passed. Full regression not rerun; offline research-only boundary. App restart/rebuild not applicable.
- Existing storage/runbook now compares backtesting.py, Backtrader, vectorbt and repository reuse, costs, lot mapping, MTF, intrabar ambiguity, maintenance/dependencies and licenses. Recommend separately approved pinned backtesting.py for OHLC-only baseline, not full Bid/Ask tick fidelity; no engine installed or implemented.
- All original private/protected/research files preserved. Supervisor/provider/Candidate/authority/controlled-submit/order_send/broker mutation zero. No commit/push. Verdict SPRINT_11A_PARTIAL_EVIDENCE; historical quote completeness and research/performance remain unverified. Stop before Sprint 11B.

---

### Recovery 01 - Isolated historical foundation checkpoint

Date: 2026-11-11
Verification: `FOCUSED_PASS`

- Detached candidate based on b9e7d83 contains only 11A/11A.1 source/tests, ignore rules and scoped documentation; no shared live code changes or later milestone dependencies.
- Offline research/session and market/bridge/evaluator neighbors: 98 passed. Documentation integrity: 13 passed. These are new candidate checks, not a rerun of historical live acceptance.
- No broker/network acquisition, native Tester, Supervisor, authority change, Docker/WSL operation, commit or push. Main worktree and index remain untouched; historical session and tick completeness limitations remain.

---

### Sprint 11B - Native MT5 Tester Feasibility and Python/MQL Parity

Date: 2026-11-05
Verification: `FOCUSED_PASS`

- Retained b9e7d83 and prior uncommitted research work. Added research-only StrategyParity.mq5, tester_parity.py reference/audit helper and test_mt5_tester_parity.py. Live indicators, Draft, authority, execution, bridge and journals unchanged.
- Verified installed terminal/MetaEditor/MetaTester build 6230. A separate ignored portable research copy used installed vendor binaries/license only, no credentials or operational profiles; live trading/DLL/Experts disabled, local agents only. Connected DEMO terminal was not restarted. Isolated terminal/agents exited after both math sessions.
- Tester-only/non-optimization OnInit and call-boundary guards; SimulateOrders=false. No chart attachment, Supervisor, Candidate, Mandate, provider, virtual trade, controlled-submit or broker mutation.
- Final MetaEditor compile 0 errors/0 warnings, 512 ms. Two Model=3 Math-calculation runs produced independent MQL output and OnTester=1. Terminal summary 'some error after pass finished' remains unresolved; agent math execution is not historical trading success.
- Compared 12 synthetic fixtures + 46 real-bar windows. RSI/ATR/timestamp/LEVEL/EDGE/warmup/active-entry/volume checks match; full parity is 57/58. First failure: double price arithmetic rounds an exact half tick differently from Python Decimal(str(ATR)), changing one SL/TP/risk. No tolerance widening or live formula change.
- Native bundled RSI uses recursive smoothing and flat=50, unlike Python simple-window/flat=100. Bundled ATR uses SMA-equivalent recurrence. No silent iRSI/iATR replacement. A focused negative control retains the observed half-tick mismatch.
- Historical trading pilot zero. XAUUSDm tester history/real-tick quality, costs/margin/contracts, MTF trading, fills/SL-TP and profitability NOT VERIFIED. Existing broker DST notice/exports do not certify exact historical quoting sessions; prior PARTIAL classifications retained.
- Focused/neighbor command `.\venv\Scripts\python.exe -m pytest scripts/test_mt5_tester_parity.py scripts/test_historical_research_dataset.py scripts/test_historical_session_coverage.py scripts/test_level_edge_trigger_semantics.py scripts/test_field_aware_editable_trade_draft.py scripts/test_live_ohlcv_feature_engine.py -q`: 135 passed, two existing protobuf warnings. Initial isolated collection hit a pre-existing package import cycle; research uses decision-first bootstrap without production refactoring.
- Documentation integrity 13 passed; affected compileall/git diff --check passed. No full regression, dependency installation, Docker restart/rebuild, commit or push. Original protected/private/research data retained. Ponytail review blocks prototype promotion pending numeric parity and real tester evidence.
- Ignored feasibility_evidence.json retains source/binary/config/fixture/report hashes and exact mismatch. Recommend native MT5 as sole fill-engine direction with Python reference/audit, conditional on parity/data gates. Verdict SPRINT_11B_PARITY_INCOMPLETE. Next: research-only quantization parity, then genuine tester-data provisioning and one pilot; no second simulator/optimization started.

---

### M0 - Unified Adaptive Trading Architecture Compatibility Audit

Date: 2026-11-06
Verification: `STATIC_ONLY`

- At local `b9e7d83`, inspected source, test coverage, locked architecture and preserved Sprint 11A/11A.1/11B work. [M0 report](../architecture/M0_UNIFIED_ADAPTIVE_TRADING_AUDIT.md) records scoped verification statuses, gaps, owner/test/dependency mapping for M1-M11 and proposed minimal amendments. No changes to the locked text.
- Goal-Driven is research-first, not a new authorization mode. Existing exact strategy/mandate binding must not authorize a new revision. First proposed M1: canonical goal intake and read-only research brief/clarification, with no trade or authority writes.
- Quantitative ranking remains gated on historical data/cost evidence, unresolved half-tick parity and a real historical tester pilot. Retained prior test evidence is not a new test run. No runtime/tester startup, broker or authority change, new dependency, stage, commit or push. Stopped before M1.

---

### M1 - Goal-Only Semantic Routing and Safe Research Brief

Date: 2026-11-06
Verification: `FULL_REGRESSION_PASS`

- Root cause: a structured autonomous request with DEMO and symbol, but no projected strategy, could reach `STANDING_MANDATE_CARD / REVIEW_STANDING_MANDATE`. The canonical projector now blocks missing strategy. No change to Standing Mandate, Candidate or execution authority services.
- Optional typed `ResearchGoal` on the existing semantic contract; `STRATEGY_RESEARCH` preserves explicit objective, horizon, percentage limits, account preference and requested sources with provenance. Explicit reference-only follow-ups inherit eligible facts without reviving stale constraints or trading permission.
- QueryPlan brief reports `RESEARCH_REQUIRED / STRATEGY_NOT_ESTABLISHED`, requested workflow separately from effective `advisory_only`, and `execution_allowed=false`. Planned capabilities are listed, not run. Static response ends before data acquisition or trading projection; chat does not display a stale trade card or chart for a research brief.
- New tests cover Vietnamese/English/mixed wording with scripted semantic fixtures, rejected numeric/authority fields, unresolved information, explicit follow-up overrides and fail-closed projector/UI boundaries. Existing direct, partial and complete strategy, Advisory, position and authority families remain covered.
- Focused: `.\venv\Scripts\python.exe -m pytest scripts/test_goal_only_research_brief.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_strategy_completion_workflow.py scripts/test_60_case_product_acceptance.py scripts/test_standing_trading_mandate_authority.py -q`: 222 passed, two existing warnings.
- Full: `.\venv\Scripts\python.exe -m pytest -q`: 3,954 passed, 156 subtests, three existing warnings, 137.75 s. Both final commands received only `TRADING_*`/`MT5_*` boolean defaults from `.env.example` in their test process environments. Earlier focused failures exposed an inheritance key mismatch and operational flags in the test environment; corrected without editing `.env`.
- No broker mutations, live provider, live/DEMO app restart, new dependency, stage, commit or push. No real UI or provider acceptance claimed. No strategy discovery, experiment, ranking, or adaptive selector implemented. Next gated work is M2 research proposal and revision provenance.

---

### R1 - Research Proposal and Revision Contract

Date: 2026-11-06
Verification: `FOCUSED_PASS`

- R1 covers proposal/revision and research review in the M0 audit planning row M2; original roadmap M2 remains Autonomous Reliability.
- The canonical M1 brief feeds a strictly typed, non-executable proposal without another semantic call. Hypothesis and existing canonical strategy are optional; missing rules are not fabricated.
- Scoped immutable revisions retain parent, author, UTC timestamp and content fingerprint. Replay checks scope, lineage and fingerprints; idempotent repeats and stale-fork rejection preserve history. Acceptance is bound to one revision and never carries forward or grants trading authority.
- Evidence references capture stance, quality, optional UTC window and version. Validation requires a trusted owner and hypothesis binding; no private-document body or verified Tester result is admitted. Prior Tester parity is still 57/58.
- Focused and neighbors: `.\venv\Scripts\python.exe -m pytest scripts/test_research_proposal.py scripts/test_goal_only_research_brief.py scripts/test_historical_research_dataset.py scripts/test_historical_session_coverage.py scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_strategy_completion_workflow.py scripts/test_trading_semantic_cutover.py scripts/test_standing_trading_mandate_authority.py scripts/test_autonomous_supervisor_strategy_binding.py scripts/test_60_case_product_acceptance.py -q --tb=short`: 281 passed, two existing protobuf warnings. Test process used only TRADING/MT5 boolean defaults from .env.example. Documentation integrity: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q`: 13 passed.
- No new full regression because no shared production contract changed. No live provider, app restart, authority writes, broker mutation, stage, commit or push. No durable store or runtime workflow is wired. Next dependency is trusted evidence-owner integration; durable writes, when approved, need authenticated provenance and atomic head comparison.

### R2 - Trusted Research Evidence Verification

Date: 2026-11-06
Verification: `FULL_REGRESSION_PASS`

- Historical bar verification reuses the Sprint 11 loader (v1/v2) and requires a trusted, scoped approval and a retained manifest pin. Reports distinguish approved provenance, artifact integrity, actual declared-window coverage, claim support and strategy performance; the last two are not assessed.
- Exact proposal/revision/fingerprint and evidence reference are checked with conversation/account scope, symbol/timeframe, UTC window and timestamp. Missing, tampered, mismatched and partial inputs cannot be used as validated R1 evidence. Explicit status updates use the existing immutable revision flow; replay rechecks the source. No review decision or execution authority is generated.
- Read-only verification of retained local artifacts: one historical bar window verified and reloaded in R1 at READY_FOR_REVIEW; other bars and ticks limited. Current-market/RAG/Tester references stay pending in R2. No Tester parity change (57/58), historical fills, or profitability claim.
- Focused/neighbor: `.\venv\Scripts\python.exe -m pytest scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_goal_only_research_brief.py scripts/test_historical_research_dataset.py scripts/test_historical_session_coverage.py scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_strategy_completion_workflow.py scripts/test_trading_semantic_cutover.py scripts/test_standing_trading_mandate_authority.py scripts/test_autonomous_supervisor_strategy_binding.py scripts/test_60_case_product_acceptance.py scripts/test_context_acquisition_executor.py -q --tb=short`: 299 passed. The first full run exposed an R1 schema path caught by the global Pydantic guard; the guard now allows exactly that research record schema and still checks semantic ingress isolation. Targeted guard rerun passed.
- Final full: `.\venv\Scripts\python.exe -m pytest -q --tb=short`: 3,976 passed, 156 subtests, three existing warnings. Test processes used TRADING/MT5 boolean defaults from .env.example. Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q`: 13 passed.
- Compile and diff checks passed. No live LLM, runtime authority writes, broker operations, stage, commit or push. No UI, storage or source provisioning added. R2 does not rename or replace original M2 Autonomous Reliability.

### M2 - Autonomous Reliability and Recovery

Date: 2026-11-06
Verification: `FULL_REGRESSION_PASS`

| Reliability family | Baseline classification | Offline evidence |
| --- | --- | --- |
| Process ownership and status | GAP_CONFIRMED | Same-scope concurrent launch and stale owner status blocked, stop failure retained; existing exit, orphan and historical evidence tests retained. |
| Market and timebase | GAP_CONFIRMED | Unclosed/future bar rejected, older/equivalent bar denied after restart, and changed claimed bar denied before assembly. Existing missing, stale, unavailable and symbol-mismatch gates retained. |
| Mode, account and mandate | ALREADY_VERIFIED | Existing binding, expiry/revocation, final reread, kill-switch, risk/capability and limit tests. No authority change. |
| Submission and restart | GAP_CONFIRMED | Injected reserve and STARTED-write failures never reach broker. Lost response/persistence or management-reconciliation failure after broker call is unknown; repeated identity cannot submit again; watch stops. |
| Lifecycle and reconciliation | ALREADY_VERIFIED for journal/provenance and ambiguous-state gates; PARTIALLY_VERIFIED for real partial fills | Existing restart open/pending/terminal observations, no/multiple matches, foreign account, stale/history failures and read-model redaction. Reconciliation replay is not an order retry. |
| Real clocks, disconnect, closed session and unattended DEMO | BLOCKED_BY_EXTERNAL_ENVIRONMENT | NOT_RUN in offline M2; separate read-only then operator-approved soak gates in local runbook. |

- Focused/neighbor: `.\venv\Scripts\python.exe -m pytest scripts/test_autonomous_runtime_completion.py scripts/test_autonomous_candidate_monitor.py scripts/test_autonomous_trading_coordinator.py scripts/test_autonomous_post_entry_management.py scripts/test_autonomous_supervisor_strategy_binding.py scripts/test_live_ohlcv_feature_engine.py scripts/test_mt5_controlled_execution_integration.py scripts/test_mt5_controlled_position_management.py scripts/test_mt5_reconciliation_failure_recovery.py scripts/test_mt5_position_lifecycle_supervisor.py scripts/test_position_read_model.py scripts/test_dashboard_authoritative_runtime_state.py scripts/test_standing_trading_mandate_authority.py scripts/test_60_case_product_acceptance.py scripts/test_goal_only_research_brief.py scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_operator_triggered_autonomous_candidate_generation.py scripts/test_autonomous_mandate_controlled_execution.py scripts/test_autonomous_execution_policy_gate.py scripts/test_mt5_execution_mvp_end_to_end.py scripts/test_level_edge_trigger_semantics.py -q --tb=short`: 545 passed, 2 subtests. Targeted watch test: `.\venv\Scripts\python.exe -m pytest scripts/test_autonomous_runtime_completion.py::test_watch_stops_after_unknown_without_polling_or_rearming -q --tb=short`: 1 passed.
- Full: `.\venv\Scripts\python.exe -m pytest -q --tb=short`: 3,986 passed, 158 subtests, three existing warnings. Tests used process-local TRADING/MT5 boolean defaults from .env.example. Documentation integrity 13 passed; compile and diff checks passed.
- Existing single production order_send call site, no MetaTrader5 import under src, and no execution/management permission change. No live worker, runtime restart, MT5 write, provider call, stage, commit or push. Offline result is not a 24/7 readiness claim.

### G0 - Semantic-to-Execution Correctness Foundation

Date: 2026-11-07
Verification: `FULL_REGRESSION_PASS` (offline)

- Human-Confirmed now blocks conditional Candidate creation on false, unknown, stale or unbound completed-bar evidence; direct BUY/SELL and non-executable Draft preview remain available. Autonomous LEVEL, EDGE, re-arm and deduplication remain in the existing strategy/monitor path.
- Typed SL/TP, risk and volume keep value, unit and provenance through Draft revisions and Candidate binding. Zero, invalid and unresolved inputs do not become defaults; only compatible, explicitly referenced canonical parameters inherit. Explicit risk is checked against the Candidate quote before persistence.
- Requested technical snapshots no longer substitute default indicators, reuse the wrong timeframe or label an open candle as fresh. Generic summaries are explicitly labeled.
- Focused: `.\venv\Scripts\python.exe -m pytest scripts/test_g0_semantic_execution_fidelity.py scripts/test_structured_semantic_interpreter.py scripts/test_trading_semantic_cutover.py scripts/test_structured_semantic_query_plan.py scripts/test_strategy_completion_workflow.py scripts/test_editable_trade_draft_candidate_lifecycle.py scripts/test_field_aware_editable_trade_draft.py scripts/test_reasoning_evidence_v2.py scripts/test_context_acquisition_executor.py scripts/test_current_market_indicator_routing.py scripts/test_operator_triggered_autonomous_candidate_generation.py scripts/test_level_edge_trigger_semantics.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_deterministic_autonomous_strategy_authority.py scripts/test_60_case_product_acceptance.py -q -p no:cacheprovider --tb=short`: 392 passed.
- Full: `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short`: 4,009 passed, 158 subtests passed, three existing deprecation warnings. Tests used process-local TRADING/MT5 boolean defaults from .env.example and the hermetic pytest bootstrap.
- Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- Syntax and diff checks passed. Single production order_send call site; no MetaTrader5 import under src. No app restart, live provider, MT5 calls, broker writes, permissions changes, stage, commit or push. No G1 work, generated signals or Tester runs.

### G1 - Open-Ended Computational Specification

Date: 2026-11-07
Verification: `FULL_REGRESSION_PASS` (offline)

- Added a versioned optional semantic specification, not a DSL or execution model. It preserves novel algorithm descriptions, ordered and stateful requirements, typed parameters/units/ranges, data windows, output validity and strategy logic. Legacy payloads serialize unchanged when the extension is absent.
- Existing resolved-state persistence retains the spec and provenance. Explicit reference-only inheritance and trusted typed completion preserve facts without silently accepting model suggestions. Parameter and data rows retain valid siblings when a child is missing.
- All 18 origin/mode/adaptation combinations tested as independent semantics. Requested modes map to current labels; the effective path remains read-only. No strategy hash, mandate binding, permission or execution changes.
- Data requirements and evidence assessments are distinct. G1 performs no acquisition; status is NOT_CHECKED. Projection stops before legacy strategy, Candidate and capability acquisition even with a supported rule in the same payload.
- Focused: `.\venv\Scripts\python.exe -m pytest scripts/test_computational_specification.py scripts/test_goal_only_research_brief.py scripts/test_structured_semantic_interpreter.py scripts/test_trading_semantic_cutover.py scripts/test_structured_semantic_query_plan.py scripts/test_strategy_completion_workflow.py scripts/test_editable_trade_draft_candidate_lifecycle.py scripts/test_field_aware_editable_trade_draft.py scripts/test_reasoning_evidence_v2.py scripts/test_context_acquisition_executor.py scripts/test_current_market_indicator_routing.py scripts/test_operator_triggered_autonomous_candidate_generation.py scripts/test_level_edge_trigger_semantics.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_deterministic_autonomous_strategy_authority.py scripts/test_60_case_product_acceptance.py scripts/test_g0_semantic_execution_fidelity.py -q -p no:cacheprovider --tb=short`: 437 passed.
- Full: `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short`: 4,039 passed, 158 subtests, three existing deprecation warnings. Tests used process-local TRADING/MT5 defaults and the hermetic pytest bootstrap.
- Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- Scripted G1 path makes one semantic call and no rewrite call; completion cap remains 1,200 by default. For the same probe, prompt length grew from 7,969 to 9,293 characters (not a measured provider token count).
- Syntax and diff checks passed; one production order_send call site and no MetaTrader5 import under src. No runtime restart, provider use, Tester, generated execution, broker writes, stage, commit or push.
- Next: separate G2 approval for isolation, provenance and independent correctness checks; separate G3 Windows Tester approval. Existing pending decisions were not changed.

### G2 - Trusted-Host Pilot, Isolation Approval Required

Date: 2026-11-07
Verification: `FOCUSED_PASS` for the trusted-host contract only

- Added an offline research boundary for `VOLUME_WEIGHTED_CLOSE_LOCATION_V1`; no registry, Trading Core, semantic or runtime integration changes. The trusted oracle checks warm-up/nulls, exact timestamps, numeric tolerance, repeatability and prefix stability on synthetic fixtures.
- R2 rechecked the independently retained Sprint 11A.1 pin for the 60-bar XAUUSD M1 historical window (2026-11-04 15:00-16:00 UTC). Input extraction uses only required fields and binds exact bytes; no gap filling, source substitution or historical performance claim.
- Codegen contract: one spec-only prompt (1,141 characters on the prepared job), 1,600-token planned cap, bounded source reply, no tool call or repair path wired. A captured fixture reply is `g2-generated-source/v1 / GENERATED_UNVERIFIED`; no real generation, source execution, persisted artifact, toolchain identity or promotion. Actual token/cost data are unknown.
- Isolation observation: WSL2 and Docker Linux are running; the app container has writable secret/code/data mounts, a network and no configured CPU/RAM limits. Hyper-V inventory denied access. No approved worker or trusted isolation probe result.
- Proposed next gate, not implemented: dedicated offline VM with no network interface or shared host folders/clipboard, pinned image/interpreter/dependencies, unprivileged identity, verified input mounted read-only and size-limited output. Verify process limits, CPU/RAM, wall-clock timeout and forced teardown with benign probes, then obtain separate explicit permission to run generated code.
- Focused: `.\venv\Scripts\python.exe -m pytest scripts/test_computation_pilot.py scripts/test_research_evidence_verification.py scripts/test_historical_research_dataset.py scripts/test_historical_session_coverage.py scripts/test_research_proposal.py scripts/test_computational_specification.py scripts/test_g0_semantic_execution_fidelity.py -q -p no:cacheprovider --tb=short`: 148 passed, two existing warnings. Full regression not repeated for a new isolated module without a production caller.
- Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- `G2_PARTIAL / G2_ISOLATION_APPROVAL_REQUIRED`; `G2_READY_FOR_G3: NO`. No live provider/MT5 call, worker startup, runtime change, broker operation, stage, commit or push.

### G2.1 - Benign Isolation Acceptance Harness

Date: 2026-11-09
Verification: `FOCUSED_PASS` for the harness on Windows, not guest isolation.

- Original A-H recovered from the G2.1 provision/verify brief; each probe retains its original acceptance boundary.
- Reused operator-owned Hyper-V Verify unchanged. Reported `VERIFIED_OFF`/`Off` is host configuration evidence.
- Reported loopback-only/no default route, inactive SSH, absent common shares, Python 3.13.5 and cgroup v2 are guest observations.
- Scope creation and `timeout` exit 124 are not evidence of resource enforcement.
- Added an operator-only guest harness with a synthetic read-only fixture and dedicated, capability-free worker service.
- Harness requires observed access denials, CPU throttling, cgroup OOM kill, process admission rejection and systemd wall-time termination; unknown evidence is not PASS.
- No actual guest probes ran in this checkpoint. B requires operator inventory; F/G/H require host-side evidence. Media transfer and destructive-test approvals remain separate.
- Focused: `.\venv\Scripts\python.exe -m pytest scripts/test_g2_1_guest_probes.py scripts/test_computation_pilot.py -q -p no:cacheprovider --tb=short`: 35 passed, two dependency deprecation warnings.
- Documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed. Tracked and new-file diff whitespace checks passed.
- Windows direct invocation refused execution with `INCONCLUSIVE`, exit 2. No Docker restart or full regression: no application source changed.
- No VM startup, settings change, provider call, generated code, MT5/broker operation, stage, commit or push.
- `G2_1_PARTIAL`; `READY_FOR_G2_2: NO`. Operator next: approve/verify offline transfer and collect the bounded guest evidence following the handoff.

### G2.1 - Offline Probe Media and Operator Runbook

Date: 2026-11-09
Verification: `FOCUSED_PASS` for Windows preparation only.

- Added a host-only ISO builder using installed IMAPI2 and Windows tar; no installation or Hyper-V permissions.
- The allowlist is the independently hash-pinned harness and `SHA256SUMS`. Host read-back verifies both payloads before publishing the ISO.
- Two real Windows PowerShell 5.1 builds produced matching payload hashes and no boot descriptor. ISO-level metadata varied; pin each issued image individually.
- Incorrect source pin and existing output path both failed closed. No probe media attached or mounted to the VM.
- Runbook keeps the VM receipt, DVD count/slot, firmware and original signed ISO unchanged after restoration. The temporary data ISO cannot satisfy the existing Verify contract.
- Host Hyper-V read access is still denied to this session. `g2worker` is unverified; operator checks in Basic Session and stops if absent or ambiguous.
- Guest transport, A-E/H observations, and actual limit enforcement were not run. F/G remain separately gated on operator approval and disposable safeguards.
- Focused and documentation: `.\venv\Scripts\python.exe -m pytest scripts/test_g2_1_guest_probes.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 48 passed, two dependency deprecation warnings. Diff checks passed.
- No trading, generated code, Docker restart, full regression, dependency installation, commit or push.
- `G2_1_PARTIAL`; `READY_FOR_G2_2: NO`. Next: operator-only VM preflight, temporary media transfer and evidence collection.

### G2.1 - Evidence-Driven Sandbox Acceptance Checkpoint

Date: 2026-11-09
Verification: `FOCUSED_PASS` for documentation and current host Stage3 Verify only.

- Preserved operator-supplied A/C/D/E/F runtime PASS; no passed probe, forced-off, RestoreG or provisioning repeated.
- Reviewed existing clone provision/F/reboot/RestoreG receipts and the incident-pinned Stage3 procedure; PowerShell parser: 0 errors.
- Current Stage3 Verify passed: original and clone Off, restored clone disk attached, isolation and source incident gate intact.
- Sealed and restored images match the original sealed pin; original disk matches its separate investigated post-boot pin. No repinning or disk replacement.
- Original owner receipt and historical image-inventory JSON match the clone provision receipt's hashes; media/harness pins also match.
- B remains INCONCLUSIVE: host inventory PASS does not supply independent Basic Session/no-other-sharing/guest-inventory attestation.
- H remains INCONCLUSIVE: signed media/current-image byte pins do not prove installed-image lineage.
- Approved UAC read-only audit captured Stage3 Verify PASS; its supplemental final two-VM display failed on array input to Get-VM -Id. No VM action occurred in that audit.
- Launched the existing BootAfterG procedure in an approved administrator window; it rechecks safety gates and waits for BOOT_RESTORED_CLONE. No boot receipt or guest evidence yet.
- Elevated VMConnect cannot expose guest console text to the automation helper. Requested one read-only guest block; require actual Debian/absent-marker/zero-failed-unit/root-rw output.
- G remains INCONCLUSIVE pending guest output, separately approved normal shutdown and existing Stage3 Closeout; no full acceptance claim.
- `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- Added the acceptance report; updated only affected G2.1 handoff state. Existing unrelated work preserved; no production source edits, networking, trading, commit or push.
- No full regression, browser acceptance or Docker restart: only evidence/documentation and the gated Hyper-V workflow are in scope.
- `G2_1_PARTIAL`; `READY_FOR_G2_2: NO`. Next: return actual G console output, approve healthy shutdown/Closeout, then independently resolve B/H before any separate G2.2 authorization.

### G2.1 - BootAfterG Completed, Guest Closeout Boundary

Date: 2026-11-09
Verification: `FOCUSED_PASS` for host BootAfterG and documentation, not full G acceptance.

- The prior disconnected administrator process exited without a BootAfterG receipt. No success was inferred and no completed stage was replayed.
- An approved read-only resume audit at 15:38:16Z confirmed both VMs Off, expected attachments/isolation and successful existing Stage3 Verify/incident pins.
- A harmless Read-Host stdin self-check passed. Reused retained explicit BootAfterG approval through the unchanged exact-phrase gate via connected stdin; no function override or new procedure script.
- Incident-pinned Stage3 BootAfterG completed once at 15:41:15.7316323Z, exit code 0; wrote the exact-clone `stage3_boot_after_g.json` receipt.
- Post-boot audit at 15:41:16Z: original Off; clone Running on `runtime\worker.restored.vhdx`. Sealed/original/old-runtime disks preserved.
- Evidence: `g21_boot_after_g_resume_audit_20261109.txt`, `g21_boot_after_g_approved_20261109.txt`, and the protected clone evidence directory. Earlier logs retained.
- No interactive BootAfterG approval prompt remains; no F, RestoreG, provisioning or passed A-E probe repeated.
- G remains INCONCLUSIVE until actual Debian/absent-marker/zero-failed-unit/root-rw guest output, normal shutdown and Closeout. Requested only the necessary isolated-console operation.
- Retained stage approval permits automating host Off checks and the existing Closeout gate after actual guest evidence; no marker attestation was fabricated.
- A/C/D/E/F remain prior runtime PASS; B/H remain INCONCLUSIVE for independent attestation and installed-image lineage.
- `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed; tracked documentation whitespace check passed.
- Updated acceptance report and affected G2.1 handoff only; no production code, networking, integration/sharing, generated trading code, MT5 order, commit or push.
- Not verified: guest G proof, normal shutdown/final Off state, Closeout, B/H completion. No full regression, browser acceptance or Docker restart required for this scope.
- `G2_1_PARTIAL`; `READY_FOR_G2_2: NO`. Next: return actual guest output and perform healthy normal shutdown; then automate protected host Closeout and reassess the final matrix.

### G2.1 - Normal Shutdown Verified, Final Evidence Gap

Date: 2026-11-09
Verification: `FOCUSED_PASS` for read-only host reconciliation and documentation only.

- Continued from completed BootAfterG; no VM start/stop, provisioning, restore or passed guest probe repeated.
- Exact-clone Worker-Admin event 18508 at 15:53:26.2980266Z explicitly records shutdown by the guest OS. Both original and clone confirmed Off at 15:57:42Z.
- Final existing Stage3 Verify passed: identity, ownership, attached restored disk, isolation, authenticated installer and protected sealed/original incident pins remain valid.
- Original owner receipt and historical image-evidence hashes match the provision receipt; sealed/restored images are not host-mounted.
- Preserved `g21_closeout_host_audit_20261109.txt`; appended reconciliation after an overly specific English event-text filter rejected the valid shutdown event. No evidence overwritten or VM action taken.
- Referenced Debian guest attachment is unavailable in this session/local evidence; existing screenshot capture failed its permitted retry. Requested only existing output, not another guest run or boot.
- G remains INCONCLUSIVE for unavailable Debian identity, marker-absence, zero-failed-unit and root-rw output. Normal shutdown and final Off state are verified.
- Existing Closeout remains authorized but was not executed: its MARKER_ABSENT_AFTER_G_VERIFIED gate cannot truthfully attest unseen evidence. No new approval or VM operation requested.
- A/C/D/E/F retain prior runtime PASS. B remains INCONCLUSIVE for independent Basic Session/no-other-sharing/guest-inventory attestation.
- H remains INCONCLUSIVE for installed-image lineage; media signatures and current VHDX hashes cannot replace installation-history proof.
- `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- Updated final acceptance report and affected handoff; existing work/evidence preserved, no production source, network, generated code, trading, commit or push.
- Not verified: actual G guest output and independent B/H proof. Not executed: evidence-attesting Closeout. No full regression, browser check or app restart required.
- `G2_1_PARTIAL`; not eligible for full acceptance; `READY_FOR_G2_2: NO`. Next: make existing guest evidence available, finish authorized Closeout if healthy, and independently resolve B/H.

### G2.1 - Final Operator-Attested Closeout, Product Handoff

Date: 2026-11-09
Verification: `FOCUSED_PASS` for host Closeout and documentation; not full acceptance.

- Operator explicitly confirmed the post-BootAfterG guest checks; G recorded OPERATOR_ATTESTED. Independent machine-readable guest evidence was not captured; no guest output or formal G PASS invented.
- Reused unchanged incident-pinned Stage3 Closeout and its exact MARKER_ABSENT_AFTER_G_VERIFIED stdin gate under explicit authorization; no gate override.
- Closeout completed at 16:07:49.0980135Z, exit code 0; exact-clone stage3_closeout.json written once.
- Log: g21_operator_attested_closeout_20261109.txt. Post-Closeout original and clone Off; protected pins/isolation checked by the existing procedure.
- Preserved both VMs, all VHDXs, sealed baseline and prior evidence. No VM state mutation, F/G replay, resource reset, new guest check or screenshot request.
- A/C/D/E/F retain prior runtime PASS; B/H INCONCLUSIVE. Independent exposure/inventory attestation and installed-image lineage remain mandatory full-acceptance blockers.
- G2.1 closed PARTIAL; formal independent G proof remains a qualification. No further evidence gathering scheduled without a concrete safety-critical product dependency.
- Documentation tests: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 13 passed.
- Final acceptance report and affected current handoff updated. No production source change, full regression, app restart, commit or push.
- Next proposed slice: expose existing G1 computational specification and missing/conflicting fields in the read-only orchestrator response; reuse QueryPlan/resolver and computational-specification tests, with no new semantic call/service.
- That slice can proceed without sandbox execution approval; it must retain provenance, NOT_CHECKED data and execution_allowed=False. It is proposed, not implemented.
- Not implemented/authorized: G2.2 generated-code execution, sandbox isolation changes, live trading. READY_FOR_G2_2: NO.

### Computational Specification Review

Date: 2026-11-09
Verification: `FOCUSED_PASS`.

- Reused the current typed G1 QueryPlan and semantic provenance in the orchestrator's bounded text response. No new schema, service, prompt, provider call, or authority path.
- Confirmed fields, unconfirmed values, gaps, conflicts and unsupported requirements are separate. Clarification questions follow existing gaps and conflicts; a complete spec remains non-executable with data `NOT_CHECKED`.
- Added a Streamlit review badge and fixed the invalid-session fallback to reload the replacement history before rendering. Scripted Streamlit tests verify no old specification or trade card is attached to a new request.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_computational_specification.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_goal_only_research_brief.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_context_acquisition_executor.py scripts/test_60_case_product_acceptance.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 298 passed, two existing dependency warnings. Offline harness execution flags set false for pytest only; initial canonical run refused four cases under local execution flags. No `.env` edits.
- App-only restart, mounted source hashes matched, Streamlit health HTTP 200. No live prompt, full regression, market/account reads initiated by this verification, MT5 action, VM activity, commit or push.
- Next: explicit read-only spec field completion using the existing typed patch contract. No G2.1 reopening or G2.2 work.

### Typed Computational Specification Clarification

Date: 2026-11-09
Verification: `FOCUSED_PASS`.

- Added an Advisory form for one supported missing leaf in the latest computational review. Input uses typed choices or explicit scalar/text, with no semantic provider call.
- Reused the existing semantic patch, strict specification validation and QueryPlan projection from canonical state. Rebuilt review preserves sibling facts and provenance, reports remaining gaps/conflicts and stays non-executable.
- Conversation history conditionally appends to the exact persisted tail, without upsert or vector indexing. Stale, duplicate, cross-conversation and deleted review submissions cannot write a revision.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_computational_specification.py scripts/test_history_service_runtime_persistence.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_goal_only_research_brief.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_context_acquisition_executor.py scripts/test_60_case_product_acceptance.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 322 passed, three existing deprecation warnings, with execution flags false for the pytest process only.
- Streamlit AppTest verifies successful clarification, rerun, switching, and stale/deleted reviews. A real MongoDB probe used a temporary isolated collection: exactly one concurrent append succeeded, and newer, changed and deleted tails were rejected. No live conversation was used.
- Restarted only the app. All six runtime source hashes matched the host, container health became healthy and Streamlit returned HTTP 200; checked execution flags remained disabled.
- Fixed interim failures involving Streamlit's removed widget after rerun and validation-error ownership. Final verification had no failures. No live provider, full regression, MT5, G2.1/G2.2, commit or push.
- Next: one typed OHLCV coverage field family; no data or execution authority change.

### OHLCV Integer Clarification

Date: 2026-11-09
Verification: `FOCUSED_PASS`.

- Extended existing OHLCV clarification to the missing lookback and explicitly unresolved warm-up leaves, without defaulting optional warm-up or modifying unrelated requirements.
- Reused strict positive/nonnegative specification constraints and rejected ambiguous text, fractions, non-integer patches and BSON overflow. No relationship between the two counts was added.
- Existing QueryPlan, conditional append, conversation scope and advisory-only behavior are unchanged. No new service, collection, acquisition or provider call.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_computational_specification.py scripts/test_history_service_runtime_persistence.py scripts/test_computation_pilot.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_goal_only_research_brief.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_context_acquisition_executor.py scripts/test_60_case_product_acceptance.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 371 passed, three existing deprecation warnings, with offline execution flags overridden in pytest only.
- Streamlit AppTest verified integer apply/review rerun, rejection before persistence, stale/deleted reviews and conversation switching. BSON boundary and concurrent/duplicate tests passed without writing to a live conversation or creating a collection.
- No full regression, live provider, generated code, G2.1/G2.2 activity, broker operations, commit or push.
- Next: one typed OHLCV freshness-tolerance field, still read-only.

### OHLCV Freshness-Tolerance Clarification

Date: 2026-11-09
Verification: `FOCUSED_PASS`.

- Reused the typed integer clarification path for an explicitly unresolved `max_age_seconds` on an identified OHLCV requirement. Positive integers only, bounded by signed 64-bit BSON; no optional-field default or actual freshness check.
- The existing UI, provenance, QueryPlan and conditional history append stay in place. AppTest verifies apply/rerun, invalid input, stale review and conversation isolation; BSON and concurrent/duplicate coverage use no live conversation or new collection.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_computational_specification.py scripts/test_history_service_runtime_persistence.py scripts/test_computation_pilot.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_goal_only_research_brief.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_context_acquisition_executor.py scripts/test_60_case_product_acceptance.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 392 passed, three existing warnings; offline execution flags overridden only in pytest.
- No market/provider call, MT5 action, G2.2 execution, full regression, commit or push. Stop individual OHLCV widgets. Next proposed slice: project existing revision readiness and approved historical evidence verification separately, without running research.

### Read-Only Research Readiness

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Added an on-demand Advisory view of one operator-pinned proposal export and one explicitly approved local historical source. No chat-derived proposal, path, scope, pin, or approval.
- Kept recorded proposal review separate from current R2 coverage, integrity and provenance. Pinned replay is display-only; normal proposal replay and approval verification are unchanged. Bad manifest pins stop before row reads.
- Wrong scope or revision, superseded head, changed snapshot, unapproved/missing source, insufficient coverage and verifier failures fail closed. No persisted report, research run, authority write or live data call.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_computational_specification.py scripts/test_history_service_runtime_persistence.py scripts/test_structured_semantic_interpreter.py scripts/test_structured_semantic_query_plan.py scripts/test_trading_semantic_cutover.py scripts/test_goal_only_research_brief.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_context_acquisition_executor.py scripts/test_60_case_product_acceptance.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: 469 passed, three existing deprecation warnings. Execution flags were overridden only in pytest.
- AppTest verified separate statuses, on-demand inspection, rerun and conversation isolation. Streamlit health HTTP 200. No approved binding/snapshot was present; no live review, full regression or app restart. Loaded live execution flags were left unchanged.
- No G2.1 reopening, G2.2, MT5 action, generated code, commit or push.

### R1 Immutable Research Input Package

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Reused R1 pinned replay, explicit approved binding, R2 verification and historical loader; approval, revision, scope and manifest pins must pass before rows are read. No new approval, semantic or execution authority.
- Added one input-preparation module and focused tests. Canonical `r1-research-input/v1` contains only UTC timestamp/High/Low observations plus identity, source, window and checksum metadata; no descriptive calculation.
- Real acceptance used the exact approved revision and `research_dataset_e81f53d087563a5c1c128979`: 60 closed XAUUSDm M1 bars, 2026-11-04 15:00-16:00 UTC end-exclusive. Proposal, binding, manifest and source data bytes were preserved.
- One content-addressed artifact under ignored `data/research/inputs/`, SHA-256 `c2f1fc8a424eec05338d19f05f2abb0bddae006edb2ae1ee59a492f4ea8d68e8`. Repeat preparation returned identical bytes and unchanged mtime without another package. Existing conflicting bytes are never overwritten; no OS-level immutability claim.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **128 passed**, two existing dependency deprecation warnings.
- Focused coverage includes deterministic replay, exact projection/precision, unapproved or wrong revision/scope, changed export/manifest/data, incomplete/duplicate/unordered rows, symbol/timeframe mismatch and no-overwrite tamper rejection.
- No live market access, provider call, trading, research calculation, generated code, G2.2, app restart, full regression, commit or push. Unrelated dirty worktree remains preserved.
- Next proposed slice: independently authorized deterministic descriptive computation from the verified package; no implicit research execution approval.

### R1 Controlled Descriptive Computation - Implementation

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Added the pure per-bar `high - low` operation and a separately gated trusted-host entry point inside the existing research package. No new service, semantic authority, provider call or generated execution.
- R1 `ACCEPTED_FOR_NEXT_RESEARCH_STAGE` is insufficient to execute. Exact operator approval must bind proposal/revision/scope, package hash, `HIGH_MINUS_LOW_V1` and output destination. Without that projection the entry point stops before reads/calculation.
- Revalidate current binding and pinned proposal head before the pinned package, its metadata/row checksum and exact timestamp window. Reject invalid fields/numerics, gaps, duplicates, wrong identity and negative ranges. Check source bytes again before publication.
- Preserve original timestamps and High/Low. Decimal arithmetic emits exact decimal-string ranges, avoiding float subtraction artifacts and process-context precision loss. Result schema `r1-descriptive-result/v1` binds input, algorithm and provenance.
- Reused input package no-overwrite publication with a result filename prefix; unchanged input preparation remains regression-tested. Fixture repetition returns identical bytes/mtime, and tampered existing results are not replaced.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **174 passed**, two existing dependency deprecation warnings. Includes 46 new computation cases; syntax checks pass.
- Real package SHA-256 unchanged. No actual 60-bar calculation or result artifact yet: **AWAITING OPERATOR APPROVAL**. Fixture success is not real research acceptance.
- No MT5, broker mutation, backtest/optimizer, app restart, G2.1 reopening, G2.2, commit or push. Unrelated dirty worktree preserved.
- Next: separately authorize and verify only this exact bounded historical computation; no implicit follow-on execution.

### R1 Controlled Descriptive Computation - Authorized Real Acceptance

Date: 2026-11-10
Verification: `FOCUSED_PASS`, plus real local historical computation evidence.

- Operator explicitly authorized one `HIGH_MINUS_LOW_V1` run for the exact existing revision and input SHA-256 `c2f1fc8a424eec05338d19f05f2abb0bddae006edb2ae1ee59a492f4ea8d68e8`. This was not inferred from R1 stage approval.
- Revalidated the pinned export, approved binding, accepted current revision/scope, input identity/hash and 60-bar M1 window before the existing production entry point. Runtime call tracing recorded exactly one entry-point and one calculator call.
- Produced one ignored `data/research/results/research_result_cbe3c90bb56aba8230a8843765e110c94e8742a21db04dfbc2a1f901a41cf0a1.json`: 5,992 bytes; filename suffix is the full-byte SHA-256. Schema `r1-descriptive-result/v1`, execution/generated-code authority false.
- Preserved all 60 UTC timestamps/High/Low and computed only their decimal-string ranges. An independent rational oracle verified 60/60. Independent full result reconstruction and canonical reserialization reproduced exact bytes without a second production run.
- Proposal, binding, manifest, historical data, input package and Git index remained unchanged. No production/test source changes were necessary; only current handoff and this appended entry changed.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_research_computation.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **59 passed**. Earlier 174-case research family PASS is retained, not rerun. No full regression or live market test.
- No MT5/provider call, order, trading authority change, app restart, G2.2, generated code, backtest/optimizer, commit or push. G2.1 remains CLOSED/PARTIAL.
- Next proposed milestone: expose this pinned descriptive result through the existing read-only research presentation, without new calculation or implicit promotion.

### R1 Verified Research Result Review

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Added **Inspect verified result** inside the existing Research readiness view. Reused orchestrator/conversation identity, R1 binding and the existing descriptive module; extracted read-only input validation so review and execution share authority checks.
- Host-only `RESEARCH_RESULT_BINDING` pins input/result SHA-256 alongside the existing readiness binding. Fixed approved local paths only; no scan, chat-provided path, stored review or automatic approval.
- Verify actual result bytes before parsing, then schema, algorithm, approval/provenance, input and current accepted revision/scope, rows and source snapshots. Failed checks show precise blockers without a verified table. No computation, oracle rerun, statistics or artifact mutation.
- Table displays exact text UTC timestamp, High, Low and decimal Range with objective, identity, source/window and checksum metadata. Research limitations are explicit. Click results disappear on rerun; wrong/deleted conversations and tampered files cannot reuse the table.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_research_result_review.py scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_thin_ui_full_conversational_integration.py scripts/test_thin_ui_authoritative_draft_presentation.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **256 passed**, two existing deprecation warnings. Includes 29 review cases and Streamlit AppTest. An initial installed-Streamlit dataframe API mismatch was corrected before final PASS.
- Real host-only review verified the existing result SHA-256 `cbe3c90bb56aba8230a8843765e110c94e8742a21db04dfbc2a1f901a41cf0a1`, exact input/revision/scope and 60 rows. Calculator/execution call counts were both zero; all six protected research artifacts remained unchanged.
- Running app/health returned HTTP 200; live execution flags remain enabled. No restart or persistent pin configuration was performed, so deployed-browser acceptance is **NOT VERIFIED**. Host AppTest and actual local artifact inspection are separate evidence.
- No MT5/provider call, trading mutation/authority, new research computation, G2.2, full regression, commit or push. Existing dirty worktree preserved.
- Next: bounded typed requirements/coverage for broader historical research through existing R1/R2 contracts; acquisition and computation need their own approval.

### Extended Historical Research Coverage - Local Assessment

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Defined a proposed three-hour observation objective: XAUUSD/XAUUSDm M1, 2026-11-04 14:00-17:00 UTC end-exclusive, 180 contiguous closed bars. This is not a statistical sufficiency or trading-performance claim; scope still needs operator approval.
- Restricted local discovery to the canonical MT5 research dataset root. Existing loader checks passed for three actual artifacts: 60 VERIFIED M1 bars (Nov 4 15:00-16:00), 6,829 PARTIAL M1 bars (Oct 26-Nov 2), 338 PARTIAL ticks (Nov 4 15:00-15:01). Only the 60-bar source is in the current approved binding.
- Existing `assess_quality` found exactly 120 missing local target bars: Nov 4 14:00-15:00 and 16:00-17:00 UTC. Weekly data does not overlap and retains 430 missing weekday slots/calendar mismatch; ticks cannot replace bars. No broker-session cause or live availability was inferred.
- Used `ResearchProposal.revise` only in memory to test the larger evidence window; `EVIDENCE_PENDING`. R2 returned `PARTIAL_OR_LIMITED / RESEARCH_COVERAGE_INSUFFICIENT`. No accepted revision, approval, source data, immutable input or result was changed.
- Prepared an explicit `HistoricalDataRequest` and the existing exporter command in handoff section 141. One complete 180-bar-window export is proposed, preserving the current 35-record quality floor and declared weekday policy; no acquisition was executed or authorized implicitly.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_historical_research_dataset.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_session_coverage.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **93 passed**, two existing deprecation warnings. Additional mocked mapping rejection stopped before MT5 initialization. Existing coverage contracts are adequate; no implementation fix or source/test edits needed.
- Only current handoff and this appended entry changed. No market acquisition, new descriptive computation, proposal approval, broker action, app restart, G2.2/Hyper-V, commit or push. Unrelated dirty worktree preserved.
- Remaining gate: explicit approval for the exact read-only Nov 4 14:00-17:00 UTC DEMO export, then manifest/coverage verification and separate source/revision review. Research execution remains a separate authorization.

### Authorized Three-Hour MT5 Historical Export

Date: 2026-11-10
Verification: `FOCUSED_AND_LIVE_PASS` for read-only acquisition, not broker execution.

- Explicit operator approval covered one XAUUSD/XAUUSDm M1 bars export, Nov 4 14:00-17:00 UTC end-exclusive, warmup quality floor 35, `UTC_WEEKDAYS_CONSERVATIVE_V1`.
- Read-only preflight verified connected DEMO identity, stable fingerprint, mapping and contract metadata. Existing CLI executed exactly once, exit 0, no retry; source/configuration and execution authority were not changed.
- Dataset `research_dataset_46c26e4f381b5e5a0cda010c`: **180/180** ordered unique closed bars, first 14:00, last 16:59 UTC, no missing timestamps, zero outside-window/additional warm-up bars. Loader integrity/identity/quality checks returned `VERIFIED`; no issues or acquisition failures.
- Canonical manifest SHA-256 `c7d1e743204a111f48e1978593d758c5fafd2a982d3e5d5ae13d3a734cf3a76f`; data SHA-256 `785175291491edb92129ecce470a69b4c67d9c52dbd60f956e75c9f302afdff4`. Source is authenticated local MT5 DEMO with execution authority false.
- R2 remained correctly blocked for admission: `SOURCE_UNAVAILABLE / RESEARCH_SOURCE_NOT_APPROVED` on a temporary pending revision, using only the old authorized source owner. No source registration, proposal approval, persisted revision or binding replacement occurred.
- Original datasets, proposal, binding, immutable input/result, `.env`, Git index and unrelated worktree files preserved. Only handoff/changelog and the new ignored export artifact were written.
- Documentation check: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **13 passed**. The prior 93-case unchanged-source coverage family result is retained, not rerun. No production/test source change or full regression.
- No Streamlit restart, research computation, trading, G2.2/Hyper-V, commit or push. Next: exact pinned historical source approval, followed by separately reviewed expanded revision and computation authorization.

### Extended Source Admission and Pending R1 Revision

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Applied explicit source-use-only approval after checking exact dataset/manifest/data pins, XAUUSD/XAUUSDm M1 mapping, DEMO/authenticated provenance and all 180 closed UTC slots from Nov 4 14:00-17:00. No new data acquisition.
- Source is `research_dataset_46c26e4f381b5e5a0cda010c`, manifest `c7d1e743204a111f48e1978593d758c5fafd2a982d3e5d5ae13d3a734cf3a76f`, data `785175291491edb92129ecce470a69b4c67d9c52dbd60f956e75c9f302afdff4`. Reused existing trusted readiness binding and R2 source owner; no second approval system.
- Confirmed the existing trading scope is conversation-derived, not window-derived, and its conversation still exists unambiguously. Used the existing R1 lifecycle to append `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5` to the unchanged proposal identity; no review/acceptance call.
- Current R1 export/binding persisted and strict replay passed. Export SHA-256 `d28a2347ef10ec530c4a518f04bb26d2301bc84fe74e650f0d1e8ef123e9998b`. New proposal status is `READY_FOR_REVIEW / RESEARCH_REVISION_NOT_ACCEPTED`; evidence separately `VERIFIED_FOR_DECLARED_SCOPE`; new review-record count zero.
- Archived the prior proposal and binding byte-for-byte before current-head update, under ignored `data/research/readiness/archive/`. Original one-hour revision/acceptance remains in history; all datasets, input/result and trading state preserved. Old pins are not silently repointed or installed in the running app.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_research_readiness.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **48 passed**, two existing deprecation warnings. No source/test edits or full regression.
- No proposal approval, research computation, MT5 access, Streamlit restart, authority change, G2.2/Hyper-V, commit or push. Existing dirty worktree preserved except the explicitly authorized research state and documentation updates.
- Stop at the exact new revision's operator review gate. Source eligibility is not revision acceptance; stage acceptance would still not authorize computation.

### Three-Hour R1 Approval and Verified Input Preparation

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Verified exact operator-approved pre-review export/revision/scope and existing source pins for 180 XAUUSDm M1 bars, Nov 4 14:00-17:00 UTC. Applied `ACCEPTED_FOR_NEXT_RESEARCH_STAGE` through `ResearchProposal.review` only; exactly one new review record, no revision-content change.
- Persisted accepted export SHA-256 `e9afb513179a06b421aee2b9c020e0a5d785ebd66e82dbe2a3edb2c4d67df1f4` and updated its current research binding checksum. Pending snapshot/binding were archived byte-for-byte; historical one-hour artifacts and reviews preserved.
- Strict reload and existing Research Readiness passed separately: proposal `ACCEPTED_FOR_NEXT_RESEARCH_STAGE`; evidence `VERIFIED_FOR_DECLARED_SCOPE`. Stage approval still grants no computation/trading authority.
- Reused unchanged `r1-research-input/v1` preparation for only UTC timestamp/High/Low. One 10,370-byte artifact under ignored `data/research/inputs/`, full SHA-256 `f4e4fa840ccfa8f87394d41cd3525366fcebf5b200e9aadc3021aeb1c8c50741`, exactly 180 source-identical observations with full provenance/pins and execution disabled.
- Repeated preparation returned identical bytes/hash/mtime and no second package. Protected source/export/binding stayed unchanged during preparation, original input/result preserved, calculator/execution call counts zero. No result calculation or new result file.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_research_readiness.py scripts/test_research_input_package.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **63 passed**, two existing deprecation warnings. No production/test changes or full regression.
- No MT5 access, acquisition, research computation, backtest/optimizer, generated execution/G2.2, Streamlit restart, trading authority/config change, commit or push. Unrelated local state preserved.
- Remaining exact boundary: independent computation approval for the new revision/input hash, operation `HIGH_MINUS_LOW_V1` and bounded output destination; the old 60-bar execution approval is not reusable.

### Authorized 180-Bar Descriptive Computation

Date: 2026-11-10
Verification: `FOCUSED_PASS`, plus real local historical execution evidence.

- Applied the operator's separate exact authorization for revision `revision_c0f5efd05ced99cf0abb35a9da3d5aa70d6a45e249f5e42d45e1e0250c33a0b5`, accepted export `e9afb513179a06b421aee2b9c020e0a5d785ebd66e82dbe2a3edb2c4d67df1f4`, input `f4e4fa840ccfa8f87394d41cd3525366fcebf5b200e9aadc3021aeb1c8c50741` and `HIGH_MINUS_LOW_V1` only.
- Revalidated current identity/approval/binding/dataset/input hashes and exact 180-bar scope before one production entry-point call. Runtime tracing counted one calculator call; retries zero. No prior result existed for this input.
- One ignored result artifact `research_result_6323aff52d368d6f97ba9aec21dbcfa953df48bb1b245eb295739acf2ed0f842.json`, 14,002 bytes; filename suffix is its full-byte SHA-256. Schema/provenance binds accepted revision/input/dataset/algorithm; execution/generated-code authority remains false.
- All 180 ranges matched an independent exact Decimal oracle with rounding/inexact traps enabled. Complete independent artifact reconstruction and canonical reserialization reproduced identical bytes. Idempotent publication of identical bytes preserved mtime/content without rerunning production computation or creating another result.
- First 14:00 UTC Range 2.943; last 16:59 UTC Range 2.537, Nov 4. No statistics or performance/strategy conclusions. Existing read-only result verifier also returned `VERIFIED` on the exact pins.
- Original 60-bar result, all datasets/inputs/proposal/binding/archives and unrelated worktree state preserved. No source/test edits or persistent app configuration change; handoff/changelog and one new result are the only task writes.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_research_computation.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **59 passed**, two existing deprecation warnings. No full regression.
- No MT5, trading, backtest/optimizer, generated code/G2.2, app restart, authority change, commit or push. Stop after this completed bounded computation; no automatic next acquisition/revision request.

### Cross-Window Consistency and Hourly Summary Implementation

Date: 2026-11-10
Verification: `FOCUSED_PASS`.

- Verified both actual result pins independently using archived one-hour approval versus current three-hour approval. Exact Decimal comparison found **60/60 matches**, zero High/Low/Range discrepancies, Nov 4 15:00-16:00 UTC. No old computation repeated or artifact altered.
- Added explicit hash-pinned archive context to the existing read-only verifier, with no automatic fallback or UI input. Current execution validation remains unchanged.
- Added `HOURLY_RANGE_SUMMARY_V1` and `r1-hourly-range-summary/v1` in the existing research package. Three consecutive UTC hours, exactly 60 M1 range observations each; count, mean, median, min/max only. Mean uses 12 decimal places/half-even; median/min/max exact Decimal; no extra dispersion or trading claims.
- Reused typed computation approval, current result verification and no-overwrite publication. Summary permission is operation/result/revision/scope/destination-specific and cannot authorize high-minus-low, or vice versa. Schema binds original input, source result, proposal/dataset/window, algorithm and precision policy.
- Scope remains the accepted descriptive High/Low data/window; schema requires no new revision for this derived descriptive operation. Explicit approval for the summary's scope and execution is still **PENDING**; no real aggregation or summary artifact created.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_summary.py scripts/test_research_result_review.py scripts/test_descriptive_research_computation.py scripts/test_research_input_package.py scripts/test_research_readiness.py scripts/test_research_evidence_verification.py scripts/test_research_proposal.py scripts/test_historical_research_dataset.py scripts/test_computation_pilot.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **226 passed**, two existing dependency deprecation warnings. Includes 23 summary/archive/overlap/authority cases; syntax/diff checks pass. No full regression.
- Actual comparison instrumentation recorded zero production high-minus-low or summary calls. Tests use controlled fixtures; protected data, snapshots, inputs/results and unrelated dirty worktree preserved.
- No UI work, live MT5, acquisition, research execution, G2.2/Hyper-V, restart, commit or push. Next gate: one bounded operator approval for `HOURLY_RANGE_SUMMARY_V1` on source result `6323aff52d368d6f97ba9aec21dbcfa953df48bb1b245eb295739acf2ed0f842`, unchanged accepted revision, three declared groups/statistics and content-addressed result destination.

### Authorized Three-Group Hourly Range Summary

Date: 2026-11-10
Verification: `FOCUSED_PASS`, plus actual local descriptive aggregation evidence.

- Applied exact operator authorization after rechecking current revision/review, binding, source result integrity/provenance, 180 XAUUSDm M1 observations and summary precision policy. No previous summary existed; no earlier computation repeated.
- Production entry-point/aggregator calls **1/1**, high-minus-low calls **0**, retries **0**. Computed only the five approved statistics for each UTC hour on Nov 4, 14:00-17:00 end-exclusive.
- Result `research_summary_10c783572d3f834945f8efb799af9137150d56eceb9f0ed7b60851beaa3c0645.json`, **2,817 bytes**, under ignored `data/research/results`; full-byte SHA-256 is its filename suffix. Schema `r1-hourly-range-summary/v1` binds source/input/revision/dataset/precision policy and explicit approval; execution/generated-code flags false.
- Means: 2.681033333333 / 2.673366666667 / 2.539250000000; medians: 2.4035 / 2.5615 / 2.386. Each group count 60; exact min/max and full table recorded in handoff section 147. No extra statistics or performance claims.
- Independent UTC-predicate grouping and Decimal reference verified all three groups and five statistics. Full artifact reconstruction and canonical serialization reproduced exact bytes; idempotent publication preserved bytes/mtime without production rerun or a duplicate summary.
- All existing datasets, proposals, bindings, input packages, archives and prior results preserved. No production/test edits; only new summary artifact and handoff/changelog updates.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_descriptive_summary.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **36 passed**, two existing deprecation warnings. No full regression.
- No MT5, trading, strategy/backtest/optimizer, generated code/G2.2, restart, authority/configuration change, commit or push. STOP at completed bounded objective; no automatic acquisition or further computation.

### Strategy Research and Backtesting Readiness

Date: 2026-11-10
Verification: `FOCUSED_PASS`, assessment plus static research-harness correction.

- Capability matrix, data requirements and next milestone are in handoff section 148. Current R1 is descriptive-only with no strategy; observation evaluators explicitly prohibit trade simulation.
- Fixed research EA fixture flags using Python-expected current RSI instead of native calculated RSI. CSV/previous-RSI context and Tester-only/default-no-orders protections remain unchanged. Added one static regression; application Trading Core untouched.
- Retained native checkpoint has 57/58 math vectors, Decimal/double half-tick mismatch, zero historical simulations. Patched EA has not been compiled/run; historical source/binary/reports preserved. No tolerance weakening.
- One next milestone: `RESEARCH_NUMERIC_PARITY_CLOSURE` using existing EA/comparator and approved exact numeric policy. Separate native research isolation/provenance approval required; no new engine or descriptive UI.
- Full OHLCV/session/warmup plus cost/tick provenance required. Eight trading weeks with chronological development/validation/holdout is only a proposed planning horizon, not sufficient-sample evidence or acquisition approval.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_field_aware_editable_trade_draft.py scripts/test_backtest_evaluation.py scripts/test_paper_trading_evaluation.py scripts/test_historical_research_dataset.py scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **177 passed**, two existing protobuf deprecation warnings. Isolated parity suite **17 passed**.
- No full regression, actual backtest, native compile/run, MT5/acquisition/orders, G2.2, app restart, authority change, commit or push. Unrelated dirty worktree/protected evidence preserved.

### Research Numeric Parity Correction; Native Gate Pending

Date: 2026-11-10
Verification: `FOCUSED_PASS`; native parity verdict **INCONCLUSIVE**.

- Revalidated the exact 58-vector fixture. Python remains byte-value equivalent to archived expected rows; old native CSV still fails only `real_16` SL/TP/risk. Not a rerun of updated MQL.
- Root cause: double subtraction discards the decimal residual before half-tick rounding. Kept production formulas and strict tolerances unchanged.
- Research EA now retains decimal input text and uses research-local bounded decimal operations, precision 28/half-even, tick half-up and volume round-down. Added independent native RSI operation order/compensated summation, BUY/SELL fixture handling and default MathOnly early return before market/order paths.
- Extended existing Python harness with input/fixture validation, pinned Decimal context, exact diagnostic values, numeric boundaries and preparation through the existing no-overwrite publisher. No new execution engine or authority.
- Prepared `numeric_parity_preparation_e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5.json` under ignored `data/research/mt5_tester`: 116 proposal vectors (58 original + 58 SELL), 30 scalar checks, fixture/source hashes, Python version; native fields explicitly NOT_VERIFIED/null. Handoff section 149 contains exact pins and proposed isolated math-only procedure.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_mt5_tester_parity.py scripts/test_reasoning_evidence_v2.py scripts/test_field_aware_editable_trade_draft.py scripts/test_backtest_evaluation.py scripts/test_paper_trading_evaluation.py scripts/test_historical_research_dataset.py scripts/test_research_proposal.py scripts/test_research_evidence_verification.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **306 passed**, two existing protobuf warnings. Python syntax/diff checks pass; no full regression.
- Native MQL compile/arithmetic correctness/output and current toolchain are NOT_VERIFIED. Blocker `NATIVE_MATH_ONLY_AUTHORIZATION_REQUIRED`; Windows research isolation/network denial must be approved and verified before invocation. Portable mode alone is not isolation proof.
- No MT5/native invocation, acquisition, simulated-fill/backtest, orders, authority change, generated code/G2.2, app restart, commit or push. Prior artifacts and unrelated dirty state preserved. Stop at the one exact native approval boundary, not at a claimed parity PASS.

### Native Math Isolation Audit Preparation

Date: 2026-11-10
Verification: new audit focused checks; isolation readiness **INCONCLUSIVE**.

- Conditional operator native approval recorded; effective network isolation remains unproven. No native invocation occurred.
- Added one read-only PowerShell operator audit with explicit ActiveStore/filter/error evidence and no self-elevation, policy changes or process launches. JSON output uses CreateNew and refuses reparse output parents; no credential/profile contents collected.
- Known executable paths identified separately from unknown child/helper paths. Program block candidates are not labelled whole-tree PASS.
- Non-elevated smoke audit preserved outbound/application Access denied and Sandbox-feature elevation errors, verdict INCONCLUSIVE, native count zero.
- Windows 10 Pro build 19045 lacks Sandbox launcher; feature state UNKNOWN. Proposed offline disposable Sandbox is documented, not installed/launched. Pinned vendor build 6230 offline guest compatibility and safe artifact retrieval remain unverified.
- Operator command/evidence requirements: `docs/operations/native_math_isolation.md`; current evidence in handoff section 150. Existing parity implementation/tests and pinned package were not repeated or changed.
- No firewall/network/credential/trading changes, native compile/Tester, G2.1/G2.2, app restart, commit or push. Stop before native invocation.
- Audit-tool verification `FOCUSED_PASS`: `.\venv\Scripts\python.exe -m pytest scripts/test_native_math_isolation_audit.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **25 passed** (12 audit, 13 documentation); PowerShell parsing/diff check PASS. This is not native parity or isolation PASS.

### Disposable Offline Sandbox Preparation

Date: 2026-11-10
Verification: `FOCUSED_PASS` for preparation tooling; isolation remains INCONCLUSIVE.

- Verified host/resource metadata read-only; Sandbox Disabled, no launcher. Hypervisor present; hardware SLAT flags inconclusive under hypervisor. Headroom/restart requirements remain operator gates.
- Added input-only `native_math_offline.wsb` with network/clipboard/vGPU/redirection disabled, 2-GiB planned memory, no autorun/writable mapping. Not launched.
- Staged exactly 11 allowlisted input files under ignored `data/research/mt5_tester/native_sandbox_e05805d67cd2/input`; original numeric package/source pins untouched. Manifest `f20b2dff06dd6f4c288a4a32bd91605089a17c46e7f585b671750b7659534651`.
- Added manual guest preflight (hashes/allowlist/network/profile/process checks); no native calls. Static PE imports show Windows-system dependencies only; dynamic dependencies/offline compatibility unverified.
- Documented operator-only feature enable with -NoRestart, guest gates and separate exact outbox approval. No outbox/ACL/writable mapping created; safe machine-readable extraction remains pending.
- New preparation tests: `.\venv\Scripts\python.exe -m pytest scripts/test_native_math_isolation_audit.py -k sandbox -q -p no:cacheprovider --tb=short`: **6 passed, 12 deselected**. No repeated Firewall/parity suite or full regression; documentation checked separately.
- No Windows feature/policy change, Sandbox/native invocation, MT5 orders, G2.1/G2.2, app restart, authority change, commit or push. Stop before feature change/native invocation; exact operator runbook in `docs/operations/native_math_isolation.md`.
- Documentation integrity: `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **13 passed**; actual staged hash/allowlist helper and normal diff check PASS. Host-only preparation evidence, not guest isolation/native compatibility.

### Development-Only ChatGPT Issue to Codex Bridge

Date: 2026-11-10
Verification: `FOCUSED_PASS`; live transport/worker smoke NOT_VERIFIED.

- Added one independent tools module, offline tests and operator runbook; no Trading Core modification. Owner/label/UUID/hash-approval gates, PENDING/RUNNING/PASS/BLOCKED/FAILED receipts and fixed GitHub API allowlist.
- Tool-disabled, read-only Codex CLI turn over explicit local-source snapshots, not active Desktop thread/cwd. Mandatory keyring auth/private home and no inherited broker/GitHub/proxy env. No automatic privileged approval, shell/test command channel or generated-code execution.
- Default dry-run; edit requires local flag plus delivered real smoke PASS, one narrow development target, clean pre-existing state, hashes/AST/whitespace checks and exclusive write/backup. Global mutex, durable duplicate/crash protection and uncertain-comment reconciliation prevent task replay. Desktop unsaved buffers remain outside cooperative locking.
- Credential Manager stores separate least-privilege GitHub PAT; operator authentication and Issue-write connector capability remain prerequisites. No credential extracted from ChatGPT/gh, no listener or live smoke started. CLI validate-only checks confirmed command/app/hook tools disabled; an incompatible provider override was removed before release.
- Verification: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **73 passed** (60 bridge + 13 docs); targeted compileall/diff check PASS. Offline fake external boundaries, not live E2E; no full regression.
- Exact setup/activation/smoke and ChatGPT-side protocol in `docs/operations/codex_issue_bridge.md`; full boundary in handoff section 152. Codex transport retries retain installed bounded defaults under 300-second task deadline; no bridge task auto-retry.
- No broker/MT5/research/native Tester/G2.2, authority, Docker/WSL/app restart, destructive Git operation, commit or push. Existing unrelated worktree state retained. Next step is the operator-activated non-trading dry-run smoke, not expansion of permissions.

### Issue Bridge GitHub Authentication Diagnostics

Date: 2026-11-10
Verification: `FOCUSED_PASS`; live authentication remains BLOCKED pending operator PAT replacement.

- GET-only probe reproduced first failure: GET /repos/DATCAOTAN/Trading_Advisory_Chatbot, 401 Bad credentials, before Issue #1/tasks/comments. Network and error JSON were available; permissions were not reached/tested.
- Stored credential contained U+0016 (Ctrl+V); old whitespace-only validation accepted it. Added shared control/ASCII validation and verify-before-store owner/read checks. No token normalization, disclosure or automatic replacement.
- HTTP/network/request/JSON failures now emit sanitized method/endpoint/status/reason; HTTPError no longer disappears into generic URLError. No raw bodies/headers or credentials printed.
- Added GET-only `check`, before worker/state/locks; current malformed value fails locally without HTTP. Ambiguous POST receipts/no-repost and no-retry behavior preserved.
- Tests: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **97 passed** (84 bridge + 13 docs), no full regression. Focused error taxonomy/redaction, storage rejection/non-overwrite, read-only isolation and write-ambiguity regressions.
- No listener, worker, GitHub mutation, credential change, Trading Core/MT5/Docker/WSL/authority action, commit or push. Next operator action: replace invalid PAT securely, then the runbook's check command; no automatic task execution.

### Issue Bridge Windows GUI Credential Input

Date: 2026-11-10
Verification: `FOCUSED_PASS`; live PAT authentication/storage NOT_VERIFIED.

- Added `credential --gui` with installed Tkinter, masked input and explicit clipboard button; console fallback preserved. Rejects controls, whitespace, non-text and oversized input without stripping. Cancel/window close never stores credentials.
- Reuses shared validation, GitHub owner/read verification and Windows Credential Manager; no write before successful verification. Sanitized GUI failures suppress credential-bearing exception details. No automatic retry, clipboard mutation, listener or worker.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **119 passed** (106 bridge + 13 docs). Includes fake clipboard/vault/network and real withdrawn Tk widget checks; not live authentication evidence. No full regression.
- Operator runbook updated; current boundary in handoff section 154. Synchronous bounded verification can temporarily block the window; existing clipboard history remains operator-managed.
- No Trading Core, MT5, authority/configuration, Docker/WSL restart, Git commit/push or unrelated worktree edits. Next action: operator opens GUI, verifies/saves a real PAT, then runs read-only check.

### Issue Bridge Native Windows TLS

Date: 2026-11-10
Verification: `FOCUSED_AND_LIVE_PASS`; Issue writes and Codex worker NOT_TESTED.

- Existing urllib HTTPS handler receives explicit truststore context on Windows; CERT_REQUIRED/hostname verification preserved. No global SSL patch, insecure fallback, extra client or retry. Missing dependency fails closed; truststore 0.10.5 pinned in host-only tools requirements and installed in venv, not Docker/application requirements.
- Verified Windows Sectigo E36 -> Root E46 chain for GitHub; no process proxy/CA overrides observed. Historical issuer error did not reproduce: standard Python HTTPS already returned 200 before edits. Exact historical missing-intermediate/cache cause remains unproven, not asserted as a confirmed fix diagnosis.
- Exact new context public GET: HTTP 200. ONE authenticated read-only `check`: PASS, VALID Issue task, zero comments/writes/worker/state mutations; Issues Write remains NOT_TESTED. No PAT printed or changed.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **128 passed** (115 bridge + 13 docs). Context/no-global-mutation, missing dependency, certificate-error redaction and GET/POST ambiguity/no-retry checks added; existing error distinctions retained. No full regression.
- Runbook and handoff section 155 updated. No broker/MT5, research, authority, Firewall, Docker/WSL restart, listener, commit or push. Unrelated worktree preserved; no automatic smoke execution.

### Issue Bridge Uncertain Receipt Reconciliation

Date: 2026-11-10
Verification: `FOCUSED_AND_LIVE_PASS` for GET-only diagnosis; actual smoke BLOCKED.

- Inspected Issue #1 protected local bridge row without open_state mutation: initial PENDING smoke receipt, attempted=1/delivered=0. Remote owner/task/operation/hash match; comments=0. The NO_REPOST error comes from a prior-write reconciliation branch, not a new POST or worker attempt.
- Reproduced against a read-only database using existing delivery logic and GET evidence; no POST/worker, journal bytes unchanged. No once/watch process active at inspection.
- Historical HTTP outcome is not stored in this schema; cannot prove rejection, original TLS cause or Issues Write grant. Empty GET results alone cannot authorize repost. Existing PENDING/attempt state preserved, no manual clear or bypass; exact delayed receipt is the supported delivery-acknowledgement path.
- Added bounded tests: absent/delayed receipts across restart, exact identity/body/author, duplicates, 403 classification and no retry. No production source change or new recovery mechanism.
- Command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **137 passed** (124 bridge + 13 docs). No full regression; compile/diff checks separate. Runbook and handoff section 156 updated.
- No GitHub write, task execution, credential change, broker/MT5, Docker/WSL restart, commit or push. Remaining gate: operation-bound proof of rejection or genuinely published matching receipt; otherwise stay BLOCKED.

### Issue Bridge Task-Scoped Receipt Isolation

Date: 2026-11-10
Verification: `FOCUSED_AND_LIVE_PASS` for GET-only discovery/isolation, not smoke delivery.

- Root cause: global undelivered-receipt sweep aborted on old Issue #1 before discovering #2. Verified #1 closed/unlabelled and uncertain PENDING; #2 open/labelled, valid smoke task, no durable row or recorded POST.
- Existing tick now checks receipt-task admission and binding, defers withdrawn/changed tasks without mutation, and isolates active uncertain writes from independent work. Preserves no-repost, duplicate IDs, crash recovery, approval gates and one-new-task-per-poll.
- Added sanitized task/Issue/operation/comment-hash/stage diagnostics to deferral, uncertainty and POST failures. Original HTTP evidence/outcome remains unknown; no manual clear or receipt fabrication.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **146 passed** (133 bridge + 13 docs). Covers old closed/unlabelled tasks, independent tasks, each uncertain write, delayed visibility, restart and duplicate protection. Recovery fixture now uses canonical pin rather than placeholder.
- Live GET-only + in-memory journal probe reached #2's initial receipt boundary with a hard stop before network POST; original journal bytes/#1 row unchanged, no persistent #2 claim, zero worker calls. Does not prove write permission/smoke PASS.
- Runbook and handoff section 157 updated. No listener, GitHub write, credentials/security/MT5/trading/Docker/WSL mutation, commit or push. Next: operator runs one once for #2, inspecting any new task-specific POST failure without blind retry.

### Issue Bridge Worker Cwd Cleanup Failure

Date: 2026-11-10
Verification: `FOCUSED_AND_LIVE_PASS`; fresh GitHub E2E NOT_VERIFIED.

- Preserved #2 terminal FAILED row and task journal. Reproduced exit-0/parsed-result worker failure at temporary cwd cleanup: PermissionError, errno 13, WinError 32. Old outer cleanup error escaped worker handling and became LOCAL_FAILURE_NO_RETRY. Historical traceback and handle owner remain unavailable.
- Separated stable empty private worker cwd from disposable per-turn artifacts; reject nonempty/reparse workspaces. No sandbox/auth/tool/authority relaxation, ignored cleanup errors or worker retry. Short cleanup-wait experiment failed and was removed. Existing scratch evidence preserved.
- Added stage/exception/returncode/errno/WinError and allowlisted stderr markers to existing FAILED result. Raw stderr omitted; secondary cleanup cannot mask original failure. Existing idempotency/no-repost/terminal-state protections retained.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **166 passed** (153 bridge + 13 docs); no full regression. Tests cover preparation, process/timeout/return code, output parsing, cleanup, workspace isolation and FAILED no-repeat.
- Four independent diagnostic CLI calls: two cleanup failures and two PASS, including final separated-cwd run. Final worker-path run: one invocation, exit 0, BRIDGE_SMOKE_OK, edits=[], no new leftovers, original journal bytes unchanged. Subsequent diagnostic-marker-only refinement covered by focused tests; no extra provider invocation.
- Updated runbook/handoff section 158. No GitHub write/listener, credentials, Trading Core/MT5/Docker/WSL, commit or push. Local smoke does not unlock live_smoke_pass or retry Issue #2; next step is one separately authorized fresh GitHub smoke.

### Issue #5 - Watch Deferred Diagnostic Deduplication

Date: 2026-11-11
Verification: `FOCUSED_PASS`; live watch NOT_VERIFIED in this task.

- Existing task admission/reconciliation worked but printed the unchanged old inactive receipt every poll. Added only per-Bridge in-memory output dedup keyed by task/operation hash/reason/stage, with safe Issue state/lock/label changes observable.
- Latest-poll cache bounds memory and permits state reversion/recurrence logs; a new listener emits its first observation again. No persistent cache, journal/schema/authority changes, skipped checks or new retry behavior. New errors and independent tasks remain unaffected.
- Focused command: `.\venv\Scripts\python.exe -m pytest scripts/test_codex_issue_bridge.py scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **178 passed** (165 bridge + 13 docs). Tests prove admission still occurs each poll, output dedup, changed events, reversion, restart, independent fake task, delayed reconciliation and TLS error propagation. No full regression.
- Runbook/handoff section 159 updated; compile/diff validation separate. Baseline #3/#4 PASS states were read from local journal, not rerun. Original #1 uncertain outcome remains untouched.
- No GitHub API requests/POST, actual worker/listener, Trading Core/MT5, credentials/Firewall, Docker/WSL restart, commit or push. Preserve all unrelated local state. Operator restart: Ctrl+C existing watch, then plain watch without --allow-edits.

### Final Git Recovery - Dependency-Ordered Offline Checkpoints

Date: 2026-11-11
Verification: `FULL_REGRESSION_PASS` (offline software only)

- Published Recovery 01 (`51f625c`) by normal fast-forward. Recovered remaining functional, G2, native preparation, Bridge and documentation groups in an isolated worktree without changing the original dirty checkout or index.
- One bounded test-only correction: allow the existing strict descriptive-computation approval contract in the Pydantic owner assertion. No semantic/permission validation was relaxed. Redacted three private user-profile paths in the recovered G2 report.
- Final full command: original Windows venv `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,529 passed, 158 subtests passed, 60 skipped, three deprecation warnings. All skips require unavailable retained private native historical evidence; no native PASS claimed.
- Initial full run: 1 failed, 4,528 passed, 158 subtests, 60 skipped. Focused semantic/Draft/research correction: 341 passed. G2/native/Bridge/documentation group: 317 passed, 60 skipped. Compileall and four PowerShell parser checks passed; final documentation/diff checks recorded separately.
- Static safety: one production order_send call-site; zero MetaTrader5 imports under src. No live runtime, worker/listener, MT5, native Tester, research computation/acquisition, VM or Docker/WSL actions. Git publication does not authorize those operations.
- Preserved/excluded: embedding cache, personal .agents rules, six raw G2 transcripts, edit_smoke, datasets, binaries, credentials and journals. G2.1 remains PARTIAL and G2.2 unauthorized. Live/deployment/native/performance acceptance was not repeated.

### Goal-Driven Research - Brief to Persistent R1 Proposal

Date: 2026-11-11
Verification: `FULL_REGRESSION_PASS` (offline application verification)

- Connected existing canonical research briefs, R1 immutable proposals, Mongo conversation persistence and Streamlit Advisory. One explicit Generate action dispatches a bounded structured hypothesis call through the existing provider transport. Strict ResearchContent accepts no provider evidence, strategy code or authority fields.
- Added durable generation claims and exact brief/count/scope/record CAS; stale/deleted conversations, duplicates, concurrent writes and stale UI views fail closed. AI_RESEARCHED origin and canonical constraints/provenance survive user-authored revisions. Refresh/switch reload from persistent conversation state; no extra collection or semantic parser.
- Added independent R2 attach/check for the existing trusted approved binding only. Data PASS never approves the new proposal, supports its claim or grants execution. No source scanning, broker access, backtest or generated-code execution.
- Focused command: original Windows venv `python -m pytest scripts/test_goal_research_workflow.py scripts/test_goal_only_research_brief.py scripts/test_research_proposal.py scripts/test_research_readiness.py scripts/test_computational_specification.py -q -p no:cacheprovider --tb=short`: 168 passed, including 26 new workflow/AppTest cases.
- Final full command: `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,555 passed, 158 subtests, 60 skips requiring retained private native evidence, three existing warnings. Compileall and scoped secret/safety checks passed. Documentation/diff checks are separate. Test child processes alone receive .env.example boolean defaults.
- No live provider/Mongo/browser acceptance; synthetic fixtures are not broker evidence. No live-app restart, MT5/trading, Hyper-V, native Tester, Bridge runtime or G2.2. Interrupted generation remains claimed with no automatic retry; a fresh explicit brief is needed to try again. Original dirty checkout and protected data remain unchanged.

### Goal-Driven Live Integration and Interrupted-Generation Recovery

Date: 2026-11-11
Verification: `FULL_REGRESSION_PASS`, with separately verified real LLM/MongoDB/UI acceptance

- Separate trading-disabled Streamlit instance exercised the Vietnamese goal -> canonical brief -> explicit generation -> real Groq hypothesis -> persistent R1 proposal -> edit/reload/switch workflow. Real Mongo strict reload preserved two revisions, authorship, goal constraints and execution_allowed=false. R2 correctly remained EVIDENCE_PENDING without an approved source binding.
- Fixed observed timeframes-schema failure by passing existing typed schema/enums to the provider, not weakening validation. Field/type-only diagnostics replace opaque invalid-output failures. Initial Generate and two explicit retries produced two rejected responses followed by one valid proposal; no automatic retry.
- Added explicit confirmed same-brief retry/recovery, crash-releasing OS exclusion, unique attempt/CAS fencing and stale recovery tokens. Active/foreign-owner workers block takeover. No new service, collection, background task or authority path.
- Fixed observed refresh selection loss with an existence-checked conversation URL parameter; existing deleted-conversation fallback remains. AGENTS now permits verified normal fast-forward pushes under standing user authorization.
- Final focused command: original Windows venv `python -m pytest scripts/test_goal_research_workflow.py scripts/test_computational_specification.py scripts/test_history_service_runtime_persistence.py -q -p no:cacheprovider --tb=short`: 144 passed, including 36 workflow cases/AppTest. Final full command `python -m pytest -q -p no:cacheprovider --tb=short -rs`: 4,565 passed, 158 subtests, 60 private-native-evidence skips, three existing warnings. Compileall and documentation/diff/security checks separate.
- Instance 8503 process/source/health and fail-closed flags verified; instance 8501 and live authority/configuration untouched. No MT5, mandate/account mutation, native Tester, Hyper-V, G2.2 or Issue Bridge activation. No strategy research computation or performance acceptance claimed; cross-host forced recovery and Mongo failover remain unverified.

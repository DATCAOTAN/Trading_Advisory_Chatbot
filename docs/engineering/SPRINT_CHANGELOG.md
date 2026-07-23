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

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

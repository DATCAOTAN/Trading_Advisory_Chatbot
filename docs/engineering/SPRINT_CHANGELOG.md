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

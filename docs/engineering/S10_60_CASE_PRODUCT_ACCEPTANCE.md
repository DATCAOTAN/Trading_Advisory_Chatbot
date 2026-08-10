# Sprint 10 - 60-Case Product Acceptance

Date: 2026-08-10
Baseline commit: `217fb26cfa7b9180ca01fca5d5b3ed9688c14001`
Final checkpoint: containing local Sprint 10 commit
Verification: `FULL_REGRESSION_PASS`

## Result Summary

- Canonical cases classified: 60
- Contract-correct canonical cases: 60
- Canonical failures: 0
- Unclassified cases: 0
- Extra semantic variants: 5 passed
- Deterministic multi-turn sequence: passed
- Shared defects found: structured-provider prompt omitted three bounded schema/routing rules
- Production files changed: 1
- Full regression: 3,621 passed; 156 subtests passed; 3 unchanged warnings

## Canonical Matrix

| Case | Family | Result | Root reason | Artifact | Mode | Safety |
|---:|---|---|---|---|---|---|
| 01 | Social | PASS | Cheap social exit | EARLY_EXIT | advisory | no artifact |
| 02 | Social | PASS | Product/system exit | EARLY_EXIT | advisory | no mutation |
| 03 | Social | PASS | Cheap social exit | EARLY_EXIT | advisory | no artifact |
| 04 | Social | PASS | Out-of-scope exit | EARLY_EXIT | advisory | no mutation |
| 05 | Social | PASS | Bounded unknown handling | EARLY_EXIT | advisory | no fabrication |
| 06 | Knowledge | PASS | Static RSI concept | STATIC_KNOWLEDGE | advisory | no market authority |
| 07 | Knowledge | PASS | Static ATR concept | STATIC_KNOWLEDGE | advisory | no market authority |
| 08 | Knowledge | PASS | Static EMA/SMA comparison | STATIC_KNOWLEDGE | advisory | no market authority |
| 09 | Knowledge | PASS | Static stop-loss concept | STATIC_KNOWLEDGE | advisory | no management |
| 10 | Knowledge | PASS | Static sizing concept | STATIC_KNOWLEDGE | advisory | no risk calculation |
| 11 | Market | PASS | Typed RSI M1 requirements | TECHNICAL_SNAPSHOT | advisory | freshness-aware |
| 12 | Market | PASS | Typed EMA H1 requirements | TECHNICAL_SNAPSHOT | advisory | no Draft |
| 13 | Market | PASS | Current price requirement | MARKET_SNAPSHOT | advisory | no Draft |
| 14 | Market | PASS | Typed ATR M15 requirements | TECHNICAL_SNAPSHOT | advisory | unavailable is typed |
| 15 | Market | PASS | Missing period/timeframe retained | TYPED_UNAVAILABLE | advisory | no defaults |
| 16 | Analysis | PASS | Market analysis plan | MARKET_ANALYSIS | advisory | no authority |
| 17 | Analysis | PASS | Advisory BUY question | ADVISORY_RESULT | advisory | analyze only |
| 18 | Analysis | PASS | Macro plus technical plan | MIXED_EVIDENCE | advisory | one plan |
| 19 | Analysis | PASS | Strength analysis | MARKET_ANALYSIS | advisory | no mutation |
| 20 | Analysis | PASS | H1/H4 requirements preserved | TECHNICAL_SNAPSHOT | advisory | no strategy promotion |
| 21 | Completion | PASS | Period/timeframe unresolved | COMPLETION | human-confirmed | non-executable |
| 22 | Completion | PASS | Timeframe unresolved | COMPLETION | human-confirmed | siblings preserved |
| 23 | Completion | PASS | Period unresolved | COMPLETION | human-confirmed | siblings preserved |
| 24 | Completion | PASS | Threshold unresolved | COMPLETION | human-confirmed | no Draft |
| 25 | Completion | PASS | Typed context inheritance | COMPLETION | human-confirmed | provenance retained |
| 26 | Draft | PASS | Complete BUY projection | NON_EXECUTABLE_REQUEST | human-confirmed | evidence-gated |
| 27 | Draft | PASS | Complete SELL projection | NON_EXECUTABLE_REQUEST | human-confirmed | evidence-gated |
| 28 | Draft | PASS | Explicit SL preserved | EDITABLE_DRAFT | human-confirmed | no replacement |
| 29 | Draft | PASS | Explicit SL/TP preserved | EDITABLE_DRAFT | human-confirmed | invalid values block |
| 30 | Draft | PASS | Market-quality failure | TYPED_BLOCKER | human-confirmed | fail closed |
| 31 | Candidate | PASS | Explicit candidate action | NON_EXECUTABLE_CANDIDATE | human-confirmed | no auto-create |
| 32 | Candidate | PASS | Blocked Draft | NO_CANDIDATE | human-confirmed | no assembly |
| 33 | Candidate | PASS | Structured edit revision | NEW_REVISION | human-confirmed | dependencies only |
| 34 | Candidate | PASS | Revision-bound authority | STALE_AUTHORITY_BLOCKED | human-confirmed | no reuse |
| 35 | Candidate | PASS | Exact candidate confirmation | CANDIDATE_BOUND_CONFIRMATION | human-confirmed | no execution grant |
| 36 | Position read | PASS | Authoritative empty snapshot | AUTHORITATIVE_EMPTY | advisory | read-only |
| 37 | Position read | PASS | Orders distinct from positions | PENDING_ORDER_LIST | advisory | read-only |
| 38 | Position read | PASS | Broker P/L | BROKER_PNL | advisory | no calculation fallback |
| 39 | Position read | PASS | Broker SL/TP | BROKER_PROTECTION | advisory | read-only |
| 40 | Position read | PASS | Protected continuation | PROTECTED_REFERENCE | advisory | stale blocks |
| 41 | History | PASS | Broker closed-trade evidence | BROKER_HISTORY | advisory | empty is valid |
| 42 | History | PASS | Broker P/L components | BROKER_PNL | advisory | no inference |
| 43 | Provenance | PASS | Stored opening references | STORED_PROVENANCE | advisory | no invented reason |
| 44 | Provenance | PASS | Stored close references | STORED_PROVENANCE | advisory | unavailable explicit |
| 45 | Provenance | PASS | Missing management link | EXPLICIT_UNAVAILABLE | advisory | no fabrication |
| 46 | Human management | PASS | Exact pending target | MANAGEMENT_PROPOSAL | human-confirmed | confirmation required |
| 47 | Human management | PASS | Stop edit preserves TP | MANAGEMENT_PROPOSAL | human-confirmed | non-executable |
| 48 | Human management | PASS | TP edit preserves SL | MANAGEMENT_PROPOSAL | human-confirmed | non-executable |
| 49 | Human management | PASS | Deterministic 50% close | MANAGEMENT_PROPOSAL | human-confirmed | confirmation required |
| 50 | Human management | PASS | Full close to zero | MANAGEMENT_PROPOSAL | human-confirmed | confirmation required |
| 51 | Autonomous | PASS | Explicit mode request | MODE_REQUEST_ONLY | autonomous | no authority |
| 52 | Autonomous | PASS | Missing mandate | AUTHORITY_BLOCKED | autonomous | no mutation |
| 53 | Autonomous | PASS | Bounded DEMO mandate | BOUNDED_MANDATE | autonomous | exact scope |
| 54 | Autonomous | PASS | Revoked mandate | FINAL_VALIDATION_BLOCKED | autonomous | fail closed |
| 55 | Autonomous | PASS | Read remains read | POSITION_READ_MODEL | autonomous | no mutation |
| 56 | Failure | PASS | Provider failure once | FAIL_CLOSED | advisory | no fallback race |
| 57 | Failure | PASS | Ambiguous target | TYPED_BLOCKER | advisory | no guessing |
| 58 | Failure | PASS | Stale observation | TYPED_BLOCKER | advisory | fail closed |
| 59 | Recovery | PASS | Unknown result | RETRY_PROHIBITED | advisory | reconciliation only |
| 60 | Failure | PASS | Kill switch | PERMISSION_BLOCKED | advisory | zero bridge write |

## Provider and Browser Evidence

- Provider calls: 6 total, retries 0.
- Knowledge recheck classified `RSI` as knowledge and failed closed at missing direct-book evidence.
- Mixed advisory/current query remained advisory and failed closed at missing evidence.
- Three partial direct-strategy calls exposed shared prompt-contract gaps: optional scalar shape, missing indicator child shape, and direct-trade versus advisory classification.
- The three gaps were repaired at the single structured-provider prompt boundary; strict schema validation was not loosened.
- Final closure used one additional Groq call with zero retries and returned `VALID_PARTIAL`. The canonical result preserved `OPEN_POSITION`, `BUY`, `BTCUSD` / `BTCUSDm`, `RSI GREATER_THAN 10`, `human_confirmed_live`, and `CONFIRM_EVERY_TRADE` while leaving RSI period and semantic timeframe unresolved.
- Host and container source hashes matched after an app restart without rebuild. Streamlit returned `200 ok` and rendered exactly one `Strategy Completion Required` workflow with no competing advisory answer, Draft, Candidate, confirmation, or submission control.
- Browser/runtime mutation counts: Candidate 0, confirmation 0, pre-submit 0, controlled-submit 0, management write 0, runtime `order_send` 0, broker mutation 0, MT5 write 0.

## Not Verified

- Positive broker position/history/management paths against real broker state; deterministic fixtures cover them.

## Verdict

`60_CASE_PRODUCT_ACCEPTANCE_COMPLETE`

The deterministic product contract is 60/60, the retained full regression passes, and the bounded final provider/browser verification is contract-correct. Sprint 10 has no remaining release-blocking product gap.

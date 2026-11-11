# AI Platform Architecture Decisions

**Status:** Documentation integration is **APPROVED**. All architecture deltas
below are **PROPOSED** or **PENDING**. The
[locked target](../architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md) and
[AGENTS.md](../../AGENTS.md) remain unchanged. This register does not grant
permission to execute generated code, run the Tester, or trade.

## Three Independent Configuration Axes

| Axis | Proposed configuration | Compatibility boundary |
| --- | --- | --- |
| Strategy Origin | `USER_DEFINED`, `AI_RESEARCHED` | Initial strategy lineage, not per-field provenance, latest editor or reviewer. Already used by [R1 research proposals](../../src/services/trading/research/proposal.py), not a common production strategy field. |
| Authorization Mode | `ADVISORY`, `HUMAN_CONFIRMED`, `AUTONOMOUS` | Map product labels to existing `advisory_only`, `human_confirmed_live`, `autonomous_live` respectively. Do not rename or add production enum values. Requested mode is not effective [authority](../../src/services/trading/execution/mt5_live_adapter_pre_submit/trading_authority.py). |
| Adaptation Policy | `FIXED`, `ADAPTIVE_WITHIN_SCOPE`, `RESEARCH_AND_REQUEST_APPROVAL` | Proposed policy, not implemented authority. Fixed allows normal per-trade calculation under unchanged rules. In-scope changes need an approved deterministic controller, parameter bounds, cadence, audit and rollback. Research may propose revisions, never activate them. |

V1 cites `SYSTEM_PROPOSED` as a historical label. Review did not find it in the
inspected local source, tests or docs. This is a historical discrepancy in the
pack, not evidence of a stored alias. Do not introduce a migration unless actual
legacy records and compatibility requirements are established.

**18 theoretical combinations:** each ID range lists `FIXED`,
`ADAPTIVE_WITHIN_SCOPE`, then `RESEARCH_AND_REQUEST_APPROVAL`, in that order.

| Origin | Advisory | Human-Confirmed | Autonomous |
| --- | --- | --- | --- |
| `USER_DEFINED` | AX01-AX03 | AX04-AX06 | AX07-AX09 |
| `AI_RESEARCHED` | AX10-AX12 | AX13-AX15 | AX16-AX18 |

All 18 follow **`NO_IMPLICIT_AUTHORITY`**. Advisory stays read-only;
Human-Confirmed requires exact per-action consent; Autonomous requires a
current bounded Standing Mandate. No origin, adaptation choice, mode request,
spec review or artifact promotion replaces final Trading Core checks. Treat
these as configuration/authority invariants for G1, not 18 implemented or
verified workflows; full operational combinations are a later acceptance gate.

## Deltas Requiring Separate Approval

| Gate | Status | Proposed decision and constraints |
| --- | --- | --- |
| Before G1 | **PROPOSED** | Extend the canonical semantic path with a versioned computational spec, provenance, unresolved fields and typed data requirements. Reuse M1 goal and R1/R2 review/evidence where applicable. Preserve the existing rule path, use one semantic authority and do not introduce retries by default. Ratify the three axes before persistence changes. |
| Before G2 generated execution | **PENDING** | Choose enforceable OS/VM isolation: separate identity, no broker or provider secrets/network, read-only pinned data, pinned toolchain/dependencies, bounded resources and diagnostics. Establish independent correctness checks and immutable spec/source/data/toolchain/report provenance. Promotion is explicit, version-specific and limited to read-only computation. LLM calls and repair must be bounded and measured; no LLM in the signal loop. |
| Before any G3 Tester run | **PENDING** | Approve Windows research isolation and provenance before G3, not only before G4. Separate terminal/profile from the authorized bridge, record source/binary/toolchain/data/config/report identity, and verify coverage and trading costs. Recorded 57/58 math parity is neither resolved parity nor evidence of historical fills. |
| Before G5 signal admission | **PENDING** | Choose isolated Python with verified parity or isolated signal-only MQL5 on evidence. Trusted ingestion must attest runtime and artifact identity and bind exact spec/revision/hash, scope, symbol/timeframe, snapshot/window and closed-bar time. Reject invalid, stale, out-of-order and replayed signals; maintain durable dedup/checkpoint state across restart. Worker has no Candidate write, account authority or broker access. |
| Before G6 authority integration or G7 adaptation | **PENDING** | Define artifact-to-strategy binding and reapproval, approved tunables, rollback and revocation. Reuse existing Candidate, confirmation, mandate, pre-submit and reconciliation; no second execution engine. Research selection needs its own budget, out-of-sample evidence and a no-trade outcome. Broker DEMO mutation requires separate approval. |

The current [strategy identity](../../src/services/trading/reasoning/strategy_evidence.py)
hash includes mode, confirmation, account scope, strategy rules/parameters and
trading scope when present. Independence of the axes is semantic, not permission
to change the hash contract. Preserve existing identities and journals.
If code, rules, or other bound material changes, require new artifact approval
and rebind trading authority where the strategy binding changes; never inherit
the previous mandate. Until an approved policy proves an adaptation preserves
the binding, treat the change as a proposed revision. Rollback or revocation
blocks new signals and Candidates; it does not authorize position closure,
revive a mandate or permit automatic retry of `RESULT_UNKNOWN`.

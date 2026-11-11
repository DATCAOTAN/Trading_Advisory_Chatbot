# B2 - STATIC_ONLY - BLOCKED
HEAD b9e7d83b3ed5046fa02effba1508ceb69f505fdd
Refs: H=TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md sections149-151; R=docs/operations/native_math_isolation.md; W=docs/operations/native_math_offline.wsb; P=src/services/trading/research/tester_parity.py.
Matrix:
VERIFIED_EVIDENCE | W: network/clipboard disabled, one RO input, no autorun. Input/manifest/package/source hashes match (H151 staging path); 11 allowlisted files. P:116 vectors+30 probes, native_status=NOT_VERIFIED.
REPORTED | H150-151/R: prior elevated audit had zero errors, Sandbox disabled; verdict INCONCLUSIVE. Not current host proof.
MISSING | Egress/provisioning approval; bundle admission in P/R; binary/toolchain/output pins.
UNKNOWN | Host/guest resources, secrets/RO/offline enforcement, toolchain startup, native parity.
BLOCKER: whole-environment isolation/output provenance not established.
DECISION: approve/reject R's provisioning + dedicated six-file outbox scope; guest-write/disk risk requires explicit consent.
GATE: STOP on any gap. Approval -> clean offline guest/no broker secrets/RO pinned input + resource/timeout evidence -> compatible toolchain -> one consumed Model3 MathOnly=true/SimulateOrders=false session -> pinned binary/log/CSV receipts;116+30 pinned comparisons. No prior result reuse.
NEXT PROMPT: authorize local read-only bundle admission in P, reusing comparators; outside Bridge edits; pin/schema/size/reparse tests with fixtures only. No native run.

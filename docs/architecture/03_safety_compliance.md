# Safety and Compliance

The system is an advisory and review platform. The core safety invariant is `execution_allowed=false`.

## Safety Layers

- ResponseGate: blocks or degrades answers when evidence is insufficient.
- Controlled Failure Gate: prevents fabricated source-backed confidence.
- Agent-to-Answer Compliance Gate: checks that final answer content stays within advisory boundaries.
- ClaimEvidenceValidator: checks that claims are supported by EvidenceBundle content.
- AnswerCompleteness: checks required structure, source references, and final artifact identity.
- SystemHardeningService: detects unsafe persisted or diagnostic artifacts.

## Explicit Prohibitions

The system must not generate:

- BUY/SELL command generation.
- Entry price instructions.
- Stop-loss instructions.
- Take-profit instructions.
- Lot size instructions.
- Position size instructions.
- Account-risk percent instructions.
- MT5 order execution.
- Broker order payloads.
- Account-data-based recommendations.

The system can analyze market context, risk themes, thesis consistency, and evidence-backed scenarios, but it does not provide executable trade instructions.

## Compliance Relationship

Compliance validation records issues; it does not rewrite source evidence or weaken answer completeness. If a final answer violates the boundary, the correct result is WARN or FAIL, not silent cleanup into a high-quality record.

## Runtime Boundary

Evaluation, benchmark, dashboard, analytics, human review, and hardening layers must preserve `execution_allowed=false`. They may flag unsafe source records or annotations, but they must not turn unsafe text into normal safe output.

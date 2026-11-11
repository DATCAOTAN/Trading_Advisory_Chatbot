# Open-Ended AI Computational & Trading Platform

**Status:** The documentation layout is approved. The platform design below is
**PROPOSED**; no milestone, runtime permission, or change to the locked target
is approved by this document.

## Objective

Preserve an unfamiliar computational request in the canonical semantic flow,
then develop and independently verify an algorithm against trusted data.
The first slice is a new Python indicator running in isolation against a pinned
historical MT5 window, with read-only output. Later slices may admit signals from
approved artifacts into the existing Draft/Candidate flow. Generated code never
gets broker access or trading authority; the existing Trading Core owns execution.

## Read Only What the Sprint Needs

1. Start with [AGENTS.md](../../AGENTS.md), current local Git state, and the
   relevant latest [handoff](../../TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md)
   and [changelog](../engineering/SPRINT_CHANGELOG.md) sections.
2. Use the table to open the actual owner and focused tests. Use the
   [project map](../PROJECT_CONTEXT_FOR_AI.md) only if ownership is unclear.
   Source, tests and Git establish what exists; old reports do not establish
   current runtime behavior.
3. Read relevant sections of the [locked target](../architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md)
   and [decision register](DECISIONS.md) when the task crosses those contracts.
   Use the [local runbook](../operations/local_runbook.md) only for operational
   work. Do not load the whole blueprint, audit, CSVs or sprint prompts by default.
   For G0, a separately approved brief and the three existing code paths below suffice.

## Proposed Milestones and Existing Owners

Tests below are starting points, not evidence that the proposed features exist.
G0 closes fidelity defects before new signal integration. G1 precedes G2/G4;
G3 can proceed separately after its own approval and isolation gate, and must
pass before G4. G5 needs verification for the selected backend, not two runtimes
by default. G6, G7 and G8 follow in order. M2 Autonomous Reliability is a
separate existing milestone with recorded offline evidence, not a new G sprint.

| Milestone | Deliverable | Existing owner | Relevant tests |
| --- | --- | --- | --- |
| G0 | Conditional entry, explicit SL/TP/risk and requested indicator fidelity | [Strategy evidence](../../src/services/trading/reasoning/strategy_evidence.py), [Draft](../../src/services/trading/proposal/editable_trade_draft.py), [technical snapshot](../../src/services/decision_context.py) | [Semantic cutover](../../scripts/test_trading_semantic_cutover.py), [Draft/Candidate](../../scripts/test_editable_trade_draft_candidate_lifecycle.py), [context acquisition](../../scripts/test_context_acquisition_executor.py) |
| G1 | Typed spec, data requirements and independent configuration axes | [Semantic schema](../../src/services/semantic/structured_semantics.py), [resolver](../../src/services/semantic/resolved_semantics.py), [QueryPlan](../../src/services/semantic/query_plan.py) | [Semantic interpreter](../../scripts/test_structured_semantic_interpreter.py), [structured planning](../../scripts/test_structured_semantic_query_plan.py) |
| G2 | One new Python indicator, isolated, verified and read-only | [LLM transport](../../src/core/llm_client.py), [historical loader](../../src/services/trading/research/historical_dataset.py), [R2 verifier](../../src/services/trading/research/evidence_verification.py) | [Historical dataset](../../scripts/test_historical_research_dataset.py), [evidence verification](../../scripts/test_research_evidence_verification.py) |
| G3 | Native Tester parity, coverage and historical pilot | [Research EA](../../tools/mt5_bridge/research/StrategyParity.mq5), [parity helper](../../src/services/trading/research/tester_parity.py) | [Parity](../../scripts/test_mt5_tester_parity.py), [session coverage](../../scripts/test_historical_session_coverage.py) |
| G4 | Bounded MQL5 generation, compile/repair and verified Tester report | [LLM transport](../../src/core/llm_client.py), [research EA](../../tools/mt5_bridge/research/StrategyParity.mq5); no production build worker yet | [Parity](../../scripts/test_mt5_tester_parity.py), [research evidence](../../scripts/test_research_evidence_verification.py) |
| G5 | Artifact promotion and authenticated shadow signals with replay controls | [Completed-bar monitor](../../src/services/trading/decision/autonomous_candidate_monitor.py), [coordinator](../../src/services/trading/decision/autonomous_trading_coordinator.py), [input assembler](../../src/services/trading/decision/operator_candidate_generation.py) | [Monitor](../../scripts/test_autonomous_candidate_monitor.py), [runtime recovery](../../scripts/test_autonomous_runtime_completion.py) |
| G6 | Strategy-Driven integration through existing Candidate and authority | [Candidate input](../../src/services/trading/decision/operator_candidate_generation.py), [authority](../../src/services/trading/execution/mt5_live_adapter_pre_submit/trading_authority.py), [pre-submit](../../src/services/trading/execution/mt5_live_adapter_pre_submit/approval_pre_submit.py) | [Draft/Candidate](../../scripts/test_editable_trade_draft_candidate_lifecycle.py), [mandate](../../scripts/test_standing_trading_mandate_authority.py), [controlled execution](../../scripts/test_mt5_controlled_execution_integration.py) |
| G7 | Goal-Driven research, reviewed revisions and bounded adaptation | [QueryPlan](../../src/services/semantic/query_plan.py), [R1 proposal](../../src/services/trading/research/proposal.py), [R2 verifier](../../src/services/trading/research/evidence_verification.py) | [Goal-only brief](../../scripts/test_goal_only_research_brief.py), [proposal revisions](../../scripts/test_research_proposal.py), [evidence verification](../../scripts/test_research_evidence_verification.py) |
| G8 | End-to-end acceptance, recovery, rollback and measured cost | [Runtime owner](../../src/services/trading/decision/autonomous_runtime.py), [bridge reconciliation](../../tools/mt5_bridge/reconciliation.py), [runbook](../operations/local_runbook.md) | [Product regression](../../scripts/test_60_case_product_acceptance.py), [reconciliation](../../scripts/test_mt5_reconciliation_failure_recovery.py) |

**Status vocabulary:** `PROPOSED` is a design option; `APPROVED` authorizes only
the recorded scope; `IMPLEMENTED` requires source evidence; `VERIFIED` requires
recorded checks with a stated boundary (offline, read-only DEMO, or separately
authorized operational acceptance). None of these labels alone grants a trade.

## Tool Notes

- Ponytail 5.3.3 was available in full mode during review; use its focused
  minimal-change review, not a repeated repo-wide audit.
- RTK 0.42.4 worked manually; no hook was detected. Use `rtk proxy` or raw
  commands when output detail matters. Keep the Windows pytest invocation in
  [AGENTS.md](../../AGENTS.md); shell compression is not LLM billing evidence.
- Codebase-memory 0.9.0 responded. The index named
  `D-GitHub-Trading_Advisory_Chatbot` found sampled local R1/R2/M2 symbols that
  the other same-HEAD index missed. Use it for discovery, verify source directly,
  and fall back to targeted search when stale. Auto-refresh and complete
  exclusions were not verified. Do not reindex or change hooks/MCP config as
  part of ordinary sprint preflight.

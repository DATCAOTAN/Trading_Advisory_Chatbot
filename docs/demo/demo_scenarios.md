# Demo Scenarios

## Static Book Concept

Expected:

- Intent family is static/book.
- Source refs point to book/static material.
- Market agents are not required for the static task.
- No executable trading output.
- `execution_allowed=false`.

## Macro Report Summary

Expected:

- Macro/report source refs are used.
- The answer summarizes evidence without order instructions.
- No account data, broker data, or MT5 data.

## Macro Market Impact

Expected:

- Market/macro task scope is present.
- MarketContextAgent may be used as analytical context.
- Strategy/Risk/Consistency agents remain analytical only when used.
- No executable trading output.

## Market State Analysis

Expected:

- MarketContextAgent and related analytical agents can contribute bounded context.
- Compliance gate remains active.
- FinalAnswerArtifact hash is preserved by downstream evaluation.

## Multi-Intent Macro Plus Static

Expected:

- Task 1 is market/macro.
- Task 2 is book/static.
- Task 2 has no inherited market symbol, market source refs, or market agents.
- Static task is not failed because backtest or paper evaluation is not applicable.

## Controlled Failure

Expected:

- Missing evidence is reported safely.
- No fabricated source is created.
- Unsupported confidence is avoided.

## Safety Boundary

Expected:

- No BUY/SELL command.
- No entry price, stop-loss, take-profit, lot size, position size, or account-risk percent instruction.
- No MT5 or broker order action.
- `execution_allowed=false`.

## Dashboard / Review / Analytics

Expected:

- Registry records are inspectable.
- Source refs and hashes are visible.
- Human annotation is task-scoped.
- Analytics metrics are deterministic and review-oriented.

## Benchmark / Hardening

Expected:

- Golden benchmark fixture mode runs without live providers.
- System health detects missing/corrupt/unsafe artifacts without deleting data.

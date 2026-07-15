# Limitations and Boundaries

## Current Limitations

- No ExecutionAgent.
- No MT5 execution.
- No broker API.
- No account data.
- No position sizing.
- No live paper trading bot.
- No PnL or win-rate optimization.
- No guarantee of market correctness.
- Evaluation uses deterministic/local fixtures unless real artifacts are supplied.
- Dashboard persistence is local JSONL/JSON.
- Human reviewer IDs have no authentication in V1.
- Golden benchmark coverage is useful but not exhaustive.
- System hardening is non-destructive by default and does not auto-repair all corrupted stores.

## Boundaries

The system is an evidence-grounded advisory and evaluation governance platform. It is not a live trading bot, trading approval workflow, execution platform, broker connector, MT5 connector, or financial performance guarantee.

The expected invariant is `execution_allowed=false`.

## Future Work

- Stronger benchmark coverage.
- Richer demo scenario pack.
- Documentation polish as implementation evolves.
- Config and deployment cleanup.
- Optional dashboard screenshot automation.
- Optional authenticated reviewer workflow.
- Optional cloud deployment later.

Live execution is not an immediate next step for this system identity. Any future execution-related work would require a separate safety, legal, account, broker, and compliance design.

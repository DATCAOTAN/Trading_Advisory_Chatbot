Baseline: paper-trading-evaluation-design-v1

Validated:
- PaperTradingEvaluationRecord PASS
- Consumes JournalReviewRecord
- Consumes BacktestEvaluationRecord
- Uses explicit simulated observation timeline
- Single-intent market evaluation PASS
- Multi-intent task-scoped evaluation PASS
- Static/book not_applicable PASS
- No trade simulation
- No PnL / win-rate optimization
- No entry/SL/TP/lot/account-risk
- No MT5/broker/account data
- No provider/retrieval/LLM calls
- execution_allowed=false
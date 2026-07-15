Baseline: backtest-evaluation-design-v1

Validated:
- BacktestEvaluationRecord PASS
- Consumes JournalReviewRecord
- Uses supplied historical observation windows
- Single-intent market evaluation PASS
- Multi-intent task-scoped evaluation PASS
- Static/book not_applicable PASS
- No trade simulation
- No PnL / win-rate optimization
- No entry/SL/TP/lot/account-risk
- No MT5/order execution
- No provider/retrieval/LLM calls
- execution_allowed=false
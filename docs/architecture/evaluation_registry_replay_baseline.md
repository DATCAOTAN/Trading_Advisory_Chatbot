Baseline: evaluation-registry-replay-v1

Validated:
- EvaluationRegistry PASS
- ReplayHarness PASS
- ReviewDataset export PASS
- Registers JournalReviewRecord
- Registers BacktestEvaluationRecord
- Registers PaperTradingEvaluationRecord
- Task-scoped indexing PASS
- Multi-intent isolation PASS
- Static/book isolation PASS
- Full-chain replay PASS
- No provider/retrieval/MT5/account calls
- No ExecutionAgent
- No BUY/SELL command
- No entry/SL/TP/lot/account-risk output
- execution_allowed=false
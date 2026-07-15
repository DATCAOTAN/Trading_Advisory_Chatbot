Baseline: evaluation-persistence-versioning-v1

Validated:
- EvaluationPersistenceStore PASS
- JSONL registry persistence PASS
- DatasetVersionManifest PASS
- Dashboard reload after restart PASS
- JSON/CSV export PASS
- Import validate-only PASS
- Unsafe import rejection PASS
- Multi-intent isolation preserved
- Static/book isolation preserved
- No raw prompts/full answers persisted
- No secrets/account/order/MT5 data persisted
- No provider/retrieval/MT5/account calls
- No ExecutionAgent
- No BUY/SELL command
- No entry/SL/TP/lot/account-risk output
- execution_allowed=false
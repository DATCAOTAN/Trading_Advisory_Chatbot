Baseline: human-review-workflow-v1

Validated:
- HumanReviewStore PASS
- Annotation JSONL storage PASS
- ReviewWorkflowState PASS
- Reason code taxonomy PASS
- Locking PASS
- Review history PASS
- Annotated dataset versioning PASS
- Annotated JSON/CSV export PASS
- Import validate-only PASS
- Unsafe annotation redaction PASS
- Multi-intent isolation preserved
- Static/book isolation preserved
- No raw prompts/full answers persisted
- No secrets/account/order/MT5 data persisted
- No provider/retrieval/MT5/account calls
- No ExecutionAgent
- No BUY/SELL command
- No entry/SL/TP/lot/account-risk output
- execution_allowed=false
Baseline: journal-review-agent-v1

Validated:
- JournalReviewAgent PASS
- Stores task-scoped JournalReviewRecord in runtime_artifacts
- Records final answer hash
- Records AgentAnswerCompliance result
- Records AnswerCompleteness result
- Records MemoryQualityPolicy action
- Preserves final answer text
- Does not create EvidenceItem
- Does not mutate EvidenceBundle
- Does not override memory policy
- Static/book no-agent path PASS
- Multi-intent task reviews PASS
- Safety/redaction checks PASS
- No ExecutionAgent
- No BUY/SELL command
- No entry/SL/TP/lot-size/account-risk output
- No MT5/order execution
- execution_allowed=false
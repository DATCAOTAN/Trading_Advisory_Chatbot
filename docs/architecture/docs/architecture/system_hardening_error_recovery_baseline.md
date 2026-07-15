Baseline: system-hardening-error-recovery-v1

Validated:
- SystemHardeningService PASS
- IntegrityReport PASS
- RecoveryPlan PASS
- SafeErrorEnvelope PASS
- QuarantineRecord PASS
- DiagnosticReport PASS
- Persistence hardening PASS
- Dashboard health/recovery section PASS
- Benchmark invalid-file handling PASS
- Corrupt JSONL detection/quarantine PASS
- Unsafe field/secret/account/MT5/trading-field detection PASS
- Static/book NOT_APPLICABLE behavior preserved
- Multi-intent leakage validation preserved
- No valid artifact mutation
- No final answer mutation
- No provider/retrieval/MT5/account calls
- No ExecutionAgent
- No BUY/SELL command
- No entry/SL/TP/lot/account-risk output
- execution_allowed=false
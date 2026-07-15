# Benchmark and Hardening

Golden Benchmark and System Hardening are defensive layers above existing artifacts. They validate behavior and integrity without changing answer generation, retrieval, agent routing, or compliance semantics.

## Golden Benchmark

GoldenBenchmarkCase defines canonical scenarios, expected task decomposition, source behavior, agent activation, safety expectations, evaluation artifacts, persistence behavior, review behavior, and analytics behavior.

GoldenBenchmarkRunner runs deterministic fixture validation. It does not call providers, retrieval, market APIs, MT5, broker APIs, or account services.

GoldenBenchmarkReport summarizes total cases, pass/warn/fail/skipped counts, pass rate, case-family coverage, safety summary, and regression summary.

## Canonical Case Families

- static_book
- macro_report
- macro_market_impact
- market_state
- multi_intent
- controlled_failure
- safety_boundary
- dashboard_evaluation
- persistence_review
- analytics_quality

Deliberate failure fixtures are expected to fail clearly when task leakage, missing source refs, forbidden source refs, unsafe output, or `execution_allowed=true` is present.

## System Hardening

SystemHardeningService validates runtime, persistence, benchmark, dashboard, replay, analytics, and human review artifacts.

Important structures:

- IntegrityReport: status, issue counts, corrupt record counts, unsafe artifact counts, warnings.
- RecoveryPlan: non-destructive recovery actions by default.
- QuarantineRecord: preserves original hash and stores a redacted excerpt of corrupt or unsafe records.
- SafeErrorEnvelope: safe wrapper for provider or streaming error artifacts.
- DiagnosticReport: safe export for integrity and recovery details.

## Hardening Behavior

- Missing optional files produce WARN and safe empty states.
- Empty stores are handled safely.
- Corrupt JSONL lines are detected and can be quarantined.
- Invalid manifests are FAIL and are not overwritten automatically.
- Unsafe fields and secret-like values are flagged.
- Dashboard empty states and partial chains should not crash.
- Recovery plans do not delete or compact data by default.

The hardening layer never upgrades unsafe or invalid data to high quality.

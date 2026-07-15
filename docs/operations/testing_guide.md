# Testing Guide

Use the project virtual environment explicitly. Do not run tests with a bare test runner command.

## Documentation Tests

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_documentation_integrity.py -q
```

## Golden Benchmark and Hardening

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_golden_evaluation_benchmark.py scripts\test_system_hardening_error_recovery.py -q
```

## Analytics / Review / Persistence / Dashboard / Registry

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_review_analytics_quality_metrics.py scripts\test_human_review_workflow.py scripts\test_evaluation_persistence_versioning.py scripts\test_evaluation_dashboard.py scripts\test_evaluation_registry_replay.py -q
```

## Evaluation Suites

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_journal_review_agent.py scripts\test_backtest_evaluation.py scripts\test_paper_trading_evaluation.py scripts\test_agent_answer_compliance.py -q
```

## Agent Suites

```powershell
.\venv\Scripts\python.exe -m pytest scripts\test_agent_runtime.py scripts\test_market_context_agent.py scripts\test_strategy_agent.py scripts\test_risk_agent.py scripts\test_strategy_risk_consistency.py -q
```

## Compile and Compose Checks

```powershell
.\venv\Scripts\python.exe -m compileall -q src scripts
docker-compose config
```

## Full Regression

```powershell
.\venv\Scripts\python.exe -m pytest scripts -q
```

## Golden Benchmark CLI

```powershell
.\venv\Scripts\python.exe scripts\run_golden_benchmark.py --cases data\evaluations\benchmarks\golden_cases.v1.json --out data\evaluations\benchmarks\reports\latest.json
```

Benchmark fixture mode does not call providers, retrieval, market APIs, MT5, broker APIs, or account services.

# Offline Autonomous Candidate Acceptance

This developer harness exercises the production proposal normalization, candidate construction, validation, and classification logic with deterministic offline fixtures. It never uses live data and is not evidence of live-market acceptance.

## Safety

- Every fixture uses `operating_mode=offline_fixture` and `offline_fixture:` source references.
- The fixed fixture timestamp drives freshness and expiry; wall-clock time is not substituted.
- Protected handoff and pending mapping reject offline provenance with `OFFLINE_PROVENANCE_NOT_EXECUTABLE`.
- External LLM, bridge, export, submission, reconciliation mutation, and broker-mutation counts remain zero.
- The harness fails closed if any execution, pending-submission, autonomous-policy, or position-management permission is enabled.

## Run

From the repository root:

```powershell
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py fresh_no_action
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py fresh_human_review
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py fresh_market
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py fresh_pending
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py stale_market
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py account_context_mismatch
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py lifecycle_discrepancy
.\venv\Scripts\python.exe scripts\run_offline_candidate_acceptance.py malformed_proposal
```

A fixture file may be supplied instead of a built-in name. It must exactly contain the schema version, built-in scenario name, timezone-aware reference timestamp, `offline_fixture` provenance, and true `non_exportable`/`non_submittable` flags.

Offline MARKET and PENDING outcomes are candidate-policy test results only. They are not broker-ready and cannot be exported or submitted. Live acceptance remains `DEFERRED_UNTIL_FRESH_XAUUSDM_MARKET_DATA`.
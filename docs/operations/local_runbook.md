# Local Runbook

## Prerequisites

- Python virtual environment for the project.
- Docker and Docker Compose.
- A local `.env` file based on `.env.example`.
- Optional provider credentials for normal app use. Tests and deterministic benchmarks do not require live provider calls.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with only the provider settings needed for local experimentation. Do not commit secrets.

## Start Services

1. Open the MT5 terminal on the Windows host and log in manually to the intended demo/test account.
2. In a separate PowerShell window at the repository root, start the authenticated host bridge:

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.server
```

The bridge loads the local ignored `.env`. `MT5_BRIDGE_EXECUTION_TOKEN` must match the Docker caller token for authenticated lifecycle, reconciliation, and controlled endpoints. Never print or commit it.

3. Start the Docker services:

```powershell
docker-compose up -d
```

Open:

```text
http://localhost:8501
```

Check health without enabling execution:

```powershell
Invoke-WebRequest http://127.0.0.1:8765/health
Invoke-WebRequest http://localhost:8501/_stcore/health
docker-compose ps
```

## Restart After Python Changes

```powershell
docker-compose restart app
```

Do not rebuild unless Dockerfile or dependency files changed.

## Trading Runtime

The dashboard exposes the existing Review Card and one service-owned Trading Authority and Runtime Supervisor section. Its modes are:

- `advisory_only`: analysis only; no execution authority.
- `human_confirmed_live`: every controlled action requires its protected human confirmation.
- `autonomous_live`: each candidate requires an exact, current Standing Trading Mandate authorization plus every policy, account, lifecycle, reconciliation, pre-submit, idempotency, capability, and kill-switch check.

Standing mandates are demo-account-bound, scoped, expiring, revocable, and integrity-protected. Revocation blocks subsequent authorization. Real accounts remain hard-blocked. `RESULT_UNKNOWN` prohibits retry until authoritative reconciliation resolves it or requires human review.

Execution, autonomous eligibility, controlled management, submission, and `order_send` remain disabled and hard-blocked by default. Operational enablement is a separate demo-account acceptance procedure, not a startup requirement.

### Read-Only DEMO Recovery Gate

1. Keep existing fail-closed permissions and do not click Start. Check `docker-compose ps`, Streamlit health, bridge `GET /health` and redacted `GET /account`. Verify DEMO and compare account binding inside the existing authority reader; only publish match/mismatch. Inspect process state separately from monitor history. If ownership is UNKNOWN, verify host/container worker inventory before considering any operator action. Do not delete the launch guard, clear diagnostics, or manually start another watch process.
2. Compare Windows and container UTC against an approved trusted clock, then compare bridge `GET /tick` and completed `GET /ohlcv` timestamps with validation UTC. Use `GET /symbols` and tick metadata to verify exact broker mapping and symbol capabilities. Missing, stale, future or mismatched evidence blocks the gate; do not change tolerances.
3. Use the existing read-only PositionReadModel to inspect positions and active orders. It reads the authenticated lifecycle snapshot and protected journals without persisting a reconciliation result. Inspect journal integrity and reconciliation state through read methods only; do not call `/execution/reconcile` as a read-only check, since it may persist changes. Keep account, broker IDs and raw payloads out of logs.
4. If the worker exited with RESULT_UNKNOWN, keep it stopped until the existing protected reconciliation workflow establishes the outcome or requests human resolution. A restart is not recovery evidence and must not be used to retry an order. Unavailable access or unresolved state is a blocked gate, not a reason to enable a permission.

### Future Unattended DEMO Soak

After a separate operator approval and successful read-only gate, record deployment identity and a supervised initial Start under one current bounded DEMO mandate. Observe completed-bar, process, authority, journal and broker-correlation health during authorized market-open and market-closed windows, a controlled disconnect/reconnect, and explicit stop/restart. Verify that expiry and revocation block new submissions and require fresh operator authority; do not extend a mandate automatically to span a window. Check a stable account fingerprint and position provenance, no duplicate submission, and matching protected journal and broker outcomes. Stop on unknown ownership, RESULT_UNKNOWN, mismatched account, unresolved exposure, or a failed safety check. Record the final process state and preserve protected evidence. A single confirmed DEMO trade or offline PASS is not soak evidence.

## Dashboard Usage

Open the Evaluation Dashboard tab to inspect registry entries, detail view, chain view, replay results, persistence, human review, analytics, safe exports, and System Health / Recovery diagnostics.

## Storage Paths

- `data/evaluations/registry/evaluation_registry.jsonl`
- `data/evaluations/versions/dataset_versions.json`
- `data/evaluations/reviews/`
- `data/evaluations/benchmarks/`
- `data/evaluations/quarantine/`
- `data/evaluations/diagnostics/`

These paths are for safe evaluation artifacts. They should not contain raw prompts, full final answers, secrets, account data, broker data, MT5 data, or order data.

Trading authority, candidate, pre-submit, execution, reconciliation, lifecycle, and supervisor journals live under the Git-ignored `data/trading/execution_journal/` tree. Public UI and general logs expose redacted status only; exact broker identifiers remain confined to protected execution/reconciliation records when required.

## Shutdown

1. Stop the Runtime Supervisor from Streamlit if it is running.
2. Stop Docker services:

```powershell
docker-compose down
```

3. Press `Ctrl+C` in the host-bridge PowerShell window and wait for it to close.
4. Close the MT5 terminal when no further read-only or controlled operation is required.

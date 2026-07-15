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

```powershell
docker-compose up -d
```

Open:

```text
http://localhost:8501
```

## Restart After Python Changes

```powershell
docker-compose restart app
```

Do not rebuild unless Dockerfile or dependency files changed.

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

# Data Storage and Cleanup

Evaluation governance uses local storage for safe review artifacts.

This page also classifies the trading workspace. A large or old file is not
automatically disposable. See the [project map](../PROJECT_CONTEXT_FOR_AI.md)
for the current production owners.

## Workspace Retention

| Path | Treatment |
| --- | --- |
| `src/`, `tools/`, `scripts/`, `src/metadata/` | Source, contracts, tests and operator CLIs. Check imports, dynamic references, fixtures and exports before deletion. |
| `docs/architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md` | Locked product target; preserve. |
| Handoff, changelog, numbered architecture/demo notes | Current checkpoints and historical evidence; retain and distinguish current from historical claims. |
| `data/knowledge_repository/`, `data/knowledge_compiled/` | Knowledge sources, manifests and method/policy cards; preserve. |
| `data/qdrant_db/`, `data/knowledge_catalog/`, MongoDB/Redis volumes | Databases and durable/local state; no blanket cleanup. |
| `data/trading/execution_journal/`, `data/trading/protected_requests/` | Protected authority, idempotency, execution and recovery evidence; never delete to unblock trading. |
| `data/cache/embedding_cache.sqlite` | Reusable embedding cache, currently Git-tracked; preserve user changes and avoid paid re-embedding. |
| `.env`, local API-key files, `.agents/`, virtual environments | Local configuration, secrets, agent instructions and installed dependencies; preserve. |
| `Trading_Advisory_Chatbot.zip`, `logs/`, `tmp_debug_mt5_dry/` | Backup/diagnostics, potentially private; retain until a separate retention review. |
| `__pycache__/`, `*.pyc`, `.pytest_cache/` | Regenerable caches; safe to remove when no test process is using them. |

The 2026-11-01 housekeeping removed only the unreferenced root `diff.txt`
patch dump, duplicate `cmd_docker` command notes, and empty `log_terminal`.
Supported commands remain in the local runbook and Docker workflow. It also
removed regenerable code/test caches and the empty `tmp_preflight_diag/`.
No databases, protected journal records, backups, credentials, or dependencies
were deleted.

The follow-up source review removed 20 unreferenced exception-only modules,
the unused `src/services/trading/execution/receipt.py` alias, and two old root
experiments (`run_manual_test.py`, `test_reranker_manual.py`). Their collection
exclusions were removed from root `conftest.py`; hermetic provider guards remain.
Exception modules still exported by their packages were retained. Canonical
receipt models, supported manual MT5 CLIs, and existing regression cases remain.
The full default test collection passed with 3,771 tests and 156 subtests after
this deletion, using disabled execution defaults in the test process.
One legacy simulation test was also changed to inject a temporary journal after
the full suite exposed a local simulated-receipt append. The original local
journal was not truncated or rewritten; its one extra non-executed receipt was
retained. Later simulator verification left that journal unchanged.

## Docker Build Context

Git ignore rules do not control `COPY . .`. The `.dockerignore` additionally
excludes host key files, `.agents/`, the local ZIP, diagnostic folders,
`data/trading/`, `data/cache/`, and `data/knowledge_catalog/`.
Compose supplies local runtime data through the existing `./data:/app/data`
mount and supplies `.env` separately. These exclusions affect future builds;
they do not remove content from an already-built image. Never publish an old
image without reviewing its contents.

## Paths

- `data/evaluations/registry`: JSONL registry entries.
- `data/evaluations/versions`: dataset version manifests.
- `data/evaluations/reviews`: human review annotations, workflow states, annotated dataset versions, and exports.
- `data/evaluations/benchmarks`: golden cases and reports.
- `data/evaluations/quarantine`: quarantined corrupt or unsafe record excerpts with original hashes.
- `data/evaluations/diagnostics`: safe diagnostic reports.

## What Should Not Be Stored

These stores should not contain raw prompts, hidden/system prompts, full final answers, full raw documents, secrets, account data, broker data, MT5 data, order data, or executable trading instruction details.

## Safe Cleanup

For local experiments, prefer archiving or moving generated evaluation exports and reports instead of deleting source stores. If cleanup is needed, inspect files first and keep a backup of registry and review data.

Do not delete Qdrant collections as part of evaluation cleanup.

Do not delete `.env` or secret-bearing files through documentation workflows.

Quarantine files preserve original hashes and safe excerpts. They can be reviewed separately from the source JSONL.

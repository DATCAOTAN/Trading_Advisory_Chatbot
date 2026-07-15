# Data Storage and Cleanup

Evaluation governance uses local storage for safe review artifacts.

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

# Knowledge Platform V3 Staging Verification

This guide verifies the V3 ingestion/search path in Docker or staging without changing the default chatbot runtime.

## Safety Defaults

- The Streamlit chatbot still defaults to legacy retrieval.
- `Config.USE_KNOWLEDGE_V3` must remain `False` by default.
- The verifier does not index, call Cohere, call Qdrant, or mutate the real catalog unless `--index` is passed.
- The verifier never uses `xauusd_knowledge_v2`.
- Real indexing uses the V3 path and collection configured by `VectorServiceV3`.

## Find The Docker Service Name

```bash
docker-compose ps
```

In this repo, the app service is currently named `app`.

## Start Docker

```bash
docker-compose up --build -d
```

## Fake Mode

Use this first. It does not require Qdrant, Cohere, or real PDFs.

```bash
docker-compose exec app python scripts/stage_v3_verify.py --fake
docker-compose exec app python scripts/stage_v3_verify.py --fake --adapter-smoke
```

## Dry Run A Real Repository PDF

This validates metadata, manifest, registry, and chunking without indexing.

```bash
docker-compose exec app python scripts/stage_v3_verify.py --pdf data/knowledge_repository/book/technical/indicators/author_slug/file.pdf --dry-run
```

You can also create a temporary sample file and manifest:

```bash
docker-compose exec app python scripts/stage_v3_verify.py --sample --dry-run
```

## Opt-In Real Indexing

Only run this when staging Qdrant/Cohere configuration is ready.

```bash
docker-compose exec app python scripts/stage_v3_verify.py --pdf data/knowledge_repository/book/technical/indicators/author_slug/file.pdf --index
```

Real indexing requires:

- `qdrant_client` installed.
- `COHERE_API_KEY` configured.
- A valid PDF path under `data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{author_slug}/{file.pdf}`.
- A sidecar `.manifest.yaml`.

## Expected Summary

The verifier prints individual checks and a final status:

```text
[PASS] default_config: USE_KNOWLEDGE_V3 is False; legacy chatbot remains default.
[SKIP] index: Indexing disabled by default. Pass --index to run real V3 indexing.

FINAL: SKIP
```

`SKIP` is acceptable when optional staging dependencies or explicit `--index` are absent. `FAIL` means a required safety or verification step failed.

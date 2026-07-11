# V3 Docker E2E Trial Runbook

This is a manual/staging E2E trial for Knowledge Platform V3 retrieval.

It verifies:

- V3 repository path and manifest handling.
- V3 ingestion through `kp_ingest.py`.
- `KnowledgeService` search behavior.
- `RetrievalAdapter` behavior through the experimental UI toggle.

It does not migrate production defaults to V3. The chatbot must still default to legacy retrieval with `USE_KNOWLEDGE_V3=False`.

## 1. Build And Start Docker

```bash
docker-compose up --build -d
```

Find the service name:

```bash
docker-compose ps
```

In this repo the app service is currently `app`, but use `docker-compose ps` as the source of truth.

Enter the container:

```bash
docker-compose exec <service> bash
```

Example:

```bash
docker-compose exec app bash
```

## 2. Verify Dependencies

Inside the container:

```bash
python -c "import qdrant_client, yaml, pandas, numpy; print('deps OK')"
```

For real indexing you also need:

- `COHERE_API_KEY` configured.
- Local Qdrant path/availability through the app configuration.
- A valid PDF that PyMuPDF can extract text from.

## 3. Prepare One Sample Document

The V3 repository path convention is:

```text
data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{author_slug}/{file.pdf}
```

Example:

```text
data/knowledge_repository/book/technical/indicators/john_murphy/sample.pdf
```

Create or copy one PDF into that path. Then create its sidecar manifest:

```bash
python scripts/kp_manifest.py init data/knowledge_repository/book/technical/indicators/john_murphy/sample.pdf
```

Open the generated `.manifest.yaml` and edit fields as needed:

- `title`
- `author`
- `publish_year`
- `publisher`
- `tags.strategies`
- `tags.assets`
- `tags.timeframe_focus`

Keep `lifecycle: ACTIVE` for the E2E trial.

## 4. Run A Dry Run

```bash
python scripts/kp_ingest.py dry-run data/knowledge_repository/book/technical/indicators/john_murphy/sample.pdf
```

Expected:

- Metadata resolves with a stable `doc_id`.
- Lifecycle is not `QUARANTINE`.
- OCR status is not `NEEDS_OCR`.
- Chunk count is greater than zero.
- No indexing occurs.

If dry-run returns `QUARANTINE`, `EMPTY_DOCUMENT`, `NEEDS_OCR`, or `FAILED`, stop and fix that issue before indexing.

## 5. Real Ingest

Only run this after dry-run passes and staging dependencies are ready:

```bash
python scripts/kp_ingest.py ingest-file data/knowledge_repository/book/technical/indicators/john_murphy/sample.pdf
```

Expected:

- Catalog lock is acquired.
- Vectors are upserted through `VectorServiceV3`.
- The document is indexed into the V3 collection `knowledge_current`.

Do not delete or recreate any Qdrant collection during this trial.

## 6. Search Smoke

You can run the staging verifier:

```bash
python scripts/stage_v3_verify.py --pdf data/knowledge_repository/book/technical/indicators/john_murphy/sample.pdf --index
```

This command performs an opt-in indexing/search smoke. It requires `qdrant_client` and `COHERE_API_KEY`.

Current limitation: there is no dedicated search-only CLI mode for an already indexed document. If the document is already indexed, use the UI test below or a controlled Python snippet through `KnowledgeService` in staging.

## 7. UI Trial

Open the app in the browser, usually:

```text
http://localhost:8501
```

Go to **Settings** and enable:

- `Use Knowledge Platform V3 (experimental)`
- `Fallback to legacy if V3 fails`

Ask queries with clear domain keywords:

```text
EMA indicator trend following là gì?
risk position sizing 2% rule là gì?
FOMC ảnh hưởng vàng như thế nào?
```

Verify:

- The app does not crash.
- The V3 experimental badge/warning appears.
- If V3 finds context, sources include V3 metadata/citation fields where visible.
- If V3 fails, the answer still works through legacy fallback.

## 8. Rollback

Turn off `Use Knowledge Platform V3 (experimental)` in Settings.

Restart the app if needed:

```bash
docker-compose restart <service>
```

Confirm legacy retrieval still works. Do not delete collections unless explicitly instructed.

## 9. Troubleshooting

Missing `qdrant_client`:

```bash
pip install qdrant-client
```

Missing `COHERE_API_KEY`:

```bash
echo $COHERE_API_KEY
```

`NEEDS_OCR`:

- The PDF text extraction quality is too low.
- Use an OCR-ready source or run OCR before ingestion.

`QUARANTINE`:

- Check the path convention.
- Check that `.manifest.yaml` exists next to the PDF.
- Check duplicate checksum warnings.

Duplicate checksum:

- The same content may already exist under another `doc_id`.
- Do not bypass duplicate detection for staging trials.

Empty `knowledge_current`:

- Confirm `ingest-file` succeeded.
- Confirm `COHERE_API_KEY` was available.
- Confirm the Qdrant local path is mounted/persistent inside Docker.

Domain inference falls back to legacy:

- Use explicit domain keywords such as `indicator`, `risk`, `position sizing`, `macro`, `FOMC`, or `CPI`.
- Ambiguous queries intentionally fall back to legacy when fallback is enabled.

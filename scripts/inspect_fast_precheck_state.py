import argparse
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config
from src.services.knowledge.catalog_manager import KnowledgeCatalog


def _prefix(value, length=12):
    text = str(value or "")
    return text[:length] if text else ""


def _format_bool(value):
    return "yes" if value else "no"


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect Knowledge V3 fast precheck catalog state.")
    parser.add_argument(
        "--catalog",
        default=str(Config.DATA_DIR / "knowledge_catalog" / "catalog.sqlite"),
        help="Path to Knowledge V3 catalog SQLite database.",
    )
    parser.add_argument("--missing-only", action="store_true", help="Show indexed docs missing fast precheck state.")
    parser.add_argument("--doc-id", default="", help="Filter by exact doc_id.")
    parser.add_argument("--path-contains", default="", help="Filter by source_path substring.")
    return parser.parse_args()


def main():
    args = parse_args()
    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        print(f"Catalog not found: {catalog_path}")
        return 1

    # Initializes/migrates lightweight columns before reading.
    KnowledgeCatalog(str(catalog_path))

    with sqlite3.connect(str(catalog_path)) as conn:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT
                doc_id,
                source_path,
                fast_precheck_fingerprint,
                fast_precheck_ingestion_fingerprint,
                last_successful_status,
                pending_retry,
                failed_stage,
                failure_category,
                chunk_count,
                chunks_count,
                vector_count,
                updated_at,
                last_precheck_at,
                last_validated_at,
                index_status
            FROM documents
            WHERE 1 = 1
        """
        params = []
        if args.doc_id:
            query += " AND doc_id = ?"
            params.append(args.doc_id)
        if args.path_contains:
            query += " AND source_path LIKE ?"
            params.append(f"%{args.path_contains}%")
        if args.missing_only:
            query += " AND index_status = 'INDEXED' AND (fast_precheck_fingerprint IS NULL OR fast_precheck_fingerprint = '')"
        query += " ORDER BY doc_id"
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]

    if not rows:
        print("No documents matched.")
        return 0

    headers = [
        "doc_id",
        "has_fast_precheck",
        "fast_fp",
        "paired_ingestion_fp",
        "last_successful_status",
        "pending_retry",
        "failed_stage",
        "chunk_count",
        "vector_count",
        "updated_at",
        "file_path",
    ]
    print("\t".join(headers))
    for row in rows:
        fast_fp = row.get("fast_precheck_fingerprint") or ""
        updated_at = row.get("last_validated_at") or row.get("last_precheck_at") or row.get("updated_at") or ""
        chunk_count = row.get("chunk_count")
        if chunk_count in (None, ""):
            chunk_count = row.get("chunks_count") or 0
        values = [
            row.get("doc_id") or "",
            _format_bool(bool(fast_fp)),
            _prefix(fast_fp),
            _prefix(row.get("fast_precheck_ingestion_fingerprint")),
            row.get("last_successful_status") or "",
            str(row.get("pending_retry") or 0),
            row.get("failed_stage") or "",
            str(chunk_count or 0),
            str(row.get("vector_count") or 0),
            str(updated_at),
            row.get("source_path") or "",
        ]
        print("\t".join(values))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

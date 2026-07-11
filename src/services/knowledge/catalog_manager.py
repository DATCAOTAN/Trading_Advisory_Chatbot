import os
import sqlite3
import json
import time
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

class KnowledgeCatalog:
    """
    Theo dõi metadata trạng thái bằng SQLite.
    Bảo đảm an toàn đa luồng bằng WAL và BEGIN IMMEDIATE (Job Lock).
    Tích hợp Heartbeat và Duplicate Detection qua Checksum (Content Fingerprint).
    """

    def __init__(self, db_path: str = "data/knowledge_catalog/catalog.sqlite"):
        self.db_path = db_path
        self._ensure_db_exists()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def _connect(self):
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_db_exists(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    source_path TEXT,
                    manifest_path TEXT,
                    checksum TEXT,
                    lifecycle TEXT,
                    index_status TEXT,
                    parser_version TEXT,
                    chunker_version TEXT,
                    embedding_model TEXT,
                    embedding_version TEXT,
                    index_version TEXT,
                    chunk_count INTEGER,
                    chunk_ids_hash TEXT,
                    ingestion_fingerprint TEXT,
                    ingestion_fingerprint_version TEXT,
                    ingestion_fingerprint_payload TEXT,
                    metadata_schema_version TEXT,
                    last_indexed_at TEXT,
                    error_message TEXT
                )
            ''')
            self._ensure_document_columns(cursor)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_hash_cache (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER,
                    mtime_ns INTEGER,
                    content_sha256 TEXT,
                    computed_at REAL
                )
            ''')
            # Thêm heartbeat_at và worker_id vào schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS index_jobs (
                    job_id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    job_status TEXT,
                    worker_id TEXT,
                    started_at REAL,
                    heartbeat_at REAL,
                    completed_at REAL,
                    log TEXT,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
                )
            ''')
            conn.commit()

    def _ensure_document_columns(self, cursor):
        cursor.execute("PRAGMA table_info(documents)")
        existing = {row[1] for row in cursor.fetchall()}
        columns = {
            "ingestion_fingerprint": "TEXT",
            "ingestion_fingerprint_version": "TEXT",
            "ingestion_fingerprint_payload": "TEXT",
            "metadata_schema_version": "TEXT",
            "failed_stage": "TEXT",
            "failure_category": "TEXT",
            "failure_reason": "TEXT",
            "retryable": "INTEGER",
            "attempts": "INTEGER",
            "last_attempt_at": "REAL",
            "next_retry_after": "REAL",
            "chunks_count": "INTEGER",
            "vectors_expected": "INTEGER",
            "parser_type": "TEXT",
            "embedding_provider": "TEXT",
            "fast_precheck_fingerprint": "TEXT",
            "fast_precheck_fingerprint_version": "TEXT",
            "fast_precheck_payload": "TEXT",
            "fast_precheck_ingestion_fingerprint": "TEXT",
            "fast_precheck_content_sha256": "TEXT",
            "fast_precheck_file_size": "INTEGER",
            "fast_precheck_mtime_ns": "INTEGER",
            "last_successful_status": "TEXT",
            "last_precheck_at": "REAL",
            "last_validated_at": "REAL",
            "vector_count": "INTEGER",
            "pending_retry": "INTEGER",
            "updated_at": "REAL",
        }
        for name, column_type in columns.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE documents ADD COLUMN {name} {column_type}")

    def find_doc_id_by_checksum(self, checksum: str) -> Optional[str]:
        """Duplicate Knowledge Detection: Quét content fingerprint."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id FROM documents WHERE checksum = ?", (checksum,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    def acquire_index_lock(self, doc_id: str, job_id: str, worker_id: str = "worker_1") -> bool:
        """
        Khóa tài liệu để index. Đảm bảo 1 doc_id chỉ có 1 job đang INDEXING.
        """
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT index_status FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            
            if row and row[0] == "INDEXING":
                conn.rollback()
                return False

            if row:
                cursor.execute("UPDATE documents SET index_status = 'INDEXING' WHERE doc_id = ?", (doc_id,))
            else:
                cursor.execute("INSERT INTO documents (doc_id, index_status) VALUES (?, 'INDEXING')", (doc_id,))
            
            now = time.time()
            cursor.execute('''
                INSERT INTO index_jobs (job_id, doc_id, job_status, worker_id, started_at, heartbeat_at) 
                VALUES (?, ?, 'RUNNING', ?, ?, ?)
            ''', (job_id, doc_id, worker_id, now, now))
            
            conn.commit()
            return True
        except sqlite3.Error:
            conn.rollback()
            return False
        finally:
            conn.close()

    def heartbeat(self, job_id: str):
        """Báo cáo quá trình Indexing vẫn đang sống."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE index_jobs SET heartbeat_at = ? WHERE job_id = ?", (time.time(), job_id))
            conn.commit()

    def get_stale_jobs(self, timeout_seconds: float = 300) -> List[Dict[str, Any]]:
        """Lấy danh sách các jobs INDEXING mà không có heartbeat trong timeout_seconds."""
        cutoff_time = time.time() - timeout_seconds
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM index_jobs 
                WHERE job_status = 'RUNNING' AND heartbeat_at < ?
            ''', (cutoff_time,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def release_index_lock(self, doc_id: str, job_id: str, status: str, error_msg: str = ""):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("UPDATE documents SET index_status = ?, error_message = ? WHERE doc_id = ?", 
                           (status, error_msg, doc_id))
            cursor.execute("UPDATE index_jobs SET job_status = ?, completed_at = ?, log = ? WHERE job_id = ?",
                           (status, time.time(), error_msg, job_id))
            conn.commit()

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def upsert_document(self, doc_id: str, data: Dict[str, Any]):
        with self._connect() as conn:
            cursor = conn.cursor()
            data = dict(data or {})
            data.setdefault("updated_at", time.time())
            columns = [
                "source_path", "manifest_path", "checksum", "lifecycle", 
                "index_status", "parser_version", "chunker_version", 
                "embedding_model", "embedding_version", "index_version", 
                "chunk_count", "chunk_ids_hash", "ingestion_fingerprint",
                "ingestion_fingerprint_version", "ingestion_fingerprint_payload",
                "metadata_schema_version", "last_indexed_at", "error_message",
                "failed_stage", "failure_category", "failure_reason", "retryable",
                "attempts", "last_attempt_at", "next_retry_after", "chunks_count",
                "vectors_expected", "parser_type", "embedding_provider",
                "fast_precheck_fingerprint", "fast_precheck_fingerprint_version",
                "fast_precheck_payload", "fast_precheck_ingestion_fingerprint",
                "fast_precheck_content_sha256", "fast_precheck_file_size",
                "fast_precheck_mtime_ns", "last_successful_status",
                "last_precheck_at", "last_validated_at", "vector_count",
                "pending_retry", "updated_at",
            ]
            updates, values, insert_cols, insert_vals, insert_placeholders = [], [], ["doc_id"], [doc_id], ["?"]
            
            for col in columns:
                if col in data:
                    updates.append(f"{col} = ?")
                    values.append(data[col])
                    insert_cols.append(col)
                    insert_vals.append(data[col])
                    insert_placeholders.append("?")
            
            if not updates:
                updates.append("doc_id = ?")
                values.append(doc_id)

            query = f'''
                INSERT INTO documents ({", ".join(insert_cols)})
                VALUES ({", ".join(insert_placeholders)})
                ON CONFLICT(doc_id) DO UPDATE SET
                {", ".join(updates)}
            '''
            cursor.execute(query, insert_vals + values)
            conn.commit()

    def get_retryable_documents(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM documents
                WHERE index_status IN ('PENDING_RETRY', 'FAILED_UPSERT')
                AND COALESCE(retryable, 0) = 1
                ORDER BY COALESCE(next_retry_after, 0), COALESCE(last_attempt_at, 0)
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_file_hash_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_hash_cache WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_file_hash_cache(
        self,
        file_path: str,
        file_size: int,
        mtime_ns: int,
        content_sha256: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO file_hash_cache
                (file_path, file_size, mtime_ns, content_sha256, computed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_path, file_size, mtime_ns, content_sha256, time.time()),
            )
            conn.commit()

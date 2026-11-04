import hashlib
import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


RETRYABLE_CATEGORIES = {"rate_limited", "timeout", "network_error", "provider_error"}
NON_RETRYABLE_CATEGORIES = {"missing_api_key", "invalid_api_key", "provider_bad_response"}


@dataclass
class EmbeddingErrorInfo:
    category: str
    retryable: bool
    error_type: str = ""
    error_tail: str = ""
    retry_after: Optional[float] = None


class EmbeddingProviderError(RuntimeError):
    def __init__(self, info: EmbeddingErrorInfo):
        super().__init__(info.error_tail or info.category)
        self.info = info


class EmbeddingCircuitOpen(RuntimeError):
    def __init__(self, info: EmbeddingErrorInfo, cooldown_seconds: int):
        super().__init__(info.error_tail or info.category)
        self.info = info
        self.cooldown_seconds = cooldown_seconds


def classify_embedding_error(exc: Any = None, missing_key: bool = False) -> EmbeddingErrorInfo:
    if missing_key:
        return EmbeddingErrorInfo("missing_api_key", False, "MissingApiKey", "COHERE_API_KEY is missing")

    text = str(exc or "")
    lower = text.lower()
    error_type = type(exc).__name__ if exc is not None else "UnknownError"
    retry_after = _extract_retry_after(exc, lower)

    if "invalid api key" in lower or "unauthorized" in lower or "401" in lower or "403" in lower:
        category = "invalid_api_key"
    elif "quota" in lower or "billing" in lower or "exceeded your current quota" in lower:
        category = "quota_exceeded"
    elif "429" in lower or "rate limit" in lower or "rate_limited" in lower:
        category = "rate_limited"
    elif "timeout" in lower or error_type.lower() in {"timeout", "timeouterror"}:
        category = "timeout"
    elif any(token in lower for token in ("connection", "network", "dns", "temporarily unavailable", "connection reset")):
        category = "network_error"
    elif any(token in lower for token in ("bad response", "malformed", "embeddings", "dimension")):
        category = "provider_bad_response"
    elif exc is not None:
        category = "provider_error"
    else:
        category = "unknown_error"

    retryable = category in RETRYABLE_CATEGORIES
    if category == "quota_exceeded":
        retryable = True
    if category == "unknown_error":
        retryable = False
    if category in NON_RETRYABLE_CATEGORIES:
        retryable = False

    return EmbeddingErrorInfo(
        category=category,
        retryable=retryable,
        error_type=error_type,
        error_tail=_tail(text),
        retry_after=retry_after,
    )


def compute_backoff_seconds(
    retry_index: int,
    base_seconds: int,
    max_seconds: int,
    retry_after: Optional[float] = None,
    jitter: bool = True,
) -> float:
    if retry_after is not None and retry_after > 0:
        return min(float(max_seconds), float(retry_after))
    wait = min(float(max_seconds), float(base_seconds) * (2 ** max(0, retry_index - 1)))
    if jitter:
        wait = wait * random.uniform(0.8, 1.2)
    return round(wait, 2)


class EmbeddingCache:
    def __init__(
        self,
        path: str,
        enabled: bool = True,
        normalization_version: str = "v1",
    ):
        self.path = path
        self.enabled = enabled
        self.normalization_version = normalization_version
        if self.enabled:
            self._ensure()

    def get_many(
        self,
        provider: str,
        model: str,
        input_type: str,
        texts: List[str],
    ) -> tuple[List[Optional[List[float]]], int, int]:
        if not self.enabled or not texts:
            return [None for _ in texts], 0, len(texts)
        keys = [self.cache_key(provider, model, input_type, text) for text in texts]
        vectors: List[Optional[List[float]]] = [None for _ in texts]
        hits = 0
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            for index, key in enumerate(keys):
                cursor.execute("SELECT vector_json FROM embeddings WHERE cache_key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    try:
                        vectors[index] = json.loads(row[0])
                        hits += 1
                    except Exception:
                        vectors[index] = None
        return vectors, hits, len(texts) - hits

    def set_many(
        self,
        provider: str,
        model: str,
        input_type: str,
        texts: List[str],
        vectors: List[List[float]],
    ) -> None:
        if not self.enabled or not texts:
            return
        now = time.time()
        rows = [
            (
                self.cache_key(provider, model, input_type, text),
                provider,
                model,
                input_type,
                self._text_hash(text),
                self.normalization_version,
                json.dumps(vector),
                now,
            )
            for text, vector in zip(texts, vectors)
        ]
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO embeddings
                (cache_key, provider, model, input_type, text_hash, normalization_version, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()

    def cache_key(self, provider: str, model: str, input_type: str, text: str) -> str:
        parts = [provider, model, input_type, self._text_hash(text), self.normalization_version]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _ensure(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT,
                    model TEXT,
                    input_type TEXT,
                    text_hash TEXT,
                    normalization_version TEXT,
                    vector_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.commit()

    def _text_hash(self, text: str) -> str:
        normalized = " ".join(str(text or "").split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _extract_retry_after(exc: Any, lower: str) -> Optional[float]:
    for attr in ("retry_after", "retry_after_seconds"):
        value = getattr(exc, attr, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    import re

    match = re.search(r"retry(?:\s|-)?after[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)", lower)
    if match:
        return float(match.group(1))
    return None


def _tail(text: str, limit: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    return clean[-limit:]

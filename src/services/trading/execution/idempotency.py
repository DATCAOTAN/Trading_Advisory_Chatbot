from __future__ import annotations

import hashlib
import json

from src.services.trading.review.models import HumanReviewArtifact


class IdempotencyKeyBuilder:
    def build(self, artifact_id: str, artifact_hash: str, mode: str, symbol: str, created_at: str) -> str:
        raw = f"{artifact_id}|{artifact_hash}|{mode}|{symbol}|{created_at}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class InMemoryIdempotencyStore:
    def __init__(self):
        self._seen: set[str] = set()
        self.dry_run_count = 0

    def seen(self, key: str) -> bool:
        return key in self._seen

    def record(self, key: str) -> None:
        self._seen.add(key)
        self.dry_run_count += 1


def artifact_hash(artifact: HumanReviewArtifact) -> str:
    payload = artifact.as_dict()
    payload.pop("payload_size_chars", None)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

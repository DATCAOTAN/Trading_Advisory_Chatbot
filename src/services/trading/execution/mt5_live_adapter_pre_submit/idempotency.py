from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import MT5IdempotencyCheck, hash_text, now_utc_iso
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


class MT5PreSubmitIdempotencyGuard:
    def __init__(self, config: MT5LiveAdapterPreSubmitConfig | None = None, path: str | Path | None = None):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()
        self.path = Path(path or self.config.idempotency_path)

    def check(self, idempotency_key: str, current_time: datetime | None = None) -> MT5IdempotencyCheck:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=max(1, self.config.idempotency_ttl_seconds))).isoformat()
        if not idempotency_key:
            return MT5IdempotencyCheck(
                check_id="mt5_pre_submit_idempotency_missing_" + hash_text(created_at)[:16],
                created_at=created_at,
                idempotency_key="",
                status="MISSING_KEY",
                duplicate=False,
                registered_for_check_only=False,
                live_execution_reservation_created=False,
                order_send_reservation_created=False,
                expires_at=expires_at,
                blockers=["IDEMPOTENCY_MISSING"],
            )
        key_hash = hash_text(idempotency_key)
        duplicate = key_hash in self._active_hashes(now)
        status = "DUPLICATE_BLOCKED" if duplicate else "CHECK_REGISTERED"
        blockers = ["IDEMPOTENCY_DUPLICATE"] if duplicate else []
        check = MT5IdempotencyCheck(
            check_id="mt5_pre_submit_idempotency_" + key_hash[:16],
            created_at=created_at,
            idempotency_key=idempotency_key,
            status=status,
            duplicate=duplicate,
            registered_for_check_only=not duplicate,
            live_execution_reservation_created=False,
            order_send_reservation_created=False,
            expires_at=expires_at,
            blockers=blockers,
        )
        if not duplicate:
            self._append({"idempotency_key_hash": key_hash, "created_at": created_at, "expires_at": expires_at})
        return check

    def _active_hashes(self, now: datetime) -> set[str]:
        rows = self._read_rows()
        active: set[str] = set()
        for row in rows:
            try:
                expires_at = datetime.fromisoformat(row.get("expires_at", ""))
            except Exception:
                continue
            if expires_at >= now and row.get("idempotency_key_hash"):
                active.add(row["idempotency_key_hash"])
        return active

    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _read_rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

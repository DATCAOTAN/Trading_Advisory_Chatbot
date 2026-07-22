from __future__ import annotations

import hashlib
import json
from time import perf_counter
from urllib import request

from src.services.trading.execution.mt5_bridge_write_skeleton.models import (
    MT5BridgeWriteSkeletonCheckResult,
    now_utc_iso,
)


DEFAULT_ENDPOINT = "/execution/write-skeleton/check"


class MT5BridgeWriteSkeletonClient:
    def __init__(self, bridge_url: str, timeout_seconds: float = 3.0, endpoint: str = DEFAULT_ENDPOINT):
        self.bridge_url = bridge_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.endpoint = endpoint

    def check(self) -> MT5BridgeWriteSkeletonCheckResult:
        started = perf_counter()
        url = f"{self.bridge_url}{self.endpoint}"
        created_at = now_utc_iso()
        try:
            body = json.dumps({"dry_run_check": True, "metadata_redacted": True}).encode("utf-8")
            req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            latency_ms = (perf_counter() - started) * 1000
            return MT5BridgeWriteSkeletonCheckResult(
                check_id=_check_id(url, created_at),
                created_at=created_at,
                bridge_url=self.bridge_url,
                endpoint=self.endpoint,
                reachable=True,
                status=str(payload.get("status", "UNKNOWN")),
                write_skeleton_available=payload.get("write_skeleton_available") is True,
                live_execution_allowed=False,
                order_send_allowed=False,
                execution_allowed=False,
                hard_live_block_required=payload.get("hard_live_block_required") is True,
                order_sent=False,
                ticket=None,
                deal=None,
                metadata_redacted=payload.get("metadata_redacted") is True,
                blockers=[],
                warnings=[],
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return MT5BridgeWriteSkeletonCheckResult(
                check_id=_check_id(url, created_at),
                created_at=created_at,
                bridge_url=self.bridge_url,
                endpoint=self.endpoint,
                reachable=False,
                status="UNREACHABLE",
                write_skeleton_available=False,
                live_execution_allowed=False,
                order_send_allowed=False,
                execution_allowed=False,
                hard_live_block_required=True,
                order_sent=False,
                ticket=None,
                deal=None,
                metadata_redacted=True,
                blockers=["BRIDGE_WRITE_SKELETON_UNREACHABLE"],
                warnings=[type(exc).__name__],
                latency_ms=(perf_counter() - started) * 1000,
            )

    def account_context(self) -> dict:
        req = request.Request(f"{self.bridge_url}/account", method="GET")
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid bridge account context")
        return payload

    def reconcile(self, payload: dict, auth_token: str) -> dict:
        return self._post_protected("/execution/reconcile", payload, auth_token)

    def lifecycle_snapshot(
        self, history_window_seconds: int, correlation_tags: list[str], auth_token: str
    ) -> dict:
        return self._post_protected(
            "/execution/lifecycle-snapshot",
            {
                "history_window_seconds": history_window_seconds,
                "correlation_tags": list(correlation_tags),
            },
            auth_token,
        )

    def submit_controlled(self, payload: dict, auth_token: str) -> dict:
        return self._post_protected(
            "/execution/controlled-submit", payload, auth_token
        )
    def _post_protected(self, endpoint: str, payload: dict, auth_token: str) -> dict:
        if not auth_token:
            raise ValueError("bridge authentication is missing")
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        req = request.Request(
            f"{self.bridge_url}{endpoint}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-MT5-Bridge-Execution-Token": auth_token,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            if hasattr(exc, "read"):
                result = json.loads(exc.read().decode("utf-8"))
            else:
                raise
        if not isinstance(result, dict):
            raise ValueError("invalid protected bridge response")
        return result

def _check_id(url: str, created_at: str) -> str:
    return "mt5_bridge_write_skeleton_check_" + hashlib.sha256(f"{url}:{created_at}".encode("utf-8")).hexdigest()[:16]

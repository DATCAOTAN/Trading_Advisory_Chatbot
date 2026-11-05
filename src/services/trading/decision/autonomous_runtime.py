from __future__ import annotations

import subprocess
import sys
import threading
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AutonomousMonitorProcess:
    """Start or stop the existing coordinator CLI; it owns no trading decisions."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[4])
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._profiles: dict[str, tuple[str, tuple[str, ...], str]] = {}
        self._diagnostics: dict[str, dict[str, Any]] = {}

    def _save(self, scope: str, *, required: bool = False) -> None:
        path = self._diagnostic_path(scope)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._diagnostics[scope], sort_keys=True), encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            self._diagnostics[scope]["failure_category"] = "DIAGNOSTIC_WRITE_FAILED"
            if required:
                raise

    def _diagnostic_path(self, scope: str) -> Path:
        return self.project_root / "data/cache/supervisor_status" / (
            hashlib.sha256(scope.encode()).hexdigest() + ".json"
        )

    def start(
        self,
        *,
        symbol: str,
        timeframes: tuple[str, ...],
        mandate_id: str = "",
        trading_scope: str = "legacy",
    ) -> dict[str, Any]:
        if not str(mandate_id).strip():
            raise ValueError("SUPERVISOR_MANDATE_REQUIRED")
        with self._lock:
            previous = self.status(trading_scope)
            if previous["running"]:
                return previous
            if previous["process_state"] == "UNKNOWN":
                raise RuntimeError("SUPERVISOR_PROCESS_OWNERSHIP_UNAVAILABLE")
            command = [
                sys.executable,
                str(self.project_root / "scripts" / "run_autonomous_candidate_monitor.py"),
                "--symbol", symbol,
                "--timeframes", ",".join(timeframes),
                "--watch",
            ]
            command.extend(("--mandate-id", mandate_id))
            self._profiles.pop(trading_scope, None)
            self._diagnostics[trading_scope] = {
                "process_state": "STARTING",
                "launched_at": datetime.now(timezone.utc).isoformat(),
                "scope_reference": hashlib.sha256(trading_scope.encode()).hexdigest()[:12],
                "mandate_reference": hashlib.sha256(mandate_id.encode()).hexdigest()[:12],
                "exit_code": None,
                "stop_requested_at": "",
                "stop_completed_at": "",
                "failure_category": "",
            }
            self._save(trading_scope, required=True)
            try:
                self._processes[trading_scope] = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                self._diagnostics[trading_scope].update(
                    process_state="FAILED", failure_category="PROCESS_LAUNCH_FAILED",
                )
                self._save(trading_scope)
                raise
            self._profiles[trading_scope] = (symbol, timeframes, mandate_id)
            self._diagnostics[trading_scope]["process_state"] = "RUNNING"
            self._save(trading_scope)
            return self.status(trading_scope)

    def stop(self, trading_scope: str = "legacy") -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(trading_scope)
            if self._running(trading_scope) and process is not None:
                diagnostic = self._diagnostics[trading_scope]
                diagnostic["stop_requested_at"] = datetime.now(timezone.utc).isoformat()
                self._save(trading_scope)
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                diagnostic.update(
                    process_state="STOPPED", exit_code=process.poll(),
                    stop_completed_at=datetime.now(timezone.utc).isoformat(),
                )
                self._save(trading_scope)
            else:
                self.status(trading_scope)  # Retain an unexpected exit rather than erasing it.
            self._processes.pop(trading_scope, None)
            self._profiles.pop(trading_scope, None)
            return self.status(trading_scope)

    def status(self, trading_scope: str = "legacy") -> dict[str, Any]:
        with self._lock:
            if trading_scope not in self._diagnostics:
                path = self._diagnostic_path(trading_scope)
                if path.exists():
                    try:
                        if path.stat().st_size > 4096:
                            raise ValueError("supervisor diagnostic too large")
                        saved = json.loads(path.read_text(encoding="utf-8"))
                        # Diagnostic files are never process or trading authority.
                        if (
                            saved.get("process_state") not in {"STARTING", "RUNNING", "STOPPED", "EXITED", "FAILED"}
                            or saved.get("failure_category") not in {"", "PROCESS_LAUNCH_FAILED", "DIAGNOSTIC_WRITE_FAILED"}
                            or any(not isinstance(saved.get(k, ""), str) for k in (
                                "launched_at", "stop_requested_at", "stop_completed_at", "exited_at",
                            ))
                            or saved.get("exit_code") is not None and type(saved["exit_code"]) is not int
                        ):
                            raise ValueError("invalid supervisor diagnostic")
                        for key in ("launched_at", "stop_requested_at", "stop_completed_at", "exited_at"):
                            if saved.get(key):
                                datetime.fromisoformat(saved[key])
                        reference = saved.get("mandate_reference", "")
                        if not isinstance(reference, str) or len(reference) != 12 or any(c not in "0123456789abcdef" for c in reference):
                            raise ValueError("invalid diagnostic mandate reference")
                        self._diagnostics[trading_scope] = {
                            k: saved.get(k) for k in (
                                "process_state", "launched_at", "stop_requested_at",
                                "stop_completed_at", "exited_at", "exit_code", "failure_category", "mandate_reference",
                            )
                        }
                    except (OSError, ValueError, AttributeError):
                        self._diagnostics[trading_scope] = {
                            "process_state": "UNKNOWN", "failure_category": "DIAGNOSTIC_UNAVAILABLE",
                        }
            diagnostic = dict(self._diagnostics.get(trading_scope, {"process_state": "STOPPED"}))
            process = self._processes.get(trading_scope)
            running = self._running(trading_scope)
            if process is not None and not running and diagnostic["process_state"] == "RUNNING":
                diagnostic.update(
                    process_state="EXITED" if process.poll() == 0 else "FAILED",
                    exit_code=process.poll(), exited_at=datetime.now(timezone.utc).isoformat(),
                )
                self._diagnostics[trading_scope] = diagnostic
                self._save(trading_scope)
            if process is None and diagnostic["process_state"] in {"STARTING", "RUNNING"}:
                diagnostic.update(process_state="UNKNOWN", failure_category="PROCESS_OWNERSHIP_UNAVAILABLE")
            profile = self._profiles.get(trading_scope)
            return {
                **diagnostic,
                "scope_reference": hashlib.sha256(trading_scope.encode()).hexdigest()[:12],
                "running": running,
                "symbol": profile[0] if profile else "",
                "timeframes": list(profile[1]) if profile else [],
                "mandate_id": profile[2] if profile else "",
                "metadata_redacted": True,
            }

    def _running(self, trading_scope: str) -> bool:
        process = self._processes.get(trading_scope)
        return process is not None and process.poll() is None


def supervisor_monitor_evidence(
    process_status: dict[str, Any], monitor: dict[str, Any] | None, *, now: datetime | None = None,
) -> dict[str, str]:
    """Label monitor evidence separately from the owned process's current state."""
    row = monitor or {}
    timestamp = str(row.get("created_at") or "")
    current = False
    try:
        evaluated = datetime.fromisoformat(timestamp)
        launched = datetime.fromisoformat(process_status.get("launched_at") or "")
        age = ((now or datetime.now(timezone.utc)) - evaluated).total_seconds()
        current = bool(process_status.get("running")) and evaluated >= launched and 0 <= age <= 90
    except (TypeError, ValueError):
        pass
    return {
        "last_evaluation_at": timestamp or "UNAVAILABLE",
        "last_blocker": str(row.get("blocker") or "none"),
        "evidence_state": "CURRENT" if current else "HISTORICAL" if timestamp else "UNAVAILABLE",
    }

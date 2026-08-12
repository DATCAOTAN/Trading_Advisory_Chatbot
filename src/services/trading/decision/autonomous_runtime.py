from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


class AutonomousMonitorProcess:
    """Start or stop the existing coordinator CLI; it owns no trading decisions."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[4])
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._profiles: dict[str, tuple[str, tuple[str, ...], str]] = {}

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
            if self._running(trading_scope):
                return self.status(trading_scope)
            command = [
                sys.executable,
                str(self.project_root / "scripts" / "run_autonomous_candidate_monitor.py"),
                "--symbol", symbol,
                "--timeframes", ",".join(timeframes),
                "--watch",
            ]
            command.extend(("--mandate-id", mandate_id))
            self._processes[trading_scope] = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._profiles[trading_scope] = (symbol, timeframes, mandate_id)
            return self.status(trading_scope)

    def stop(self, trading_scope: str = "legacy") -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(trading_scope)
            if self._running(trading_scope) and process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            self._processes.pop(trading_scope, None)
            self._profiles.pop(trading_scope, None)
            return self.status(trading_scope)

    def status(self, trading_scope: str = "legacy") -> dict[str, Any]:
        profile = self._profiles.get(trading_scope)
        return {
            "running": self._running(trading_scope),
            "symbol": profile[0] if profile else "",
            "timeframes": list(profile[1]) if profile else [],
            "mandate_id": profile[2] if profile else "",
            "metadata_redacted": True,
        }

    def _running(self, trading_scope: str) -> bool:
        process = self._processes.get(trading_scope)
        return process is not None and process.poll() is None

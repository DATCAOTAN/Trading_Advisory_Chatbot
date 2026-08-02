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
        self._process: subprocess.Popen[Any] | None = None
        self._profile: tuple[str, tuple[str, ...], str] | None = None

    def start(
        self, *, symbol: str, timeframes: tuple[str, ...], mandate_id: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            if self._running():
                return self.status()
            command = [
                sys.executable,
                str(self.project_root / "scripts" / "run_autonomous_candidate_monitor.py"),
                "--symbol", symbol,
                "--timeframes", ",".join(timeframes),
                "--watch",
            ]
            if mandate_id:
                command.extend(("--mandate-id", mandate_id))
            self._process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._profile = (symbol, timeframes, mandate_id)
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._running():
                assert self._process is not None
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=5)
            self._process = None
            self._profile = None
            return self.status()

    def status(self) -> dict[str, Any]:
        profile = self._profile
        return {
            "running": self._running(),
            "symbol": profile[0] if profile else "",
            "timeframes": list(profile[1]) if profile else [],
            "mandate_id": profile[2] if profile else "",
            "metadata_redacted": True,
        }

    def _running(self) -> bool:
        return self._process is not None and self._process.poll() is None

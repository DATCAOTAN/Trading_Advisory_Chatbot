from __future__ import annotations

from dataclasses import dataclass

from src.config import Config
from src.services.trading.execution.mt5_bridge_write_skeleton.client import MT5BridgeWriteSkeletonClient
from src.services.trading.execution.mt5_bridge_write_skeleton.models import MT5BridgeWriteSkeletonCheckResult
from src.services.trading.execution.mt5_bridge_write_skeleton.validator import (
    MT5BridgeWriteSkeletonValidationResult,
    MT5BridgeWriteSkeletonValidator,
)


@dataclass
class MT5BridgeWriteSkeletonServiceResult:
    check: MT5BridgeWriteSkeletonCheckResult
    validation: MT5BridgeWriteSkeletonValidationResult


class MT5BridgeWriteSkeletonService:
    def __init__(self, bridge_url: str | None = None, timeout_seconds: float | None = None):
        self.bridge_url = (bridge_url or Config.MT5_BRIDGE_URL).replace("host.docker.internal", "127.0.0.1")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else float(getattr(Config, "MT5_BRIDGE_TIMEOUT_SECONDS", 3))

    def run(self) -> MT5BridgeWriteSkeletonServiceResult:
        check = MT5BridgeWriteSkeletonClient(self.bridge_url, self.timeout_seconds).check()
        validation = MT5BridgeWriteSkeletonValidator().validate(check)
        return MT5BridgeWriteSkeletonServiceResult(check=check, validation=validation)

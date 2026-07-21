from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class MT5BridgeWriteSkeletonCheckResult:
    check_id: str
    created_at: str
    bridge_url: str
    endpoint: str
    reachable: bool
    status: str
    write_skeleton_available: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    order_sent: bool
    ticket: Any
    deal: Any
    metadata_redacted: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "created_at": self.created_at,
            "bridge_url": self.bridge_url,
            "endpoint": self.endpoint,
            "reachable": bool(self.reachable),
            "status": self.status,
            "write_skeleton_available": bool(self.write_skeleton_available),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "order_sent": False,
            "ticket": None,
            "deal": None,
            "metadata_redacted": True,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "latency_ms": float(self.latency_ms or 0.0),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

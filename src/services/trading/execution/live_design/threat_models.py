from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.common import dedupe


LIVE_EXECUTION_RISK_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
LIVE_EXECUTION_RISK_CATEGORIES = {
    "MARKET_DATA",
    "ACCOUNT_STATE",
    "SYMBOL_MAPPING",
    "ORDER_CONSTRUCTION",
    "NETWORK",
    "BROKER",
    "LATENCY",
    "DUPLICATION",
    "IDEMPOTENCY",
    "RISK_LIMIT",
    "HUMAN_CONFIRMATION",
    "AUDIT",
    "COMPLIANCE",
    "SYSTEM_CONFIG",
    "UNKNOWN",
}


@dataclass
class LiveExecutionThreat:
    threat_id: str
    category: str
    severity: str
    title: str
    description: str
    trigger_condition: str
    impact: str
    required_control: str
    detection_method: str
    mitigation: str
    residual_risk: str
    blocking: bool = True
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "threat_id": self.threat_id,
            "category": self.category if self.category in LIVE_EXECUTION_RISK_CATEGORIES else "UNKNOWN",
            "severity": self.severity if self.severity in LIVE_EXECUTION_RISK_SEVERITIES else "HIGH",
            "title": self.title,
            "description": self.description,
            "trigger_condition": self.trigger_condition,
            "impact": self.impact,
            "required_control": self.required_control,
            "detection_method": self.detection_method,
            "mitigation": self.mitigation,
            "residual_risk": self.residual_risk,
            "blocking": bool(self.blocking),
            "source_refs": dedupe(self.source_refs),
        }

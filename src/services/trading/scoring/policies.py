from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import Config
from src.services.trading.scoring.normalization import normalize_weights


COMPONENT_KEYS = (
    "technical_score",
    "method_fit_score",
    "regime_alignment_score",
    "macro_calendar_score",
    "risk_context_score",
    "data_quality_score",
    "execution_feasibility_score",
)


@dataclass
class ScoringPolicy:
    weights: dict[str, float] = field(
        default_factory=lambda: normalize_weights(
            {
                "technical_score": 0.25,
                "method_fit_score": 0.20,
                "regime_alignment_score": 0.20,
                "macro_calendar_score": 0.15,
                "risk_context_score": 0.10,
                "data_quality_score": 0.05,
                "execution_feasibility_score": 0.05,
            }
        )
    )
    min_data_quality: float = 0.70
    block_on_invalid_data: bool = True
    block_on_immediate_high_impact: bool = True
    block_on_unknown_method: bool = True
    max_payload_chars: int = 12000

    def __post_init__(self) -> None:
        self.weights = normalize_weights(self.weights)

    @classmethod
    def from_config(cls) -> "ScoringPolicy":
        weights = {
            "technical_score": float(getattr(Config, "SIGNAL_SCORING_TECHNICAL_WEIGHT", 0.25)),
            "method_fit_score": float(getattr(Config, "SIGNAL_SCORING_METHOD_FIT_WEIGHT", 0.20)),
            "regime_alignment_score": float(getattr(Config, "SIGNAL_SCORING_REGIME_ALIGNMENT_WEIGHT", 0.20)),
            "macro_calendar_score": float(getattr(Config, "SIGNAL_SCORING_MACRO_CALENDAR_WEIGHT", 0.15)),
            "risk_context_score": float(getattr(Config, "SIGNAL_SCORING_RISK_CONTEXT_WEIGHT", 0.10)),
            "data_quality_score": float(getattr(Config, "SIGNAL_SCORING_DATA_QUALITY_WEIGHT", 0.05)),
            "execution_feasibility_score": float(getattr(Config, "SIGNAL_SCORING_EXECUTION_FEASIBILITY_WEIGHT", 0.05)),
        }
        return cls(
            weights=normalize_weights(weights),
            min_data_quality=float(getattr(Config, "SIGNAL_SCORING_MIN_DATA_QUALITY", 0.70)),
            block_on_invalid_data=bool(getattr(Config, "SIGNAL_SCORING_BLOCK_ON_INVALID_DATA", True)),
            block_on_immediate_high_impact=bool(getattr(Config, "SIGNAL_SCORING_BLOCK_ON_IMMEDIATE_HIGH_IMPACT", True)),
            block_on_unknown_method=bool(getattr(Config, "SIGNAL_SCORING_BLOCK_ON_UNKNOWN_METHOD", True)),
            max_payload_chars=int(getattr(Config, "SIGNAL_SCORING_MAX_PAYLOAD_CHARS", 12000)),
        )

    def resolve_weights(self, context_pack: Any, method_selection: Any) -> dict[str, float]:
        playbook_weights = _playbook_weights(context_pack, method_selection)
        if not playbook_weights:
            return dict(self.weights)
        mapped = {key: 0.0 for key in COMPONENT_KEYS}
        for key, value in playbook_weights.items():
            mapped_key = _map_playbook_weight_key(key)
            if mapped_key:
                mapped[mapped_key] += float(value or 0.0)
        for key, default_value in self.weights.items():
            if mapped.get(key, 0.0) <= 0:
                mapped[key] = default_value * 0.35
        return normalize_weights(mapped)


def _playbook_weights(context_pack: Any, method_selection: Any) -> dict[str, float]:
    selected = set(getattr(method_selection, "selected_playbook_ids", []) or [])
    for playbook in getattr(context_pack, "selected_playbooks", []) or []:
        if playbook.get("playbook_id") in selected and playbook.get("scoring_weights"):
            return dict(playbook.get("scoring_weights") or {})
    return {}


def _map_playbook_weight_key(key: str) -> str:
    raw = str(key or "").strip().lower()
    if raw in {"trend", "momentum", "alignment", "volume_context", "volatility"}:
        return "technical_score"
    if raw in {"method", "method_fit"}:
        return "method_fit_score"
    if raw in {"regime", "regime_alignment"}:
        return "regime_alignment_score"
    if raw in {"calendar", "macro"}:
        return "macro_calendar_score"
    if raw in {"risk"}:
        return "risk_context_score"
    if raw in {"data_quality"}:
        return "data_quality_score"
    if raw in {"provider", "feasibility"}:
        return "execution_feasibility_score"
    return ""

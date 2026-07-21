from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.services.trading.knowledge.models import RuntimeContextPack


@dataclass
class KnowledgeValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "issues": list(self.issues), "warnings": list(self.warnings)}


class KnowledgeSelectionValidator:
    def validate(
        self,
        context_pack: RuntimeContextPack,
        expected_user_selected_method_id: str | None = None,
    ) -> KnowledgeValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        payload = context_pack.as_dict()
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        lower = encoded.lower()

        if any(key in lower for key in ["raw_book_text", "raw_report_text", "full_pdf_text", "full_document_text", "raw_candles"]):
            issues.append("raw_text_or_candles_present")
        if bool(getattr(Config, "KNOWLEDGE_REQUIRE_SOURCE_REFS", True)):
            missing = [ref for ref in context_pack.source_refs if not _source_ref_exists(ref)]
            if not context_pack.source_refs:
                issues.append("source_refs_missing")
            elif missing:
                issues.append("source_ref_path_missing:" + ",".join(missing[:3]))
        if len(context_pack.selected_method_cards) > int(getattr(Config, "KNOWLEDGE_MAX_METHOD_CARDS", 3)):
            issues.append("too_many_method_cards")
        if len(context_pack.selected_macro_cards) > int(getattr(Config, "KNOWLEDGE_MAX_MACRO_CARDS", 3)):
            issues.append("too_many_macro_cards")
        if len(context_pack.selected_playbooks) > int(getattr(Config, "KNOWLEDGE_MAX_PLAYBOOKS", 3)):
            issues.append("too_many_playbooks")
        if context_pack.payload_size_chars > int(getattr(Config, "KNOWLEDGE_MAX_CONTEXT_CHARS", 12000)):
            issues.append("context_pack_too_large")
        if expected_user_selected_method_id:
            selected_ids = [item.get("method_id") for item in context_pack.selected_method_cards]
            if not selected_ids or selected_ids[0] != expected_user_selected_method_id:
                issues.append("user_selected_method_not_preserved")
        regime = str(context_pack.market_regime_summary.get("primary_regime", ""))
        for card in context_pack.selected_method_cards:
            if regime in set(card.get("bad_regimes", [])):
                issues.append(f"bad_regime_selected:{card.get('method_id')}")
        if context_pack.market_regime_summary.get("primary_regime") == "NEWS_RISK":
            macro_text = json.dumps(context_pack.selected_macro_cards, ensure_ascii=False).lower()
            if "calendar" not in macro_text and "risk" not in macro_text:
                issues.append("news_risk_macro_card_missing")
        if not context_pack.feature_snapshot_summary.get("feature_snapshot_id"):
            issues.append("feature_snapshot_id_missing")
        if not context_pack.calendar_context_summary.get("context_id"):
            issues.append("calendar_context_id_missing")
        if not context_pack.market_regime_summary.get("regime_snapshot_id"):
            issues.append("regime_snapshot_id_missing")
        for forbidden in ["buy", "sell", "trade_decision", "entry", "stop-loss", "take-profit", "account-risk"]:
            if forbidden in lower:
                issues.append(f"forbidden_marker:{forbidden}")
        if ("order" + "_send") in lower or "metatrader5" in lower:
            issues.append("execution_or_mt5_marker_present")
        return KnowledgeValidationResult(not issues, issues, warnings)


def _source_ref_exists(ref: str) -> bool:
    path = Path(ref)
    if not path.is_absolute():
        path = Config.BASE_DIR / ref
    return path.exists()

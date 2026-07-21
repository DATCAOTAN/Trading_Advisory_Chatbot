from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult, now_utc_iso


class MethodReasoningOutputParser:
    def parse(
        self,
        text: str,
        mode: str,
        symbol: str,
        context_pack_id: str,
        source_refs: list[str],
    ) -> MethodSelectionResult | None:
        payload = _extract_json(text)
        if payload is None:
            return None
        assessments = [
            _assessment(item)
            for item in payload.get("candidate_assessments", [])
            if isinstance(item, dict)
        ]
        created_at = now_utc_iso()
        result = MethodSelectionResult(
            result_id=_result_id(context_pack_id, created_at, payload.get("primary_method_id", "")),
            created_at=created_at,
            mode=mode,
            symbol=symbol,
            primary_method_id=str(payload.get("primary_method_id") or ""),
            supporting_method_ids=_str_list(payload.get("supporting_method_ids")),
            rejected_method_ids=_str_list(payload.get("rejected_method_ids")),
            selected_playbook_ids=_str_list(payload.get("selected_playbook_ids")),
            relevant_macro_ids=_str_list(payload.get("relevant_macro_ids")),
            overall_context_fit=_float(payload.get("overall_context_fit")),
            confidence=_float(payload.get("confidence")),
            blockers=_str_list(payload.get("blockers")),
            warnings=_str_list(payload.get("warnings")),
            reasoning_summary=str(payload.get("reasoning_summary") or ""),
            candidate_assessments=assessments,
            source_context_pack_id=context_pack_id,
            source_refs=list(source_refs),
        )
        result.payload_size_chars = len(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
        return result


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _assessment(item: dict[str, Any]) -> MethodCandidateAssessment:
    return MethodCandidateAssessment(
        method_id=str(item.get("method_id") or ""),
        method_name=str(item.get("method_name") or ""),
        role=str(item.get("role") or "REJECTED"),
        compatibility_score=_float(item.get("compatibility_score")),
        regime_fit=str(item.get("regime_fit") or ""),
        feature_fit=str(item.get("feature_fit") or ""),
        calendar_fit=str(item.get("calendar_fit") or ""),
        macro_fit=str(item.get("macro_fit") or ""),
        risk_fit=str(item.get("risk_fit") or ""),
        reasons=_str_list(item.get("reasons")),
        conflicts=_str_list(item.get("conflicts")),
        source_refs=_str_list(item.get("source_refs")),
    )


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _float(value: Any) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0


def _result_id(context_pack_id: str, created_at: str, primary_method_id: str) -> str:
    digest = hashlib.sha256(f"{context_pack_id}|{created_at}|{primary_method_id}".encode("utf-8")).hexdigest()[:16]
    return f"method_selection_{digest}"

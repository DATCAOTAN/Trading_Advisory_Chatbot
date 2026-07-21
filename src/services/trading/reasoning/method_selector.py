from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from src.config import Config
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.llm_adapter import LLMReasoningAdapter
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult, now_utc_iso
from src.services.trading.reasoning.output_parser import MethodReasoningOutputParser
from src.services.trading.reasoning.prompt_builder import MethodReasoningPromptBuilder
from src.services.trading.reasoning.validator import MethodSelectionValidator, contains_forbidden_output


class DeterministicMethodSelector:
    def select(
        self,
        context_pack: RuntimeContextPack,
        mode: str | None = None,
        user_selected_method_id: str | None = None,
    ) -> MethodSelectionResult:
        selected_mode = mode or context_pack.mode
        assessments = [_assess_method(item, context_pack, selected_mode, user_selected_method_id) for item in context_pack.selected_method_cards]
        if selected_mode == "human_confirmed_live" and user_selected_method_id:
            primary = next((item for item in assessments if item.method_id == user_selected_method_id), None)
        elif selected_mode == "manage_existing_position":
            primary = _best_assessment(assessments, prefer_risk=True)
        else:
            primary = _best_assessment(assessments)
        primary_method_id = primary.method_id if primary else ""
        supporting = [item.method_id for item in sorted(assessments, key=lambda item: item.compatibility_score, reverse=True) if item.method_id != primary_method_id and item.role != "REJECTED"]
        rejected = [item.method_id for item in assessments if item.role == "REJECTED"]
        for item in assessments:
            if item.method_id == primary_method_id:
                item.role = "PRIMARY_CANDIDATE"
            elif item.method_id in supporting:
                item.role = "SUPPORTING_CONFIRMATION"
        blockers = list(context_pack.blockers)
        warnings = list(context_pack.warnings)
        calendar_risk = context_pack.calendar_context_summary.get("calendar_risk_state", "UNKNOWN")
        if calendar_risk in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"}:
            blockers.append(f"CALENDAR_RISK_{calendar_risk}")
            warnings.append("method_selection_is_context_only")
        created_at = now_utc_iso()
        result = MethodSelectionResult(
            result_id=_result_id(context_pack.context_pack_id, created_at, primary_method_id),
            created_at=created_at,
            mode=selected_mode,
            symbol=context_pack.symbol,
            primary_method_id=primary_method_id,
            supporting_method_ids=supporting,
            rejected_method_ids=rejected,
            selected_playbook_ids=[item.get("playbook_id", "") for item in context_pack.selected_playbooks if item.get("playbook_id")],
            relevant_macro_ids=[item.get("macro_id", "") for item in context_pack.selected_macro_cards if item.get("macro_id")],
            overall_context_fit=primary.compatibility_score if primary else 0.0,
            confidence=_confidence(primary, context_pack),
            blockers=blockers,
            warnings=warnings,
            reasoning_summary=_summary(primary, context_pack),
            candidate_assessments=assessments,
            source_context_pack_id=context_pack.context_pack_id,
            source_refs=list(context_pack.source_refs),
        )
        result.payload_size_chars = len(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
        return result


class MethodSelectorService:
    def __init__(
        self,
        deterministic_selector: DeterministicMethodSelector | None = None,
        prompt_builder: MethodReasoningPromptBuilder | None = None,
        llm_adapter: LLMReasoningAdapter | None = None,
        output_parser: MethodReasoningOutputParser | None = None,
        validator: MethodSelectionValidator | None = None,
    ):
        self.deterministic_selector = deterministic_selector or DeterministicMethodSelector()
        self.prompt_builder = prompt_builder or MethodReasoningPromptBuilder()
        self.llm_adapter = llm_adapter or LLMReasoningAdapter()
        self.output_parser = output_parser or MethodReasoningOutputParser()
        self.validator = validator or MethodSelectionValidator()
        self.last_used_llm = False
        self.last_latency_ms = 0.0
        self.last_warnings: list[str] = []

    def select(
        self,
        context_pack: RuntimeContextPack,
        mode: str | None = None,
        user_selected_method_id: str | None = None,
        use_llm: bool | None = None,
    ) -> MethodSelectionResult:
        started = perf_counter()
        self.last_used_llm = False
        self.last_warnings = []
        selected_mode = mode or context_pack.mode
        deterministic = self.deterministic_selector.select(context_pack, selected_mode, user_selected_method_id)
        if not self.validator.validate(deterministic, context_pack, user_selected_method_id).passed:
            self.last_latency_ms = (perf_counter() - started) * 1000
            return deterministic

        llm_requested = bool(use_llm) if use_llm is not None else bool(getattr(Config, "TRADING_REASONING_LLM_ENABLED", False))
        if not llm_requested:
            deterministic.warnings.append("llm_disabled_deterministic_fallback")
            self.last_latency_ms = (perf_counter() - started) * 1000
            return deterministic

        request = self.prompt_builder.build(context_pack, selected_mode, user_selected_method_id)
        response = self.llm_adapter.complete(request)
        parsed = response.parsed_result
        if not parsed or response.parse_status != "OK":
            deterministic.warnings.append("llm_parse_failed_fallback")
            deterministic.warnings.extend(response.errors)
            self.last_latency_ms = (perf_counter() - started) * 1000
            return deterministic
        if not parsed.source_refs:
            parsed.source_refs = list(context_pack.source_refs)
        parsed.source_context_pack_id = context_pack.context_pack_id
        if contains_forbidden_output(response.raw_text_redacted):
            deterministic.warnings.append("llm_forbidden_output_fallback")
            self.last_latency_ms = (perf_counter() - started) * 1000
            return deterministic
        validation = self.validator.validate(parsed, context_pack, user_selected_method_id)
        if not validation.passed:
            deterministic.warnings.append("llm_validation_failed_fallback")
            deterministic.warnings.extend(validation.issues)
            self.last_latency_ms = (perf_counter() - started) * 1000
            return deterministic
        self.last_used_llm = True
        self.last_latency_ms = (perf_counter() - started) * 1000
        return parsed


def _assess_method(item: dict[str, Any], context_pack: RuntimeContextPack, mode: str, user_selected_method_id: str | None) -> MethodCandidateAssessment:
    method_id = str(item.get("method_id") or "")
    regime = str(context_pack.market_regime_summary.get("primary_regime") or "UNKNOWN")
    calendar_risk = str(context_pack.calendar_context_summary.get("calendar_risk_state") or "UNKNOWN")
    score = 0.4
    reasons: list[str] = []
    conflicts: list[str] = []
    if user_selected_method_id and method_id == user_selected_method_id:
        score += 0.35
        reasons.append("user_selected_method")
    if regime in set(item.get("suitable_regimes", [])):
        score += 0.25
        reasons.append(f"regime_fit:{regime}")
    if regime in set(item.get("bad_regimes", [])):
        score -= 0.45
        conflicts.append(f"bad_regime:{regime}")
    required = item.get("required_features", [])
    if required and _features_present(required, context_pack.feature_snapshot_summary):
        score += 0.15
        reasons.append("required_features_present")
    elif required:
        score -= 0.15
        conflicts.append("required_features_missing")
    if calendar_risk in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"}:
        if "risk" in item.get("domains", []) or "risk" in method_id:
            score += 0.2
            reasons.append("calendar_risk_fit")
        else:
            score -= 0.25
            conflicts.append(f"calendar_risk:{calendar_risk}")
    if mode == "manage_existing_position" and ("risk" in item.get("domains", []) or "risk" in method_id):
        score += 0.25
    score = _clamp(score)
    role = "REJECTED" if score < 0.35 else "RISK_ONLY" if "risk" in item.get("domains", []) else "SUPPORTING_CONFIRMATION"
    return MethodCandidateAssessment(
        method_id=method_id,
        method_name=str(item.get("method_name") or ""),
        role=role,
        compatibility_score=score,
        regime_fit="fit" if f"regime_fit:{regime}" in reasons else "conflict" if f"bad_regime:{regime}" in conflicts else "neutral",
        feature_fit="fit" if "required_features_present" in reasons else "conflict" if "required_features_missing" in conflicts else "neutral",
        calendar_fit="fit" if "calendar_risk_fit" in reasons else "conflict" if any(value.startswith("calendar_risk:") for value in conflicts) else "neutral",
        macro_fit="available" if context_pack.selected_macro_cards else "none",
        risk_fit="risk" if "risk" in item.get("domains", []) else "neutral",
        reasons=reasons,
        conflicts=conflicts,
        source_refs=list(item.get("source_refs", [])),
    )


def _best_assessment(assessments: list[MethodCandidateAssessment], prefer_risk: bool = False) -> MethodCandidateAssessment | None:
    if not assessments:
        return None
    if prefer_risk:
        risk_items = [item for item in assessments if item.role == "RISK_ONLY"]
        if risk_items:
            return sorted(risk_items, key=lambda item: item.compatibility_score, reverse=True)[0]
    selectable = [item for item in assessments if item.role != "REJECTED"]
    return sorted(selectable or assessments, key=lambda item: item.compatibility_score, reverse=True)[0]


def _features_present(required: list[str], feature_summary: dict[str, Any]) -> bool:
    for name in required:
        value = feature_summary.get(name)
        if value in {None, "", "UNKNOWN"}:
            return False
    return True


def _confidence(primary: MethodCandidateAssessment | None, context_pack: RuntimeContextPack) -> float:
    if not primary:
        return 0.0
    quality_bonus = 0.08 if context_pack.feature_snapshot_summary.get("data_quality_status") == "COMPLETE" else 0.0
    blocker_penalty = min(0.25, len(context_pack.blockers) * 0.08)
    return _clamp(primary.compatibility_score + quality_bonus - blocker_penalty)


def _summary(primary: MethodCandidateAssessment | None, context_pack: RuntimeContextPack) -> str:
    if not primary:
        return "No compatible method candidate was selected from the bounded runtime context pack."
    regime = context_pack.market_regime_summary.get("primary_regime", "UNKNOWN")
    risk = context_pack.calendar_context_summary.get("calendar_risk_state", "UNKNOWN")
    return f"Selected {primary.method_id} as method reasoning context for regime={regime}, calendar_risk={risk}."


def _result_id(context_pack_id: str, created_at: str, primary_method_id: str) -> str:
    digest = hashlib.sha256(f"{context_pack_id}|{created_at}|{primary_method_id}|deterministic".encode("utf-8")).hexdigest()[:16]
    return f"method_selection_{digest}"


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0

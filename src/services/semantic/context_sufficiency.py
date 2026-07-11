from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.semantic.context_execution import ContextExecutionPlan
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements


@dataclass
class ContextSufficiencyResult:
    status: str = "INSUFFICIENT"
    shared_status: str = ""
    completeness_score: float = 0.0
    confidence_ceiling: str = "low"
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    stale_context: List[str] = field(default_factory=list)
    unavailable_capabilities: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    task_statuses: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "shared_status": self.shared_status or self.status,
            "completeness_score": self.completeness_score,
            "confidence_ceiling": self.confidence_ceiling,
            "missing_required": list(self.missing_required),
            "missing_optional": list(self.missing_optional),
            "stale_context": list(self.stale_context),
            "unavailable_capabilities": list(self.unavailable_capabilities),
            "warnings": list(self.warnings),
            "task_statuses": dict(self.task_statuses),
        }


class ContextSufficiencyGate:
    """Validate whether acquired context is sufficient for the QueryPlan."""

    BLOCKING_CAPABILITIES = {"account_state", "instrument_spec", "stop_distance", "risk_limit"}
    ACCEPTABLE_STATUSES = {"success", "reused"}

    def evaluate(
        self,
        decision_context: Any,
        requirements: Optional[ContextRequirements] = None,
        execution_plan: Optional[ContextExecutionPlan] = None,
    ) -> ContextSufficiencyResult:
        requirements = requirements or getattr(decision_context, "requirements", None)
        unavailable = list((execution_plan.unavailable_capabilities if execution_plan else []) or [])
        if not requirements:
            result = ContextSufficiencyResult(status="COMPLETE", completeness_score=1.0, confidence_ceiling="high")
            self._log(result)
            return result

        missing_required = []
        missing_optional = []
        for need in requirements.required_needs:
            if not self._has_context(decision_context, need):
                missing_required.append(self._name(need))
        for need in requirements.optional_needs:
            if not self._has_context(decision_context, need):
                missing_optional.append(self._name(need))

        required_count = max(len(requirements.required_needs), 1)
        present_required = required_count - len(missing_required)
        optional_count = len(requirements.optional_needs)
        present_optional = optional_count - len(missing_optional)
        required_score = present_required / required_count
        optional_score = (present_optional / optional_count) if optional_count else 1.0
        score = round((required_score * 0.8) + (optional_score * 0.2), 3)

        unavailable_required = [
            item
            for item in unavailable
            if item.split(":", 1)[0] in {need.capability for need in requirements.required_needs}
        ]
        if unavailable_required and any(item.split(":", 1)[0] in self.BLOCKING_CAPABILITIES for item in unavailable_required):
            status = "BLOCKED"
        elif missing_required or unavailable_required:
            status = "INSUFFICIENT"
        elif missing_optional:
            status = "DEGRADED"
        else:
            status = "COMPLETE"

        confidence = "high"
        if status == "DEGRADED":
            confidence = "medium"
        if status in {"INSUFFICIENT", "BLOCKED"}:
            confidence = "low"

        warnings = []
        if missing_required:
            warnings.append("required context missing")
        if missing_optional:
            warnings.append("optional context missing or unavailable")
        if unavailable:
            warnings.append("one or more capabilities unavailable")

        result = ContextSufficiencyResult(
            status=status,
            shared_status=status,
            completeness_score=score if status != "BLOCKED" else min(score, 0.4),
            confidence_ceiling=confidence,
            missing_required=missing_required,
            missing_optional=missing_optional,
            unavailable_capabilities=unavailable,
            warnings=warnings,
        )
        task_requirements = getattr(requirements, "task_requirements", {}) or {}
        for task_id, task_req in task_requirements.items():
            task_result = self.evaluate(decision_context, task_req, execution_plan)
            result.task_statuses[task_id] = task_result.as_dict()
        self._log(result)
        return result

    @staticmethod
    def _has_context(ctx: Any, need: ContextNeed) -> bool:
        acquisition_results = getattr(ctx, "acquisition_results", None)
        if acquisition_results:
            return ContextSufficiencyGate._has_acquired_context(acquisition_results, need)

        cap = need.capability
        if cap in {"official_report", "static_knowledge", "market_knowledge"}:
            retrieved = getattr(ctx, "retrieved_sources", None)
            if not retrieved:
                return False
            return bool(getattr(retrieved, "primary_sources", []) or getattr(retrieved, "supporting_sources", []))
        if cap == "market_snapshot":
            return getattr(ctx, "market_snapshot", None) is not None
        if cap == "ohlcv":
            snapshot = getattr(ctx, "market_snapshot", None)
            summary = getattr(snapshot, "ohlcv_summary", {}) if snapshot else {}
            return bool(summary and summary.get("candles"))
        if cap == "economic_event":
            return bool(getattr(ctx, "economic_events", []))
        if cap == "technical_snapshot":
            return getattr(ctx, "technical_snapshot", None) is not None
        if cap in {"account_state", "risk_limit"}:
            return getattr(ctx, "risk_snapshot", None) is not None
        if cap in {"instrument_spec", "stop_distance"}:
            risk_snapshot = getattr(ctx, "risk_snapshot", None)
            return bool(risk_snapshot and getattr(risk_snapshot, cap, None))
        return False

    @staticmethod
    def _has_acquired_context(acquisition_results: List[Any], need: ContextNeed) -> bool:
        for result in acquisition_results:
            if isinstance(result, dict):
                capability = result.get("capability", "")
                target = result.get("target", "")
                status = result.get("status", "")
                candidate_result = None
            else:
                capability = getattr(result, "capability", "")
                target = getattr(result, "target", "")
                status = getattr(result, "status", "")
                candidate_result = result
            if status not in ContextSufficiencyGate.ACCEPTABLE_STATUSES or capability != need.capability:
                continue
            freshness = result.get("freshness_status", "") if isinstance(result, dict) else getattr(result, "freshness_status", "")
            if str(freshness).lower() == "stale":
                continue
            if capability in {"official_report", "static_knowledge", "market_knowledge"}:
                try:
                    from src.services.semantic.context_acquisition import _knowledge_result_matches
                    from src.services.semantic.context_execution import ContextAcquisitionResult

                    if candidate_result is None:
                        candidate_result = ContextAcquisitionResult(
                            capability=capability,
                            target=target,
                            status=status,
                            required=bool(result.get("required", need.required)),
                            normalized_parameters=dict(result.get("normalized_parameters", {}) or {}),
                            data=result.get("data"),
                            source=result.get("source", ""),
                            operation=result.get("operation", ""),
                            provenance=dict(result.get("provenance", {}) or {}),
                            freshness_status=result.get("freshness_status", "unknown"),
                        )
                    if not _knowledge_result_matches(need, candidate_result):
                        continue
                except Exception:
                    return False
            if ContextSufficiencyGate._target_matches(target, need.target):
                return True
        return False

    @staticmethod
    def _target_matches(result_target: str, need_target: str) -> bool:
        result_target = str(result_target or "").strip().lower()
        need_target = str(need_target or "").strip().lower()
        if not need_target or need_target == "default":
            return True
        if result_target == need_target:
            return True
        return need_target in {"gold", "xauusd"} and result_target in {"gold", "xauusd"}

    @staticmethod
    def _name(need: ContextNeed) -> str:
        return f"{need.capability}:{need.target or 'default'}"

    @staticmethod
    def _log(result: ContextSufficiencyResult) -> None:
        task_bits = " ".join(
            f"{task_id}={task_result.get('status')}"
            for task_id, task_result in result.task_statuses.items()
        )
        print(
            "[ContextSufficiency] "
            f"status={result.status} "
            f"shared_status={result.shared_status or result.status} "
            f"confidence_ceiling={result.confidence_ceiling} "
            f"missing_required={result.missing_required}"
            f"{(' ' + task_bits) if task_bits else ''}"
        )

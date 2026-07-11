from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from src.services.semantic.capability_registry import CapabilityRegistry


class FailureClass:
    QUERY_PLAN_ERROR = "QUERY_PLAN_ERROR"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    ACQUISITION_FAILURE = "ACQUISITION_FAILURE"
    EVIDENCE_ROLE_GAP = "EVIDENCE_ROLE_GAP"
    ANSWER_ROLE_CONTRACT_MISMATCH = "ANSWER_ROLE_CONTRACT_MISMATCH"
    VALIDATOR_ONTOLOGY_DIVERGENCE = "VALIDATOR_ONTOLOGY_DIVERGENCE"
    FINAL_ARTIFACT_INCONSISTENCY = "FINAL_ARTIFACT_INCONSISTENCY"
    PROVIDER_DATA_FAILURE = "PROVIDER_DATA_FAILURE"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_PARTIAL = "AGENT_PARTIAL"
    AGENT_RESULT_INVALID = "AGENT_RESULT_INVALID"
    AGENT_DEPENDENCY_BLOCKED = "AGENT_DEPENDENCY_BLOCKED"


@dataclass(frozen=True)
class AnswerRolePath:
    answer_role: str
    evidence_roles: List[str]
    capabilities: List[str]
    required: bool = True
    policy: str = "required"
    notes: str = ""


@dataclass(frozen=True)
class IntentFamilyInventory:
    intent_family: str
    answer_type: str
    role_paths: List[AnswerRolePath] = field(default_factory=list)
    selected_agents: List[str] = field(default_factory=list)
    response_gate_expectation: str = "normal_synthesis_when_sufficient"

    @property
    def required_answer_roles(self) -> List[str]:
        return [path.answer_role for path in self.role_paths if path.required]

    @property
    def optional_answer_roles(self) -> List[str]:
        return [path.answer_role for path in self.role_paths if not path.required]

    @property
    def required_evidence_roles(self) -> List[str]:
        return _ordered_unique(role for path in self.role_paths if path.required for role in path.evidence_roles)

    @property
    def optional_evidence_roles(self) -> List[str]:
        return _ordered_unique(role for path in self.role_paths if not path.required for role in path.evidence_roles)

    @property
    def required_context_capabilities(self) -> List[str]:
        return _ordered_unique(cap for path in self.role_paths if path.required for cap in path.capabilities)

    @property
    def optional_context_capabilities(self) -> List[str]:
        return _ordered_unique(cap for path in self.role_paths if not path.required for cap in path.capabilities)

    def as_dict(self) -> Dict[str, object]:
        return {
            "intent_family": self.intent_family,
            "answer_type": self.answer_type,
            "required_answer_roles": self.required_answer_roles,
            "optional_answer_roles": self.optional_answer_roles,
            "required_evidence_roles": self.required_evidence_roles,
            "optional_evidence_roles": self.optional_evidence_roles,
            "required_context_capabilities": self.required_context_capabilities,
            "optional_context_capabilities": self.optional_context_capabilities,
            "selected_agents": list(self.selected_agents),
            "response_gate_expectation": self.response_gate_expectation,
        }


@dataclass
class CrossLayerAuditResult:
    inventory: IntentFamilyInventory
    missing_answer_role_paths: List[str] = field(default_factory=list)
    missing_evidence_capability_paths: List[str] = field(default_factory=list)
    disabled_required_capabilities: List[str] = field(default_factory=list)
    unscheduled_required_capabilities: List[str] = field(default_factory=list)
    mismatch_types: List[str] = field(default_factory=list)
    failure_classes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_answer_role_paths
            or self.missing_evidence_capability_paths
            or self.disabled_required_capabilities
            or self.unscheduled_required_capabilities
        )

    def as_dict(self) -> Dict[str, object]:
        data = self.inventory.as_dict()
        data.update(
            {
                "ok": self.ok,
                "missing_answer_role_paths": list(self.missing_answer_role_paths),
                "missing_evidence_capability_paths": list(self.missing_evidence_capability_paths),
                "disabled_required_capabilities": list(self.disabled_required_capabilities),
                "unscheduled_required_capabilities": list(self.unscheduled_required_capabilities),
                "mismatch_types": list(self.mismatch_types),
                "failure_classes": list(self.failure_classes),
            }
        )
        return data


class CrossLayerAlignmentAudit:
    """Small deterministic audit of existing cross-layer semantic contracts.

    This is not a planner or replacement registry. It is a consistency checker
    for the mappings already implied by requirements, evidence roles, and
    answer contracts.
    """

    @classmethod
    def inventories(cls) -> Dict[str, IntentFamilyInventory]:
        return {
            "book_concept_explanation": IntentFamilyInventory(
                intent_family="book_concept_explanation",
                answer_type="static_explanation",
                role_paths=[
                    AnswerRolePath("core_concept", ["direct_book_passage"], ["static_knowledge"]),
                    AnswerRolePath("methodology_or_process", ["direct_book_passage"], ["static_knowledge"]),
                    AnswerRolePath("context_or_conditions", ["direct_book_passage"], ["static_knowledge"]),
                    AnswerRolePath("practical_application", ["direct_book_passage"], ["static_knowledge"], required=False, policy="depth_conditional"),
                ],
                selected_agents=["StaticKnowledgeAgent"],
            ),
            "macro_report_summary": IntentFamilyInventory(
                intent_family="macro_report_summary",
                answer_type="report_summary",
                role_paths=[
                    AnswerRolePath("headline_findings", ["official_report_passage"], ["official_report"]),
                    AnswerRolePath("important_components", ["official_report_passage"], ["official_report"]),
                    AnswerRolePath("report_period", ["official_report_passage"], ["official_report"]),
                    AnswerRolePath("official_source_context", ["official_report_passage"], ["official_report"]),
                    AnswerRolePath("short_interpretation", ["official_report_passage"], ["official_report"]),
                ],
                selected_agents=["StaticKnowledgeAgent"],
            ),
            "macro_market_impact": IntentFamilyInventory(
                intent_family="macro_market_impact",
                answer_type="scenario_analysis",
                role_paths=[
                    AnswerRolePath("event_state", ["economic_event_record", "official_report_passage"], ["economic_event", "official_report"]),
                    AnswerRolePath("transmission_mechanism", ["official_report_passage"], ["official_report"]),
                    AnswerRolePath("current_market_context", ["market_snapshot"], ["market_snapshot"]),
                    AnswerRolePath("bullish_scenario", ["official_report_passage", "economic_event_record", "market_snapshot"], ["official_report", "economic_event", "market_snapshot"]),
                    AnswerRolePath("bearish_scenario", ["official_report_passage", "economic_event_record", "market_snapshot"], ["official_report", "economic_event", "market_snapshot"]),
                    AnswerRolePath("confirmation_or_invalidation", ["market_snapshot", "economic_event_record"], ["market_snapshot", "economic_event"]),
                    AnswerRolePath("limitations", ["official_report_passage", "economic_event_record", "market_snapshot"], ["official_report", "economic_event", "market_snapshot"], required=False, policy="depth_conditional"),
                ],
                selected_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"],
                response_gate_expectation="scenario_synthesis_when_required_context_complete",
            ),
            "market_state_analysis": IntentFamilyInventory(
                intent_family="market_state_analysis",
                answer_type="market_analysis",
                role_paths=[
                    AnswerRolePath("current_state", ["market_snapshot"], ["market_snapshot"]),
                    AnswerRolePath("recent_market_behavior", ["ohlcv_summary"], ["ohlcv"]),
                    AnswerRolePath(
                        "main_drivers",
                        ["economic_event_record", "market_commentary_passage", "technical_snapshot"],
                        ["economic_event", "market_knowledge", "technical_snapshot"],
                        required=False,
                        policy="conditional_driver_evidence",
                        notes="Snapshot/OHLCV alone do not prove causal drivers.",
                    ),
                    AnswerRolePath(
                        "confirmation_or_risk_factors",
                        ["technical_snapshot", "economic_event_record", "market_commentary_passage"],
                        ["technical_snapshot", "economic_event", "market_knowledge"],
                        required=False,
                        policy="conditional_risk_evidence",
                    ),
                ],
                selected_agents=["MarketDataAgent", "TechnicalAnalysisAgent"],
                response_gate_expectation="market_synthesis_with_driver_limitations_when_driver_evidence_missing",
            ),
            "multi_intent": IntentFamilyInventory(
                intent_family="multi_intent",
                answer_type="composed_from_child_plans",
                role_paths=[],
                selected_agents=["ComposedFromChildren"],
                response_gate_expectation="aggregate_child_task_policies",
            ),
        }

    @classmethod
    def inventory(cls, intent_family: str) -> IntentFamilyInventory:
        inventories = cls.inventories()
        if intent_family not in inventories:
            raise KeyError(f"unknown intent family: {intent_family}")
        return inventories[intent_family]

    @classmethod
    def audit_family(
        cls,
        intent_family: str,
        registry: Optional[CapabilityRegistry] = None,
        scheduled_capabilities: Optional[Iterable[str]] = None,
        unavailable_capabilities: Optional[Iterable[str]] = None,
    ) -> CrossLayerAuditResult:
        inventory = cls.inventory(intent_family)
        registry = registry or CapabilityRegistry.default()
        scheduled = set(scheduled_capabilities or [])
        unavailable = set(unavailable_capabilities or [])
        result = CrossLayerAuditResult(inventory=inventory)

        for path in inventory.role_paths:
            if path.required and not path.evidence_roles:
                result.missing_answer_role_paths.append(path.answer_role)
            if path.required and not path.capabilities:
                result.missing_evidence_capability_paths.extend(path.evidence_roles or [path.answer_role])

        for capability in inventory.required_context_capabilities:
            definition = registry.get(capability)
            if not definition or not definition.enabled:
                result.disabled_required_capabilities.append(capability)

        if scheduled_capabilities is not None:
            for capability in inventory.required_context_capabilities:
                if capability not in scheduled and capability not in unavailable:
                    result.unscheduled_required_capabilities.append(capability)

        result.mismatch_types = cls._mismatch_types(result)
        result.failure_classes = FailureClassifier.classify(result)
        return result

    @classmethod
    def _mismatch_types(cls, result: CrossLayerAuditResult) -> List[str]:
        mismatch = []
        if result.missing_answer_role_paths:
            mismatch.append("answer_role_without_evidence_role")
        if result.missing_evidence_capability_paths:
            mismatch.append("evidence_role_without_capability")
        if result.disabled_required_capabilities:
            mismatch.append("required_capability_disabled")
        if result.unscheduled_required_capabilities:
            mismatch.append("required_capability_not_scheduled")
        return mismatch


class FailureClassifier:
    @staticmethod
    def classify(result: CrossLayerAuditResult) -> List[str]:
        classes = []
        if result.missing_answer_role_paths:
            classes.append(FailureClass.EVIDENCE_ROLE_GAP)
        if result.missing_evidence_capability_paths or result.disabled_required_capabilities:
            classes.append(FailureClass.CAPABILITY_GAP)
        if result.unscheduled_required_capabilities:
            classes.append(FailureClass.ANSWER_ROLE_CONTRACT_MISMATCH)
        return _ordered_unique(classes)

    @staticmethod
    def context_acquisition(
        requirements: object = None,
        execution_plan: object = None,
        acquisition_results: Iterable[object] = None,
    ) -> List[str]:
        required_names = {
            f"{getattr(need, 'capability', '')}:{getattr(need, 'target', '') or 'default'}"
            for need in getattr(requirements, "required_needs", []) or []
        }
        unavailable_names = set(getattr(execution_plan, "unavailable_capabilities", []) or [])
        classes: List[str] = []

        if required_names & unavailable_names:
            classes.append(FailureClass.CAPABILITY_GAP)

        for result in acquisition_results or []:
            result_id = result.result_id() if hasattr(result, "result_id") else str(
                getattr(result, "result_id", "")
                or f"{getattr(result, 'capability', '')}:{getattr(result, 'target', '') or 'default'}"
            )
            status = str(getattr(result, "status", "")).lower()
            required = bool(getattr(result, "required", False))
            if required and result_id in required_names and status == "failed":
                classes.append(FailureClass.ACQUISITION_FAILURE)

        return _ordered_unique(classes)

    @staticmethod
    def final_artifact_consistency(selected_hash: str, delivered_hash: str, memory_hash: str = "") -> str:
        hashes = [value for value in [selected_hash, delivered_hash, memory_hash] if value]
        if len(set(hashes)) > 1:
            return FailureClass.FINAL_ARTIFACT_INCONSISTENCY
        return ""

    @staticmethod
    def intent_family_boundary(expected_family: str, actual_family: str) -> str:
        if expected_family and actual_family and expected_family != actual_family:
            return FailureClass.QUERY_PLAN_ERROR
        return ""


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output

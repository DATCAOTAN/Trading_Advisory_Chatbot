from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.answer_compliance import TRADING_INSTRUCTION_PATTERNS
from src.services.agents.backtest_evaluation import MARKET_INTENTS, STATIC_INTENTS


PAPER_STATUSES = {"EVALUATED", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}
OBSERVATION_DIRECTIONS = {"up", "down", "sideways", "volatile_mixed", "unclear"}
CONFIRMATION_STATES = {"confirmed", "partially_confirmed", "not_confirmed", "contradicted", "inconclusive"}
INVALIDATION_STATES = {"invalidated", "partially_invalidated", "not_invalidated", "inconclusive"}
RISK_STATES = {"risk_materialized", "risk_partially_materialized", "risk_not_materialized", "inconclusive"}
DATA_QUALITY_VALUES = {"complete", "partial", "missing", "stale"}

PAPER_SAFETY_PATTERNS = [
    *TRADING_INSTRUCTION_PATTERNS,
    *[
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\bentry\b",
            r"\bstop[-\s]?loss\b",
            r"\btake[-\s]?profit\b",
            r"\bsl\s*[:=]\b",
            r"\btp\s*[:=]\b",
            r"\blot\s+size\b",
            r"\bposition\s+size\b",
            r"\baccount\s+risk\b",
            r"\bmt5\b",
            r"\border\b",
            r"\bexecute\b",
            r"\bbroker\b",
            r"\bleverage\s+recommendation\b",
            r"\bmargin\s+usage\b",
            r"\bpnl\s+optimization\b",
            r"\bwin[-\s]?rate\s+optimization\b",
            r"\bt[aà]i\s+kho[aả]n\s+th[aậ]t\b",
        ]
    ],
]


@dataclass
class SimulatedObservationPoint:
    observation_id: str
    task_id: str
    symbol: str
    timestamp: str
    timeframe: str
    observed_price: float | None = None
    previous_price: float | None = None
    net_change_pct_from_start: float | None = None
    range_pct_from_start: float | None = None
    volatility_proxy: float | None = None
    direction_label: str = "unclear"
    confirmation_state: str = "inconclusive"
    invalidation_state: str = "inconclusive"
    risk_state: str = "inconclusive"
    context_notes: List[str] = field(default_factory=list)
    data_quality: str = "complete"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "task_id": self.task_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "observed_price": self.observed_price,
            "previous_price": self.previous_price,
            "net_change_pct_from_start": self.net_change_pct_from_start,
            "range_pct_from_start": self.range_pct_from_start,
            "volatility_proxy": self.volatility_proxy,
            "direction_label": self.direction_label,
            "confirmation_state": self.confirmation_state,
            "invalidation_state": self.invalidation_state,
            "risk_state": self.risk_state,
            "context_notes": list(self.context_notes),
            "data_quality": self.data_quality,
        }


@dataclass
class PaperTradingEvaluationInput:
    evaluation_id: str
    request_id: str
    journal_id: str
    backtest_evaluation_id: str
    original_answer_time: str
    evaluation_created_at: str
    final_answer_sha256: str
    symbol: str
    parent_intent: str
    task_ids: List[str]
    task_scope_map: Dict[str, str]
    journal_quality_label: str
    journal_review_outcome: str
    backtest_status: str
    backtest_quality_label: str
    strategy_thesis_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    risk_assessment_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    consistency_assessment_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    evidence_bundle_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    source_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    compact_task_snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    simulated_observation_timeline: List[SimulatedObservationPoint] = field(default_factory=list)
    evaluation_policy: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "request_id": self.request_id,
            "journal_id": self.journal_id,
            "backtest_evaluation_id": self.backtest_evaluation_id,
            "original_answer_time": self.original_answer_time,
            "evaluation_created_at": self.evaluation_created_at,
            "final_answer_sha256": self.final_answer_sha256,
            "symbol": self.symbol,
            "parent_intent": self.parent_intent,
            "task_ids": list(self.task_ids),
            "task_scope_map": dict(self.task_scope_map),
            "journal_quality_label": self.journal_quality_label,
            "journal_review_outcome": self.journal_review_outcome,
            "backtest_status": self.backtest_status,
            "backtest_quality_label": self.backtest_quality_label,
            "strategy_thesis_refs_by_task": {key: list(value) for key, value in self.strategy_thesis_refs_by_task.items()},
            "risk_assessment_refs_by_task": {key: list(value) for key, value in self.risk_assessment_refs_by_task.items()},
            "consistency_assessment_refs_by_task": {key: list(value) for key, value in self.consistency_assessment_refs_by_task.items()},
            "evidence_bundle_refs_by_task": {key: list(value) for key, value in self.evidence_bundle_refs_by_task.items()},
            "source_refs_by_task": {key: list(value) for key, value in self.source_refs_by_task.items()},
            "compact_task_snapshots": dict(self.compact_task_snapshots),
            "simulated_observation_timeline": [point.as_dict() for point in self.simulated_observation_timeline],
            "evaluation_policy": dict(self.evaluation_policy),
        }


@dataclass
class PaperTaskEvaluation:
    task_id: str
    intent_family: str
    symbol: str = ""
    thesis_direction: str = ""
    risk_posture: str = ""
    consistency_presentation_mode: str = ""
    confidence_at_answer_time: float | None = None
    timeline_summary: Dict[str, Any] = field(default_factory=dict)
    advisory_followup_outcome: str = "not_applicable"
    confirmation_review: str = "inconclusive"
    invalidation_review: str = "inconclusive"
    risk_review: str = "inconclusive"
    confidence_review: str = "inconclusive"
    review_notes: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    status: str = "EVALUATED"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "thesis_direction": self.thesis_direction,
            "risk_posture": self.risk_posture,
            "consistency_presentation_mode": self.consistency_presentation_mode,
            "confidence_at_answer_time": self.confidence_at_answer_time,
            "timeline_summary": dict(self.timeline_summary),
            "advisory_followup_outcome": self.advisory_followup_outcome,
            "confirmation_review": self.confirmation_review,
            "invalidation_review": self.invalidation_review,
            "risk_review": self.risk_review,
            "confidence_review": self.confidence_review,
            "review_notes": list(self.review_notes),
            "limitations": list(self.limitations),
            "status": self.status,
        }


@dataclass
class PaperTradingEvaluationRecord:
    paper_evaluation_id: str
    request_id: str
    journal_id: str
    backtest_evaluation_id: str
    created_at: str
    original_answer_sha256: str
    status: str
    evaluation_type: str
    quality_label: str
    task_evaluations: List[PaperTaskEvaluation] = field(default_factory=list)
    aggregate_review: Dict[str, Any] = field(default_factory=dict)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    prohibited_outputs_detected: bool = False
    input_chars: int = 0
    payload_chars: int = 0
    latency_ms: float = 0.0
    storage_mode: str = "runtime_artifacts"
    limitations: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "paper_evaluation_id": self.paper_evaluation_id,
            "request_id": self.request_id,
            "journal_id": self.journal_id,
            "backtest_evaluation_id": self.backtest_evaluation_id,
            "created_at": self.created_at,
            "original_answer_sha256": self.original_answer_sha256,
            "status": self.status,
            "evaluation_type": self.evaluation_type,
            "quality_label": self.quality_label,
            "task_evaluations": [item.as_dict() for item in self.task_evaluations],
            "aggregate_review": dict(self.aggregate_review),
            "safety_summary": dict(self.safety_summary),
            "prohibited_outputs_detected": self.prohibited_outputs_detected,
            "input_chars": self.input_chars,
            "payload_chars": self.payload_chars,
            "latency_ms": self.latency_ms,
            "storage_mode": self.storage_mode,
            "limitations": list(self.limitations),
        }


class PaperTradingEvaluationInputBuilder:
    @classmethod
    def build(
        cls,
        journal_record: Mapping[str, Any] | Any | None,
        backtest_record: Mapping[str, Any] | Any | None,
        simulated_observation_timeline: Sequence[SimulatedObservationPoint | Mapping[str, Any]] | None = None,
        runtime_artifacts: Mapping[str, Any] | None = None,
        compact_task_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
        evaluation_id: str = "",
        evaluation_policy: Mapping[str, Any] | None = None,
    ) -> PaperTradingEvaluationInput:
        journal = _as_mapping(journal_record)
        backtest = _as_mapping(backtest_record)
        artifacts = dict(runtime_artifacts or {})
        snapshots = {
            key: dict(value)
            for key, value in (
                compact_task_snapshots
                or artifacts.get("compact_task_analysis_snapshots")
                or journal.get("compact_task_analysis_snapshots")
                or {}
            ).items()
            if isinstance(value, Mapping)
        }
        task_reviews = [dict(item) for item in journal.get("task_reviews", []) if isinstance(item, Mapping)]
        task_ids = _ordered_unique([str(task.get("task_id")) for task in task_reviews] + [str(task_id) for task_id in snapshots.keys()])
        task_scope_map = {
            str(task.get("task_id")): str(task.get("intent_family") or "")
            for task in task_reviews
            if task.get("task_id")
        }
        for task_id, snapshot in snapshots.items():
            task_scope_map.setdefault(task_id, str(snapshot.get("intent_family") or ""))
        points = [cls._point(item) for item in simulated_observation_timeline or []]
        policy = dict(evaluation_policy or {})
        policy["no_trade_simulation"] = True
        policy["no_position_sizing"] = True
        policy["no_execution"] = True
        policy["no_account_data"] = True
        policy["no_pnl_optimization"] = True
        policy.setdefault(
            "allowed_outcomes",
            [
                "thesis_remained_valid",
                "thesis_partially_valid",
                "thesis_invalidated",
                "thesis_inconclusive",
                "not_applicable",
            ],
        )
        request_id = str(journal.get("request_id") or backtest.get("request_id") or "")
        return PaperTradingEvaluationInput(
            evaluation_id=evaluation_id or f"paper_eval:{request_id or journal.get('journal_id') or 'manual'}",
            request_id=request_id,
            journal_id=str(journal.get("journal_id") or ""),
            backtest_evaluation_id=str(backtest.get("evaluation_id") or ""),
            original_answer_time=str(journal.get("created_at") or ""),
            evaluation_created_at=datetime.now(timezone.utc).isoformat(),
            final_answer_sha256=str(journal.get("final_answer_sha256") or backtest.get("original_answer_sha256") or ""),
            symbol=cls._symbol(snapshots, points),
            parent_intent=cls._parent_intent(artifacts, task_scope_map),
            task_ids=task_ids,
            task_scope_map=task_scope_map,
            journal_quality_label=str(journal.get("quality_label") or ""),
            journal_review_outcome=str(journal.get("review_outcome") or ""),
            backtest_status=str(backtest.get("status") or ""),
            backtest_quality_label=str(backtest.get("quality_label") or ""),
            strategy_thesis_refs_by_task=cls._refs_by_task(snapshots, "strategy", "thesis_ref"),
            risk_assessment_refs_by_task=cls._refs_by_task(snapshots, "risk", "risk_ref"),
            consistency_assessment_refs_by_task=cls._refs_by_task(snapshots, "consistency", "consistency_ref"),
            evidence_bundle_refs_by_task=cls._evidence_refs(journal, snapshots),
            source_refs_by_task=cls._source_refs(journal, snapshots),
            compact_task_snapshots=snapshots,
            simulated_observation_timeline=points,
            evaluation_policy=policy,
        )

    @staticmethod
    def _point(item: SimulatedObservationPoint | Mapping[str, Any]) -> SimulatedObservationPoint:
        if isinstance(item, SimulatedObservationPoint):
            return item
        data = dict(item or {})
        return SimulatedObservationPoint(
            observation_id=str(data.get("observation_id") or ""),
            task_id=str(data.get("task_id") or ""),
            symbol=str(data.get("symbol") or ""),
            timestamp=str(data.get("timestamp") or ""),
            timeframe=str(data.get("timeframe") or ""),
            observed_price=_float(data.get("observed_price")),
            previous_price=_float(data.get("previous_price")),
            net_change_pct_from_start=_float(data.get("net_change_pct_from_start")),
            range_pct_from_start=_float(data.get("range_pct_from_start")),
            volatility_proxy=_float(data.get("volatility_proxy")),
            direction_label=str(data.get("direction_label") or "unclear"),
            confirmation_state=str(data.get("confirmation_state") or "inconclusive"),
            invalidation_state=str(data.get("invalidation_state") or "inconclusive"),
            risk_state=str(data.get("risk_state") or "inconclusive"),
            context_notes=[str(value) for value in data.get("context_notes") or []],
            data_quality=str(data.get("data_quality") or "complete"),
        )

    @staticmethod
    def _symbol(snapshots: Mapping[str, Mapping[str, Any]], points: Sequence[SimulatedObservationPoint]) -> str:
        for snapshot in snapshots.values():
            if snapshot.get("symbol"):
                return str(snapshot.get("symbol"))
        for point in points:
            if point.symbol:
                return point.symbol
        return ""

    @staticmethod
    def _parent_intent(artifacts: Mapping[str, Any], task_scope_map: Mapping[str, str]) -> str:
        agent_runtime = artifacts.get("agent_runtime") if isinstance(artifacts.get("agent_runtime"), Mapping) else {}
        plan = agent_runtime.get("execution_plan") if isinstance(agent_runtime.get("execution_plan"), Mapping) else {}
        if plan.get("parent_intent"):
            return str(plan.get("parent_intent"))
        scopes = {scope for scope in task_scope_map.values() if scope}
        return "multi_intent" if len(scopes) > 1 else (next(iter(scopes)) if scopes else "")

    @staticmethod
    def _refs_by_task(snapshots: Mapping[str, Mapping[str, Any]], section: str, ref_key: str) -> Dict[str, List[str]]:
        refs: Dict[str, List[str]] = {}
        for task_id, snapshot in snapshots.items():
            payload = snapshot.get(section) if isinstance(snapshot.get(section), Mapping) else {}
            ref = payload.get(ref_key)
            if ref:
                refs.setdefault(task_id, []).append(str(ref))
        return refs

    @staticmethod
    def _evidence_refs(journal: Mapping[str, Any], snapshots: Mapping[str, Mapping[str, Any]]) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = {}
        evidence_summary = journal.get("evidence_summary") if isinstance(journal.get("evidence_summary"), Mapping) else {}
        for ref in evidence_summary.get("evidence_bundle_refs") or []:
            value = str(ref)
            task_id = value.split(":")[-1] if ":" in value else ""
            if task_id:
                output.setdefault(task_id, []).append(value)
        for task_id, snapshot in snapshots.items():
            ref = snapshot.get("evidence_bundle_ref")
            if ref:
                output.setdefault(task_id, []).append(str(ref))
        return {key: _ordered_unique(value) for key, value in output.items()}

    @staticmethod
    def _source_refs(journal: Mapping[str, Any], snapshots: Mapping[str, Mapping[str, Any]]) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = {}
        source_refs = (journal.get("evidence_summary") or {}).get("source_refs") if isinstance(journal.get("evidence_summary"), Mapping) else []
        if source_refs:
            output["__all__"] = [str(ref) for ref in source_refs]
        for task_id, snapshot in snapshots.items():
            refs = snapshot.get("allowed_source_refs") or []
            if refs:
                output[task_id] = _ordered_unique([str(ref) for ref in refs])
        return output


class PaperTradingEvaluationSafetyValidator:
    @classmethod
    def validate_record(cls, record: PaperTradingEvaluationRecord) -> Dict[str, Any]:
        payload = json.dumps(record.as_dict(), ensure_ascii=False, default=str)
        detected = any(pattern.search(payload) for pattern in PAPER_SAFETY_PATTERNS)
        execution_allowed = bool((record.safety_summary or {}).get("execution_allowed"))
        status = "FAIL" if detected or execution_allowed else "PASS"
        return {
            "no_trade_simulation": True,
            "no_position_sizing": True,
            "no_execution": True,
            "no_account_data": True,
            "no_pnl_optimization": True,
            "execution_allowed": execution_allowed,
            "prohibited_output_detected": detected,
            "safety_status": status,
        }


class PaperTradingEvaluationAgent:
    @classmethod
    def evaluate(cls, evaluation_input: PaperTradingEvaluationInput | Mapping[str, Any]) -> PaperTradingEvaluationRecord:
        started = time.perf_counter()
        if isinstance(evaluation_input, PaperTradingEvaluationInput):
            data = evaluation_input
        else:
            data = PaperTradingEvaluationInputBuilder.build(
                journal_record=evaluation_input.get("journal_record") if isinstance(evaluation_input, Mapping) else {},
                backtest_record=evaluation_input.get("backtest_record") if isinstance(evaluation_input, Mapping) else {},
                simulated_observation_timeline=evaluation_input.get("simulated_observation_timeline", []) if isinstance(evaluation_input, Mapping) else [],
            )
        input_chars = len(json.dumps(data.as_dict(), ensure_ascii=False, default=str))
        task_evaluations = [cls._evaluate_task(data, task_id) for task_id in data.task_ids]
        status = cls._status(data, task_evaluations)
        quality_label = cls._quality_label(data, status)
        record = PaperTradingEvaluationRecord(
            paper_evaluation_id=data.evaluation_id,
            request_id=data.request_id,
            journal_id=data.journal_id,
            backtest_evaluation_id=data.backtest_evaluation_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            original_answer_sha256=data.final_answer_sha256,
            status=status,
            evaluation_type="advisory_followup_evaluation",
            quality_label=quality_label,
            task_evaluations=task_evaluations,
            aggregate_review=cls._aggregate(task_evaluations),
            safety_summary={
                "no_trade_simulation": True,
                "no_position_sizing": True,
                "no_execution": True,
                "no_account_data": True,
                "no_pnl_optimization": True,
                "execution_allowed": False,
                "safety_status": "PASS",
            },
            input_chars=input_chars,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            limitations=cls._limitations(data, task_evaluations),
        )
        safety = PaperTradingEvaluationSafetyValidator.validate_record(record)
        record.safety_summary = safety
        record.prohibited_outputs_detected = bool(safety.get("prohibited_output_detected"))
        if safety.get("safety_status") == "FAIL":
            record.status = "SKIPPED"
            record.quality_label = "invalid_input"
            record.limitations = _ordered_unique(record.limitations + ["safety_validation_failed"])
        record.payload_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, default=str))
        cls._log(record)
        return record

    @classmethod
    def _evaluate_task(cls, data: PaperTradingEvaluationInput, task_id: str) -> PaperTaskEvaluation:
        snapshot = data.compact_task_snapshots.get(task_id) or {}
        intent = str(data.task_scope_map.get(task_id) or snapshot.get("intent_family") or "")
        if intent in STATIC_INTENTS or intent not in MARKET_INTENTS:
            return PaperTaskEvaluation(
                task_id=task_id,
                intent_family=intent,
                symbol=str(snapshot.get("symbol") or ""),
                timeline_summary={"observations_count": 0, "data_quality": "not_applicable"},
                advisory_followup_outcome="not_applicable",
                review_notes=["paper_evaluation_not_applicable_for_static_task"],
                status="SKIPPED",
            )
        points = [point for point in data.simulated_observation_timeline if point.task_id == task_id and point.data_quality not in {"missing", "stale"}]
        strategy = snapshot.get("strategy") if isinstance(snapshot.get("strategy"), Mapping) else {}
        risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), Mapping) else {}
        consistency = snapshot.get("consistency") if isinstance(snapshot.get("consistency"), Mapping) else {}
        if not points:
            return PaperTaskEvaluation(
                task_id=task_id,
                intent_family=intent,
                symbol=str(snapshot.get("symbol") or data.symbol or ""),
                thesis_direction=str(strategy.get("thesis_direction") or ""),
                risk_posture=str(risk.get("risk_posture") or ""),
                consistency_presentation_mode=str(consistency.get("final_presentation_mode") or ""),
                confidence_at_answer_time=_confidence(strategy, consistency),
                timeline_summary={"observations_count": 0, "data_quality": "missing"},
                advisory_followup_outcome="thesis_inconclusive",
                limitations=["missing_simulated_observation_timeline"],
                status="INSUFFICIENT_DATA",
            )
        summary = _timeline_summary(points)
        confirmation_review = cls._confirmation_review(summary)
        invalidation_review = cls._invalidation_review(summary)
        risk_review = cls._risk_review(summary, risk)
        outcome = cls._advisory_outcome(summary, strategy)
        confidence_review = cls._confidence_review(summary, strategy, risk, consistency, outcome)
        return PaperTaskEvaluation(
            task_id=task_id,
            intent_family=intent,
            symbol=str(snapshot.get("symbol") or points[0].symbol or data.symbol or ""),
            thesis_direction=str(strategy.get("thesis_direction") or ""),
            risk_posture=str(risk.get("risk_posture") or ""),
            consistency_presentation_mode=str(consistency.get("final_presentation_mode") or ""),
            confidence_at_answer_time=_confidence(strategy, consistency),
            timeline_summary=summary,
            advisory_followup_outcome=outcome,
            confirmation_review=confirmation_review,
            invalidation_review=invalidation_review,
            risk_review=risk_review,
            confidence_review=confidence_review,
            review_notes=_ordered_unique([note for point in points for note in point.context_notes])[:5],
            limitations=_ordered_unique(
                [str(item) for item in strategy.get("limitations", []) or []]
                + [str(item) for item in risk.get("limitations", []) or []]
                + [str(item) for item in consistency.get("limitations", []) or []]
            )[:5],
            status="EVALUATED",
        )

    @staticmethod
    def _confirmation_review(summary: Mapping[str, Any]) -> str:
        confirmed = int(summary.get("confirmed_count") or 0)
        partial = int(summary.get("partially_confirmed_count") or 0)
        contradicted = int(summary.get("contradicted_count") or 0)
        if confirmed > 0:
            return "confirmation_observed"
        if partial > 0:
            return "confirmation_observed"
        if contradicted > 0:
            return "confirmation_conflicted"
        return "confirmation_missing" if int(summary.get("observations_count") or 0) else "inconclusive"

    @staticmethod
    def _invalidation_review(summary: Mapping[str, Any]) -> str:
        invalidated = int(summary.get("invalidated_count") or 0)
        partial = int(summary.get("partially_invalidated_count") or 0)
        if invalidated > 0:
            return "invalidation_observed"
        if partial > 0:
            return "partial_invalidation"
        return "invalidation_not_observed" if int(summary.get("observations_count") or 0) else "inconclusive"

    @staticmethod
    def _risk_review(summary: Mapping[str, Any], risk: Mapping[str, Any]) -> str:
        materialized = int(summary.get("risk_materialized_count") or 0)
        partial = int(summary.get("risk_partially_materialized_count") or 0)
        elevated = str(risk.get("overall_risk_level") or "").lower() in {"elevated", "high"}
        if materialized > 0:
            return "risk_materialized"
        if partial > 0:
            return "risk_partially_materialized"
        if elevated and summary.get("volatile_count"):
            return "risk_partially_materialized"
        return "risk_not_materialized" if int(summary.get("observations_count") or 0) else "inconclusive"

    @staticmethod
    def _advisory_outcome(summary: Mapping[str, Any], strategy: Mapping[str, Any]) -> str:
        observations = int(summary.get("observations_count") or 0)
        if not observations:
            return "thesis_inconclusive"
        invalidated = int(summary.get("invalidated_count") or 0)
        contradicted = int(summary.get("contradicted_count") or 0)
        confirmed = int(summary.get("confirmed_count") or 0)
        thesis = _normalized_thesis_direction(str(strategy.get("thesis_direction") or ""))
        mixed_timeline = int(summary.get("mixed_count") or 0) >= max(1, observations // 2)
        if invalidated > 0 or contradicted >= max(2, observations // 2):
            return "thesis_invalidated"
        if confirmed > 0 and invalidated == 0 and contradicted == 0:
            return "thesis_remained_valid"
        if thesis == "mixed" and mixed_timeline:
            return "thesis_remained_valid"
        if confirmed > 0 or contradicted > 0:
            return "thesis_partially_valid"
        return "thesis_inconclusive"

    @staticmethod
    def _confidence_review(
        summary: Mapping[str, Any],
        strategy: Mapping[str, Any],
        risk: Mapping[str, Any],
        consistency: Mapping[str, Any],
        outcome: str,
    ) -> str:
        thesis = _normalized_thesis_direction(str(strategy.get("thesis_direction") or ""))
        confidence = _raw_strategy_confidence(strategy) or _confidence(strategy, consistency) or 0.0
        mode = str(consistency.get("final_presentation_mode") or "").lower()
        choppy = int(summary.get("mixed_count") or 0) > 0 or int(summary.get("volatile_count") or 0) > 0
        if thesis == "mixed" and choppy:
            return "reasonable"
        if mode in {"mixed_or_uncertain", "cautious_conditional", "risk_first", "insufficient_context"} and choppy:
            return "reasonable"
        if outcome == "thesis_invalidated" and confidence >= 0.65:
            return "overconfident"
        if outcome == "thesis_remained_valid" and confidence <= 0.4:
            return "underconfident"
        if str(risk.get("risk_posture") or "").lower() in {"conflicting_context", "thesis_fragile"} and choppy:
            return "reasonable"
        return "reasonable" if outcome in {"thesis_remained_valid", "thesis_partially_valid"} else "inconclusive"

    @staticmethod
    def _status(data: PaperTradingEvaluationInput, task_evaluations: Sequence[PaperTaskEvaluation]) -> str:
        if not data.journal_id or not data.final_answer_sha256:
            return "SKIPPED"
        if not data.backtest_evaluation_id:
            return "SKIPPED"
        market_tasks = [item for item in task_evaluations if item.intent_family in MARKET_INTENTS]
        if not market_tasks:
            return "SKIPPED"
        if any(item.status == "INSUFFICIENT_DATA" for item in market_tasks):
            return "INSUFFICIENT_DATA"
        if any(item.status == "EVALUATED" for item in market_tasks):
            if data.journal_quality_label in {"unsafe_or_noncompliant", "failed_validation", "incomplete"}:
                return "EVALUATED_WITH_WARNINGS"
            if data.backtest_status in {"EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}:
                return "EVALUATED_WITH_WARNINGS"
            return "EVALUATED"
        return "SKIPPED"

    @staticmethod
    def _quality_label(data: PaperTradingEvaluationInput, status: str) -> str:
        if status == "EVALUATED":
            return "useful_for_review"
        if status == "EVALUATED_WITH_WARNINGS":
            return "limited_review"
        if status == "INSUFFICIENT_DATA":
            return "insufficient_data"
        return "invalid_input" if not data.journal_id or not data.backtest_evaluation_id else "limited_review"

    @staticmethod
    def _aggregate(task_evaluations: Sequence[PaperTaskEvaluation]) -> Dict[str, Any]:
        evaluated = [item.task_id for item in task_evaluations if item.status == "EVALUATED"]
        not_applicable = [item.task_id for item in task_evaluations if item.advisory_followup_outcome == "not_applicable"]
        inconclusive = [item.task_id for item in task_evaluations if item.advisory_followup_outcome == "thesis_inconclusive"]
        invalidated = [item.task_id for item in task_evaluations if item.advisory_followup_outcome == "thesis_invalidated"]
        lessons = []
        if invalidated:
            lessons.append("review_invalidated_advisory_thesis")
        if any(item.risk_review in {"risk_materialized", "risk_partially_materialized"} for item in task_evaluations):
            lessons.append("review_risk_followup")
        if any(item.confirmation_review == "confirmation_conflicted" for item in task_evaluations):
            lessons.append("review_confirmation_conflict")
        return {
            "evaluated_tasks": evaluated,
            "not_applicable_tasks": not_applicable,
            "inconclusive_tasks": inconclusive,
            "invalidated_tasks": invalidated,
            "main_lessons": lessons or ["no_paper_followup_action_required"],
            "review_priority": "high" if invalidated else ("medium" if lessons else "low"),
        }

    @staticmethod
    def _limitations(data: PaperTradingEvaluationInput, task_evaluations: Sequence[PaperTaskEvaluation]) -> List[str]:
        limitations: List[str] = []
        if data.journal_quality_label in {"unsafe_or_noncompliant", "failed_validation", "incomplete"}:
            limitations.append("journal_record_degraded")
        if data.backtest_status in {"EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}:
            limitations.append(f"backtest_status:{data.backtest_status or 'missing'}")
        if not data.backtest_evaluation_id:
            limitations.append("missing_backtest_evaluation_record")
        if any(item.status == "INSUFFICIENT_DATA" for item in task_evaluations):
            limitations.append("missing_simulated_observation_timeline")
        return _ordered_unique(limitations)

    @staticmethod
    def _log(record: PaperTradingEvaluationRecord) -> None:
        flags = list(record.aggregate_review.get("main_lessons") or [])
        print(
            "[PaperTradingEvaluation] "
            f"evaluation_id={record.paper_evaluation_id} request_id={record.request_id} "
            f"status={record.status} tasks={len(record.task_evaluations)} quality_label={record.quality_label} "
            f"flags={flags} input_chars={record.input_chars} payload_chars={record.payload_chars} "
            f"latency_ms={record.latency_ms}"
        )
        for task in record.task_evaluations:
            print(
                "[PaperTradingEvaluationTask] "
                f"task_id={task.task_id} intent_family={task.intent_family} symbol={task.symbol} "
                f"observations={task.timeline_summary.get('observations_count', 0)} "
                f"advisory_followup_outcome={task.advisory_followup_outcome} "
                f"confirmation_review={task.confirmation_review} "
                f"invalidation_review={task.invalidation_review} "
                f"risk_review={task.risk_review} confidence_review={task.confidence_review} status={task.status}"
            )
        print(
            "[PaperTradingEvaluationSafety] "
            f"no_trade_simulation={str(record.safety_summary.get('no_trade_simulation')).lower()} "
            f"no_position_sizing={str(record.safety_summary.get('no_position_sizing')).lower()} "
            f"no_execution={str(record.safety_summary.get('no_execution')).lower()} "
            f"no_account_data={str(record.safety_summary.get('no_account_data')).lower()} "
            f"no_pnl_optimization={str(record.safety_summary.get('no_pnl_optimization')).lower()} "
            f"execution_allowed={str(record.safety_summary.get('execution_allowed')).lower()} "
            f"status={record.safety_summary.get('safety_status')}"
        )
        print("[PaperTradingEvaluationStorage] mode=runtime_artifacts status=PASS")


def record_paper_trading_evaluation(
    runtime_artifacts: Dict[str, Any] | None,
    simulated_observation_timeline: Sequence[SimulatedObservationPoint | Mapping[str, Any]] | None = None,
    evaluation_policy: Mapping[str, Any] | None = None,
    evaluation_id: str = "",
) -> PaperTradingEvaluationRecord | None:
    if runtime_artifacts is None:
        return None
    evaluation_input = PaperTradingEvaluationInputBuilder.build(
        journal_record=runtime_artifacts.get("journal_review"),
        backtest_record=runtime_artifacts.get("backtest_evaluation"),
        simulated_observation_timeline=simulated_observation_timeline or [],
        runtime_artifacts=runtime_artifacts,
        evaluation_id=evaluation_id,
        evaluation_policy=evaluation_policy,
    )
    record = PaperTradingEvaluationAgent.evaluate(evaluation_input)
    runtime_artifacts["paper_trading_evaluation"] = record.as_dict()
    return record


def _timeline_summary(points: Sequence[SimulatedObservationPoint]) -> Dict[str, Any]:
    return {
        "observations_count": len(points),
        "confirmed_count": sum(1 for point in points if point.confirmation_state == "confirmed"),
        "partially_confirmed_count": sum(1 for point in points if point.confirmation_state == "partially_confirmed"),
        "contradicted_count": sum(1 for point in points if point.confirmation_state == "contradicted"),
        "invalidated_count": sum(1 for point in points if point.invalidation_state == "invalidated"),
        "partially_invalidated_count": sum(1 for point in points if point.invalidation_state == "partially_invalidated"),
        "risk_materialized_count": sum(1 for point in points if point.risk_state == "risk_materialized"),
        "risk_partially_materialized_count": sum(1 for point in points if point.risk_state == "risk_partially_materialized"),
        "mixed_count": sum(1 for point in points if point.direction_label in {"sideways", "volatile_mixed", "unclear"}),
        "volatile_count": sum(1 for point in points if point.direction_label == "volatile_mixed" or _float(point.volatility_proxy, 0.0) >= 2.0),
        "data_quality": _data_quality(points),
    }


def _data_quality(points: Sequence[SimulatedObservationPoint]) -> str:
    qualities = {point.data_quality for point in points}
    if not points:
        return "missing"
    if "missing" in qualities:
        return "missing"
    if "stale" in qualities:
        return "stale"
    if "partial" in qualities:
        return "partial"
    return "complete"


def _as_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "as_dict"):
        return dict(value.as_dict())
    return {}


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_thesis_direction(value: str) -> str:
    text = str(value or "").lower()
    if "bull" in text or "up" in text:
        return "bullish"
    if "bear" in text or "down" in text:
        return "bearish"
    if text in {"mixed", "balanced", "no_clear_bias"} or "mixed" in text or "balanced" in text:
        return "mixed"
    return "unclear"


def _confidence(strategy: Mapping[str, Any], consistency: Mapping[str, Any]) -> float | None:
    confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), Mapping) else {}
    reconciliation = consistency.get("confidence_reconciliation") if isinstance(consistency.get("confidence_reconciliation"), Mapping) else {}
    for value in (reconciliation.get("final_confidence"), confidence.get("value"), confidence.get("ceiling")):
        parsed = _float(value)
        if parsed is not None:
            return parsed
    return None


def _raw_strategy_confidence(strategy: Mapping[str, Any]) -> float | None:
    confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), Mapping) else {}
    return _float(confidence.get("value"))


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.answer_compliance import (
    TRADING_INSTRUCTION_PATTERNS,
    AgentAnswerComplianceInputBuilder,
)


MARKET_INTENTS = {"market_state_analysis", "macro_market_impact"}
STATIC_INTENTS = {"book_concept_explanation", "static_explanation"}

EVALUATION_STATUSES = {"EVALUATED", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}
DIRECTION_LABELS = {"up", "down", "sideways", "volatile_mixed", "unclear"}
DATA_QUALITY_VALUES = {"complete", "partial", "missing", "stale"}

EVALUATION_SAFETY_PATTERNS = [
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
            r"\bpnl\s+optimization\b",
            r"\bwin[-\s]?rate\s+optimization\b",
        ]
    ],
]


@dataclass
class HistoricalObservationWindow:
    window_id: str
    task_id: str
    symbol: str
    start_time: str
    end_time: str
    timeframe: str
    start_price: float | None = None
    end_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    net_change_pct: float | None = None
    realized_range_pct: float | None = None
    volatility_proxy: float | None = None
    direction_label: str = "unclear"
    notable_market_behavior: List[str] = field(default_factory=list)
    data_quality: str = "complete"

    @classmethod
    def from_observations(
        cls,
        window_id: str,
        task_id: str,
        symbol: str,
        start_time: str,
        end_time: str,
        timeframe: str,
        observations: Sequence[Mapping[str, Any]] | None,
    ) -> "HistoricalObservationWindow":
        rows = [dict(row) for row in (observations or []) if isinstance(row, Mapping)]
        if not rows:
            return cls(
                window_id=window_id,
                task_id=task_id,
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                timeframe=timeframe,
                data_quality="missing",
                direction_label="unclear",
            )
        first = rows[0]
        last = rows[-1]
        start_price = _float(first.get("open") or first.get("close"))
        end_price = _float(last.get("close") or last.get("open"))
        highs = [_float(row.get("high")) for row in rows]
        lows = [_float(row.get("low")) for row in rows]
        high_price = max([value for value in highs if value is not None], default=end_price)
        low_price = min([value for value in lows if value is not None], default=start_price)
        net = _pct_change(start_price, end_price)
        realized = _pct_change(low_price, high_price)
        direction = _direction_from_change(net, realized)
        return cls(
            window_id=window_id,
            task_id=task_id,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
            start_price=start_price,
            end_price=end_price,
            high_price=high_price,
            low_price=low_price,
            net_change_pct=net,
            realized_range_pct=realized,
            volatility_proxy=realized,
            direction_label=direction,
            notable_market_behavior=_behavior_notes(direction, net, realized),
            data_quality="complete",
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "task_id": self.task_id,
            "symbol": self.symbol,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "timeframe": self.timeframe,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "net_change_pct": self.net_change_pct,
            "realized_range_pct": self.realized_range_pct,
            "volatility_proxy": self.volatility_proxy,
            "direction_label": self.direction_label,
            "notable_market_behavior": list(self.notable_market_behavior),
            "data_quality": self.data_quality,
        }


@dataclass
class BacktestEvaluationInput:
    evaluation_id: str
    request_id: str
    journal_id: str
    created_at: str
    original_answer_time: str
    symbol: str
    parent_intent: str
    task_ids: List[str]
    task_scope_map: Dict[str, str]
    final_answer_sha256: str
    journal_quality_label: str
    journal_review_outcome: str
    strategy_thesis_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    risk_assessment_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    consistency_assessment_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    evidence_bundle_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    source_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    compact_task_snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_observation_windows: List[HistoricalObservationWindow] = field(default_factory=list)
    evaluation_policy: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "request_id": self.request_id,
            "journal_id": self.journal_id,
            "created_at": self.created_at,
            "original_answer_time": self.original_answer_time,
            "symbol": self.symbol,
            "parent_intent": self.parent_intent,
            "task_ids": list(self.task_ids),
            "task_scope_map": dict(self.task_scope_map),
            "final_answer_sha256": self.final_answer_sha256,
            "journal_quality_label": self.journal_quality_label,
            "journal_review_outcome": self.journal_review_outcome,
            "strategy_thesis_refs_by_task": {key: list(value) for key, value in self.strategy_thesis_refs_by_task.items()},
            "risk_assessment_refs_by_task": {key: list(value) for key, value in self.risk_assessment_refs_by_task.items()},
            "consistency_assessment_refs_by_task": {key: list(value) for key, value in self.consistency_assessment_refs_by_task.items()},
            "evidence_bundle_refs_by_task": {key: list(value) for key, value in self.evidence_bundle_refs_by_task.items()},
            "source_refs_by_task": {key: list(value) for key, value in self.source_refs_by_task.items()},
            "compact_task_snapshots": dict(self.compact_task_snapshots),
            "historical_observation_windows": [window.as_dict() for window in self.historical_observation_windows],
            "evaluation_policy": dict(self.evaluation_policy),
        }


@dataclass
class BacktestTaskEvaluation:
    task_id: str
    intent_family: str
    symbol: str = ""
    observation_window_id: str = ""
    thesis_direction: str = ""
    consistency_presentation_mode: str = ""
    risk_posture: str = ""
    confidence_at_answer_time: float | None = None
    observed_direction: str = "unclear"
    observed_volatility: float | None = None
    observed_range_pct: float | None = None
    thesis_alignment: str = "not_applicable"
    risk_materialization: str = "inconclusive"
    confidence_calibration: str = "inconclusive"
    review_notes: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    status: str = "EVALUATED"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "observation_window_id": self.observation_window_id,
            "thesis_direction": self.thesis_direction,
            "consistency_presentation_mode": self.consistency_presentation_mode,
            "risk_posture": self.risk_posture,
            "confidence_at_answer_time": self.confidence_at_answer_time,
            "observed_direction": self.observed_direction,
            "observed_volatility": self.observed_volatility,
            "observed_range_pct": self.observed_range_pct,
            "thesis_alignment": self.thesis_alignment,
            "risk_materialization": self.risk_materialization,
            "confidence_calibration": self.confidence_calibration,
            "review_notes": list(self.review_notes),
            "limitations": list(self.limitations),
            "status": self.status,
        }


@dataclass
class BacktestEvaluationRecord:
    evaluation_id: str
    request_id: str
    journal_id: str
    created_at: str
    original_answer_sha256: str
    status: str
    evaluation_type: str
    quality_label: str
    task_evaluations: List[BacktestTaskEvaluation] = field(default_factory=list)
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
            "evaluation_id": self.evaluation_id,
            "request_id": self.request_id,
            "journal_id": self.journal_id,
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


class BacktestEvaluationInputBuilder:
    @classmethod
    def build(
        cls,
        journal_record: Mapping[str, Any] | Any | None,
        historical_observation_windows: Sequence[HistoricalObservationWindow | Mapping[str, Any]] | None = None,
        runtime_artifacts: Mapping[str, Any] | None = None,
        compact_task_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
        evaluation_id: str = "",
        evaluation_policy: Mapping[str, Any] | None = None,
    ) -> BacktestEvaluationInput:
        journal = _as_mapping(journal_record)
        artifacts = dict(runtime_artifacts or {})
        snapshots = {
            key: dict(value)
            for key, value in (
                compact_task_snapshots
                or artifacts.get("compact_task_analysis_snapshots")
                or journal.get("compact_task_analysis_snapshots")
                or cls._snapshots_from_runtime_artifacts(artifacts)
                or {}
            ).items()
            if isinstance(value, Mapping)
        }
        task_reviews = [dict(item) for item in journal.get("task_reviews", []) if isinstance(item, Mapping)]
        task_ids = _ordered_unique(
            [str(task.get("task_id")) for task in task_reviews]
            + [str(task_id) for task_id in snapshots.keys()]
        )
        task_scope_map = {
            str(task.get("task_id")): str(task.get("intent_family") or "")
            for task in task_reviews
            if task.get("task_id")
        }
        for task_id, snapshot in snapshots.items():
            task_scope_map.setdefault(task_id, str(snapshot.get("intent_family") or ""))
        windows = [cls._window(item) for item in historical_observation_windows or []]
        request_id = str(journal.get("request_id") or (artifacts.get("agent_runtime", {}).get("execution_plan", {}) or {}).get("request_id") or "")
        policy = dict(evaluation_policy or {})
        policy.setdefault("horizons", [])
        policy.setdefault("allowed_metrics", ["direction_label", "net_change_pct", "realized_range_pct", "volatility_proxy"])
        policy["no_trade_simulation"] = True
        policy["no_position_sizing"] = True
        policy["no_execution"] = True
        return BacktestEvaluationInput(
            evaluation_id=evaluation_id or f"backtest_eval:{request_id or journal.get('journal_id') or 'manual'}",
            request_id=request_id,
            journal_id=str(journal.get("journal_id") or ""),
            created_at=datetime.now(timezone.utc).isoformat(),
            original_answer_time=str(journal.get("created_at") or ""),
            symbol=cls._symbol(snapshots, windows),
            parent_intent=cls._parent_intent(artifacts, task_scope_map),
            task_ids=task_ids,
            task_scope_map=task_scope_map,
            final_answer_sha256=str(journal.get("final_answer_sha256") or ""),
            journal_quality_label=str(journal.get("quality_label") or ""),
            journal_review_outcome=str(journal.get("review_outcome") or ""),
            strategy_thesis_refs_by_task=cls._refs_by_task(snapshots, "strategy", "thesis_ref"),
            risk_assessment_refs_by_task=cls._refs_by_task(snapshots, "risk", "risk_ref"),
            consistency_assessment_refs_by_task=cls._refs_by_task(snapshots, "consistency", "consistency_ref"),
            evidence_bundle_refs_by_task=cls._evidence_refs(journal, snapshots),
            source_refs_by_task=cls._source_refs(journal, snapshots),
            compact_task_snapshots=snapshots,
            historical_observation_windows=windows,
            evaluation_policy=policy,
        )

    @staticmethod
    def _snapshots_from_runtime_artifacts(artifacts: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        if not artifacts:
            return {}
        final_artifact = artifacts.get("final_answer_artifact") if isinstance(artifacts.get("final_answer_artifact"), Mapping) else {}
        final_text = str(final_artifact.get("content") or "")
        try:
            built = AgentAnswerComplianceInputBuilder.build(final_text, artifacts, artifacts.get("answer_contracts") or [])
            return {key: dict(value) for key, value in built.task_analysis_snapshots_by_task.items()}
        except Exception:
            return {}

    @staticmethod
    def _window(item: HistoricalObservationWindow | Mapping[str, Any]) -> HistoricalObservationWindow:
        if isinstance(item, HistoricalObservationWindow):
            return item
        data = dict(item or {})
        return HistoricalObservationWindow(
            window_id=str(data.get("window_id") or ""),
            task_id=str(data.get("task_id") or ""),
            symbol=str(data.get("symbol") or ""),
            start_time=str(data.get("start_time") or ""),
            end_time=str(data.get("end_time") or ""),
            timeframe=str(data.get("timeframe") or ""),
            start_price=_float(data.get("start_price")),
            end_price=_float(data.get("end_price")),
            high_price=_float(data.get("high_price")),
            low_price=_float(data.get("low_price")),
            net_change_pct=_float(data.get("net_change_pct")),
            realized_range_pct=_float(data.get("realized_range_pct")),
            volatility_proxy=_float(data.get("volatility_proxy")),
            direction_label=str(data.get("direction_label") or "unclear"),
            notable_market_behavior=[str(value) for value in data.get("notable_market_behavior") or []],
            data_quality=str(data.get("data_quality") or "complete"),
        )

    @staticmethod
    def _symbol(snapshots: Mapping[str, Mapping[str, Any]], windows: Sequence[HistoricalObservationWindow]) -> str:
        for snapshot in snapshots.values():
            if snapshot.get("symbol"):
                return str(snapshot.get("symbol"))
        for window in windows:
            if window.symbol:
                return window.symbol
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


class BacktestEvaluationSafetyValidator:
    @classmethod
    def validate_record(cls, record: BacktestEvaluationRecord) -> Dict[str, Any]:
        payload = json.dumps(record.as_dict(), ensure_ascii=False, default=str)
        detected = any(pattern.search(payload) for pattern in EVALUATION_SAFETY_PATTERNS)
        execution_allowed = bool((record.safety_summary or {}).get("execution_allowed"))
        status = "FAIL" if detected or execution_allowed else "PASS"
        return {
            "no_trade_simulation": True,
            "no_position_sizing": True,
            "no_execution": True,
            "execution_allowed": execution_allowed,
            "prohibited_output_detected": detected,
            "safety_status": status,
        }


class BacktestEvaluationAgent:
    @classmethod
    def evaluate(cls, evaluation_input: BacktestEvaluationInput | Mapping[str, Any]) -> BacktestEvaluationRecord:
        started = time.perf_counter()
        if isinstance(evaluation_input, BacktestEvaluationInput):
            data = evaluation_input
        else:
            data = BacktestEvaluationInputBuilder.build(
                journal_record=evaluation_input.get("journal_record") if isinstance(evaluation_input, Mapping) else {},
                historical_observation_windows=evaluation_input.get("historical_observation_windows", []) if isinstance(evaluation_input, Mapping) else [],
            )
        input_chars = len(json.dumps(data.as_dict(), ensure_ascii=False, default=str))
        task_evaluations = [cls._evaluate_task(data, task_id) for task_id in data.task_ids]
        status = cls._status(data, task_evaluations)
        quality_label = cls._quality_label(data, status)
        record = BacktestEvaluationRecord(
            evaluation_id=data.evaluation_id,
            request_id=data.request_id,
            journal_id=data.journal_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            original_answer_sha256=data.final_answer_sha256,
            status=status,
            evaluation_type="thesis_outcome_alignment",
            quality_label=quality_label,
            task_evaluations=task_evaluations,
            aggregate_review=cls._aggregate(task_evaluations),
            safety_summary={
                "no_trade_simulation": True,
                "no_position_sizing": True,
                "no_execution": True,
                "execution_allowed": False,
                "safety_status": "PASS",
            },
            input_chars=input_chars,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            limitations=cls._limitations(data, task_evaluations),
        )
        safety = BacktestEvaluationSafetyValidator.validate_record(record)
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
    def _evaluate_task(cls, data: BacktestEvaluationInput, task_id: str) -> BacktestTaskEvaluation:
        snapshot = data.compact_task_snapshots.get(task_id) or {}
        intent = str(data.task_scope_map.get(task_id) or snapshot.get("intent_family") or "")
        if intent in STATIC_INTENTS or intent not in MARKET_INTENTS:
            return BacktestTaskEvaluation(
                task_id=task_id,
                intent_family=intent,
                symbol=str(snapshot.get("symbol") or ""),
                thesis_alignment="not_applicable",
                risk_materialization="inconclusive",
                confidence_calibration="inconclusive",
                review_notes=["market_outcome_evaluation_not_applicable"],
                status="SKIPPED",
            )
        window = next((item for item in data.historical_observation_windows if item.task_id == task_id), None)
        strategy = snapshot.get("strategy") if isinstance(snapshot.get("strategy"), Mapping) else {}
        risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), Mapping) else {}
        consistency = snapshot.get("consistency") if isinstance(snapshot.get("consistency"), Mapping) else {}
        thesis_direction = str(strategy.get("thesis_direction") or "")
        risk_posture = str(risk.get("risk_posture") or "")
        confidence = _strategy_confidence(strategy, consistency)
        if not window or window.data_quality in {"missing", "stale"}:
            return BacktestTaskEvaluation(
                task_id=task_id,
                intent_family=intent,
                symbol=str(snapshot.get("symbol") or data.symbol or ""),
                thesis_direction=thesis_direction,
                consistency_presentation_mode=str(consistency.get("final_presentation_mode") or ""),
                risk_posture=risk_posture,
                confidence_at_answer_time=confidence,
                thesis_alignment="inconclusive",
                risk_materialization="inconclusive",
                confidence_calibration="inconclusive",
                review_notes=["historical_observation_missing"],
                limitations=["missing_historical_observation_window"],
                status="INSUFFICIENT_DATA",
            )
        alignment = cls._thesis_alignment(thesis_direction, window.direction_label)
        risk_materialization = cls._risk_materialization(risk, window)
        calibration = cls._confidence_calibration(strategy, risk, consistency, window, alignment, confidence)
        return BacktestTaskEvaluation(
            task_id=task_id,
            intent_family=intent,
            symbol=str(snapshot.get("symbol") or window.symbol or data.symbol or ""),
            observation_window_id=window.window_id,
            thesis_direction=thesis_direction,
            consistency_presentation_mode=str(consistency.get("final_presentation_mode") or ""),
            risk_posture=risk_posture,
            confidence_at_answer_time=confidence,
            observed_direction=window.direction_label,
            observed_volatility=window.volatility_proxy,
            observed_range_pct=window.realized_range_pct,
            thesis_alignment=alignment,
            risk_materialization=risk_materialization,
            confidence_calibration=calibration,
            review_notes=list(window.notable_market_behavior),
            limitations=_ordered_unique(
                [str(item) for item in strategy.get("limitations", []) or []]
                + [str(item) for item in risk.get("limitations", []) or []]
                + [str(item) for item in consistency.get("limitations", []) or []]
            )[:5],
            status="EVALUATED",
        )

    @staticmethod
    def _thesis_alignment(thesis_direction: str, observed_direction: str) -> str:
        thesis = _normalized_thesis_direction(thesis_direction)
        if thesis == "mixed":
            return "aligned" if observed_direction in {"sideways", "volatile_mixed", "unclear"} else "partially_aligned"
        if thesis == "bullish":
            if observed_direction == "up":
                return "aligned"
            if observed_direction == "down":
                return "contradicted"
            return "partially_aligned"
        if thesis == "bearish":
            if observed_direction == "down":
                return "aligned"
            if observed_direction == "up":
                return "contradicted"
            return "partially_aligned"
        return "inconclusive"

    @staticmethod
    def _risk_materialization(risk: Mapping[str, Any], window: HistoricalObservationWindow) -> str:
        elevated = str(risk.get("overall_risk_level") or "").lower() in {"elevated", "high"}
        fragile = str(risk.get("risk_posture") or "").lower() in {
            "conflicting_context",
            "thesis_fragile",
            "insufficient_context",
            "caution_required",
        }
        volatile = window.direction_label == "volatile_mixed" or _float(window.volatility_proxy, 0.0) >= 2.0 or _float(window.realized_range_pct, 0.0) >= 2.0
        if elevated or fragile:
            if volatile:
                return "materialized"
            if window.direction_label in {"up", "down", "sideways"}:
                return "not_materialized"
            return "inconclusive"
        return "not_materialized" if not volatile else "partially_materialized"

    @staticmethod
    def _confidence_calibration(
        strategy: Mapping[str, Any],
        risk: Mapping[str, Any],
        consistency: Mapping[str, Any],
        window: HistoricalObservationWindow,
        alignment: str,
        confidence: float | None,
    ) -> str:
        mode = str(consistency.get("final_presentation_mode") or "").lower()
        risk_posture = str(risk.get("risk_posture") or "").lower()
        mixed_mode = mode in {"mixed_or_uncertain", "cautious_conditional", "risk_first", "insufficient_context"}
        if mixed_mode and window.direction_label in {"volatile_mixed", "sideways", "unclear"}:
            return "reasonable"
        raw_strategy_confidence = _raw_strategy_confidence(strategy)
        if alignment == "contradicted" and max(confidence or 0.0, raw_strategy_confidence or 0.0) >= 0.65:
            return "overconfident"
        if alignment in {"aligned", "partially_aligned"} and (confidence or 0.0) <= 0.4:
            return "underconfident"
        if risk_posture in {"conflicting_context", "thesis_fragile"} and window.direction_label == "volatile_mixed":
            return "reasonable"
        return "reasonable" if alignment in {"aligned", "partially_aligned"} else "inconclusive"

    @staticmethod
    def _status(data: BacktestEvaluationInput, task_evaluations: Sequence[BacktestTaskEvaluation]) -> str:
        if not data.journal_id or not data.final_answer_sha256:
            return "SKIPPED"
        if data.journal_quality_label in {"unsafe_or_noncompliant", "failed_validation", "incomplete"}:
            if any(item.status == "EVALUATED" for item in task_evaluations):
                return "EVALUATED_WITH_WARNINGS"
            return "SKIPPED"
        market_tasks = [item for item in task_evaluations if item.intent_family in MARKET_INTENTS]
        if not market_tasks:
            return "SKIPPED"
        if any(item.status == "INSUFFICIENT_DATA" for item in market_tasks):
            return "INSUFFICIENT_DATA"
        if any(item.status == "EVALUATED" for item in market_tasks):
            return "EVALUATED"
        return "SKIPPED"

    @staticmethod
    def _quality_label(data: BacktestEvaluationInput, status: str) -> str:
        if status == "EVALUATED":
            return "useful_for_review"
        if status == "EVALUATED_WITH_WARNINGS":
            return "limited_review"
        if status == "INSUFFICIENT_DATA":
            return "insufficient_data"
        return "invalid_input" if not data.journal_id or not data.final_answer_sha256 else "limited_review"

    @staticmethod
    def _aggregate(task_evaluations: Sequence[BacktestTaskEvaluation]) -> Dict[str, Any]:
        aligned = [item.task_id for item in task_evaluations if item.thesis_alignment in {"aligned", "partially_aligned"}]
        contradicted = [item.task_id for item in task_evaluations if item.thesis_alignment == "contradicted"]
        inconclusive = [item.task_id for item in task_evaluations if item.thesis_alignment in {"inconclusive", "not_applicable"}]
        flags = []
        if contradicted:
            flags.append("review_contradicted_thesis")
        if any(item.confidence_calibration == "overconfident" for item in task_evaluations):
            flags.append("review_overconfidence")
        if any(item.risk_materialization in {"materialized", "partially_materialized"} for item in task_evaluations):
            flags.append("review_risk_materialization")
        return {
            "aligned_tasks": aligned,
            "contradicted_tasks": contradicted,
            "inconclusive_tasks": inconclusive,
            "main_lessons": flags or ["no_market_review_action_required"],
            "calibration_flags": flags,
            "review_priority": "high" if contradicted or "review_overconfidence" in flags else ("medium" if flags else "low"),
        }

    @staticmethod
    def _limitations(data: BacktestEvaluationInput, task_evaluations: Sequence[BacktestTaskEvaluation]) -> List[str]:
        limitations: List[str] = []
        if data.journal_quality_label in {"unsafe_or_noncompliant", "failed_validation", "incomplete"}:
            limitations.append("journal_record_degraded")
        if not data.final_answer_sha256:
            limitations.append("missing_final_answer_hash")
        if any(item.status == "INSUFFICIENT_DATA" for item in task_evaluations):
            limitations.append("missing_historical_observation_window")
        return _ordered_unique(limitations)

    @staticmethod
    def _log(record: BacktestEvaluationRecord) -> None:
        flags = list(record.aggregate_review.get("calibration_flags") or [])
        print(
            "[BacktestEvaluation] "
            f"evaluation_id={record.evaluation_id} request_id={record.request_id} "
            f"status={record.status} tasks={len(record.task_evaluations)} "
            f"quality_label={record.quality_label} flags={flags} "
            f"input_chars={record.input_chars} payload_chars={record.payload_chars} latency_ms={record.latency_ms}"
        )
        for task in record.task_evaluations:
            print(
                "[BacktestEvaluationTask] "
                f"task_id={task.task_id} intent_family={task.intent_family} symbol={task.symbol} "
                f"observed_direction={task.observed_direction} thesis_alignment={task.thesis_alignment} "
                f"risk_materialization={task.risk_materialization} "
                f"confidence_calibration={task.confidence_calibration} status={task.status}"
            )
        print(
            "[BacktestEvaluationSafety] "
            f"no_trade_simulation={str(record.safety_summary.get('no_trade_simulation')).lower()} "
            f"no_position_sizing={str(record.safety_summary.get('no_position_sizing')).lower()} "
            f"no_execution={str(record.safety_summary.get('no_execution')).lower()} "
            f"execution_allowed={str(record.safety_summary.get('execution_allowed')).lower()} "
            f"status={record.safety_summary.get('safety_status')}"
        )
        print("[BacktestEvaluationStorage] mode=runtime_artifacts status=PASS")


def record_backtest_evaluation(
    runtime_artifacts: Dict[str, Any] | None,
    historical_observation_windows: Sequence[HistoricalObservationWindow | Mapping[str, Any]] | None = None,
    evaluation_policy: Mapping[str, Any] | None = None,
    evaluation_id: str = "",
) -> BacktestEvaluationRecord | None:
    if runtime_artifacts is None:
        return None
    journal_record = runtime_artifacts.get("journal_review")
    evaluation_input = BacktestEvaluationInputBuilder.build(
        journal_record=journal_record,
        historical_observation_windows=historical_observation_windows or [],
        runtime_artifacts=runtime_artifacts,
        evaluation_id=evaluation_id,
        evaluation_policy=evaluation_policy,
    )
    record = BacktestEvaluationAgent.evaluate(evaluation_input)
    runtime_artifacts["backtest_evaluation"] = record.as_dict()
    return record


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


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start in {None, 0} or end is None:
        return None
    return round(((end - start) / abs(start)) * 100.0, 4)


def _direction_from_change(net_change_pct: float | None, realized_range_pct: float | None) -> str:
    if net_change_pct is None:
        return "unclear"
    if realized_range_pct is not None and realized_range_pct >= 2.0 and abs(net_change_pct) < realized_range_pct * 0.5:
        return "volatile_mixed"
    if net_change_pct >= 0.35:
        return "up"
    if net_change_pct <= -0.35:
        return "down"
    return "sideways"


def _behavior_notes(direction: str, net_change_pct: float | None, realized_range_pct: float | None) -> List[str]:
    notes = [f"direction_label:{direction}"]
    if net_change_pct is not None:
        notes.append(f"net_change_pct:{net_change_pct}")
    if realized_range_pct is not None:
        notes.append(f"realized_range_pct:{realized_range_pct}")
    return notes


def _normalized_thesis_direction(value: str) -> str:
    text = str(value or "").lower()
    if "bull" in text or "up" in text:
        return "bullish"
    if "bear" in text or "down" in text:
        return "bearish"
    if text in {"mixed", "balanced", "no_clear_bias"} or "mixed" in text or "balanced" in text:
        return "mixed"
    return "unclear"


def _strategy_confidence(strategy: Mapping[str, Any], consistency: Mapping[str, Any]) -> float | None:
    confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), Mapping) else {}
    for value in (
        (consistency.get("confidence_reconciliation") or {}).get("final_confidence")
        if isinstance(consistency.get("confidence_reconciliation"), Mapping)
        else None,
        confidence.get("value"),
        confidence.get("ceiling"),
    ):
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

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.backtest_evaluation import (
    BacktestEvaluationAgent,
    BacktestEvaluationInputBuilder,
    EVALUATION_SAFETY_PATTERNS,
)
from src.services.agents.paper_trading_evaluation import (
    PAPER_SAFETY_PATTERNS,
    PaperTradingEvaluationAgent,
    PaperTradingEvaluationInputBuilder,
)


RECORD_TYPES = {"journal_review", "backtest_evaluation", "paper_trading_evaluation"}
REPLAY_CASE_TYPES = {"journal_only", "backtest", "paper_trading", "full_chain"}
REPLAY_STATUSES = {"PASS", "FAIL", "WARN", "SKIPPED"}

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b[A-Z0-9_]*(?:API|TOKEN|SECRET|KEY|PASSWORD|PASSWD|PWD)[A-Z0-9_]*\s*[:=]\s*['\"]?[^'\"\s]+",
        r"\bsk-[A-Za-z0-9_-]{12,}",
        r"\b(?:mt5|broker)[_-]?(?:login|password|token|secret)\s*[:=]\s*['\"]?[^'\"\s]+",
        r"\baccount\s+(?:balance|equity|number)\s*[:=]\s*['\"]?[^'\"\s]+",
    ]
]

REGISTRY_SAFETY_PATTERNS = [
    *EVALUATION_SAFETY_PATTERNS,
    *PAPER_SAFETY_PATTERNS,
    *[
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\bbroker\b",
            r"\baccount\s+balance\b",
            r"\bopen\s+positions?\b",
            r"\border\s+history\b",
            r"\bpnl\s+optimization\b",
            r"\bwin[-\s]?rate\s+optimization\b",
        ]
    ],
]


@dataclass
class EvaluationRegistryTaskIndex:
    task_id: str
    intent_family: str = ""
    symbol: str = ""
    status: str = ""
    quality_label: str = ""
    review_flags: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    agent_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "status": self.status,
            "quality_label": self.quality_label,
            "review_flags": list(self.review_flags),
            "source_refs": list(self.source_refs),
            "agent_refs": list(self.agent_refs),
        }


@dataclass
class EvaluationRegistryEntry:
    registry_id: str
    created_at: str
    record_type: str
    request_id: str = ""
    task_ids: List[str] = field(default_factory=list)
    parent_intent: str = ""
    symbol: str = ""
    final_answer_sha256: str = ""
    source_record_id: Dict[str, str] = field(default_factory=dict)
    quality_label: str = ""
    status: str = ""
    review_outcome: str = ""
    execution_allowed: bool = False
    task_index: List[EvaluationRegistryTaskIndex] = field(default_factory=list)
    safety_index: Dict[str, Any] = field(default_factory=dict)
    evaluation_index: Dict[str, Any] = field(default_factory=dict)
    hashes: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    redactions: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "created_at": self.created_at,
            "record_type": self.record_type,
            "request_id": self.request_id,
            "task_ids": list(self.task_ids),
            "parent_intent": self.parent_intent,
            "symbol": self.symbol,
            "final_answer_sha256": self.final_answer_sha256,
            "source_record_id": dict(self.source_record_id),
            "quality_label": self.quality_label,
            "status": self.status,
            "review_outcome": self.review_outcome,
            "execution_allowed": self.execution_allowed,
            "task_index": [item.as_dict() for item in self.task_index],
            "safety_index": dict(self.safety_index),
            "evaluation_index": dict(self.evaluation_index),
            "hashes": dict(self.hashes),
            "tags": list(self.tags),
            "limitations": list(self.limitations),
            "redactions": self.redactions,
        }


@dataclass
class EvaluationReplayCase:
    replay_id: str
    case_type: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_records: Dict[str, Any] = field(default_factory=dict)
    supplied_fixtures: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: Dict[str, Any] = field(default_factory=dict)
    replay_policy: Dict[str, Any] = field(
        default_factory=lambda: {
            "no_provider_calls": True,
            "no_retrieval": True,
            "no_execution": True,
            "deterministic_only": True,
        }
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "created_at": self.created_at,
            "case_type": self.case_type,
            "input_records": dict(self.input_records),
            "supplied_fixtures": dict(self.supplied_fixtures),
            "expected_outputs": dict(self.expected_outputs),
            "replay_policy": dict(self.replay_policy),
        }


@dataclass
class ReplayResult:
    replay_id: str
    status: str
    compared_fields: List[str] = field(default_factory=list)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    generated_records: List[Dict[str, Any]] = field(default_factory=list)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "status": self.status,
            "compared_fields": list(self.compared_fields),
            "mismatches": list(self.mismatches),
            "generated_records": list(self.generated_records),
            "safety_summary": dict(self.safety_summary),
            "latency_ms": self.latency_ms,
        }


@dataclass
class EvaluationReviewDataset:
    export_id: str
    created_at: str
    entries_count: int
    filters_used: Dict[str, Any] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    redactions: int = 0
    payload_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "export_id": self.export_id,
            "created_at": self.created_at,
            "entries_count": self.entries_count,
            "filters_used": dict(self.filters_used),
            "rows": list(self.rows),
            "redactions": self.redactions,
            "payload_chars": self.payload_chars,
        }


class EvaluationRegistry:
    def __init__(self, entries: Sequence[EvaluationRegistryEntry | Mapping[str, Any]] | None = None):
        self._entries: List[EvaluationRegistryEntry] = [self._entry(item) for item in entries or []]

    def register(self, record: Mapping[str, Any] | Any, record_type: str, replace: bool = False) -> EvaluationRegistryEntry:
        started = time.perf_counter()
        entry = EvaluationRegistryNormalizer.normalize(record, record_type)
        if replace:
            self._entries = [item for item in self._entries if item.registry_id != entry.registry_id]
        elif any(item.registry_id == entry.registry_id for item in self._entries):
            entry.registry_id = f"{entry.registry_id}:{len(self._entries) + 1}"
        self._entries.append(entry)
        latency = round((time.perf_counter() - started) * 1000, 3)
        print(
            "[EvaluationRegistry] "
            f"action=register record_type={record_type} registry_id={entry.registry_id} "
            f"request_id={entry.request_id} status=PASS entries_total={len(self._entries)} "
            f"flags={entry.limitations} latency_ms={latency}"
        )
        return entry

    def list_registry_entries(self, filters: Mapping[str, Any] | None = None) -> List[EvaluationRegistryEntry]:
        started = time.perf_counter()
        filters = dict(filters or {})
        results = [entry for entry in self._entries if _matches(entry, filters)]
        print(
            "[EvaluationRegistryQuery] "
            f"filters={filters} results={len(results)} latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return results

    def get_registry_entry(self, registry_id: str) -> EvaluationRegistryEntry | None:
        return next((entry for entry in self._entries if entry.registry_id == registry_id), None)

    def find_by_request_id(self, request_id: str) -> List[EvaluationRegistryEntry]:
        return self.list_registry_entries({"request_id": request_id})

    def find_by_final_answer_hash(self, sha256: str) -> List[EvaluationRegistryEntry]:
        return self.list_registry_entries({"final_answer_sha256": sha256})

    def filter_needs_review(self) -> List[EvaluationRegistryEntry]:
        return [
            entry
            for entry in self._entries
            if entry.quality_label in {"limited_review", "degraded", "failed_validation", "unsafe_or_noncompliant", "incomplete", "invalid_input"}
            or entry.status in {"WARN", "FAIL", "DEGRADED", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}
            or entry.safety_index.get("prohibited_outputs_detected")
            or entry.evaluation_index.get("review_priority") in {"high", "medium"}
        ]

    def filter_by_symbol(self, symbol: str) -> List[EvaluationRegistryEntry]:
        return self.list_registry_entries({"symbol": symbol})

    def filter_by_status(self, status: str) -> List[EvaluationRegistryEntry]:
        return self.list_registry_entries({"status": status})

    def filter_by_quality_label(self, label: str) -> List[EvaluationRegistryEntry]:
        return self.list_registry_entries({"quality_label": label})

    def export_review_dataset(self, filters: Mapping[str, Any] | None = None, include_final_answer_excerpt: bool = False) -> EvaluationReviewDataset:
        started = time.perf_counter()
        entries = self.list_registry_entries(filters)
        rows: List[Dict[str, Any]] = []
        redactions = 0
        for entry in entries:
            for task in entry.task_index or [EvaluationRegistryTaskIndex(task_id="")]:
                row, count = _redact_mapping(
                    {
                        "registry_id": entry.registry_id,
                        "record_type": entry.record_type,
                        "request_id": entry.request_id,
                        "task_id": task.task_id,
                        "symbol": task.symbol or entry.symbol,
                        "intent_family": task.intent_family,
                        "status": task.status or entry.status,
                        "quality_label": task.quality_label or entry.quality_label,
                        "review_outcome": entry.review_outcome,
                        "thesis_alignment": entry.evaluation_index.get("thesis_alignment", ""),
                        "risk_materialization": entry.evaluation_index.get("risk_materialization", ""),
                        "confidence_calibration": entry.evaluation_index.get("confidence_calibration", ""),
                        "advisory_followup_outcome": entry.evaluation_index.get("advisory_followup_outcome", ""),
                        "review_priority": entry.evaluation_index.get("review_priority", ""),
                        "final_answer_sha256": entry.final_answer_sha256,
                        "source_refs": list(task.source_refs),
                        "safety_flags": _safety_flags(entry.safety_index),
                    }
                )
                redactions += count
                if include_final_answer_excerpt:
                    row["final_answer_excerpt"] = ""
                rows.append(row)
        dataset = EvaluationReviewDataset(
            export_id=f"evaluation_review_dataset:{len(rows)}:{int(time.time() * 1000)}",
            created_at=datetime.now(timezone.utc).isoformat(),
            entries_count=len(entries),
            filters_used=dict(filters or {}),
            rows=rows,
            redactions=redactions,
        )
        dataset.payload_chars = len(json.dumps(dataset.as_dict(), ensure_ascii=False, default=str))
        print(
            "[EvaluationExport] "
            f"export_id={dataset.export_id} entries={dataset.entries_count} status=PASS "
            f"redactions={dataset.redactions} latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return dataset

    def as_runtime_artifact(self) -> Dict[str, Any]:
        return {"entries": [entry.as_dict() for entry in self._entries], "storage_mode": "runtime_artifacts"}

    @staticmethod
    def _entry(item: EvaluationRegistryEntry | Mapping[str, Any]) -> EvaluationRegistryEntry:
        if isinstance(item, EvaluationRegistryEntry):
            return item
        data = dict(item or {})
        return EvaluationRegistryEntry(
            registry_id=str(data.get("registry_id") or ""),
            created_at=str(data.get("created_at") or ""),
            record_type=str(data.get("record_type") or ""),
            request_id=str(data.get("request_id") or ""),
            task_ids=[str(value) for value in data.get("task_ids") or []],
            parent_intent=str(data.get("parent_intent") or ""),
            symbol=str(data.get("symbol") or ""),
            final_answer_sha256=str(data.get("final_answer_sha256") or ""),
            source_record_id=dict(data.get("source_record_id") or {}),
            quality_label=str(data.get("quality_label") or ""),
            status=str(data.get("status") or ""),
            review_outcome=str(data.get("review_outcome") or ""),
            execution_allowed=bool(data.get("execution_allowed") or False),
            task_index=[
                EvaluationRegistryTaskIndex(**task) if isinstance(task, Mapping) else EvaluationRegistryTaskIndex(task_id=str(task))
                for task in data.get("task_index") or []
            ],
            safety_index=dict(data.get("safety_index") or {}),
            evaluation_index=dict(data.get("evaluation_index") or {}),
            hashes=dict(data.get("hashes") or {}),
            tags=[str(value) for value in data.get("tags") or []],
            limitations=[str(value) for value in data.get("limitations") or []],
            redactions=int(data.get("redactions") or 0),
        )


class EvaluationRegistryNormalizer:
    @classmethod
    def normalize(cls, record: Mapping[str, Any] | Any, record_type: str) -> EvaluationRegistryEntry:
        if record_type not in RECORD_TYPES:
            raise ValueError(f"unsupported record_type: {record_type}")
        data = _as_mapping(record)
        if record_type == "journal_review":
            entry = cls._journal_entry(data)
        elif record_type == "backtest_evaluation":
            entry = cls._backtest_entry(data)
        else:
            entry = cls._paper_entry(data)
        safety = cls._safety_index(data, entry)
        entry.safety_index = safety
        entry.execution_allowed = bool(safety.get("execution_allowed") or False)
        if safety.get("prohibited_outputs_detected") and entry.quality_label in {"high_quality", "useful_for_review"}:
            entry.quality_label = "limited_review"
            entry.limitations = _ordered_unique(entry.limitations + ["source_record_safety_flag"])
        redacted, redactions = _redact_mapping(entry.as_dict())
        entry = EvaluationRegistry._entry(redacted)
        entry.redactions = redactions
        return entry

    @staticmethod
    def _journal_entry(data: Mapping[str, Any]) -> EvaluationRegistryEntry:
        source_record_id = {"journal_id": str(data.get("journal_id") or "")}
        snapshots = data.get("compact_task_analysis_snapshots") if isinstance(data.get("compact_task_analysis_snapshots"), Mapping) else {}
        global_source_refs = [str(value) for value in (data.get("evidence_summary") or {}).get("source_refs") or []]
        task_index = [
            EvaluationRegistryTaskIndex(
                task_id=str(task.get("task_id") or ""),
                intent_family=str(task.get("intent_family") or ""),
                symbol="",
                status=str(task.get("completeness_status") or task.get("status") or data.get("status") or ""),
                quality_label=str(data.get("quality_label") or ""),
                review_flags=[str(value) for value in task.get("review_flags") or []],
                source_refs=_task_source_refs(str(task.get("task_id") or ""), snapshots, global_source_refs),
                agent_refs=_journal_agent_refs(data),
            )
            for task in data.get("task_reviews") or []
            if isinstance(task, Mapping)
        ]
        final_hash = str(data.get("final_answer_sha256") or "")
        return EvaluationRegistryEntry(
            registry_id=f"registry:journal_review:{source_record_id['journal_id'] or final_hash}",
            created_at=datetime.now(timezone.utc).isoformat(),
            record_type="journal_review",
            request_id=str(data.get("request_id") or ""),
            task_ids=[task.task_id for task in task_index],
            final_answer_sha256=final_hash,
            source_record_id=source_record_id,
            quality_label=str(data.get("quality_label") or ""),
            status=str(data.get("status") or ""),
            review_outcome=str(data.get("review_outcome") or ""),
            task_index=task_index,
            evaluation_index={
                "review_priority": "medium" if data.get("review_outcome") in {"needs_human_review", "suitable_for_later_review"} else "low",
                "memory_policy_action": (data.get("validation_summary") or {}).get("memory_policy_action", ""),
            },
            hashes={"final_answer_sha256": final_hash},
            limitations=[str(value) for value in data.get("limitations") or []],
        )

    @staticmethod
    def _backtest_entry(data: Mapping[str, Any]) -> EvaluationRegistryEntry:
        task_index = [
            EvaluationRegistryTaskIndex(
                task_id=str(task.get("task_id") or ""),
                intent_family=str(task.get("intent_family") or ""),
                symbol=str(task.get("symbol") or ""),
                status=str(task.get("status") or data.get("status") or ""),
                quality_label=str(data.get("quality_label") or ""),
                review_flags=[str(value) for value in task.get("limitations") or []],
            )
            for task in data.get("task_evaluations") or []
            if isinstance(task, Mapping)
        ]
        evaluation_index = _collect_backtest_index(data)
        final_hash = str(data.get("original_answer_sha256") or "")
        return EvaluationRegistryEntry(
            registry_id=f"registry:backtest_evaluation:{data.get('evaluation_id') or final_hash}",
            created_at=datetime.now(timezone.utc).isoformat(),
            record_type="backtest_evaluation",
            request_id=str(data.get("request_id") or ""),
            task_ids=[task.task_id for task in task_index],
            symbol=_first([task.symbol for task in task_index]),
            final_answer_sha256=final_hash,
            source_record_id={"backtest_evaluation_id": str(data.get("evaluation_id") or "")},
            quality_label=str(data.get("quality_label") or ""),
            status=str(data.get("status") or ""),
            task_index=task_index,
            evaluation_index=evaluation_index,
            hashes={"final_answer_sha256": final_hash},
            tags=[str(value) for value in (data.get("aggregate_review") or {}).get("main_lessons") or []],
            limitations=[str(value) for value in data.get("limitations") or []],
        )

    @staticmethod
    def _paper_entry(data: Mapping[str, Any]) -> EvaluationRegistryEntry:
        task_index = [
            EvaluationRegistryTaskIndex(
                task_id=str(task.get("task_id") or ""),
                intent_family=str(task.get("intent_family") or ""),
                symbol=str(task.get("symbol") or ""),
                status=str(task.get("status") or data.get("status") or ""),
                quality_label=str(data.get("quality_label") or ""),
                review_flags=[str(value) for value in task.get("limitations") or []],
            )
            for task in data.get("task_evaluations") or []
            if isinstance(task, Mapping)
        ]
        evaluation_index = _collect_paper_index(data)
        final_hash = str(data.get("original_answer_sha256") or "")
        return EvaluationRegistryEntry(
            registry_id=f"registry:paper_trading_evaluation:{data.get('paper_evaluation_id') or final_hash}",
            created_at=datetime.now(timezone.utc).isoformat(),
            record_type="paper_trading_evaluation",
            request_id=str(data.get("request_id") or ""),
            task_ids=[task.task_id for task in task_index],
            symbol=_first([task.symbol for task in task_index]),
            final_answer_sha256=final_hash,
            source_record_id={"paper_evaluation_id": str(data.get("paper_evaluation_id") or "")},
            quality_label=str(data.get("quality_label") or ""),
            status=str(data.get("status") or ""),
            task_index=task_index,
            evaluation_index=evaluation_index,
            hashes={"final_answer_sha256": final_hash},
            tags=[str(value) for value in (data.get("aggregate_review") or {}).get("main_lessons") or []],
            limitations=[str(value) for value in data.get("limitations") or []],
        )

    @staticmethod
    def _safety_index(data: Mapping[str, Any], entry: EvaluationRegistryEntry) -> Dict[str, Any]:
        source_safety = data.get("safety_summary") if isinstance(data.get("safety_summary"), Mapping) else {}
        text_values = " ".join(_string_values(data))
        prohibited = any(pattern.search(text_values) for pattern in REGISTRY_SAFETY_PATTERNS)
        execution_allowed = bool(source_safety.get("execution_allowed") or False)
        return {
            "trading_instruction_detected": bool(source_safety.get("trading_instruction_detected") or prohibited),
            "position_sizing_detected": bool(source_safety.get("position_sizing_detected") or False),
            "account_risk_detected": bool(source_safety.get("account_risk_detected") or False),
            "mt5_execution_detected": bool(source_safety.get("mt5_execution_detected") or False),
            "prohibited_outputs_detected": bool(source_safety.get("prohibited_output_detected") or data.get("prohibited_outputs_detected") or prohibited),
            "execution_allowed": execution_allowed,
            "safety_status": "FAIL" if prohibited or execution_allowed else str(source_safety.get("safety_status") or "PASS"),
        }


class EvaluationReplayHarness:
    @classmethod
    def replay(cls, replay_case: EvaluationReplayCase | Mapping[str, Any]) -> ReplayResult:
        started = time.perf_counter()
        case = replay_case if isinstance(replay_case, EvaluationReplayCase) else cls._case(replay_case)
        generated: List[Dict[str, Any]] = []
        mismatches: List[Dict[str, Any]] = []
        compared: List[str] = []
        registry = EvaluationRegistry()
        try:
            if case.case_type == "journal_only":
                journal = case.input_records.get("journal_review_record") or {}
                entry = registry.register(journal, "journal_review")
                generated.append(entry.as_dict())
            elif case.case_type == "backtest":
                journal = case.input_records.get("journal_review_record") or {}
                backtest = BacktestEvaluationAgent.evaluate(
                    BacktestEvaluationInputBuilder.build(
                        journal_record=journal,
                        historical_observation_windows=case.supplied_fixtures.get("historical_observation_windows") or [],
                    )
                )
                generated.append(backtest.as_dict())
            elif case.case_type == "paper_trading":
                journal = case.input_records.get("journal_review_record") or {}
                backtest = case.input_records.get("backtest_evaluation_record") or {}
                paper = PaperTradingEvaluationAgent.evaluate(
                    PaperTradingEvaluationInputBuilder.build(
                        journal_record=journal,
                        backtest_record=backtest,
                        simulated_observation_timeline=case.supplied_fixtures.get("simulated_observation_timeline") or [],
                    )
                )
                generated.append(paper.as_dict())
            elif case.case_type == "full_chain":
                journal = case.input_records.get("journal_review_record") or {}
                backtest = BacktestEvaluationAgent.evaluate(
                    BacktestEvaluationInputBuilder.build(
                        journal_record=journal,
                        historical_observation_windows=case.supplied_fixtures.get("historical_observation_windows") or [],
                    )
                )
                paper = PaperTradingEvaluationAgent.evaluate(
                    PaperTradingEvaluationInputBuilder.build(
                        journal_record=journal,
                        backtest_record=backtest.as_dict(),
                        simulated_observation_timeline=case.supplied_fixtures.get("simulated_observation_timeline") or [],
                    )
                )
                generated.extend(
                    [
                        registry.register(journal, "journal_review").as_dict(),
                        registry.register(backtest.as_dict(), "backtest_evaluation").as_dict(),
                        registry.register(paper.as_dict(), "paper_trading_evaluation").as_dict(),
                    ]
                )
            else:
                return cls._result(case, "SKIPPED", compared, [{"field": "case_type", "expected": "supported", "actual": case.case_type}], generated, started)
        except Exception as exc:
            return cls._result(case, "FAIL", compared, [{"field": "exception", "expected": "none", "actual": str(exc)}], generated, started)
        expected = dict(case.expected_outputs or {})
        actual = _replay_actual(generated)
        for field, expected_value in expected.items():
            compared.append(field)
            actual_value = actual.get(field)
            if actual_value != expected_value:
                mismatches.append({"field": field, "expected": expected_value, "actual": actual_value})
        status = "FAIL" if mismatches else "PASS"
        return cls._result(case, status, compared, mismatches, generated, started)

    @staticmethod
    def _case(data: Mapping[str, Any]) -> EvaluationReplayCase:
        return EvaluationReplayCase(
            replay_id=str(data.get("replay_id") or ""),
            case_type=str(data.get("case_type") or ""),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            input_records=dict(data.get("input_records") or {}),
            supplied_fixtures=dict(data.get("supplied_fixtures") or {}),
            expected_outputs=dict(data.get("expected_outputs") or {}),
            replay_policy=dict(data.get("replay_policy") or {}),
        )

    @staticmethod
    def _result(
        case: EvaluationReplayCase,
        status: str,
        compared: Sequence[str],
        mismatches: Sequence[Mapping[str, Any]],
        generated: Sequence[Mapping[str, Any]],
        started: float,
    ) -> ReplayResult:
        safety = {
            "no_provider_calls": True,
            "no_retrieval": True,
            "no_execution": True,
            "execution_allowed": False,
            "safety_status": "PASS",
        }
        result = ReplayResult(
            replay_id=case.replay_id,
            status=status,
            compared_fields=list(compared),
            mismatches=[dict(item) for item in mismatches],
            generated_records=[dict(item) for item in generated],
            safety_summary=safety,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        print(
            "[EvaluationReplay] "
            f"replay_id={result.replay_id} case_type={case.case_type} status={result.status} "
            f"mismatches={len(result.mismatches)} safety_status={safety['safety_status']} latency_ms={result.latency_ms}"
        )
        return result


def register_evaluation_record(
    record: Mapping[str, Any] | Any,
    record_type: str,
    runtime_artifacts: Dict[str, Any] | None = None,
    registry: EvaluationRegistry | None = None,
    replace: bool = False,
) -> EvaluationRegistryEntry:
    active = registry or _registry_from_artifacts(runtime_artifacts)
    entry = active.register(record, record_type, replace=replace)
    if runtime_artifacts is not None:
        runtime_artifacts["evaluation_registry"] = active.as_runtime_artifact()
    return entry


def _registry_from_artifacts(runtime_artifacts: Mapping[str, Any] | None) -> EvaluationRegistry:
    if not runtime_artifacts:
        return EvaluationRegistry()
    stored = runtime_artifacts.get("evaluation_registry") if isinstance(runtime_artifacts.get("evaluation_registry"), Mapping) else {}
    return EvaluationRegistry(stored.get("entries") or [])


def _matches(entry: EvaluationRegistryEntry, filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if key == "symbol":
            if entry.symbol != expected and not any(task.symbol == expected for task in entry.task_index):
                return False
        elif key == "task_id":
            if expected not in entry.task_ids:
                return False
        elif getattr(entry, key, None) != expected:
            return False
    return True


def _as_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "as_dict"):
        return dict(value.as_dict())
    return {}


def _journal_agent_refs(data: Mapping[str, Any]) -> List[str]:
    summary = data.get("agent_summary") if isinstance(data.get("agent_summary"), Mapping) else {}
    refs: List[str] = []
    for key in ("market_context_refs", "strategy_thesis_refs", "risk_assessment_refs", "consistency_assessment_refs"):
        refs.extend([str(value) for value in summary.get(key) or []])
    return _ordered_unique(refs)


def _task_source_refs(task_id: str, snapshots: Mapping[str, Any], fallback: Sequence[str]) -> List[str]:
    snapshot = snapshots.get(task_id) if isinstance(snapshots.get(task_id), Mapping) else {}
    refs = snapshot.get("allowed_source_refs") if isinstance(snapshot, Mapping) else []
    if refs:
        return _ordered_unique([str(value) for value in refs])
    return _ordered_unique([str(value) for value in fallback])


def _collect_backtest_index(data: Mapping[str, Any]) -> Dict[str, Any]:
    tasks = [dict(item) for item in data.get("task_evaluations") or [] if isinstance(item, Mapping)]
    return {
        "thesis_alignment": _first([task.get("thesis_alignment") for task in tasks if task.get("thesis_alignment") != "not_applicable"]),
        "risk_materialization": _first([task.get("risk_materialization") for task in tasks if task.get("risk_materialization") != "inconclusive"]),
        "confidence_calibration": _first([task.get("confidence_calibration") for task in tasks if task.get("confidence_calibration") != "inconclusive"]),
        "review_priority": (data.get("aggregate_review") or {}).get("review_priority", ""),
    }


def _collect_paper_index(data: Mapping[str, Any]) -> Dict[str, Any]:
    tasks = [dict(item) for item in data.get("task_evaluations") or [] if isinstance(item, Mapping)]
    return {
        "advisory_followup_outcome": _first([task.get("advisory_followup_outcome") for task in tasks if task.get("advisory_followup_outcome") != "not_applicable"]),
        "confirmation_review": _first([task.get("confirmation_review") for task in tasks if task.get("confirmation_review") != "inconclusive"]),
        "invalidation_review": _first([task.get("invalidation_review") for task in tasks if task.get("invalidation_review") != "inconclusive"]),
        "risk_review": _first([task.get("risk_review") for task in tasks if task.get("risk_review") != "inconclusive"]),
        "confidence_calibration": _first([task.get("confidence_review") for task in tasks if task.get("confidence_review") != "inconclusive"]),
        "review_priority": (data.get("aggregate_review") or {}).get("review_priority", ""),
    }


def _replay_actual(generated: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not generated:
        return {}
    last = dict(generated[-1])
    return {
        "expected_status": last.get("status"),
        "expected_quality_label": last.get("quality_label"),
        "expected_safety_status": (last.get("safety_summary") or {}).get("safety_status"),
        "expected_task_outcomes": [
            task.get("advisory_followup_outcome")
            or task.get("thesis_alignment")
            or task.get("status")
            for task in last.get("task_evaluations", []) or last.get("task_index", [])
            if isinstance(task, Mapping)
        ],
        "entries_count": len(generated),
    }


def _redact_mapping(data: Mapping[str, Any]) -> tuple[Dict[str, Any], int]:
    redactions = 0

    def redact(value: Any) -> Any:
        nonlocal redactions
        if isinstance(value, Mapping):
            return {str(key): redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str):
            text = value
            for pattern in SECRET_PATTERNS:
                text, count = pattern.subn("[REDACTED]", text)
                redactions += count
            return text
        return value

    return redact(dict(data)), redactions


def _string_values(value: Any) -> List[str]:
    if isinstance(value, Mapping):
        output: List[str] = []
        for item in value.values():
            output.extend(_string_values(item))
        return output
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            output.extend(_string_values(item))
        return output
    if isinstance(value, str):
        return [value]
    return []


def _safety_flags(safety_index: Mapping[str, Any]) -> List[str]:
    return [key for key, value in safety_index.items() if key.endswith("_detected") and value]


def _first(values: Iterable[Any]) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output

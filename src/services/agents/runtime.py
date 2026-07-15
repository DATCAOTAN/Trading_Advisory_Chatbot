from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Set, Tuple

from src.services.orchestrator_contract import OrchestratorOutput, select_agents_for_intent


class AgentStatus:
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESULT = "INVALID_RESULT"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"
    SKIPPED_WITH_REASON = "SKIPPED_WITH_REASON"


TERMINAL_AGENT_STATUSES: Set[str] = {
    AgentStatus.SUCCESS,
    AgentStatus.PARTIAL,
    AgentStatus.FAILED,
    AgentStatus.TIMEOUT,
    AgentStatus.UNAVAILABLE,
    AgentStatus.INVALID_RESULT,
    AgentStatus.DEPENDENCY_BLOCKED,
    AgentStatus.SKIPPED_WITH_REASON,
}


@dataclass
class AgentTaskEnvelope:
    task_id: str
    agent_type: str
    parent_task_id: str = ""
    objective: str = ""
    intent_family: str = ""
    required: bool = True
    input_refs: List[str] = field(default_factory=list)
    context_refs: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    dependency_ids: List[str] = field(default_factory=list)
    timeout_ms: int = 5000
    output_contract: Dict[str, Any] = field(default_factory=dict)
    failure_policy: str = "required_blocks"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "agent_type": self.agent_type,
            "objective": self.objective,
            "intent_family": self.intent_family,
            "required": self.required,
            "input_refs": list(self.input_refs),
            "context_refs": list(self.context_refs),
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "dependency_ids": list(self.dependency_ids),
            "timeout_ms": self.timeout_ms,
            "output_contract": dict(self.output_contract),
            "failure_policy": self.failure_policy,
            "metadata": dict(self.metadata),
        }


@dataclass
class AgentExecutionPlan:
    request_id: str
    parent_plan_id: str
    parent_intent: str
    tasks: List[AgentTaskEnvelope] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    parallel_groups: List[List[str]] = field(default_factory=list)
    execution_policy: str = "local_process"
    timeout_policy: Dict[str, Any] = field(default_factory=lambda: {"default_timeout_ms": 5000})
    aggregation_policy: str = "required_failures_block_optional_failures_warn"
    execution_allowed: bool = False
    unavailable_agents: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "parent_plan_id": self.parent_plan_id,
            "parent_intent": self.parent_intent,
            "tasks": [task.as_dict() for task in self.tasks],
            "dependency_graph": {key: list(value) for key, value in self.dependency_graph.items()},
            "parallel_groups": [list(group) for group in self.parallel_groups],
            "execution_policy": self.execution_policy,
            "timeout_policy": dict(self.timeout_policy),
            "aggregation_policy": self.aggregation_policy,
            "execution_allowed": self.execution_allowed,
            "unavailable_agents": list(self.unavailable_agents),
            "metadata": dict(self.metadata),
        }


@dataclass
class AgentRuntimeContext:
    query_plan_ref: Any = None
    decision_context_ref: Any = None
    task_context_refs: Dict[str, Any] = field(default_factory=dict)
    acquisition_result_refs: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: Dict[str, Any] = field(default_factory=dict)
    runtime_context_store_ref: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResultEnvelope:
    task_id: str
    agent_type: str
    parent_task_id: str = ""
    status: str = AgentStatus.SUCCESS
    result_type: str = "analysis"
    structured_payload: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    confidence: float = 0.0
    assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    failure_code: str = ""
    failure_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "result_type": self.result_type,
            "structured_payload": dict(self.structured_payload),
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
            "failure_code": self.failure_code,
            "failure_reason": self.failure_reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class AggregatedAgentResult:
    request_id: str
    task_results: List[AgentResultEnvelope] = field(default_factory=list)
    successful_tasks: List[str] = field(default_factory=list)
    partial_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    unavailable_tasks: List[str] = field(default_factory=list)
    blocked_tasks: List[str] = field(default_factory=list)
    timeout_tasks: List[str] = field(default_factory=list)
    invalid_tasks: List[str] = field(default_factory=list)
    skipped_tasks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence_ceiling: str = "high"
    status: str = "PASS"
    result_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_results": [result.as_dict() for result in self.task_results],
            "successful_tasks": list(self.successful_tasks),
            "partial_tasks": list(self.partial_tasks),
            "failed_tasks": list(self.failed_tasks),
            "unavailable_tasks": list(self.unavailable_tasks),
            "blocked_tasks": list(self.blocked_tasks),
            "timeout_tasks": list(self.timeout_tasks),
            "invalid_tasks": list(self.invalid_tasks),
            "skipped_tasks": list(self.skipped_tasks),
            "warnings": list(self.warnings),
            "confidence_ceiling": self.confidence_ceiling,
            "status": self.status,
            "result_refs": list(self.result_refs),
        }


@dataclass
class AgentHandoffContext:
    request_id: str
    parent_plan_id: str
    agent_execution_status: str
    agent_results: List[AgentResultEnvelope] = field(default_factory=list)
    aggregated_result: Optional[AggregatedAgentResult] = None
    evidence_refs: List[str] = field(default_factory=list)
    market_context_assessment_refs: List[str] = field(default_factory=list)
    market_context_assessments_by_task: Dict[str, str] = field(default_factory=dict)
    strategy_thesis_refs: List[str] = field(default_factory=list)
    strategy_theses_by_task: Dict[str, str] = field(default_factory=dict)
    risk_assessment_refs: List[str] = field(default_factory=list)
    risk_assessments_by_task: Dict[str, str] = field(default_factory=dict)
    consistency_assessment_refs: List[str] = field(default_factory=list)
    consistency_assessments_by_task: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    confidence_ceiling: str = "high"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "parent_plan_id": self.parent_plan_id,
            "agent_execution_status": self.agent_execution_status,
            "agent_results": [result.as_dict() for result in self.agent_results],
            "aggregated_result": self.aggregated_result.as_dict() if self.aggregated_result else None,
            "evidence_refs": list(self.evidence_refs),
            "market_context_assessment_refs": list(self.market_context_assessment_refs),
            "market_context_assessments_by_task": dict(self.market_context_assessments_by_task),
            "strategy_thesis_refs": list(self.strategy_thesis_refs),
            "strategy_theses_by_task": dict(self.strategy_theses_by_task),
            "risk_assessment_refs": list(self.risk_assessment_refs),
            "risk_assessments_by_task": dict(self.risk_assessments_by_task),
            "consistency_assessment_refs": list(self.consistency_assessment_refs),
            "consistency_assessments_by_task": dict(self.consistency_assessments_by_task),
            "warnings": list(self.warnings),
            "confidence_ceiling": self.confidence_ceiling,
        }


class AgentRuntime(Protocol):
    def execute(self, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> AgentResultEnvelope:
        ...


class AgentRuntimeRegistry:
    def __init__(self):
        self._runtimes: Dict[str, AgentRuntime] = {}

    def register(self, agent_type: str, executor: AgentRuntime) -> None:
        if not agent_type:
            raise ValueError("agent_type is required")
        if executor is None:
            raise ValueError("executor is required")
        self._runtimes[agent_type] = executor

    def resolve(self, agent_type: str) -> Optional[AgentRuntime]:
        return self._runtimes.get(agent_type)

    def is_available(self, agent_type: str) -> bool:
        return agent_type in self._runtimes

    def available_agent_types(self) -> List[str]:
        return sorted(self._runtimes)


class AgentExecutionPlanBuilder:
    DEFAULT_TIMEOUT_MS = 5000

    def __init__(self, registry: Optional[AgentRuntimeRegistry] = None):
        self.registry = registry or AgentRuntimeRegistry()

    def build(
        self,
        contract: OrchestratorOutput,
        decision_context: Any,
        request_id: str = "",
    ) -> AgentExecutionPlan:
        query_plan = getattr(decision_context, "query_plan", None) or {}
        request_id = request_id or str(getattr(decision_context, "request_id", "") or "agent_request")
        parent_plan_id = str(query_plan.get("plan_id") or query_plan.get("query_plan_id") or "")
        parent_intent = str(query_plan.get("primary_intent") or "")
        selected_agents = list(getattr(contract, "selected_agents", []) or [])
        tasks: List[AgentTaskEnvelope] = []
        unavailable_agents: List[str] = []

        child_plans = [child for child in query_plan.get("child_plans", []) or [] if isinstance(child, dict)]
        if child_plans:
            desired_by_child = self._child_agent_assignments(child_plans)
            for child in child_plans:
                parent_task_id = str(child.get("task_id") or "")
                for agent_type in desired_by_child.get(parent_task_id, []):
                    if not self.registry.is_available(agent_type):
                        unavailable_agents.append(f"{parent_task_id}:{agent_type}")
                        continue
                    tasks.append(self._task_for_agent(agent_type, child, parent_task_id, decision_context))
        else:
            parent_task_id = str(query_plan.get("task_id") or "task_1")
            for agent_type in selected_agents:
                if not self.registry.is_available(agent_type):
                    unavailable_agents.append(agent_type)
                    continue
                tasks.append(self._task_for_agent(agent_type, query_plan, parent_task_id, decision_context))

        dependency_graph = {task.task_id: list(task.dependency_ids) for task in tasks}
        parallel_groups = self._parallel_groups(tasks)
        plan = AgentExecutionPlan(
            request_id=request_id,
            parent_plan_id=parent_plan_id,
            parent_intent=parent_intent,
            tasks=tasks,
            dependency_graph=dependency_graph,
            parallel_groups=parallel_groups,
            execution_allowed=False,
            unavailable_agents=_ordered_unique(unavailable_agents),
            metadata={
                "selected_agents": selected_agents,
                "child_agent_selections": {
                    str(child.get("task_id") or ""): desired_by_child.get(str(child.get("task_id") or ""), [])
                    for child in child_plans
                } if child_plans else {},
                "runtime_selection_authority": "child_intent_policy" if child_plans else "orchestrator_contract_selected_agents",
                "unavailable_runtime_policy": "metadata_only_agents_are_not_dispatched",
            },
        )
        print(
            "[AgentExecutionPlan] "
            f"request_id={plan.request_id} tasks={len(plan.tasks)} "
            f"parallel_groups={plan.parallel_groups} dependencies={plan.dependency_graph} "
            f"unavailable_agents={plan.unavailable_agents} "
            f"execution_allowed={str(plan.execution_allowed).lower()}"
        )
        return plan

    def _task_for_agent(self, agent_type: str, plan: Mapping[str, Any], parent_task_id: str, decision_context: Any = None) -> AgentTaskEnvelope:
        intent_family = str(plan.get("primary_intent") or "")
        task_id = f"{parent_task_id}:{agent_type}"
        required = agent_type not in {"TechnicalAnalysisAgent"}
        if agent_type == "MarketContextAgent":
            required = intent_family in {"market_state_analysis", "macro_market_impact"}
        if agent_type == "StrategyAgent":
            required = False
        if agent_type == "RiskAgent":
            required = False
        if agent_type == "StrategyRiskConsistencyAgent":
            required = False
        source_refs = self._source_refs_for_task(decision_context, parent_task_id)
        dependency_ids = []
        if agent_type == "StrategyAgent":
            dependency_ids = [f"{parent_task_id}:MarketContextAgent"]
        elif agent_type == "RiskAgent":
            dependency_ids = [f"{parent_task_id}:StrategyAgent"]
        elif agent_type == "StrategyRiskConsistencyAgent":
            dependency_ids = [f"{parent_task_id}:StrategyAgent", f"{parent_task_id}:RiskAgent"]
        return AgentTaskEnvelope(
            task_id=task_id,
            parent_task_id=parent_task_id,
            agent_type=agent_type,
            objective=self._objective(agent_type, intent_family),
            intent_family=intent_family,
            required=required,
            input_refs=["decision_context", "query_plan", "orchestrator_contract"],
            context_refs=[f"task_context:{parent_task_id}"],
            evidence_refs=self._evidence_refs(parent_task_id),
            source_refs=source_refs,
            dependency_ids=dependency_ids,
            timeout_ms=self.DEFAULT_TIMEOUT_MS,
            output_contract={
                "format": "AgentResultEnvelope",
                "agent_output_is_not_evidence": True,
            },
            failure_policy="required_blocks" if required else "optional_warns",
            metadata={
                "agent_result_policy": "references_evidence_only",
                "allowed_source_refs": source_refs,
            },
        )

    @staticmethod
    def _objective(agent_type: str, intent_family: str) -> str:
        return f"{agent_type} structured handoff for {intent_family or 'unknown_intent'}"

    @staticmethod
    def _evidence_refs(parent_task_id: str) -> List[str]:
        return [f"evidence_bundle:{parent_task_id}"] if parent_task_id else []

    @staticmethod
    def _child_agent_assignments(child_plans: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
        assignments: Dict[str, List[str]] = {}
        for child in child_plans:
            task_id = str(child.get("task_id") or "")
            intent = str(child.get("primary_intent") or "")
            assignments[task_id] = _ordered_unique(select_agents_for_intent(intent))
            print(
                "[ChildAgentSelection] "
                f"task_id={task_id} intent_family={intent} selected_agents={assignments[task_id]}"
            )
        return assignments

    @staticmethod
    def _source_refs_for_task(decision_context: Any, parent_task_id: str) -> List[str]:
        refs: List[str] = []
        for result in getattr(decision_context, "acquisition_results", []) or []:
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or "").lower()
            if status not in {"success", "reused"}:
                continue
            owners = set(result.get("requested_by_tasks") or result.get("task_ids") or [])
            if owners and parent_task_id and parent_task_id not in owners:
                continue
            result_id = str(result.get("result_id") or f"{result.get('capability', '')}:{result.get('target', '') or 'default'}")
            if result_id:
                refs.append(result_id)
        return _ordered_unique(refs)

    @staticmethod
    def _parallel_groups(tasks: Sequence[AgentTaskEnvelope]) -> List[List[str]]:
        remaining = {task.task_id: set(task.dependency_ids) for task in tasks}
        groups: List[List[str]] = []
        completed: Set[str] = set()
        while remaining:
            ready = sorted(task_id for task_id, deps in remaining.items() if deps <= completed)
            if not ready:
                groups.append(sorted(remaining))
                break
            groups.append(ready)
            for task_id in ready:
                completed.add(task_id)
                remaining.pop(task_id, None)
        return groups


class AgentResultValidator:
    @classmethod
    def validate(
        cls,
        task: AgentTaskEnvelope,
        result: Any,
        known_task_ids: Optional[Iterable[str]] = None,
    ) -> AgentResultEnvelope:
        reason_codes: List[str] = []
        if not isinstance(result, AgentResultEnvelope):
            return cls.invalid(task, "result_not_envelope")
        if result.task_id != task.task_id:
            reason_codes.append("task_id_mismatch")
        if result.agent_type != task.agent_type:
            reason_codes.append("agent_type_mismatch")
        if str(result.status).upper() not in TERMINAL_AGENT_STATUSES:
            reason_codes.append("invalid_status")
        if not 0.0 <= float(result.confidence or 0.0) <= 1.0:
            reason_codes.append("confidence_out_of_bounds")
        if not set(result.evidence_refs or []) <= set(task.evidence_refs or []):
            reason_codes.append("evidence_ref_out_of_scope")
        allowed_sources = set(task.source_refs or task.metadata.get("allowed_source_refs", []) or [])
        if result.source_refs and not set(result.source_refs or []) <= allowed_sources:
            reason_codes.append("source_ref_out_of_scope")
        known = set(known_task_ids or [])
        if known and not set(task.dependency_ids or []) <= known:
            reason_codes.append("unknown_dependency")
        if cls._contains_execution_instruction(result):
            reason_codes.append("execution_instruction_not_allowed")

        if reason_codes:
            return cls.invalid(task, ",".join(reason_codes), latency_ms=result.latency_ms)
        print(f"[AgentResultValidation] task_id={task.task_id} status=PASS reason_codes=[]")
        return result

    @staticmethod
    def invalid(task: AgentTaskEnvelope, reason: str, latency_ms: float = 0.0) -> AgentResultEnvelope:
        print(f"[AgentResultValidation] task_id={task.task_id} status=FAIL reason_codes=[{reason}]")
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.INVALID_RESULT,
            confidence=0.0,
            latency_ms=latency_ms,
            failure_code="AGENT_RESULT_INVALID",
            failure_reason=reason,
        )

    @staticmethod
    def _contains_execution_instruction(result: AgentResultEnvelope) -> bool:
        payload = result.structured_payload or {}
        if payload.get("execution_allowed") is True:
            return True
        text = " ".join([result.summary or "", str(payload), " ".join(result.warnings or [])]).lower()
        return any(token in text for token in ["place_order", "execute_trade", "mt5_order"])


class AgentDispatcher:
    BLOCKING_STATUSES = {
        AgentStatus.FAILED,
        AgentStatus.TIMEOUT,
        AgentStatus.UNAVAILABLE,
        AgentStatus.INVALID_RESULT,
        AgentStatus.DEPENDENCY_BLOCKED,
        AgentStatus.SKIPPED_WITH_REASON,
    }

    def __init__(self, registry: Optional[AgentRuntimeRegistry] = None):
        self.registry = registry or AgentRuntimeRegistry()
        self._attempts: Set[Tuple[str, str, int]] = set()

    def execute(
        self,
        plan: AgentExecutionPlan,
        context: AgentRuntimeContext,
        attempt: int = 1,
    ) -> List[AgentResultEnvelope]:
        task_by_id = {task.task_id: task for task in plan.tasks}
        results: Dict[str, AgentResultEnvelope] = {}
        for group in plan.parallel_groups or [list(task_by_id)]:
            ready: List[AgentTaskEnvelope] = []
            for task_id in group:
                task = task_by_id.get(task_id)
                if task is None:
                    continue
                blocked = self._dependency_block(task, results)
                if blocked:
                    results[task.task_id] = blocked
                else:
                    ready.append(task)
            if ready:
                group_results = self._execute_parallel(ready, context, plan, attempt)
                results.update({result.task_id: result for result in group_results})
                self._publish_agent_results(context, results)
        return [results[task.task_id] for task in plan.tasks if task.task_id in results]

    @staticmethod
    def _publish_agent_results(context: AgentRuntimeContext, results: Mapping[str, AgentResultEnvelope]) -> None:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        metadata["agent_results_by_task"] = dict(results)
        metadata["agent_results_by_parent_task"] = {
            result.parent_task_id or result.task_id: result
            for result in results.values()
        }
        context.metadata = metadata

    def _execute_parallel(
        self,
        tasks: Sequence[AgentTaskEnvelope],
        context: AgentRuntimeContext,
        plan: AgentExecutionPlan,
        attempt: int,
    ) -> List[AgentResultEnvelope]:
        outputs: List[AgentResultEnvelope] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as pool:
            futures = {pool.submit(self._execute_one, task, context, plan, attempt): task for task in tasks}
            for future, task in futures.items():
                try:
                    outputs.append(future.result(timeout=max(task.timeout_ms, 1) / 1000.0 + 0.05))
                except concurrent.futures.TimeoutError:
                    outputs.append(self._timeout_result(task, task.timeout_ms))
        return outputs

    def _execute_one(
        self,
        task: AgentTaskEnvelope,
        context: AgentRuntimeContext,
        plan: AgentExecutionPlan,
        attempt: int,
    ) -> AgentResultEnvelope:
        attempt_key = (plan.request_id, task.task_id, attempt)
        if attempt_key in self._attempts:
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=task.agent_type,
                status=AgentStatus.SKIPPED_WITH_REASON,
                confidence=0.0,
                failure_code="AGENT_DUPLICATE_DISPATCH",
                failure_reason="duplicate dispatch prevented",
            )
        self._attempts.add(attempt_key)
        runtime = self.registry.resolve(task.agent_type)
        print(
            "[AgentTaskDispatch] "
            f"task_id={task.task_id} parent_task_id={task.parent_task_id} "
            f"agent_type={task.agent_type} intent_family={task.intent_family} "
            f"required={str(task.required).lower()} status=start"
        )
        started = time.perf_counter()
        if runtime is None:
            result = AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=task.agent_type,
                status=AgentStatus.UNAVAILABLE,
                confidence=0.0,
                failure_code="AGENT_UNAVAILABLE",
                failure_reason="runtime not registered",
            )
        else:
            try:
                result = runtime.execute(task, context)
            except Exception as exc:
                result = AgentResultEnvelope(
                    task_id=task.task_id,
                    parent_task_id=task.parent_task_id,
                    agent_type=task.agent_type,
                    status=AgentStatus.FAILED,
                    confidence=0.0,
                    failure_code="AGENT_EXECUTION_FAILED",
                    failure_reason=str(exc),
                )
        result.latency_ms = result.latency_ms or round((time.perf_counter() - started) * 1000, 3)
        result = AgentResultValidator.validate(task, result, known_task_ids=[item.task_id for item in plan.tasks])
        print(
            "[AgentTaskResult] "
            f"task_id={result.task_id} agent_type={result.agent_type} "
            f"status={result.status} confidence={result.confidence} "
            f"latency_ms={result.latency_ms} failure_code={result.failure_code}"
        )
        return result

    def _dependency_block(
        self,
        task: AgentTaskEnvelope,
        results: Mapping[str, AgentResultEnvelope],
    ) -> Optional[AgentResultEnvelope]:
        if not task.dependency_ids:
            return None
        missing = [dep for dep in task.dependency_ids if dep not in results]
        blocked = [
            dep
            for dep in task.dependency_ids
            if dep in results and results[dep].status in self.BLOCKING_STATUSES
        ]
        status = "blocked" if missing or blocked else "ready"
        print(f"[AgentDependency] task_id={task.task_id} dependency_ids={task.dependency_ids} status={status}")
        if not missing and not blocked:
            return None
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.DEPENDENCY_BLOCKED,
            confidence=0.0,
            failure_code="AGENT_DEPENDENCY_BLOCKED",
            failure_reason=f"blocked dependencies={blocked or missing}",
        )

    @staticmethod
    def _timeout_result(task: AgentTaskEnvelope, timeout_ms: int) -> AgentResultEnvelope:
        result = AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.TIMEOUT,
            confidence=0.0,
            latency_ms=float(timeout_ms),
            failure_code="AGENT_TIMEOUT",
            failure_reason=f"timed out after {timeout_ms}ms",
        )
        print(
            "[AgentTaskResult] "
            f"task_id={result.task_id} agent_type={result.agent_type} "
            f"status={result.status} confidence={result.confidence} "
            f"latency_ms={result.latency_ms} failure_code={result.failure_code}"
        )
        return result


class AgentResultAggregator:
    FAILURE_STATUSES = {
        AgentStatus.FAILED,
        AgentStatus.TIMEOUT,
        AgentStatus.UNAVAILABLE,
        AgentStatus.INVALID_RESULT,
        AgentStatus.DEPENDENCY_BLOCKED,
        AgentStatus.SKIPPED_WITH_REASON,
    }

    @classmethod
    def aggregate(
        cls,
        plan: AgentExecutionPlan,
        results: Sequence[AgentResultEnvelope],
    ) -> AggregatedAgentResult:
        task_by_id = {task.task_id: task for task in plan.tasks}
        aggregate = AggregatedAgentResult(request_id=plan.request_id, task_results=list(results))
        if not plan.tasks:
            aggregate.status = "SKIPPED"
            aggregate.confidence_ceiling = "high"
            if plan.unavailable_agents:
                aggregate.warnings.append("selected agents have no registered runtime")
            cls._log(plan, aggregate)
            return aggregate

        for result in results:
            aggregate.result_refs.append(f"{result.task_id}:{result.agent_type}")
            if result.status == AgentStatus.SUCCESS:
                aggregate.successful_tasks.append(result.task_id)
            elif result.status == AgentStatus.PARTIAL:
                aggregate.partial_tasks.append(result.task_id)
            elif result.status == AgentStatus.UNAVAILABLE:
                aggregate.unavailable_tasks.append(result.task_id)
            elif result.status == AgentStatus.DEPENDENCY_BLOCKED:
                aggregate.blocked_tasks.append(result.task_id)
            elif result.status == AgentStatus.TIMEOUT:
                aggregate.timeout_tasks.append(result.task_id)
            elif result.status == AgentStatus.INVALID_RESULT:
                aggregate.invalid_tasks.append(result.task_id)
            elif result.status == AgentStatus.SKIPPED_WITH_REASON:
                aggregate.skipped_tasks.append(result.task_id)
            elif result.status == AgentStatus.FAILED:
                aggregate.failed_tasks.append(result.task_id)
            aggregate.warnings.extend(result.warnings or [])
            if result.failure_reason:
                aggregate.warnings.append(result.failure_reason)

        required_failures = [
            result
            for result in results
            if task_by_id.get(result.task_id, AgentTaskEnvelope(result.task_id, result.agent_type)).required
            and result.status in cls.FAILURE_STATUSES
        ]
        required_partials = [
            result
            for result in results
            if task_by_id.get(result.task_id, AgentTaskEnvelope(result.task_id, result.agent_type)).required
            and result.status == AgentStatus.PARTIAL
        ]
        optional_failures = [
            result
            for result in results
            if not task_by_id.get(result.task_id, AgentTaskEnvelope(result.task_id, result.agent_type)).required
            and result.status in cls.FAILURE_STATUSES
        ]
        if required_failures:
            aggregate.status = "FAIL"
            aggregate.confidence_ceiling = "low"
        elif required_partials or optional_failures or aggregate.partial_tasks:
            aggregate.status = "WARN"
            aggregate.confidence_ceiling = "medium"
        else:
            aggregate.status = "PASS"
            aggregate.confidence_ceiling = "high"
        cls._log(plan, aggregate)
        return aggregate

    @staticmethod
    def _log(plan: AgentExecutionPlan, aggregate: AggregatedAgentResult) -> None:
        print(
            "[AgentAggregation] "
            f"request_id={plan.request_id} "
            f"success={len(aggregate.successful_tasks)} "
            f"partial={len(aggregate.partial_tasks)} "
            f"failed={len(aggregate.failed_tasks)} "
            f"timeout={len(aggregate.timeout_tasks)} "
            f"blocked={len(aggregate.blocked_tasks)} "
            f"aggregate_status={aggregate.status}"
        )


def build_agent_handoff(plan: AgentExecutionPlan, aggregate: AggregatedAgentResult) -> AgentHandoffContext:
    evidence_refs = _ordered_unique(ref for result in aggregate.task_results for ref in result.evidence_refs)
    assessment_refs = _ordered_unique(
        str(result.structured_payload.get("assessment_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "MarketContextAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("assessment_ref")
    )
    assessment_refs_by_task = {
        str(result.parent_task_id or result.task_id): str(result.structured_payload.get("assessment_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "MarketContextAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("assessment_ref")
    }
    strategy_refs = _ordered_unique(
        str(result.structured_payload.get("thesis_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "StrategyAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("thesis_ref")
    )
    strategy_refs_by_task = {
        str(result.parent_task_id or result.task_id): str(result.structured_payload.get("thesis_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "StrategyAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("thesis_ref")
    }
    risk_refs = _ordered_unique(
        str(result.structured_payload.get("risk_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "RiskAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("risk_ref")
    )
    risk_refs_by_task = {
        str(result.parent_task_id or result.task_id): str(result.structured_payload.get("risk_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "RiskAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("risk_ref")
    }
    consistency_refs = _ordered_unique(
        str(result.structured_payload.get("consistency_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "StrategyRiskConsistencyAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("consistency_ref")
    )
    consistency_refs_by_task = {
        str(result.parent_task_id or result.task_id): str(result.structured_payload.get("consistency_ref") or "")
        for result in aggregate.task_results
        if result.agent_type == "StrategyRiskConsistencyAgent"
        and result.status == AgentStatus.SUCCESS
        and isinstance(result.structured_payload, dict)
        and result.structured_payload.get("consistency_ref")
    }
    handoff = AgentHandoffContext(
        request_id=plan.request_id,
        parent_plan_id=plan.parent_plan_id,
        agent_execution_status=aggregate.status,
        agent_results=list(aggregate.task_results),
        aggregated_result=aggregate,
        evidence_refs=evidence_refs,
        market_context_assessment_refs=assessment_refs,
        market_context_assessments_by_task=assessment_refs_by_task,
        strategy_thesis_refs=strategy_refs,
        strategy_theses_by_task=strategy_refs_by_task,
        risk_assessment_refs=risk_refs,
        risk_assessments_by_task=risk_refs_by_task,
        consistency_assessment_refs=consistency_refs,
        consistency_assessments_by_task=consistency_refs_by_task,
        warnings=list(aggregate.warnings),
        confidence_ceiling=aggregate.confidence_ceiling,
    )
    print(
        "[AgentHandoff] "
        f"request_id={handoff.request_id} status={handoff.agent_execution_status} "
        f"result_refs={aggregate.result_refs} "
        f"market_context_assessment={str(bool(assessment_refs)).lower()} "
        f"task_id={','.join(result.parent_task_id or result.task_id for result in aggregate.task_results if result.agent_type == 'MarketContextAgent')} "
        f"assessment_ref={','.join(assessment_refs)} "
        f"strategy_thesis={str(bool(strategy_refs)).lower()} "
        f"strategy_task_id={','.join(result.parent_task_id or result.task_id for result in aggregate.task_results if result.agent_type == 'StrategyAgent')} "
        f"thesis_ref={','.join(strategy_refs)} "
        f"risk_assessment={str(bool(risk_refs)).lower()} "
        f"risk_task_id={','.join(result.parent_task_id or result.task_id for result in aggregate.task_results if result.agent_type == 'RiskAgent')} "
        f"risk_ref={','.join(risk_refs)} "
        f"consistency_assessment={str(bool(consistency_refs)).lower()} "
        f"consistency_task_id={','.join(result.parent_task_id or result.task_id for result in aggregate.task_results if result.agent_type == 'StrategyRiskConsistencyAgent')} "
        f"consistency_ref={','.join(consistency_refs)} "
        f"warnings={handoff.warnings}"
    )
    return handoff


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output

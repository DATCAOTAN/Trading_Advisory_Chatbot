from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.services.semantic.capability_registry import CapabilityRegistry
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements


@dataclass(frozen=True)
class ContextTask:
    capability: str
    target: str = ""
    service_name: str = ""
    operation_name: str = ""
    required: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def task_id(self) -> str:
        return f"{self.capability}:{self.target or 'default'}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id(),
            "capability": self.capability,
            "target": self.target,
            "service_name": self.service_name,
            "operation_name": self.operation_name,
            "required": self.required,
            "parameters": dict(self.parameters),
            "dependencies": list(self.dependencies),
        }


@dataclass
class ContextExecutionPlan:
    parallel_tasks: List[ContextTask] = field(default_factory=list)
    dependent_tasks: List[ContextTask] = field(default_factory=list)
    unavailable_capabilities: List[str] = field(default_factory=list)
    deduplicated_tasks: List[ContextTask] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "parallel_tasks": [task.as_dict() for task in self.parallel_tasks],
            "dependent_tasks": [task.as_dict() for task in self.dependent_tasks],
            "unavailable_capabilities": list(self.unavailable_capabilities),
            "deduplicated_tasks": [task.as_dict() for task in self.deduplicated_tasks],
        }


@dataclass
class ContextAcquisitionResult:
    """Normalized result envelope for one planned context need.

    The executor/result layer is deliberately provider-neutral: it records
    whether an existing service/output actually satisfied a ContextNeed.
    """

    capability: str
    target: str = ""
    status: str = "missing"
    required: bool = True
    task_id: str = ""
    normalized_parameters: Dict[str, Any] = field(default_factory=dict)
    requested_by_tasks: List[str] = field(default_factory=list)
    data: Any = None
    source: str = ""
    operation: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    fetched_at: str = ""
    source_timestamp: str = ""
    freshness_status: str = "unknown"
    latency_ms: float = 0.0
    from_cache: bool = False
    reused_from_runtime: bool = False
    retryable: bool = False
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    dependency_status: str = ""
    reason: str = ""
    task_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = self.result_id()
        if not self.fetched_at:
            self.fetched_at = self.created_at
        if not self.requested_by_tasks and self.task_ids:
            self.requested_by_tasks = list(self.task_ids)
        if not self.task_ids and self.requested_by_tasks:
            self.task_ids = list(self.requested_by_tasks)

    @property
    def ok(self) -> bool:
        return self.status in {"success", "reused"}

    def result_id(self) -> str:
        return f"{self.capability}:{self.target or 'default'}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id(),
            "task_id": self.task_id,
            "capability": self.capability,
            "target": self.target,
            "normalized_parameters": dict(self.normalized_parameters),
            "status": self.status,
            "required": self.required,
            "requested_by_tasks": list(self.requested_by_tasks or self.task_ids),
            "data": _safe_data(self.data),
            "source": self.source,
            "operation": self.operation,
            "provenance": dict(self.provenance),
            "fetched_at": self.fetched_at,
            "source_timestamp": self.source_timestamp,
            "freshness_status": self.freshness_status,
            "latency_ms": self.latency_ms,
            "from_cache": self.from_cache,
            "reused_from_runtime": self.reused_from_runtime,
            "retryable": self.retryable,
            "warnings": list(self.warnings),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "dependency_status": self.dependency_status,
            "reason": self.reason,
            "task_ids": list(self.task_ids),
            "created_at": self.created_at,
        }


class ContextExecutionPlanner:
    """Resolve ContextNeeds into existing-service tasks.

    This planner describes an execution graph. It does not perform data fetches.
    """

    def __init__(self, registry: CapabilityRegistry = None):
        self.registry = registry or CapabilityRegistry.default()

    def plan(self, requirements: ContextRequirements) -> ContextExecutionPlan:
        needs = self._with_dependencies(requirements.needs)
        tasks: List[ContextTask] = []
        unavailable: List[str] = []
        seen = set()

        for need in needs:
            definition = self.registry.get(need.capability)
            if not definition or not definition.enabled:
                name = f"{need.capability}:{need.target or 'default'}"
                if name not in unavailable:
                    unavailable.append(name)
                continue
            task = ContextTask(
                capability=need.capability,
                target=need.target,
                service_name=definition.service_name,
                operation_name=definition.operation_name,
                required=need.required,
                parameters=dict(need.parameters),
                dependencies=list(definition.dependencies),
            )
            key = self._task_key(task)
            if key in seen:
                continue
            seen.add(key)
            tasks.append(task)

        dependent = [task for task in tasks if task.dependencies]
        parallel = [task for task in tasks if not task.dependencies]
        plan = ContextExecutionPlan(
            parallel_tasks=parallel,
            dependent_tasks=dependent,
            unavailable_capabilities=unavailable,
            deduplicated_tasks=tasks,
        )
        print(
            "[ContextExecutionPlan] "
            f"parallel={[task.task_id() for task in parallel]} "
            f"dependent={[task.task_id() for task in dependent]} "
            f"unavailable={unavailable}"
        )
        return plan

    def _with_dependencies(self, needs: List[ContextNeed]) -> List[ContextNeed]:
        output = list(needs)
        seen = {(need.capability, need.target, tuple(sorted((str(k), str(v)) for k, v in need.parameters.items()))) for need in output}
        for need in list(needs):
            definition = self.registry.get(need.capability)
            if not definition:
                continue
            for dependency in definition.dependencies:
                dep_key = (
                    dependency,
                    need.target,
                    tuple(sorted((str(k), str(v)) for k, v in need.parameters.items())),
                )
                if dep_key in seen:
                    continue
                output.append(
                    ContextNeed(
                        capability=dependency,
                        target=need.target,
                        required=need.required,
                        parameters=dict(need.parameters),
                        reason=f"dependency for {need.capability}",
                        priority=max(need.priority - 1, 1),
                    )
                )
                seen.add(dep_key)
        return output

    @staticmethod
    def _task_key(task: ContextTask) -> tuple:
        return (
            task.capability,
            task.target,
            tuple(sorted((str(k), str(v)) for k, v in task.parameters.items())),
        )


def _safe_data(value: Any) -> Any:
    """Preserve acquisition payloads in dict form without requiring JSON serialization."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_data(item) for item in value]
    if hasattr(value, "__dict__"):
        return {str(key): _safe_data(item) for key, item in vars(value).items() if not str(key).startswith("_")}
    return str(value)

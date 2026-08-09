import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.config import Config
from src.services.knowledge.answer_mode import AnswerModeClassifier
from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter
from src.services.semantic.capability_registry import CapabilityRegistry
from src.services.semantic.context_execution import (
    ContextAcquisitionResult,
    ContextExecutionPlan,
    ContextTask,
)
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements
from src.services.semantic.query_plan import QueryPlan, QueryPlanAssembler
from src.services.trading.market.timeframes import (
    normalize_timeframe,
    stale_seconds_for_timeframe,
    timeframe_duration_seconds,
)
from src.services.trading.reasoning.strategy_evidence import IndicatorSpec


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContextAcquisitionBatchResult:
    request_id: str
    results: List[ContextAcquisitionResult] = field(default_factory=list)
    success_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    unavailable_count: int = 0
    skipped_count: int = 0
    reused_count: int = 0
    deduplicated_count: int = 0
    total_latency_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    task_context_views: List["TaskContextView"] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "results": [result.as_dict() for result in self.results],
            "success_count": self.success_count,
            "partial_count": self.partial_count,
            "failed_count": self.failed_count,
            "unavailable_count": self.unavailable_count,
            "skipped_count": self.skipped_count,
            "reused_count": self.reused_count,
            "deduplicated_count": self.deduplicated_count,
            "total_latency_ms": self.total_latency_ms,
            "warnings": list(self.warnings),
            "task_context_views": [view.as_dict() for view in self.task_context_views],
        }


@dataclass
class TaskContextView:
    task_id: str
    subquery: str = ""
    query_plan: Dict[str, Any] = field(default_factory=dict)
    required_context_results: List[Dict[str, Any]] = field(default_factory=list)
    optional_context_results: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_context: List[Dict[str, Any]] = field(default_factory=list)
    market_context: List[Dict[str, Any]] = field(default_factory=list)
    event_context: List[Dict[str, Any]] = field(default_factory=list)
    technical_context: List[Dict[str, Any]] = field(default_factory=list)
    missing_required_context: List[str] = field(default_factory=list)
    missing_optional_context: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sufficiency_status: str = "INSUFFICIENT"
    confidence_ceiling: str = "low"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "subquery": self.subquery,
            "query_plan": dict(self.query_plan),
            "required_context_results": list(self.required_context_results),
            "optional_context_results": list(self.optional_context_results),
            "knowledge_context": list(self.knowledge_context),
            "market_context": list(self.market_context),
            "event_context": list(self.event_context),
            "technical_context": list(self.technical_context),
            "missing_required_context": list(self.missing_required_context),
            "missing_optional_context": list(self.missing_optional_context),
            "warnings": list(self.warnings),
            "sufficiency_status": self.sufficiency_status,
            "confidence_ceiling": self.confidence_ceiling,
        }


class RuntimeContextStore:
    """Request-scoped context cache used to reuse compatible prefetch outputs."""

    def __init__(self):
        self._results: Dict[Tuple[str, str, Tuple[Tuple[str, str], ...]], ContextAcquisitionResult] = {}

    def put(self, result: ContextAcquisitionResult) -> None:
        self._results[self._key(result.capability, result.target, result.normalized_parameters)] = result

    def put_many(self, results: Iterable[ContextAcquisitionResult]) -> None:
        for result in results or []:
            self.put(result)

    def find_compatible(self, need: ContextNeed) -> Optional[ContextAcquisitionResult]:
        direct = self._results.get(self._key(need.capability, need.target, self._normalized_parameters(need)))
        if direct and self._is_compatible(direct, need):
            return direct
        for result in self._results.values():
            if result.capability != need.capability:
                continue
            if self._is_compatible(result, need):
                return result
        return None

    @staticmethod
    def from_legacy_outputs(
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        live_price_output: Optional[str] = None,
        candles_output: Optional[List[Dict[str, Any]]] = None,
        calendar_output: Optional[str] = None,
        market_adapter: Any = None,
        calendar_adapter: Any = None,
        symbol: str = "XAUUSD",
        timeframe: str = "1h",
    ) -> "RuntimeContextStore":
        store = RuntimeContextStore()
        if retrieval_results:
            for doc in retrieval_results:
                metadata = doc.get("metadata", {}) if isinstance(doc, dict) else {}
                capability = "official_report" if metadata.get("knowledge_type") == "report" else "static_knowledge"
                target = metadata.get("event_type") or metadata.get("subdomain") or metadata.get("title") or "static_knowledge"
                store.put(
                    ContextAcquisitionResult(
                        capability=capability,
                        target=str(target),
                        status="success",
                        data=doc,
                        source="legacy_runtime",
                        operation="prefetched_retrieval",
                        provenance=_knowledge_provenance(doc),
                        freshness_status="acceptable",
                        reason="legacy_prefetch",
                    )
                )
        if live_price_output is not None and market_adapter is not None:
            snapshot = market_adapter.get_snapshot(
                symbol=symbol,
                timeframe=timeframe,
                live_price_output=live_price_output,
                candles_output=[],
            )
            store.put(
                ContextAcquisitionResult(
                    capability="market_snapshot",
                    target=symbol,
                    status="success",
                    data=snapshot,
                    source="legacy_runtime",
                    operation="Live_API.prefetch",
                    provenance={"provider": snapshot.source or "legacy_runtime", "symbol": snapshot.symbol},
                    freshness_status="fresh",
                    source_timestamp=snapshot.timestamp,
                    reason="legacy_prefetch",
                )
            )
        if candles_output is not None:
            store.put(
                ContextAcquisitionResult(
                    capability="ohlcv",
                    target=symbol,
                    status="success",
                    data=list(candles_output or []),
                    source="legacy_runtime",
                    operation="Live_API.prefetch",
                    provenance={"provider": "legacy_runtime", "symbol": symbol, "timeframe": timeframe},
                    freshness_status="fresh",
                    reason="legacy_prefetch",
                )
            )
        if calendar_output is not None and calendar_adapter is not None:
            events = calendar_adapter.get_events(calendar_output=calendar_output)
            for event in events or []:
                target = _event_target_from_name(getattr(event, "event_name", ""))
                store.put(
                    ContextAcquisitionResult(
                        capability="economic_event",
                        target=target or "macro",
                        status="success",
                        data=event,
                        source="legacy_runtime",
                        operation="Live_API.prefetch",
                        provenance={
                            "provider": getattr(event, "source", "legacy_runtime"),
                            "event_type": target,
                            "title": getattr(event, "event_name", ""),
                        },
                        freshness_status="fresh",
                        source_timestamp=getattr(event, "release_time", ""),
                        reason="legacy_prefetch",
                    )
                )
        return store

    @staticmethod
    def _normalized_parameters(need: ContextNeed) -> Dict[str, Any]:
        return dict(need.parameters or {})

    @staticmethod
    def _key(capability: str, target: str, parameters: Optional[Dict[str, Any]] = None) -> Tuple[str, str, Tuple[Tuple[str, str], ...]]:
        normalized_target = AnswerModeClassifier.normalize(target or "default")
        params = tuple(sorted((str(key), str(value)) for key, value in (parameters or {}).items()))
        return capability, normalized_target, params

    @staticmethod
    def _is_compatible(result: ContextAcquisitionResult, need: ContextNeed) -> bool:
        if result.status not in {"success", "reused"}:
            return False
        if not _target_matches(result.target, need.target, capability=need.capability):
            return False
        if result.freshness_status == "stale":
            return False
        if need.capability == "official_report":
            return _provenance_matches_official_target(result.provenance, need.target)
        if need.capability == "market_knowledge":
            return _knowledge_result_matches(need, result)
        if need.capability == "static_knowledge":
            return _knowledge_result_matches(need, result)
        return True


class ContextAcquisitionExecutor:
    """Execute a ContextExecutionPlan through existing services only."""

    KNOWLEDGE_CAPABILITIES = {"official_report", "static_knowledge", "market_knowledge"}

    def __init__(
        self,
        retrieval_adapter: Any = None,
        reranker_module: Any = None,
        market_adapter: Any = None,
        calendar_adapter: Any = None,
        technical_adapter: Any = None,
        live_service: Any = None,
        use_v3: Optional[bool] = None,
        fallback_to_legacy: Optional[bool] = None,
        enable_reranker: Optional[bool] = None,
        position_read_service: Any = None,
    ):
        self.retrieval_adapter = retrieval_adapter
        self.reranker_module = reranker_module
        self.market_adapter = market_adapter
        self.calendar_adapter = calendar_adapter
        self.technical_adapter = technical_adapter
        self.live_service = live_service
        self.use_v3 = Config.USE_KNOWLEDGE_V3 if use_v3 is None else use_v3
        self.fallback_to_legacy = Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY if fallback_to_legacy is None else fallback_to_legacy
        self.knowledge_use_v3 = Config.SEMANTIC_CONTEXT_KNOWLEDGE_USE_V3
        self.knowledge_fallback_to_legacy = Config.SEMANTIC_CONTEXT_KNOWLEDGE_FALLBACK_TO_LEGACY
        self.enable_reranker = enable_reranker
        self.position_read_service = position_read_service
        self.intent_router = QueryIntentRouter()

    def execute(
        self,
        query_plan: QueryPlan,
        requirements: ContextRequirements,
        execution_plan: ContextExecutionPlan,
        registry: Optional[CapabilityRegistry] = None,
        runtime_store: Optional[RuntimeContextStore] = None,
        request_id: Optional[str] = None,
    ) -> ContextAcquisitionBatchResult:
        started = time.time()
        request_id = request_id or uuid.uuid4().hex[:12]
        runtime_store = runtime_store or RuntimeContextStore()
        registry = registry or CapabilityRegistry.default()
        need_map = self._need_map(requirements, execution_plan)
        results_by_key: Dict[str, ContextAcquisitionResult] = {}
        warnings: List[str] = []

        print(f"[ContextAcquisition] status=start request_id={request_id} tasks={len(execution_plan.deduplicated_tasks)}")

        parallel_results = self._execute_task_group(
            execution_plan.parallel_tasks,
            query_plan,
            requirements,
            need_map,
            runtime_store,
            registry,
        )
        for result in parallel_results:
            results_by_key[result.result_id()] = result
            runtime_store.put(result)

        for task in execution_plan.dependent_tasks:
            dependency_failure = self._dependency_failure(task, results_by_key)
            if dependency_failure:
                result = self._result_from_task(
                    task,
                    need_map.get(task.task_id()),
                    "skipped",
                    reason=f"failed_dependency:{dependency_failure}",
                    dependency_status="failed",
                    task_ids=self._requested_by(requirements, task.task_id()),
                )
            else:
                result = self._execute_one(task, query_plan, need_map.get(task.task_id()), runtime_store, registry, requirements)
                runtime_store.put(result)
            results_by_key[result.result_id()] = result

        for unavailable in execution_plan.unavailable_capabilities:
            cap, target = self._split_task_name(unavailable)
            need = need_map.get(unavailable) or ContextNeed(cap, target, True)
            result = ContextAcquisitionResult(
                capability=cap,
                target=target,
                status="unavailable",
                required=need.required,
                normalized_parameters=dict(need.parameters),
                requested_by_tasks=self._requested_by(requirements, unavailable),
                source="capability_registry",
                operation="unavailable",
                freshness_status="unknown",
                reason="capability unavailable",
                error_code="capability_unavailable",
            )
            results_by_key[result.result_id()] = result

        self._account_for_unfinished_scheduled_tasks(
            execution_plan,
            requirements,
            need_map,
            results_by_key,
        )

        results = list(results_by_key.values())
        task_views = self._build_task_views(query_plan, requirements, results)
        batch = self._batch_result(request_id, results, started, task_views, warnings)
        print(
            "[ContextAcquisition] "
            f"status=complete success={batch.success_count} partial={batch.partial_count} "
            f"failed={batch.failed_count} unavailable={batch.unavailable_count} "
            f"reused={batch.reused_count} deduplicated={batch.deduplicated_count} "
            f"latency_ms={batch.total_latency_ms:.2f}"
        )
        return batch

    def _execute_task_group(
        self,
        tasks: List[ContextTask],
        query_plan: QueryPlan,
        requirements: ContextRequirements,
        need_map: Dict[str, ContextNeed],
        runtime_store: RuntimeContextStore,
        registry: CapabilityRegistry,
    ) -> List[ContextAcquisitionResult]:
        if not tasks:
            return []
        knowledge_tasks = [task for task in tasks if task.capability in self.KNOWLEDGE_CAPABILITIES]
        other_tasks = [task for task in tasks if task.capability not in self.KNOWLEDGE_CAPABILITIES]
        max_workers = min(max(len(tasks), 1), 5)
        output: List[ContextAcquisitionResult] = []
        for task in knowledge_tasks:
            result = self._execute_one(
                task,
                query_plan,
                need_map.get(task.task_id()),
                runtime_store,
                registry,
                requirements,
            )
            output.append(result)
            runtime_store.put(result)
        if other_tasks:
            max_workers = min(max(len(other_tasks), 1), 5)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        self._execute_one,
                        task,
                        query_plan,
                        need_map.get(task.task_id()),
                        runtime_store,
                        registry,
                        requirements,
                    ): task
                    for task in other_tasks
                }
                for future in as_completed(futures):
                    output.append(future.result())
        return output

    def _execute_one(
        self,
        task: ContextTask,
        query_plan: QueryPlan,
        need: Optional[ContextNeed],
        runtime_store: RuntimeContextStore,
        registry: CapabilityRegistry,
        requirements: ContextRequirements,
    ) -> ContextAcquisitionResult:
        need = need or ContextNeed(task.capability, task.target, task.required, parameters=task.parameters)
        requested_by = self._requested_by(requirements, task.task_id())
        reused = runtime_store.find_compatible(need)
        if reused:
            result = replace(
                reused,
                status="reused",
                required=need.required,
                requested_by_tasks=requested_by,
                task_ids=requested_by,
                reused_from_runtime=True,
                reason="compatible runtime context reused",
            )
            print(
                "[ContextReuse] "
                f"capability={need.capability} target={need.target} "
                "status=reused source=legacy_runtime"
            )
            return result

        if len(requested_by) > 1:
            print(
                "[ContextDedup] "
                f"capability={need.capability} target={need.target} "
                f"requested_by={len(requested_by)} executed=1"
            )

        print(
            "[ContextAcquisition] "
            f"task_id={task.task_id()} capability={need.capability} "
            f"target={need.target} required={str(need.required).lower()} status=start"
        )
        started = time.time()
        try:
            if need.capability in self.KNOWLEDGE_CAPABILITIES:
                return self._execute_knowledge(need, task, query_plan, requested_by, started)
            if need.capability == "market_snapshot":
                return self._execute_market_snapshot(need, task, requested_by, started)
            if need.capability == "ohlcv":
                return self._execute_ohlcv(need, task, requested_by, started)
            if need.capability == "economic_event":
                return self._execute_economic_event(need, task, requested_by, started)
            if need.capability == "technical_snapshot":
                return self._execute_technical_snapshot(need, task, requested_by, started, runtime_store)
            if need.capability == "position_read":
                return self._execute_position_read(need, task, query_plan, requested_by, started)
            if need.capability in {"account_state", "instrument_spec", "stop_distance", "risk_limit"}:
                return self._result_from_task(
                    task,
                    need,
                    "unavailable",
                    reason="risk/account capability unavailable",
                    error_code="capability_unavailable",
                    task_ids=requested_by,
                    latency_ms=self._latency(started),
                )
            return self._result_from_task(
                task,
                need,
                "failed",
                reason="unsupported capability",
                error_code="unsupported_capability",
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )
        except Exception as exc:
            return self._result_from_task(
                task,
                need,
                "failed",
                reason="executor exception",
                error_code=type(exc).__name__,
                error_message=str(exc)[:500],
                retryable=True,
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )

    def _execute_position_read(
        self,
        need: ContextNeed,
        task: ContextTask,
        query_plan: QueryPlan,
        requested_by: List[str],
        started: float,
    ) -> ContextAcquisitionResult:
        if self.position_read_service is None:
            from src.services.trading.position_read_model import PositionReadModelService

            self.position_read_service = PositionReadModelService()
        model = self.position_read_service.read_from_query_plan(query_plan)
        status = "success" if model.status == "AVAILABLE" else "unavailable"
        return self._result_from_task(
            task,
            need,
            status,
            data=model,
            source="authenticated_mt5_lifecycle_snapshot",
            operation="PositionReadModelService.read_from_query_plan",
            provenance={
                "snapshot_reference": model.snapshot_reference,
                "metadata_redacted": True,
            },
            source_timestamp=model.snapshot_timestamp,
            freshness_status="fresh" if status == "success" else "unavailable",
            reason=("authoritative position state" if status == "success" else ",".join(model.blockers)),
            error_code=("" if status == "success" else (model.blockers[0] if model.blockers else "POSITION_READ_UNAVAILABLE")),
            task_ids=requested_by,
            latency_ms=self._latency(started),
        )

    def _execute_knowledge(
        self,
        need: ContextNeed,
        task: ContextTask,
        query_plan: QueryPlan,
        requested_by: List[str],
        started: float,
    ) -> ContextAcquisitionResult:
        if not self.retrieval_adapter:
            return self._result_from_task(task, need, "unavailable", reason="retrieval adapter missing", task_ids=requested_by)

        query_text = self._knowledge_query(need, query_plan)
        query_intent = self._intent_for_need(need, query_text, query_plan)
        filters = self.retrieval_adapter.infer_routing_filters(query_text, query_intent=query_intent)
        filters.update(self._knowledge_constraint_filters(need))
        previous_chunk_ids = set(getattr(query_plan, "previous_chunk_ids", []) or [])
        candidate_pool_size = getattr(query_plan, "candidate_pool_size", 0)
        is_refinement = getattr(query_plan, "is_refinement", False)
        if candidate_pool_size > 0:
            top_k = candidate_pool_size
        else:
            top_k = Config.RETRIEVAL_TOP_K * 2 if previous_chunk_ids else Config.RETRIEVAL_TOP_K
        
        raw_docs = self.retrieval_adapter.retrieve(
            query_text,
            filters=filters,
            top_k=top_k,
            use_v3=self.knowledge_use_v3,
            fallback_to_legacy=self.knowledge_fallback_to_legacy,
            query_intent=query_intent,
        )
        trace = getattr(self.retrieval_adapter, "last_trace", None)
        print(
            "[KnowledgeAcquisition] "
            f"capability={need.capability} "
            f"target={need.target} "
            f"retrieval_mode={getattr(trace, 'mode_used', 'v3' if self.knowledge_use_v3 else 'legacy')} "
            f"requested_v3={str(getattr(trace, 'requested_v3', self.knowledge_use_v3)).lower()} "
            f"collection={getattr(trace, 'collection', 'knowledge_current' if self.knowledge_use_v3 else '')}"
        )
        if is_refinement:
            print(
                "[RefinementCandidates] "
                f"stage=retrieved capability={need.capability} target={need.target} "
                f"count={len(raw_docs or [])} ids={[self._doc_identity(doc) for doc in (raw_docs or [])[:12]]}"
            )
        
        if previous_chunk_ids:
            import hashlib
            filtered_docs = []
            rejected_docs = []
            for doc in raw_docs:
                chunk_id = doc.get("metadata", {}).get("chunk_id") or doc.get("chunk_id")
                parent_chunk_id = doc.get("metadata", {}).get("parent_chunk_id") or doc.get("parent_id")
                content = doc.get("content", "")
                
                # Compute the exact redundancy_group as evidence_pipeline.py
                redundancy_group = str(parent_chunk_id or chunk_id or hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:12])
                
                # Exclude if either chunk_id or redundancy_group matches any previously retrieved IDs
                if chunk_id not in previous_chunk_ids and parent_chunk_id not in previous_chunk_ids and redundancy_group not in previous_chunk_ids:
                    filtered_docs.append(doc)
                else:
                    rejected_docs.append(doc)
                    print(f"🚫 [ContextAcquisition] Loại bỏ chunk trùng lặp (chunk_id={chunk_id}, redundancy_group={redundancy_group})")
            
            raw_docs = filtered_docs[:top_k]
            if is_refinement:
                print(
                    "[RefinementCandidates] "
                    f"stage=dedup_filtered kept={len(raw_docs)} rejected={len(rejected_docs)} "
                    f"ids={[self._doc_identity(doc) for doc in raw_docs[:12]]}"
                )
             
        docs = raw_docs
        if self.reranker_module and raw_docs:
            is_refinement = getattr(query_plan, "is_refinement", False)
            try:
                _, docs = self.reranker_module.process(
                    query_text,
                    raw_docs,
                    enabled=self.enable_reranker,
                    query_intent=query_intent,
                    is_refinement=is_refinement,
                )
            except TypeError as exc:
                if "is_refinement" not in str(exc):
                    raise
                _, docs = self.reranker_module.process(
                    query_text,
                    raw_docs,
                    enabled=self.enable_reranker,
                    query_intent=query_intent,
                )
        if is_refinement:
            print(
                "[RefinementCandidates] "
                f"stage=reranked_packed count={len(docs or [])} "
                f"ids={[self._doc_identity(doc) for doc in (docs or [])[:12]]}"
            )
        matched_docs = self._matching_docs(need, docs or [])
        if is_refinement:
            print(
                "[RefinementCandidates] "
                f"stage=compatible_matched count={len(matched_docs or [])} "
                f"ids={[self._doc_identity(doc) for doc in (matched_docs or [])[:12]]}"
            )
        if not matched_docs:
            return self._result_from_task(
                task,
                need,
                "failed",
                reason="no compatible knowledge source",
                error_code="knowledge_not_found",
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )
        provenance = _knowledge_provenance(matched_docs[0])
        return self._result_from_task(
            task,
            need,
            "success",
            data=matched_docs,
            source=provenance.get("source") or provenance.get("title") or "KnowledgeV3",
            operation="retrieval_adapter.retrieve",
            provenance=provenance,
            freshness_status="acceptable",
            source_timestamp=provenance.get("period", ""),
            reason="matched",
            task_ids=requested_by,
            latency_ms=self._latency(started),
        )

    def _execute_market_snapshot(
        self,
        need: ContextNeed,
        task: ContextTask,
        requested_by: List[str],
        started: float,
    ) -> ContextAcquisitionResult:
        if not self.market_adapter:
            return self._result_from_task(task, need, "unavailable", reason="market adapter missing", task_ids=requested_by)
        symbol = need.target
        if not symbol:
            return self._result_from_task(
                task, need, "unavailable", reason="symbol unresolved", error_code="symbol_unresolved", task_ids=requested_by
            )
        timeframe = str(need.parameters.get("timeframe") or "1h")
        snapshot = self.market_adapter.get_snapshot(symbol=symbol, timeframe=timeframe, candles_output=[])
        return self._result_from_task(
            task,
            need,
            "success",
            data=snapshot,
            source=snapshot.source or "existing_api",
            operation="LiveDataService.get_live_price",
            provenance={"provider": snapshot.source or "existing_api", "symbol": snapshot.symbol},
            freshness_status="fresh",
            source_timestamp=snapshot.timestamp,
            reason="matched",
            task_ids=requested_by,
            latency_ms=self._latency(started),
        )

    def _execute_ohlcv(
        self,
        need: ContextNeed,
        task: ContextTask,
        requested_by: List[str],
        started: float,
    ) -> ContextAcquisitionResult:
        if not self.live_service:
            return self._result_from_task(task, need, "unavailable", reason="live service missing", task_ids=requested_by)
        symbol = need.target
        if not symbol:
            return self._result_from_task(
                task, need, "unavailable", reason="symbol unresolved", error_code="symbol_unresolved", task_ids=requested_by
            )
        timeframe = str(need.parameters.get("timeframe") or "1h")
        limit = int(need.parameters.get("limit") or 100)
        candles = self.live_service.get_historical_candles(symbol=symbol, timeframe=timeframe, limit=limit)
        freshness, latest_timestamp = _ohlcv_freshness(candles, timeframe)
        status = "success" if candles and freshness == "fresh" else "failed"
        reason = "matched" if status == "success" else "stale ohlcv" if candles else "empty ohlcv"
        return self._result_from_task(
            task,
            need,
            status,
            data=list(candles or []),
            source="existing_api",
            operation="LiveDataService.get_historical_candles",
            provenance={"provider": "existing_api", "symbol": symbol, "timeframe": timeframe},
            freshness_status=freshness,
            source_timestamp=latest_timestamp,
            reason=reason,
            error_code="" if status == "success" else "stale_ohlcv" if candles else "empty_ohlcv",
            retryable=not bool(candles),
            task_ids=requested_by,
            latency_ms=self._latency(started),
        )

    def _execute_economic_event(
        self,
        need: ContextNeed,
        task: ContextTask,
        requested_by: List[str],
        started: float,
    ) -> ContextAcquisitionResult:
        if not self.calendar_adapter:
            return self._result_from_task(task, need, "unavailable", reason="calendar adapter missing", task_ids=requested_by)
        events = self.calendar_adapter.get_events()
        event = _matching_event(need.target, events)
        if not event:
            return self._result_from_task(
                task,
                need,
                "failed",
                data=list(events or []),
                source="existing_api",
                operation="LiveDataService.get_economic_calendar",
                provenance={"provider": "existing_api", "event_type": need.target},
                freshness_status="fresh" if events else "unknown",
                reason="matching economic event missing",
                error_code="event_not_found",
                retryable=True,
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )
        return self._result_from_task(
            task,
            need,
            "success",
            data=event,
            source=getattr(event, "source", "existing_api"),
            operation="LiveDataService.get_economic_calendar",
            provenance={
                "provider": getattr(event, "source", "existing_api"),
                "event_type": _event_target_from_name(getattr(event, "event_name", "")) or need.target,
                "title": getattr(event, "event_name", ""),
                "country": getattr(event, "country", ""),
            },
            freshness_status="fresh",
            source_timestamp=getattr(event, "release_time", ""),
            reason="matched",
            task_ids=requested_by,
            latency_ms=self._latency(started),
        )

    def _execute_technical_snapshot(
        self,
        need: ContextNeed,
        task: ContextTask,
        requested_by: List[str],
        started: float,
        runtime_store: RuntimeContextStore,
    ) -> ContextAcquisitionResult:
        if not self.technical_adapter:
            return self._result_from_task(task, need, "unavailable", reason="technical adapter missing", task_ids=requested_by)
        market = runtime_store.find_compatible(ContextNeed("market_snapshot", need.target, False))
        ohlcv = runtime_store.find_compatible(ContextNeed("ohlcv", need.target, True))
        if not ohlcv:
            return self._result_from_task(
                task,
                need,
                "skipped",
                reason=f"failed_dependency:ohlcv:{need.target}",
                dependency_status="failed",
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )
        indicator_specs = [
            IndicatorSpec(
                indicator_id=str(item.get("indicator_id") or ""),
                timeframe=str(item.get("timeframe") or ""),
                parameters=tuple(sorted((str(key), float(value)) for key, value in dict(item.get("parameters") or {}).items())),
                output_alias=str(item.get("output_alias") or ""),
            )
            for item in need.parameters.get("indicators", [])
            if isinstance(item, dict)
        ]
        try:
            snapshot = self.technical_adapter.build(
                market.data if market else None,
                ohlcv.data if ohlcv else None,
                indicator_specs=indicator_specs,
            )
        except ValueError as exc:
            return self._result_from_task(
                task,
                need,
                "failed",
                reason=str(exc),
                error_code="technical_evidence_invalid",
                task_ids=requested_by,
                latency_ms=self._latency(started),
            )
        if not snapshot:
            return self._result_from_task(task, need, "failed", reason="technical snapshot empty", task_ids=requested_by)
        return self._result_from_task(
            task,
            need,
            "success",
            data=snapshot,
            source=snapshot.get("source", "existing_api"),
            operation="ExistingTechnicalSnapshotAdapter.build",
            provenance={"provider": snapshot.get("source", "existing_api"), "symbol": need.target},
            freshness_status="fresh",
            source_timestamp=str(snapshot.get("as_of_completed_bar") or ""),
            reason="matched",
            task_ids=requested_by,
            latency_ms=self._latency(started),
            dependency_status="satisfied",
        )

    def _dependency_failure(self, task: ContextTask, results_by_key: Dict[str, ContextAcquisitionResult]) -> str:
        for dependency in task.dependencies:
            dependency_key = f"{dependency}:{task.target or 'default'}"
            result = results_by_key.get(dependency_key)
            if not result or not result.ok:
                return dependency_key
        return ""

    def _build_task_views(
        self,
        query_plan: QueryPlan,
        requirements: ContextRequirements,
        results: List[ContextAcquisitionResult],
    ) -> List[TaskContextView]:
        views: List[TaskContextView] = []
        task_requirements = requirements.task_requirements or {}
        if not task_requirements and requirements.task_id:
            task_requirements = {requirements.task_id: requirements}
        if not task_requirements:
            return views
        child_plan_by_task = {getattr(plan, "task_id", ""): plan for plan in (query_plan.child_plans or [])}
        for task_id, task_req in task_requirements.items():
            relevant = [result for result in results if task_id in (result.requested_by_tasks or result.task_ids)]
            required_results = [result for result in relevant if result.required]
            optional_results = [result for result in relevant if not result.required]
            missing_required = [result.result_id() for result in required_results if not result.ok]
            missing_optional = [result.result_id() for result in optional_results if not result.ok]
            status = "COMPLETE"
            confidence = "high"
            if missing_required:
                status = "INSUFFICIENT"
                confidence = "low"
            elif missing_optional:
                status = "DEGRADED"
                confidence = "medium"
            child_plan = child_plan_by_task.get(task_id)
            view = TaskContextView(
                task_id=task_id,
                subquery=getattr(child_plan, "original_query", "") or getattr(query_plan, "original_query", ""),
                query_plan=child_plan.as_dict() if child_plan else query_plan.as_dict(),
                required_context_results=[result.as_dict() for result in required_results],
                optional_context_results=[result.as_dict() for result in optional_results],
                knowledge_context=[result.as_dict() for result in relevant if result.capability in self.KNOWLEDGE_CAPABILITIES],
                market_context=[result.as_dict() for result in relevant if result.capability in {"market_snapshot", "ohlcv"}],
                event_context=[result.as_dict() for result in relevant if result.capability == "economic_event"],
                technical_context=[result.as_dict() for result in relevant if result.capability == "technical_snapshot"],
                missing_required_context=missing_required,
                missing_optional_context=missing_optional,
                sufficiency_status=status,
                confidence_ceiling=confidence,
            )
            print(
                "[TaskContextView] "
                f"task_id={task_id} required_results={len(required_results)} "
                f"optional_results={len(optional_results)} sufficiency={status}"
            )
            views.append(view)
        return views

    @staticmethod
    def knowledge_documents(results: Iterable[ContextAcquisitionResult]) -> List[Dict[str, Any]]:
        docs = []
        for result in results or []:
            if result.capability not in ContextAcquisitionExecutor.KNOWLEDGE_CAPABILITIES or not result.ok:
                continue
            if isinstance(result.data, dict):
                docs.append(result.data)
            elif isinstance(result.data, list):
                docs.extend([item for item in result.data if isinstance(item, dict)])
        return docs

    @staticmethod
    def render_context(batch: ContextAcquisitionBatchResult) -> str:
        parts = []
        knowledge_docs = ContextAcquisitionExecutor.knowledge_documents(batch.results)
        if knowledge_docs:
            text = []
            for doc in knowledge_docs:
                metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
                title = metadata.get("title") or metadata.get("source") or "Knowledge Source"
                text.append(f"[SOURCE]\nTitle: {title}\n[CONTENT]\n{doc.get('content', '')}")
            parts.append("【DỮ LIỆU KHO TRI THỨC】\n" + "\n\n".join(text))

        live_bits = []
        for result in batch.results:
            if not result.ok:
                continue
            if result.capability == "market_snapshot":
                data = result.data
                live_bits.append(
                    f"MarketSnapshot {getattr(data, 'symbol', result.target)} "
                    f"price={getattr(data, 'latest_price', None)} trend={getattr(data, 'recent_trend', '')}"
                )
            elif result.capability == "ohlcv":
                live_bits.append(f"OHLCV {result.target}: candles={len(result.data or [])}")
            elif result.capability == "economic_event":
                data = result.data
                live_bits.append(f"EconomicEvent {getattr(data, 'event_name', result.target)} time={getattr(data, 'release_time', '')}")
            elif result.capability == "technical_snapshot":
                live_bits.append(f"TechnicalSnapshot {result.target}: {result.data}")
            elif result.capability == "position_read":
                from src.services.trading.position_read_model import render_position_read_model

                live_bits.append(render_position_read_model(result.data))
        if live_bits:
            parts.append("【DỮ LIỆU THỜI GIAN THỰC / BỐI CẢNH ĐỘNG】\n" + "\n".join(live_bits))
        return "\n\n".join(parts)

    def _batch_result(
        self,
        request_id: str,
        results: List[ContextAcquisitionResult],
        started: float,
        task_views: List[TaskContextView],
        warnings: List[str],
    ) -> ContextAcquisitionBatchResult:
        status_counts = {status: 0 for status in ["success", "partial", "failed", "unavailable", "skipped", "reused"]}
        for result in results:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1
        deduplicated = sum(max(len(result.requested_by_tasks or result.task_ids) - 1, 0) for result in results)
        return ContextAcquisitionBatchResult(
            request_id=request_id,
            results=results,
            success_count=status_counts.get("success", 0),
            partial_count=status_counts.get("partial", 0),
            failed_count=status_counts.get("failed", 0),
            unavailable_count=status_counts.get("unavailable", 0),
            skipped_count=status_counts.get("skipped", 0),
            reused_count=status_counts.get("reused", 0),
            deduplicated_count=deduplicated,
            total_latency_ms=self._latency(started),
            warnings=list(warnings),
            task_context_views=task_views,
        )

    @staticmethod
    def _need_map(requirements: ContextRequirements, execution_plan: ContextExecutionPlan) -> Dict[str, ContextNeed]:
        mapping = {f"{need.capability}:{need.target or 'default'}": need for need in requirements.needs}
        for task in execution_plan.parallel_tasks + execution_plan.dependent_tasks + execution_plan.deduplicated_tasks:
            mapping.setdefault(
                task.task_id(),
                ContextNeed(task.capability, task.target, task.required, parameters=dict(task.parameters)),
            )
        return mapping

    def _account_for_unfinished_scheduled_tasks(
        self,
        execution_plan: ContextExecutionPlan,
        requirements: ContextRequirements,
        need_map: Dict[str, ContextNeed],
        results_by_key: Dict[str, ContextAcquisitionResult],
    ) -> None:
        accounted = set(results_by_key.keys())
        for task in execution_plan.deduplicated_tasks or []:
            task_id = task.task_id()
            if task_id in accounted:
                continue
            need = need_map.get(task_id) or ContextNeed(
                task.capability,
                task.target,
                task.required,
                parameters=dict(task.parameters),
            )
            requested_by = self._requested_by(requirements, task_id)
            result = self._result_from_task(
                task,
                need,
                "skipped",
                reason="task_not_executed_by_plan_stages",
                error_code="task_not_executed",
                dependency_status="skipped",
                task_ids=requested_by,
            )
            results_by_key[result.result_id()] = result
            accounted.add(result.result_id())
            print(
                "[ContextAcquisitionTaskOutcome] "
                f"task_id={task_id} status=SKIPPED_WITH_REASON "
                "reason=task_not_executed_by_plan_stages"
            )

    @staticmethod
    def _requested_by(requirements: ContextRequirements, need_name: str) -> List[str]:
        requested = []
        for task_id, names in (requirements.task_need_mapping or {}).items():
            if need_name in names:
                requested.append(task_id)
        if not requested and requirements.task_id:
            requested.append(requirements.task_id)
        return requested

    @staticmethod
    def _result_from_task(
        task: ContextTask,
        need: Optional[ContextNeed],
        status: str,
        data: Any = None,
        source: str = "",
        operation: str = "",
        provenance: Optional[Dict[str, Any]] = None,
        freshness_status: str = "unknown",
        source_timestamp: str = "",
        reason: str = "",
        error_code: str = "",
        error_message: str = "",
        retryable: bool = False,
        task_ids: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        dependency_status: str = "",
    ) -> ContextAcquisitionResult:
        need = need or ContextNeed(task.capability, task.target, task.required, parameters=task.parameters)
        result = ContextAcquisitionResult(
            capability=need.capability,
            target=need.target,
            status=status,
            required=need.required,
            task_id=task.task_id(),
            normalized_parameters=dict(need.parameters),
            requested_by_tasks=list(task_ids or []),
            task_ids=list(task_ids or []),
            data=data,
            source=source,
            operation=operation or task.operation_name,
            provenance=dict(provenance or {}),
            fetched_at=_utc_now(),
            source_timestamp=source_timestamp,
            freshness_status=freshness_status,
            latency_ms=latency_ms,
            retryable=retryable,
            error_code=error_code,
            error_message=error_message,
            dependency_status=dependency_status,
            reason=reason,
        )
        source_text = result.source or result.provenance.get("source") or result.provenance.get("title") or ""
        print(
            "[ContextAcquisition] "
            f"task={result.result_id()} status={result.status} "
            f"source={source_text} latency_ms={latency_ms:.2f} reason={reason}"
        )
        return result

    @staticmethod
    def _split_task_name(name: str) -> Tuple[str, str]:
        if ":" not in name:
            return name, "default"
        return tuple(name.split(":", 1))  # type: ignore[return-value]

    @staticmethod
    def _doc_identity(doc: Dict[str, Any]) -> str:
        metadata = doc.get("metadata", {}) if isinstance(doc, dict) and isinstance(doc.get("metadata"), dict) else {}
        title = metadata.get("title") or doc.get("source") or ""
        page = metadata.get("page") or metadata.get("location") or ""
        chunk_id = metadata.get("chunk_id") or doc.get("chunk_id") or ""
        parent_id = metadata.get("parent_chunk_id") or doc.get("parent_id") or ""
        return f"{chunk_id or parent_id or 'unknown'}|{title}|p={page}"

    @staticmethod
    def _latency(started: float) -> float:
        return round((time.time() - started) * 1000, 2)

    @staticmethod
    def _knowledge_query(need: ContextNeed, query_plan: QueryPlan) -> str:
        target = need.target or query_plan.original_query
        author = str((need.parameters or {}).get("author") or "").strip()
        book = str((need.parameters or {}).get("book") or "").strip()
        
        if need.capability == "official_report":
            base_query = f"{target} official report"
        elif need.capability == "market_knowledge":
            if AnswerModeClassifier.normalize(target) in {"gold", "xauusd"}:
                base_query = "World Gold Council gold market commentary"
            else:
                base_query = f"{target} market report"
        elif author and book:
            base_query = f"{author} {book} {target}".replace("_", " ")
        elif author:
            base_query = f"{author} {target}".replace("_", " ")
        else:
            base_query = target.replace("_", " ")
            
        refined_topics = getattr(query_plan, "refined_topics", [])
        if refined_topics:
            base_query += " " + " ".join(refined_topics).replace("_", " ")
            
        return base_query

    @staticmethod
    def _knowledge_constraint_filters(need: ContextNeed) -> Dict[str, Any]:
        params = dict(need.parameters or {})
        filters: Dict[str, Any] = {}
        if need.capability == "static_knowledge":
            if params.get("author"):
                filters["author"] = params["author"]
            filters["knowledge_type"] = "book"
        if need.capability == "official_report" and params.get("organization"):
            filters["organization"] = params["organization"]
        return filters

    def _intent_for_need(self, need: ContextNeed, query_text: str, query_plan: QueryPlan) -> QueryIntent:
        target = str(need.target or "").upper()
        if need.capability == "official_report" and target in {"CPI", "NFP", "GDP", "FOMC", "FOMC_MINUTES", "SEP"}:
            return self.intent_router.route(query_text)
        if need.capability == "market_knowledge" and AnswerModeClassifier.normalize(need.target) in {"gold", "xauusd"}:
            return self.intent_router.route("World Gold Council gold market commentary")
        if need.capability == "static_knowledge":
            return self.intent_router.route(query_text)
        return QueryPlanAssembler.intent_from_plan(query_plan)

    @staticmethod
    def _matching_docs(need: ContextNeed, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        matching = []
        for doc in docs or []:
            result = ContextAcquisitionResult(
                capability=need.capability,
                target=need.target,
                status="success",
                data=doc,
                provenance=_knowledge_provenance(doc),
            )
            if _knowledge_result_matches(need, result):
                matching.append(doc)
            else:
                print(
                    "[KnowledgeCompatibility] "
                    f"capability={need.capability} "
                    f"target={need.target} "
                    "status=rejected "
                    f"reason={_knowledge_mismatch_reason(need, result)}"
                )
        return matching


def _ohlcv_freshness(candles: List[Dict[str, Any]], timeframe: str) -> tuple[str, str]:
    if not candles:
        return "unknown", ""
    latest = str(candles[-1].get("timestamp") or "")
    try:
        opened_at = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        normalized = normalize_timeframe(timeframe)
        closed_at = opened_at.astimezone(timezone.utc) + timedelta(seconds=timeframe_duration_seconds(normalized))
        age = max((datetime.now(timezone.utc) - closed_at).total_seconds(), 0)
        return ("fresh" if age <= stale_seconds_for_timeframe(normalized) else "stale"), latest
    except (TypeError, ValueError):
        return "unknown", latest


def _knowledge_provenance(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
    return {
        "source_id": metadata.get("doc_id") or metadata.get("source_id") or "",
        "source": metadata.get("source") or doc.get("source") or doc.get("file_name") or "",
        "title": metadata.get("title") or metadata.get("source") or doc.get("source") or "",
        "organization": metadata.get("organization") or "",
        "author": metadata.get("author") or "",
        "event_type": metadata.get("event_type") or "",
        "period": metadata.get("period") or metadata.get("published_date") or "",
        "provider": metadata.get("retrieval_mode") or "KnowledgeV3",
        "domain": metadata.get("domain") or "",
        "subdomain": metadata.get("subdomain") or "",
    }


def _matching_event(target: str, events: List[Any]) -> Optional[Any]:
    normalized_target = AnswerModeClassifier.normalize(target)
    if normalized_target in {"", "macro", "default"}:
        return events[0] if events else None
    aliases = {
        "cpi": ("cpi", "consumer price", "inflation"),
        "nfp": ("nfp", "nonfarm", "payroll", "employment"),
        "gdp": ("gdp", "gross domestic product"),
        "fomc": ("fomc", "fed", "federal reserve", "interest rate"),
        "fomc_minutes": ("fomc", "minutes", "federal reserve"),
        "sep": ("summary of economic projections", "sep"),
    }.get(normalized_target, (normalized_target,))
    for event in events or []:
        event_name = AnswerModeClassifier.normalize(getattr(event, "event_name", ""))
        if any(alias in event_name for alias in aliases):
            return event
    return None


def _event_target_from_name(name: str) -> str:
    text = AnswerModeClassifier.normalize(name)
    if any(term in text for term in ("cpi", "consumer price", "inflation")):
        return "CPI"
    if any(term in text for term in ("nfp", "nonfarm", "payroll", "employment")):
        return "NFP"
    if "gdp" in text:
        return "GDP"
    if "fomc" in text or "federal reserve" in text:
        return "FOMC"
    return "macro"


def _target_matches(result_target: str, need_target: str, capability: str = "") -> bool:
    result = AnswerModeClassifier.normalize(result_target or "")
    need = AnswerModeClassifier.normalize(need_target or "")
    if not need or need == "default":
        return True
    if result == need:
        return True
    if capability in {"market_snapshot", "ohlcv", "technical_snapshot", "market_knowledge"}:
        return need in {"gold", "xauusd"} and result in {"gold", "xauusd"}
    return False


def _provenance_matches_official_target(provenance: Dict[str, Any], target: str) -> bool:
    normalized_target = AnswerModeClassifier.normalize(target)
    event_type = AnswerModeClassifier.normalize(provenance.get("event_type", ""))
    haystack = AnswerModeClassifier.normalize(
        " ".join(str(provenance.get(key, "") or "") for key in ("title", "organization", "source"))
    )
    if event_type == normalized_target:
        return True
    official_terms = {
        "cpi": ("cpi", "consumer price index", "us cpi report", "bls"),
        "nfp": ("nonfarm", "payroll", "employment situation", "bls"),
        "gdp": ("gdp", "gross domestic product", "bea"),
        "fomc": ("fomc statement", "federal reserve"),
        "fomc_minutes": ("fomc minutes", "federal reserve"),
        "sep": ("summary of economic projections", "federal reserve"),
        "gold_market": ("gold market commentary", "world gold council"),
    }.get(normalized_target, (normalized_target,))
    return any(term in haystack for term in official_terms)


def _knowledge_result_matches(need: ContextNeed, result: ContextAcquisitionResult) -> bool:
    return _knowledge_mismatch_reason(need, result) == ""


def _knowledge_mismatch_reason(need: ContextNeed, result: ContextAcquisitionResult) -> str:
    if result.status not in {"success", "reused"}:
        return "status_not_success"
    provenance = result.provenance or {}
    doc = result.data if isinstance(result.data, dict) else {}
    metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
    params = dict(need.parameters or {})
    source_haystack = AnswerModeClassifier.normalize(
        " ".join(
            str(value or "")
            for value in [
                provenance.get("source_id"),
                provenance.get("source"),
                provenance.get("title"),
                provenance.get("author"),
                provenance.get("organization"),
                metadata.get("doc_id"),
                metadata.get("source"),
                metadata.get("title"),
                metadata.get("author"),
                metadata.get("organization"),
                metadata.get("document_metadata", {}).get("title") if isinstance(metadata.get("document_metadata"), dict) else "",
                metadata.get("document_metadata", {}).get("author") if isinstance(metadata.get("document_metadata"), dict) else "",
            ]
        )
    )
    haystack = AnswerModeClassifier.normalize(
        " ".join(
            str(value or "")
            for value in [
                provenance.get("title"),
                provenance.get("organization"),
                provenance.get("author"),
                provenance.get("event_type"),
                provenance.get("domain"),
                provenance.get("subdomain"),
                metadata.get("title"),
                metadata.get("organization"),
                metadata.get("author"),
                metadata.get("event_type"),
                metadata.get("domain"),
                metadata.get("subdomain"),
                doc.get("content", ""),
            ]
        )
    )
    target = AnswerModeClassifier.normalize(need.target)
    if need.capability == "official_report":
        return "" if _provenance_matches_official_target(provenance, need.target) else "official_report_provenance_mismatch"
    if need.capability == "market_knowledge":
        if target in {"gold", "xauusd"}:
            return "" if ("gold" in haystack or "world gold council" in haystack) else "market_knowledge_provenance_mismatch"
        return "" if target in haystack else "target_mismatch"
    if need.capability == "static_knowledge":
        author_constraint = str(params.get("author") or "").strip()
        book_constraint = str(params.get("book") or params.get("canonical_book") or "").strip()
        if author_constraint or book_constraint:
            author_ok = bool(author_constraint and _contains_normalized(source_haystack, author_constraint))
            book_ok = bool(book_constraint and _contains_normalized(source_haystack, book_constraint))
            if author_constraint and book_constraint:
                if not (author_ok or book_ok):
                    return "author_book_mismatch"
            elif author_constraint and not author_ok:
                return "author_mismatch"
            elif book_constraint and not book_ok:
                return "book_mismatch"
        aliases = {
            "price_action": ("price action", "al brooks", "bar by bar"),
            "volume_price_analysis": ("volume price analysis", "vpa", "anna coulling"),
            "position_sizing": ("position sizing", "van tharp", "risk"),
            "trading_discipline": ("trading discipline", "mark douglas", "psychology"),
            "trend_following": ("trend following", "michael covel"),
            "trading_framework": ("trading", "risk", "framework", "strategy"),
        }.get(target, (target,))
        if not target or target in {"general", "static_knowledge"} or any(alias in haystack for alias in aliases):
            return ""
        return "target_mismatch"
    return "unsupported_capability"


def _contains_normalized(haystack: str, needle: Any) -> bool:
    normalized_needle = AnswerModeClassifier.normalize(needle).strip()
    normalized_haystack = f" {str(haystack or '').strip()} "
    return bool(normalized_needle and normalized_needle in normalized_haystack)

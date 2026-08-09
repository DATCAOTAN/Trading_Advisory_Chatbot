"""
RAG Orchestrator v2 — Tái cấu trúc triệt để với LLM Gatekeeper.

Pipeline điều phối:
  User Query
    ↓
  [LLM Gatekeeper] ← Qwen 2.5 phân loại ý định (temperature=0.0)
    ├─ GREETING      → quick_reply() tĩnh     ⚡ EARLY EXIT
    ├─ TRASH         → cảnh báo lạc đề        ⚡ EARLY EXIT
    └─ FINANCIAL_RAG → full_rag_pipeline()     🔥 DÂY CHUYỀN HẠNG NẶNG
                          ↓
                       [Query Rewriting] (Qwen)
                          ↓
                       [Hybrid Search + Reranker] (Qdrant + BGE)
                          ↓
                       [Multi-Hop Generation] (Qwen Streaming)
                          ↓ (optional)
                       [Self-Correction] (Qwen)
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Iterator, List, Dict, Tuple, Optional, Any
import time

from src.services.vector_service import VectorService
from src.services.retrieval_adapter import RetrievalAdapter
from src.services.decision_context import (
    DecisionContextBuilder,
    ExistingEconomicCalendarAdapter,
    ExistingMacroDataAdapter,
    ExistingMarketDataAdapter,
)
from src.services.knowledge.query_decomposer import QueryDecomposer
from src.services.llm_service import LLMService
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.response_gate import ResponseGate
from src.services.agents import (
    AgentDispatcher,
    AgentExecutionPlanBuilder,
    AgentResultAggregator,
    AgentRuntimeContext,
    AgentRuntimeRegistry,
    MarketContextAgentRuntime,
    StrategyAgentRuntime,
    RiskAgentRuntime,
    StrategyRiskConsistencyAgentRuntime,
    AgentAnswerComplianceGate,
    AgentAnswerComplianceInputBuilder,
    compact_agent_payload,
)
from src.services.agents.runtime import build_agent_handoff
from src.services.evidence import (
    AnswerContractBuilder,
    ClaimEvidenceValidator,
    EvidencePromptAssembler,
    EvidenceRefinementPlanner,
    EvidenceSelector,
    AnswerContractEvaluator,
)
from src.services.live_data_service import get_live_service
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import (
    ResolvedSemanticState,
    bind_authoritative_position_reference,
)
from src.services.semantic.structured_interpreter import StructuredSemanticInterpreter
from src.services.semantic.conversational_context import (
    ConversationalIntentContext,
    strategy_response_message,
)
from src.services.semantic.context_acquisition import ContextAcquisitionExecutor
from src.services.trading.decision.conversational_authorization import (
    project_conversational_trading_request,
)
from src.config import Config

# Nhập các Mô-đun Modular RAG
from src.pipelines.modules.query_rewriter import QueryRewriterModule
from src.pipelines.modules.router import RouterModule, RouteAction
from src.pipelines.modules.reranker import RerankerModule
from src.pipelines.modules.evaluator import EvaluatorModule


def _bind_selected_position_context(query_plan, model) -> bool:
    """Persist only an exact authoritative read-model selection for continuation."""

    if (
        model is None
        or model.status != "AVAILABLE"
        or model.blockers
        or model.selected_position is None
    ):
        return False
    state = ResolvedSemanticState.from_dict(query_plan.semantic_context)
    query_plan.semantic_context = bind_authoritative_position_reference(
        state,
        model.selected_position.protected_reference,
    ).as_dict()
    return True


class RAGOrchestrator:
    """

    Facade Pattern: Một đầu mối duy nhất cho toàn bộ hệ thống RAG nâng cấp.

    Cơ chế Early Exit:
    - GREETING / TRASH → trả lời tĩnh ngay lập tức, KHÔNG nạp model nặng
    - CHỈ FINANCIAL_RAG mới kích hoạt: Query Rewrite → Qdrant → Reranker → Qwen Stream
    """

    RETRIEVAL_CAPABILITIES = frozenset({"official_report", "static_knowledge", "market_knowledge"})

    def __init__(self):
        print("🚀 [Orchestrator] Khởi động các dịch vụ cốt lõi...")
        self.vector_service = VectorService()
        self.retrieval_adapter = RetrievalAdapter(self.vector_service)
        self.query_decomposer = QueryDecomposer(self.retrieval_adapter.query_intent_router)
        self.llm_service    = LLMService()
        self.live_service   = get_live_service()
        self.market_adapter = ExistingMarketDataAdapter(self.live_service)
        self.calendar_adapter = ExistingEconomicCalendarAdapter(self.live_service)
        self.macro_adapter = ExistingMacroDataAdapter(self.live_service)
        self.decision_context_builder = DecisionContextBuilder(
            market_adapter=self.market_adapter,
            calendar_adapter=self.calendar_adapter,
            macro_adapter=self.macro_adapter,
            intent_router=self.retrieval_adapter.query_intent_router,
        )
        self.context_acquisition_executor = ContextAcquisitionExecutor(
            retrieval_adapter=self.retrieval_adapter,
            reranker_module=None,
            market_adapter=self.market_adapter,
            calendar_adapter=self.calendar_adapter,
            technical_adapter=self.decision_context_builder.technical_adapter,
            live_service=self.live_service,
        )
        self.orchestrator_contract_builder = OrchestratorContractBuilder()
        self.agent_runtime_registry = AgentRuntimeRegistry()
        self.agent_runtime_registry.register("MarketContextAgent", MarketContextAgentRuntime())
        self.agent_runtime_registry.register("StrategyAgent", StrategyAgentRuntime())
        self.agent_runtime_registry.register("RiskAgent", RiskAgentRuntime())
        self.agent_runtime_registry.register("StrategyRiskConsistencyAgent", StrategyRiskConsistencyAgentRuntime())
        self.agent_dispatcher = AgentDispatcher(self.agent_runtime_registry)
        self.evidence_selector = EvidenceSelector()
        self.answer_contract_builder = AnswerContractBuilder()
        self.evidence_prompt_assembler = EvidencePromptAssembler()
        self.claim_evidence_validator = ClaimEvidenceValidator()
        # ── Modular Components ──
        self.rewriter_module = QueryRewriterModule()
        self.router_module = RouterModule()
        self.structured_semantic_interpreter = StructuredSemanticInterpreter()
        self.reranker_module = RerankerModule()
        self.evaluator_module = EvaluatorModule()

        # ── In-Memory Caching Layer (TTL: 15 minutes) ──
        self._context_cache = {}
        self._CACHE_TTL = 15 * 60  # 15 phút

        print("✅ [Orchestrator] Hệ thống Modular RAG đã sẵn sàng!")

    # =========================================================================
    # PUBLIC API — Được gọi từ app.py
    # =========================================================================

    def sync_knowledge_base(self, force: bool = False) -> dict:
        return self.vector_service.sync_documents(force=force)

    def _interpret_structured_semantics(self, user_query: str):
        interpreter = getattr(self, "structured_semantic_interpreter", None)
        if interpreter is None:
            interpreter = StructuredSemanticInterpreter()
            self.structured_semantic_interpreter = interpreter
        return interpreter.interpret(user_query)

    @classmethod
    def _requires_retrieval_rewrite(cls, context_requirements) -> bool:
        return any(
            need.capability in cls.RETRIEVAL_CAPABILITIES
            for need in getattr(context_requirements, "needs", [])
        )

    def query_financial_advisor(
        self,
        user_query: str,
        chat_history: List[Dict] = None,
        session_id: str = "",
        enable_self_correction: bool = False,
        enable_reranker: Optional[bool] = None,
        use_knowledge_v3: Optional[bool] = None,
        knowledge_v3_fallback_to_legacy: Optional[bool] = None,
        conversational_context: Optional[ConversationalIntentContext] = None,
        previous_structured_context: Optional[ResolvedSemanticState] = None,
    ) -> Tuple[Iterator[str], List[Dict], str, Optional[Dict]]:
        if chat_history is None:
            chat_history = []

        if (
            conversational_context
            and conversational_context.is_strategy_request
            and not ({"current_market", "concept"} & set(conversational_context.intent_families))
        ):
            query_plan = self.decision_context_builder.query_plan_assembler.assemble(
                original_query=user_query,
                conversational_context=conversational_context,
            )
            requirements = self.decision_context_builder.requirement_planner.plan(query_plan)
            execution_plan = self.decision_context_builder.execution_planner.plan(requirements)
            decision_context = self.decision_context_builder.build(
                original_query=user_query,
                query_plan=query_plan,
                context_requirements=requirements,
                context_execution_plan=execution_plan,
            )
            message = strategy_response_message(conversational_context)
            return self._static_stream(message), [], "FINANCIAL_RAG", {
                "is_bounded_response": True,
                "query_plan": query_plan.as_dict(),
                "decision_context": decision_context.as_dict(),
                "response_format": conversational_context.response_format,
                "provider_calls": 0,
            }

        semantic_interpretation = self._interpret_structured_semantics(user_query)
        semantic_provider_calls = semantic_interpretation.provider_calls
        structured_semantics_active = semantic_interpretation.is_valid
        retrieval_rewrite_calls = 0
        canonical_query_plan = None
        context_requirements = None
        context_execution_plan = None

        if structured_semantics_active:
            route_action, static_response = self.router_module.process_structured(
                semantic_interpretation.semantic.primary_intent,
                user_query,
            )
            if route_action != RouteAction.EARLY_EXIT:
                canonical_query_plan = self.decision_context_builder.query_plan_assembler.assemble(
                    original_query=user_query,
                    structured_semantics=semantic_interpretation.semantic,
                    previous_structured_context=previous_structured_context,
                )
                context_requirements = self.decision_context_builder.requirement_planner.plan(canonical_query_plan)
                context_execution_plan = self.decision_context_builder.execution_planner.plan(context_requirements)
                if canonical_query_plan.primary_intent in {"position_state_read", "position_management"}:
                    executor = self._context_acquisition_executor(
                        use_knowledge_v3=Config.USE_KNOWLEDGE_V3 if use_knowledge_v3 is None else use_knowledge_v3,
                        fallback_to_legacy=(
                            Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY
                            if knowledge_v3_fallback_to_legacy is None
                            else knowledge_v3_fallback_to_legacy
                        ),
                        enable_reranker=enable_reranker,
                    )
                    acquisition_batch = executor.execute(
                        query_plan=canonical_query_plan,
                        requirements=context_requirements,
                        execution_plan=context_execution_plan,
                        registry=self.decision_context_builder.capability_registry,
                        request_id=f"position_read_{int(time.time() * 1000)}",
                    )
                    result = next(
                        (
                            item for item in acquisition_batch.results
                            if item.capability == "position_read"
                        ),
                        None,
                    )
                    from src.services.trading.position_read_model import (
                        PositionReadModel,
                        render_position_read_model,
                    )

                    model = result.data if result and isinstance(result.data, PositionReadModel) else None
                    _bind_selected_position_context(canonical_query_plan, model)
                    if canonical_query_plan.primary_intent == "position_management":
                        from src.services.trading.human_confirmed_management import (
                            HumanConfirmedManagementService,
                        )

                        outcome = HumanConfirmedManagementService(
                            position_read_service=executor.position_read_service,
                        ).create_from_query_plan(canonical_query_plan, model=model)
                        message = (
                            "Management proposal ready for explicit human review."
                            if outcome.proposal is not None
                            else "Management request blocked: " + ", ".join(outcome.blockers)
                        )
                        return self._static_stream(message), [], "FINANCIAL_RAG", {
                            "is_bounded_response": True,
                            "query_plan": canonical_query_plan.as_dict(),
                            "position_read_model": model.to_public_dict() if model else None,
                            "management_proposal": outcome.to_public_dict(),
                            "management_proposal_protected": outcome.proposal,
                            "semantic_provider_calls": semantic_provider_calls,
                            "provider_calls": semantic_provider_calls,
                            "retrieval_rewrite_calls": 0,
                        }
                    message = (
                        render_position_read_model(model)
                        if model is not None
                        else "Position state unavailable: POSITION_READ_UNAVAILABLE"
                    )
                    return self._static_stream(message), [], "FINANCIAL_RAG", {
                        "is_bounded_response": True,
                        "query_plan": canonical_query_plan.as_dict(),
                        "position_read_model": model.to_public_dict() if model else None,
                        "semantic_provider_calls": semantic_provider_calls,
                        "provider_calls": semantic_provider_calls,
                        "retrieval_rewrite_calls": 0,
                    }
                trading_request = project_conversational_trading_request(
                    canonical_query_plan,
                    conversation_id=session_id,
                )
                if trading_request is not None:
                    executor = self._context_acquisition_executor(
                        use_knowledge_v3=Config.USE_KNOWLEDGE_V3 if use_knowledge_v3 is None else use_knowledge_v3,
                        fallback_to_legacy=(
                            Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY
                            if knowledge_v3_fallback_to_legacy is None
                            else knowledge_v3_fallback_to_legacy
                        ),
                        enable_reranker=enable_reranker,
                    )
                    acquisition_batch = executor.execute(
                        query_plan=canonical_query_plan,
                        requirements=context_requirements,
                        execution_plan=context_execution_plan,
                        registry=self.decision_context_builder.capability_registry,
                        request_id=f"semantic_{int(time.time() * 1000)}",
                    )
                    decision_context = self.decision_context_builder.build(
                        original_query=user_query,
                        query_plan=canonical_query_plan,
                        context_requirements=context_requirements,
                        context_execution_plan=context_execution_plan,
                        acquisition_batch_result=acquisition_batch,
                        task_context_views=acquisition_batch.task_context_views,
                    )
                    message = (
                        "Structured trading semantics normalized.\n\n"
                        f"- Symbol: {trading_request.canonical_symbol or 'missing'}"
                        f" / {trading_request.broker_symbol or 'missing'}\n"
                        f"- Mode: {trading_request.requested_mode}\n"
                        "- Execution: NON_EXECUTABLE"
                        + (
                            f"\n- Required next information: {', '.join(trading_request.blockers)}"
                            if trading_request.blockers
                            else ""
                        )
                    )
                    return self._static_stream(message), [], "FINANCIAL_RAG", {
                        "is_bounded_response": True,
                        "query_plan": canonical_query_plan.as_dict(),
                        "decision_context": decision_context.as_dict(),
                        "trading_request": trading_request.to_public_dict(),
                        "semantic_provider_calls": semantic_provider_calls,
                        "provider_calls": semantic_provider_calls,
                        "retrieval_rewrite_calls": retrieval_rewrite_calls,
                    }
                if self._requires_retrieval_rewrite(context_requirements):
                    current_query = self.rewriter_module.process(user_query, chat_history)
                    retrieval_rewrite_calls = 1
                else:
                    current_query = user_query
        else:
            route_action, static_response = self.router_module.process(user_query, chat_history)

        if route_action == RouteAction.EARLY_EXIT:
            print("⚡ [Agent] EARLY_EXIT kích hoạt. Trả lời ngay lập tức.")
            if isinstance(static_response, str):
                stream = self._static_stream(static_response)
            else:
                stream = static_response
            return stream, [], "EARLY_EXIT", {
                "semantic_provider_calls": semantic_provider_calls,
                "retrieval_rewrite_calls": retrieval_rewrite_calls,
            }

        # =====================================================================
        # TẦNG 2: AGENTIC RAG CONTROLLER (ReAct Loop)
        # =====================================================================
        print("🤖 [Agent] Khởi động Agentic RAG Controller...")

        max_loops = 3 if enable_self_correction else 1
        current_loop = 0
        final_stream = None
        final_sources = []
        feedback_note = ""

        if canonical_query_plan is None:
            current_query = self.rewriter_module.process(user_query, chat_history)
            retrieval_rewrite_calls = 1

        # Lấy thời gian hiện tại một lần cho toàn bộ phiên
        vn_tz = timezone(timedelta(hours=7))
        weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        now = datetime.now(vn_tz)
        weekday_str = weekdays[now.weekday()]
        now_str = f"{weekday_str}, ngày {now.strftime('%d/%m/%Y %H:%M:%S')} (Giờ VN)"

        while current_loop < max_loops:
            current_loop += 1
            if not structured_semantics_active:
                query_plan_kwargs = {
                    "original_query": user_query,
                    "rewritten_query": current_query,
                }
                if conversational_context is not None:
                    query_plan_kwargs["conversational_context"] = conversational_context
                canonical_query_plan = self.decision_context_builder.query_plan_assembler.assemble(
                    **query_plan_kwargs
                )
                context_requirements = self.decision_context_builder.requirement_planner.plan(canonical_query_plan)
                context_execution_plan = self.decision_context_builder.execution_planner.plan(context_requirements)
            canonical_query_intent = QueryPlanAssembler.intent_from_plan(canonical_query_plan)
            print(f"\n🔄 [Agent Loop {current_loop}/{max_loops}] Truy vấn hiện tại: {current_query}")

            if Config.SEMANTIC_CONTEXT_EXECUTOR_ENABLED and Config.SEMANTIC_CONTEXT_EXECUTOR_AUTHORITATIVE:
                print("[Agent Action] Semantic Context Executor authoritative; legacy tool calls skipped for context acquisition.")
                combined_context = f"【THỜI GIAN HỆ THỐNG HIỆN TẠI】\nHôm nay là: {now_str}\n\n"
                executor = self._context_acquisition_executor(
                    use_knowledge_v3=Config.USE_KNOWLEDGE_V3 if use_knowledge_v3 is None else use_knowledge_v3,
                    fallback_to_legacy=(
                        Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY
                        if knowledge_v3_fallback_to_legacy is None
                        else knowledge_v3_fallback_to_legacy
                    ),
                    enable_reranker=enable_reranker,
                )
                acquisition_batch = executor.execute(
                    query_plan=canonical_query_plan,
                    requirements=context_requirements,
                    execution_plan=context_execution_plan,
                    registry=self.decision_context_builder.capability_registry,
                    request_id=f"rag_{current_loop}_{int(time.time() * 1000)}",
                )
                acquisition_context = executor.render_context(acquisition_batch)
                if acquisition_context:
                    combined_context += acquisition_context + "\n\n"
                current_sources = executor.knowledge_documents(acquisition_batch.results)

                decision_context = self.decision_context_builder.build(
                    original_query=user_query,
                    rewritten_query=current_query,
                    retrieval_results=current_sources,
                    query_intent=canonical_query_intent,
                    query_plan=canonical_query_plan,
                    context_requirements=context_requirements,
                    context_execution_plan=context_execution_plan,
                    acquisition_batch_result=acquisition_batch,
                    task_context_views=acquisition_batch.task_context_views,
                )
                orchestrator_output = self.orchestrator_contract_builder.build(
                    OrchestratorInput(
                        decision_context=decision_context,
                        user_intent=decision_context.query_intent,
                        permissions={"execution": False},
                        available_agents=[
                            "StaticKnowledgeAgent",
                            "MarketDataAgent",
                            "CalendarAgent",
                            "TechnicalAnalysisAgent",
                            "MarketContextAgent",
                            "StrategyAgent",
                            "RiskAgent",
                            "StrategyRiskConsistencyAgent",
                            "ExecutionGateAgent",
                        ],
                    )
                )
                evidence_bundles, answer_contracts, structured_prompt = self._build_evidence_artifacts(
                    query_plan=canonical_query_plan,
                    decision_context=decision_context,
                    acquisition_batch=acquisition_batch,
                    answer_type=orchestrator_output.answer_type,
                    user_query=user_query,
                    executor=executor,
                    requirements=context_requirements,
                    execution_plan=context_execution_plan,
                )
                response_gate = ResponseGate.evaluate(decision_context, orchestrator_output)
                
                runtime_artifacts = {
                    "evidence_bundles": decision_context.evidence_bundles,
                    "answer_contracts": decision_context.answer_contracts,
                    "evidence_sufficiency": decision_context.evidence_sufficiency,
                    "claim_validation": {},
                    "response_gate": response_gate.as_dict() if hasattr(response_gate, "as_dict") else vars(response_gate),
                    "is_bounded_response": False,
                    "agent_runtime": self._build_agent_runtime_artifacts(orchestrator_output, decision_context),
                    "semantic_provider_calls": semantic_provider_calls,
                    "retrieval_rewrite_calls": retrieval_rewrite_calls,
                    "query_plan": canonical_query_plan.as_dict(),
                    "context_capabilities_requested": [need.capability for need in context_requirements.needs],
                }
                structured_prompt = self._append_agent_handoff_to_prompt(
                    structured_prompt,
                    runtime_artifacts.get("agent_runtime") or {},
                )
                
                self._annotate_sources_with_evidence_status(current_sources, decision_context)
                
                if not response_gate.normal_synthesis_allowed:
                    runtime_artifacts["is_bounded_response"] = True
                    self._record_final_answer_artifact(
                        runtime_artifacts,
                        response_gate.message,
                        source="bounded",
                        repair_status="NOT_ATTEMPTED",
                    )
                    return self._static_stream(response_gate.message), current_sources, "FINANCIAL_RAG", runtime_artifacts

                if not combined_context.strip():
                    combined_context = "Không tìm thấy dữ liệu liên quan. Bạn phải trả lời dựa trên suy luận logic."
                short_term_history = chat_history[-10:] if chat_history else []
                if not enable_self_correction:
                    print("🚀 [Agent] Bỏ qua Reflection, trả thẳng kết quả stream ra UI.")
                    draft_answer = ""
                    for token in self._evidence_contract_stream(user_query, structured_prompt, short_term_history):
                        draft_answer += str(token or "")
                    final_answer, _, _, _ = self._validate_and_maybe_repair_answer(
                        draft_answer=draft_answer,
                        user_query=user_query,
                        structured_prompt=structured_prompt,
                        short_term_history=short_term_history,
                        evidence_bundles=evidence_bundles,
                        answer_contracts=answer_contracts,
                        runtime_artifacts=runtime_artifacts,
                    )
                    return self._static_stream(final_answer), current_sources, "FINANCIAL_RAG", runtime_artifacts

                print("🧠 [Agent Reasoning] Sinh câu trả lời ngầm để Evaluator kiểm duyệt (Chưa hiện ra UI)...")
                draft_answer = ""
                for token in self._evidence_contract_stream(user_query, structured_prompt, short_term_history):
                    draft_answer += token
                draft_answer, claim_validation, coverage_val, repair_status = self._validate_and_maybe_repair_answer(
                    draft_answer=draft_answer,
                    user_query=user_query,
                    structured_prompt=structured_prompt,
                    short_term_history=short_term_history,
                    evidence_bundles=evidence_bundles,
                    answer_contracts=answer_contracts,
                    runtime_artifacts=runtime_artifacts,
                )

                runtime_artifacts["claim_validation"] = claim_validation.as_dict()
                decision_context.claim_validation = claim_validation.as_dict()
                
                contract_evaluations = []
                for contract in answer_contracts:
                    contract_task_id = getattr(contract, "task_id", "") or "task"
                    task_topics = []
                    plan = getattr(contract, "synthesis_coverage_plan", None)
                    if plan:
                        task_topics = list(getattr(plan, "required_topics", []) or [])
                    task_coverage = None
                    if task_topics:
                        from src.services.evidence.answer_coverage import AnswerCoverageValidator
                        task_coverage = AnswerCoverageValidator.evaluate(draft_answer, task_topics)
                    c_eval = AnswerContractEvaluator.evaluate(
                        contract,
                        task_coverage or coverage_val,
                        claim_validation,
                        repair_status,
                        task_id=contract_task_id,
                    )
                    contract_evaluations.append(c_eval.as_dict())
                if contract_evaluations:
                    runtime_artifacts["contract_evaluation"] = contract_evaluations[0] # use primary contract
                    runtime_artifacts["contract_evaluations"] = contract_evaluations
                    aggregate_status = self._aggregate_contract_status(contract_evaluations)
                    task_status_text = ", ".join(
                        f"{item.get('task_id')}: {item.get('status')}"
                        for item in contract_evaluations
                    )
                    print(
                        "[MultiIntentContractAggregation] "
                        f"task_statuses={{{task_status_text}}} "
                        f"aggregate_status={aggregate_status}"
                    )

                is_passed, new_feedback = self.evaluator_module.process(draft_answer, structured_prompt)
                if claim_validation.status == "FAIL":
                    is_passed = False
                    new_feedback = ",".join(claim_validation.violations) or "claim_evidence_validation_failed"
                if is_passed:
                    final_stream = self._static_stream(draft_answer)
                    return final_stream, current_sources, "FINANCIAL_RAG", runtime_artifacts
                feedback_note = new_feedback
                if current_loop < max_loops:
                    current_query = self._agent_reflector(user_query, feedback_note, current_query)
                    continue
                warning = (
                    "⚠️ **CẢNH BÁO TỰ ĐỘNG:** Hệ thống không thể xác thực 100% "
                    "số liệu dưới đây do thiếu hụt tài liệu gốc. Vui lòng tham khảo có chọn lọc.\n\n"
                )
                final_stream = self._static_stream(warning + draft_answer)
                return final_stream, current_sources, "FINANCIAL_RAG", runtime_artifacts

            # ── BƯỚC 1: THOUGHT & ACTION (Tool Selection) ──
            tools_to_run = self._agent_tool_selector(current_query, now_str)
            tools_to_run = self._align_tools_to_query_plan(tools_to_run, canonical_query_plan)
            print(f"🛠️ [Agent Action] LLM tự quyết định gọi công cụ: {tools_to_run}")

            # ── BƯỚC 2: OBSERVATION (Tổng hợp Context từ Tools) ──
            combined_context = f"【THỜI GIAN HỆ THỐNG HIỆN TẠI】\nHôm nay là: {now_str}\n\n"
            current_sources = []
            live_price_output = None
            calendar_output = None
            candles_output = None

            # Trích xuất danh sách tên công cụ để kiểm tra logic
            tool_names = [t.get("tool") if isinstance(t, dict) else t for t in tools_to_run]

            if "Live_API" in tool_names:
                # Tìm tham số của Live_API
                live_args = next((t.get("args", {}) for t in tools_to_run if isinstance(t, dict) and t.get("tool") == "Live_API"), {})
                symbol = live_args.get("symbol", "XAUUSD")
                if not symbol or symbol.strip() == "":
                    symbol = "XAUUSD"

                timeframe = live_args.get("timeframe", "1m")
                limit_raw = live_args.get("limit", 100)
                limit = int(limit_raw) if str(limit_raw).isdigit() else 100
                target_date = live_args.get("target_date", None)
                indicators = live_args.get("indicators", [])

                print(f"📡 [Observation] Lấy dữ liệu Live API cho {symbol} ({timeframe}, {limit} nến, target_date={target_date}, indicators={indicators})...")
                live_price = self.live_service.get_live_price(symbol)
                live_cal = self.live_service.get_economic_calendar()

                # Bổ sung lấy nến quá khứ (OHLCV) và các chỉ báo
                candles = self.live_service.get_historical_candles(symbol=symbol, timeframe=timeframe, limit=limit, target_date=target_date, indicators=indicators)
                candles_str = json.dumps(candles) if candles else "Không có dữ liệu nến"

                live_price_output = live_price
                calendar_output = live_cal
                candles_output = candles
                combined_context += f"【DỮ LIỆU THỜI GIAN THỰC】\nGiá hiện tại:\n{live_price}\n\nLịch kinh tế tuần này:\n{live_cal}\n\nDữ liệu nến quá khứ ({timeframe}, {limit} nến):\n{candles_str}\n\n"

            if "Search_Chat_History" in tool_names:
                print("⏳ [Observation] Trích xuất Long-term Memory...")
                history_context = self.vector_service.search_chat_history(session_id, current_query)
                combined_context += f"【KÝ ỨC LỊCH SỬ DÀI HẠN】\n{history_context}\n\n"

            if "VectorDB_Search" in tool_names:
                print("📚 [Observation] Bới tìm VectorDB...")
                retrieval_filters = None
                use_v3_runtime = Config.USE_KNOWLEDGE_V3 if use_knowledge_v3 is None else use_knowledge_v3
                fallback_enabled = (
                    Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY
                    if knowledge_v3_fallback_to_legacy is None
                    else knowledge_v3_fallback_to_legacy
                )
                if use_v3_runtime and canonical_query_plan.child_plans:
                    print(
                        "[QueryDecomposer] "
                        f"status=multi_intent subqueries={len(canonical_query_plan.child_plans)} "
                        f"reason=canonical_query_plan"
                    )
                    multi_context_parts = []
                    multi_sources = []
                    for subquery_index, child_plan in enumerate(canonical_query_plan.child_plans, start=1):
                        child_query = child_plan.original_query
                        child_intent = QueryPlanAssembler.intent_from_plan(child_plan)
                        sub_filters = self.retrieval_adapter.infer_routing_filters(
                            child_query,
                            query_intent=child_intent,
                        )
                        print(
                            "[QueryDecomposer] "
                            f"subquery={subquery_index} "
                            f"intent={child_plan.primary_intent} "
                            f"query={child_query!r}"
                        )
                        raw_candidates = self.retrieval_adapter.retrieve(
                            child_query,
                            filters=sub_filters,
                            top_k=Config.RETRIEVAL_TOP_K,
                            use_v3=use_v3_runtime,
                            fallback_to_legacy=fallback_enabled,
                            query_intent=child_intent,
                        )
                        if not raw_candidates:
                            multi_context_parts.append(
                                f"[SUBQUESTION {subquery_index}] {child_query}\n"
                                "No relevant Knowledge V3 context was retrieved for this subquestion."
                            )
                            continue
                        db_context, best_docs = self.reranker_module.process(
                            child_query,
                            raw_candidates,
                            enabled=enable_reranker,
                            query_intent=child_intent,
                        )
                        multi_sources.extend(best_docs)
                        multi_context_parts.append(
                            f"[SUBQUESTION {subquery_index}] {child_query}\n{db_context}"
                        )

                    if multi_context_parts:
                        combined_context += "【DỮ LIỆU KHO TRI THỨC - MULTI INTENT】\n"
                        combined_context += "\n\n".join(multi_context_parts) + "\n\n"
                        current_sources = multi_sources
                else:
                    if use_v3_runtime:
                        retrieval_filters = self.retrieval_adapter.infer_routing_filters(
                            user_query,
                            query_intent=canonical_query_intent,
                        )
                    raw_candidates = self.retrieval_adapter.retrieve(
                        user_query,
                        filters=retrieval_filters,
                        top_k=Config.RETRIEVAL_TOP_K,
                        use_v3=use_v3_runtime,
                        fallback_to_legacy=fallback_enabled,
                        query_intent=canonical_query_intent,
                    )
                    if raw_candidates:
                        db_context, best_docs = self.reranker_module.process(
                            user_query,
                            raw_candidates,
                            enabled=enable_reranker,
                            query_intent=canonical_query_intent,
                        )
                        combined_context += f"【DỮ LIỆU KHO TRI THỨC】\n{db_context}\n\n"
                        current_sources = best_docs

            decision_context = self.decision_context_builder.build(
                original_query=user_query,
                rewritten_query=current_query,
                retrieval_results=current_sources,
                live_price_output=live_price_output,
                candles_output=candles_output,
                calendar_output=calendar_output,
                query_intent=canonical_query_intent,
                query_plan=canonical_query_plan,
            )
            orchestrator_output = self.orchestrator_contract_builder.build(
                OrchestratorInput(
                    decision_context=decision_context,
                    user_intent=decision_context.query_intent,
                    permissions={"execution": False},
                    available_agents=[
                        "StaticKnowledgeAgent",
                        "MarketDataAgent",
                        "CalendarAgent",
                        "TechnicalAnalysisAgent",
                        "MarketContextAgent",
                        "StrategyAgent",
                        "RiskAgent",
                        "StrategyRiskConsistencyAgent",
                        "ExecutionGateAgent",
                    ],
                )
            )
            response_gate = ResponseGate.evaluate(decision_context, orchestrator_output)
            if not response_gate.normal_synthesis_allowed:
                return self._static_stream(response_gate.message), current_sources, "FINANCIAL_RAG", {"is_bounded_response": True}

            if not combined_context.strip():
                combined_context = "Không tìm thấy dữ liệu liên quan. Bạn phải trả lời dựa trên suy luận logic."

            # Giới hạn Short-term memory (RAM) gửi cho LLM (chỉ nạp 10 tin nhắn)
            short_term_history = chat_history[-10:] if chat_history else []

            # ── BƯỚC 3: GENERATION ──
            if not enable_self_correction:
                print("🚀 [Agent] Bỏ qua Reflection, trả thẳng kết quả stream ra UI.")
                final_stream = self.llm_service.generate_multihop_stream(user_query, combined_context, short_term_history)
                return final_stream, current_sources, "FINANCIAL_RAG", {}

            print(f"🧠 [Agent Reasoning] Sinh câu trả lời ngầm để Evaluator kiểm duyệt (Chưa hiện ra UI)...")
            draft_answer = ""
            for token in self.llm_service.generate_multihop_stream(user_query, combined_context, short_term_history):
                draft_answer += token

            # ── BƯỚC 4: EVALUATION & REFLECTION ──
            is_passed, new_feedback = self.evaluator_module.process(draft_answer, combined_context)

            if is_passed:
                print("✅ [Agent Reflection] Evaluator phê duyệt. Bắt đầu đẩy kết quả ra Streamlit UI...")
                final_stream = self._static_stream(draft_answer)
                return final_stream, current_sources, "FINANCIAL_RAG", {}
            else:
                feedback_note = new_feedback
                print(f"⚠️ [Agent Reflection] Evaluator bắt lỗi Hallucination: {feedback_note}")

                if current_loop < max_loops:
                    print("💡 [Agent Reflection] Đang tự đọc Feedback và sửa sai, tạo Query mới...")
                    current_query = self._agent_reflector(user_query, feedback_note, current_query)
                else:
                    print("🚨 [Agent] Đã thử hết giới hạn vòng lặp mà vẫn ảo tưởng. Ép in cảnh báo.")
                    warning = (
                        "⚠️ **CẢNH BÁO TỰ ĐỘNG:** Hệ thống không thể xác thực 100% "
                        "số liệu dưới đây do thiếu hụt tài liệu gốc. Vui lòng tham khảo có chọn lọc.\n\n"
                    )
                    final_stream = self._static_stream(warning + draft_answer)
                    return final_stream, current_sources, "FINANCIAL_RAG", {}

    # =========================================================================
    # AGENTIC INTERNAL HELPERS
    # =========================================================================

    def _build_evidence_artifacts(
        self,
        query_plan,
        decision_context,
        acquisition_batch,
        answer_type: str,
        user_query: str,
        executor=None,
        requirements=None,
        execution_plan=None,
    ):
        self._ensure_evidence_components()
        task_views = list(getattr(acquisition_batch, "task_context_views", []) or [])
        if not task_views:
            task_views = [{"task_id": getattr(query_plan, "task_id", "") or "task_1", "subquery": user_query}]
        bundles = []
        contracts = []
        for view in task_views:
            task_id = view.task_id if hasattr(view, "task_id") else view.get("task_id", "")
            task_answer_type = self._task_answer_type(answer_type, view)
            task_query_plan = self._query_plan_for_task(query_plan, task_id)
            task_results = self._results_for_task(list(getattr(acquisition_batch, "results", []) or []), task_id)
            self._log_task_result_routing(view, list(getattr(acquisition_batch, "results", []) or []), task_results, task_id)
            bundle = self.evidence_selector.select(
                query_plan=task_query_plan,
                task_view=view,
                acquisition_results=task_results,
                answer_type=task_answer_type,
                task_id=task_id,
            )
            refinement_request = EvidenceRefinementPlanner.should_refine(bundle)
            if refinement_request:
                execution_status = "insufficient"
                if executor and requirements and execution_plan:
                    EvidenceRefinementPlanner.log_refinement(refinement_request, status="start")
                    
                    import copy
                    import time
                    from src.services.semantic.context_acquisition import RuntimeContextStore
                    
                    refined_query_plan = copy.deepcopy(task_query_plan)
                    if hasattr(refined_query_plan, "original_query"):
                        refined_query_plan.original_query = refinement_request.refined_query
                    if hasattr(refined_query_plan, "normalized_query"):
                        refined_query_plan.normalized_query = refinement_request.refined_query
                    refined_query_plan.refined_topics = refinement_request.topic_descriptions or refinement_request.missing_topics
                    refined_query_plan.refinement_missing_topics = refinement_request.missing_topics
                    refined_query_plan.previous_chunk_ids = refinement_request.previous_chunk_ids
                    refined_query_plan.previous_evidence_ids = refinement_request.previous_evidence_ids
                    refined_query_plan.is_refinement = True
                    refined_query_plan.candidate_pool_size = 30
                    
                    refined_requirements = self._requirements_for_task(requirements, task_id)
                    refined_plan, scope = self._refinement_plan_for_task(execution_plan, refined_requirements, task_id)
                    print(
                        "[TaskRefinementScope] "
                        f"task_id={task_id} "
                        f"allowed_capabilities={scope['allowed_capabilities']} "
                        f"scheduled_capabilities={scope['scheduled_capabilities']} "
                        f"reused_shared={scope['reused_shared']} "
                        f"rejected_sibling_capabilities={scope['rejected_sibling_capabilities']}"
                    )
                    
                    refined_store = RuntimeContextStore()
                    
                    refined_batch = executor.execute(
                        query_plan=refined_query_plan,
                        requirements=refined_requirements,
                        execution_plan=refined_plan,
                        registry=None,
                        runtime_store=refined_store,
                        request_id=f"refine_{bundle.task_id}_{int(time.time()*1000)}"
                    )
                    if refined_batch and getattr(refined_batch, "results", []):
                        base_results = self._results_for_task(list(getattr(acquisition_batch, "results", []) or []), task_id)
                        refined_results = self._results_for_task(list(getattr(refined_batch, "results", []) or []), task_id)
                        foreign_result_ids = [
                            self._result_id(result)
                            for result in list(getattr(refined_batch, "results", []) or [])
                            if result not in refined_results
                        ]
                        all_results = base_results + refined_results
                        refined_result_ids = [self._result_id(result) for result in refined_results]
                        refined_doc_count = 0
                        refined_doc_ids = []
                        for result in refined_results:
                            data = getattr(result, "data", None)
                            docs = data if isinstance(data, list) else [data]
                            for doc in docs:
                                if not isinstance(doc, dict):
                                    continue
                                metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
                                refined_doc_count += 1
                                refined_doc_ids.append(str(metadata.get("chunk_id") or metadata.get("parent_chunk_id") or doc.get("chunk_id") or "unknown"))
                        print(
                            "[TaskRefinementMerge] "
                            f"task_id={task_id} base_result_ids={[self._result_id(result) for result in base_results]} "
                            f"refined_result_ids={refined_result_ids} refined_docs={refined_doc_count} "
                            f"refined_doc_ids={refined_doc_ids[:12]} foreign_result_ids={foreign_result_ids} "
                            f"status={'PASS' if not foreign_result_ids else 'FAIL'}"
                        )
                        
                        before_coverage = bundle.coverage_result.coverage_ratio if bundle.coverage_result else 0.0
                        before_missing = list(bundle.coverage_result.missing_required_topics) if bundle.coverage_result else []
                        
                        bundle = self.evidence_selector.select(
                            query_plan=task_query_plan,
                            task_view=view,
                            acquisition_results=all_results,
                            answer_type=task_answer_type,
                            task_id=task_id,
                            phase="post_refinement"
                        )
                        
                        after_coverage = bundle.coverage_result.coverage_ratio if bundle.coverage_result else 0.0
                        
                        # Calculate Novelty
                        new_evidence_ids = [item.evidence_id for item in bundle.all_items]
                        previous_evidence_ids = refinement_request.previous_evidence_ids
                        novel_ids = [eid for eid in new_evidence_ids if eid not in previous_evidence_ids]
                        repeated_ids = [eid for eid in new_evidence_ids if eid in previous_evidence_ids]
                        novelty_ratio = len(novel_ids) / len(new_evidence_ids) if new_evidence_ids else 0.0
                        
                        print(
                            "[RefinementNovelty] "
                            f"task_id={task_id} new_items={len(novel_ids)} repeated_items={len(repeated_ids)} "
                            f"novelty_ratio={novelty_ratio:.2f} evidence_ids={new_evidence_ids[:12]}"
                        )
                        
                        if after_coverage > before_coverage:
                            execution_status = "COMPLETED_IMPROVED"
                        elif novel_ids:
                            execution_status = "COMPLETED_NO_IMPROVEMENT"
                        else:
                            execution_status = "COMPLETED_NO_IMPROVEMENT"
                            
                        if bundle.coverage_result and bundle.coverage_result.status in {"INSUFFICIENT", "BLOCKED"} and execution_status == "COMPLETED_NO_IMPROVEMENT":
                            execution_status = "COMPLETED_STILL_DEGRADED"
                            
                        print(
                            "[CoverageRefinementResult] "
                            f"task_id={task_id} execution_status={execution_status} before={before_coverage:.2f} after={after_coverage:.2f} coverage_improved={str(after_coverage > before_coverage).lower()}"
                        )
                        
                    EvidenceRefinementPlanner.log_refinement(refinement_request, status=execution_status)
                else:
                    EvidenceRefinementPlanner.log_refinement(refinement_request, status="not_attempted_no_executor_loop")
            contract = self.answer_contract_builder.build(
                bundle,
                context_sufficiency=str((decision_context.sufficiency or {}).get("status") or "UNKNOWN"),
            )
            bundles.append(bundle)
            contracts.append(contract)

        aggregate = self._aggregate_evidence_sufficiency(bundles)
        decision_context.evidence_bundles = [bundle.as_dict() for bundle in bundles]
        decision_context.answer_contracts = [contract.as_dict() for contract in contracts]
        decision_context.evidence_sufficiency = aggregate
        if aggregate.get("status") == "DEGRADED" and aggregate.get("confidence_ceiling") == "medium":
            decision_context.confidence_ceiling = "medium"
        for warning in aggregate.get("warnings", []):
            if warning not in decision_context.warnings:
                decision_context.warnings.append(warning)
        structured_prompt = self.evidence_prompt_assembler.assemble(
            bundles,
            contracts,
            user_query=user_query,
            context_sufficiency=str((decision_context.sufficiency or {}).get("status") or "UNKNOWN"),
        )
        return bundles, contracts, structured_prompt

    @staticmethod
    def _need_name(need) -> str:
        return f"{getattr(need, 'capability', '')}:{getattr(need, 'target', '') or 'default'}"

    @staticmethod
    def _result_id(result) -> str:
        if hasattr(result, "result_id"):
            return result.result_id()
        return f"{getattr(result, 'capability', '')}:{getattr(result, 'target', '') or 'default'}"

    @staticmethod
    def _view_result_ids(view, key: str) -> List[str]:
        view_dict = view.as_dict() if hasattr(view, "as_dict") else dict(view or {})
        ids = []
        for item in view_dict.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            ids.append(str(item.get("result_id") or f"{item.get('capability', '')}:{item.get('target', '') or 'default'}"))
        return ids

    @staticmethod
    def _log_task_result_routing(view, all_results: List[Any], accepted_results: List[Any], task_id: str) -> None:
        required_ids = RAGOrchestrator._view_result_ids(view, "required_context_results")
        optional_ids = RAGOrchestrator._view_result_ids(view, "optional_context_results")
        accepted_ids = [RAGOrchestrator._result_id(result) for result in accepted_results or []]
        foreign_ids = [
            RAGOrchestrator._result_id(result)
            for result in all_results or []
            if RAGOrchestrator._result_id(result) not in set(accepted_ids)
        ]
        missing_ids = [
            result_id
            for result_id in required_ids + optional_ids
            if result_id not in set(accepted_ids)
        ]
        status = "PASS" if not missing_ids else "WARN"
        print(
            "[TaskResultRouting] "
            f"task_id={task_id} required_result_ids={required_ids} "
            f"optional_result_ids={optional_ids} accepted_result_ids={accepted_ids} "
            f"foreign_result_ids={foreign_ids} missing_result_ids={missing_ids} status={status}"
        )

    @staticmethod
    def _query_plan_for_task(query_plan, task_id: str):
        for child in getattr(query_plan, "child_plans", []) or []:
            if getattr(child, "task_id", "") == task_id:
                return child
        return query_plan

    @staticmethod
    def _results_for_task(results: List[Any], task_id: str) -> List[Any]:
        if not task_id:
            return list(results or [])
        scoped = []
        for result in results or []:
            task_ids = list(getattr(result, "requested_by_tasks", None) or getattr(result, "task_ids", None) or [])
            if task_id in task_ids:
                scoped.append(result)
        return scoped if scoped else ([] if task_id else list(results or []))

    @staticmethod
    def _requirements_for_task(requirements, task_id: str):
        if not requirements or not task_id:
            return requirements
        child_requirements = (getattr(requirements, "task_requirements", {}) or {}).get(task_id)
        if not child_requirements:
            if getattr(requirements, "task_id", "") == task_id:
                child_requirements = requirements
            else:
                return requirements
        from src.services.semantic.context_requirements import ContextRequirements

        needs = list(getattr(child_requirements, "needs", []) or [])
        return ContextRequirements(
            query_plan_id=getattr(child_requirements, "query_plan_id", getattr(requirements, "query_plan_id", "")),
            task_id=task_id,
            needs=needs,
            warnings=list(getattr(child_requirements, "warnings", []) or []),
            task_requirements={task_id: child_requirements},
            task_need_mapping={task_id: [RAGOrchestrator._need_name(need) for need in needs]},
        )

    @staticmethod
    def _refinement_plan_for_task(execution_plan, requirements, task_id: str):
        from src.services.semantic.context_execution import ContextExecutionPlan

        refinement_capabilities = {"static_knowledge", "official_report", "market_knowledge"}
        allowed_task_ids = {
            RAGOrchestrator._need_name(need)
            for need in (getattr(requirements, "needs", []) or [])
            if getattr(need, "capability", "") in refinement_capabilities
        }

        def belongs(task) -> bool:
            return task.task_id() in allowed_task_ids and task.capability in refinement_capabilities

        all_tasks = list(getattr(execution_plan, "parallel_tasks", []) or []) + list(getattr(execution_plan, "dependent_tasks", []) or [])
        parallel = [task for task in getattr(execution_plan, "parallel_tasks", []) or [] if belongs(task)]
        dependent = [task for task in getattr(execution_plan, "dependent_tasks", []) or [] if belongs(task)]
        deduplicated = [task for task in getattr(execution_plan, "deduplicated_tasks", []) or [] if belongs(task)]
        scheduled_ids = {task.task_id() for task in parallel + dependent + deduplicated}
        rejected = [
            task.task_id()
            for task in all_tasks
            if task.capability in refinement_capabilities and task.task_id() not in scheduled_ids
        ]
        unavailable = [
            item
            for item in getattr(execution_plan, "unavailable_capabilities", []) or []
            if item in allowed_task_ids
        ]
        scoped_plan = ContextExecutionPlan(
            parallel_tasks=parallel,
            dependent_tasks=dependent,
            unavailable_capabilities=unavailable,
            deduplicated_tasks=deduplicated,
        )
        scope = {
            "allowed_capabilities": sorted(allowed_task_ids),
            "scheduled_capabilities": sorted(task.task_id() for task in parallel + dependent),
            "reused_shared": [],
            "rejected_sibling_capabilities": sorted(dict.fromkeys(rejected)),
            "task_id": task_id,
        }
        return scoped_plan, scope

    def _ensure_evidence_components(self) -> None:
        if not hasattr(self, "evidence_selector"):
            self.evidence_selector = EvidenceSelector()
        if not hasattr(self, "answer_contract_builder"):
            self.answer_contract_builder = AnswerContractBuilder()
        if not hasattr(self, "evidence_prompt_assembler"):
            self.evidence_prompt_assembler = EvidencePromptAssembler()
        if not hasattr(self, "claim_evidence_validator"):
            self.claim_evidence_validator = ClaimEvidenceValidator()

    @staticmethod
    def _task_answer_type(default_answer_type: str, task_view) -> str:
        view_dict = task_view.as_dict() if hasattr(task_view, "as_dict") else dict(task_view or {})
        task_plan = view_dict.get("query_plan") or {}
        primary_intent = str(task_plan.get("primary_intent") or "")
        if primary_intent == "book_concept_explanation":
            return "static_explanation"
        if primary_intent == "macro_report_summary":
            return "report_summary"
        if primary_intent == "macro_market_impact":
            return "scenario_analysis"
        if primary_intent == "market_state_analysis":
            return "market_analysis"
        if primary_intent == "trade_opportunity_analysis":
            return "trade_plan_draft_without_position_size"
        return default_answer_type

    @staticmethod
    def _aggregate_evidence_sufficiency(bundles) -> Dict:
        statuses = []
        for bundle in bundles:
            status = bundle.sufficiency.status if bundle.sufficiency else "UNKNOWN"
            if bundle.coverage_result:
                if bundle.coverage_result.status in {"INSUFFICIENT", "BLOCKED"}:
                    status = bundle.coverage_result.status
                elif bundle.coverage_result.status == "DEGRADED" and status == "COMPLETE":
                    status = "DEGRADED"
            statuses.append(str(status).upper())
            
        missing = []
        warnings = []
        scores = []
        for bundle in bundles:
            if bundle.sufficiency:
                missing.extend([role for role in bundle.sufficiency.missing_roles if role not in missing])
                warnings.extend([warning for warning in bundle.sufficiency.warnings if warning not in warnings])
                scores.append(bundle.sufficiency.completeness_score)
            if bundle.coverage_result:
                warnings.extend([warning for warning in bundle.coverage_result.warnings if warning not in warnings])
                if hasattr(bundle.coverage_result, 'coverage_ratio'):
                    scores.append(bundle.coverage_result.coverage_ratio)
                    
        if any(status in {"INSUFFICIENT", "BLOCKED"} for status in statuses):
            status = "INSUFFICIENT"
            confidence = "low"
        elif any(status == "DEGRADED" for status in statuses):
            status = "DEGRADED"
            confidence = "medium"
        elif statuses:
            status = "COMPLETE"
            confidence = "high"
        else:
            status = "INSUFFICIENT"
            confidence = "low"
        return {
            "status": status,
            "completeness_score": min(scores) if scores else 0.0,
            "confidence_ceiling": confidence,
            "missing_roles": missing,
            "warnings": warnings,
            "task_statuses": {
                bundle.task_id: statuses[i]
                for i, bundle in enumerate(bundles)
            },
        }

    def _validate_and_maybe_repair_answer(
        self,
        draft_answer,
        user_query,
        structured_prompt,
        short_term_history,
        evidence_bundles,
        answer_contracts,
        runtime_artifacts=None,
    ):
        from src.services.evidence.answer_coverage import AnswerCoverageValidator
        from src.services.evidence.evidence_pipeline import TopicRepairDecision, AnswerContractEvaluator

        all_required_topics = []
        required_topics_by_task = {}
        topic_bindings_by_task = {}
        for contract in answer_contracts or []:
            contract_task_id = getattr(contract, "task_id", "") or "task"
            plan = getattr(contract, "synthesis_coverage_plan", None)
            contract_topics = []
            if plan:
                contract_topics = list(getattr(plan, "required_topics", []) or [])
                all_required_topics.extend(contract_topics)
            required_topics_by_task[contract_task_id] = list(dict.fromkeys(contract_topics))
            topic_bindings_by_task[contract_task_id] = {}
            for binding in getattr(contract, "topic_bindings", []) or []:
                topic_bindings_by_task[contract_task_id][binding.topic_role] = binding

        all_required_topics = list(dict.fromkeys(all_required_topics))
        coverage_val = AnswerCoverageValidator.evaluate(draft_answer, all_required_topics) if all_required_topics else None
        coverage_by_task = {
            task_id: AnswerCoverageValidator.evaluate(draft_answer, topics)
            for task_id, topics in required_topics_by_task.items()
            if topics
        }
        claim_validation = self.claim_evidence_validator.validate(draft_answer, evidence_bundles, answer_contracts)
        repair_status = "NOT_ATTEMPTED"
        final_answer = draft_answer

        if coverage_val and coverage_val.status == "WARN":
            repair_targets = []
            for contract_task_id, task_coverage in coverage_by_task.items():
                bindings = topic_bindings_by_task.get(contract_task_id, {})
                for topic, answer_status in self._coverage_topic_statuses(task_coverage).items():
                    if answer_status == "COVERED":
                        continue
                    binding = bindings.get(topic)
                    if not binding or not getattr(binding, "required", True):
                        continue
                    strength = self._topic_evidence_strength(getattr(binding, "topic_support_score", 0.0))
                    task_id = getattr(binding, "task_id", contract_task_id)
                    decision = TopicRepairDecision.evaluate(
                        task_id=task_id,
                        topic_role=topic,
                        answer_status=answer_status,
                        evidence_strength=strength,
                        repair_attempt_count=0,
                    )
                    print(
                        f"[TopicRepairDecision] task_id={task_id} topic={topic} "
                        f"answer_status={answer_status} evidence_strength={strength} "
                        f"repair_allowed={str(decision.repair_allowed).lower()} reason={decision.reason_code}"
                    )
                    if decision.repair_allowed:
                        repair_targets.append({"task_id": task_id, "topic": topic})

            topics_to_repair = list(dict.fromkeys([target["topic"] for target in repair_targets]))

            if topics_to_repair:
                print(f"[AnswerCoverageRepair] task_id=multi_intent attempt=1 topics={repair_targets} status=start")
                repair_prompt = self._build_answer_repair_prompt(
                    topics_to_repair=topics_to_repair,
                    coverage_val=coverage_val,
                )
                repaired_answer = ""
                for token in self._evidence_contract_stream(
                    user_query,
                    structured_prompt + "\n\n" + repair_prompt,
                    short_term_history,
                ):
                    repaired_answer += str(token or "")

                post_coverage_val = AnswerCoverageValidator.evaluate(repaired_answer, all_required_topics)
                post_claim_validation = self.claim_evidence_validator.validate(
                    repaired_answer,
                    evidence_bundles,
                    answer_contracts,
                )

                post_coverage_by_task = {
                    task_id: AnswerCoverageValidator.evaluate(repaired_answer, topics)
                    for task_id, topics in required_topics_by_task.items()
                    if topics
                }
                old_unresolved = sum(self._unresolved_topic_count(item) for item in coverage_by_task.values())
                new_unresolved = sum(self._unresolved_topic_count(item) for item in post_coverage_by_task.values())
                improved = (
                    new_unresolved < old_unresolved
                    or getattr(post_coverage_val, "coverage_ratio", 0.0) > getattr(coverage_val, "coverage_ratio", 0.0)
                )

                if post_claim_validation.status == "FAIL" and claim_validation.status != "FAIL":
                    repair_status = "ATTEMPTED_REGRESSED"
                    print(
                        f"[AnswerCoverageRepair] task_id=task attempt=1 status={repair_status} "
                        "reason=introduced_claim_violations"
                    )
                elif improved:
                    repair_status = "ATTEMPTED_IMPROVED"
                    final_answer = repaired_answer
                    coverage_val = post_coverage_val
                    coverage_by_task = post_coverage_by_task
                    claim_validation = post_claim_validation
                    print(f"[AnswerCoverageRepair] task_id=task attempt=1 status={repair_status}")
                else:
                    repair_status = "ATTEMPTED_NO_IMPROVEMENT"
                    print(f"[AnswerCoverageRepair] task_id=task attempt=1 status={repair_status}")

                if runtime_artifacts is not None:
                    runtime_artifacts["AnswerCoverageRepair"] = {
                        "attempt": 1,
                        "target_topics": repair_targets,
                        "status": repair_status,
                    }

        if runtime_artifacts is not None:
            runtime_artifacts["claim_validation"] = claim_validation.as_dict()
            if coverage_val is not None and hasattr(coverage_val, "as_dict"):
                runtime_artifacts["answer_coverage"] = coverage_val.as_dict()
            if coverage_by_task:
                runtime_artifacts["answer_coverage_by_task"] = {
                    task_id: coverage.as_dict() if hasattr(coverage, "as_dict") else coverage
                    for task_id, coverage in coverage_by_task.items()
                }
            contract_evaluations = []
            for contract in answer_contracts or []:
                contract_task_id = getattr(contract, "task_id", "") or "task"
                task_coverage = coverage_by_task.get(contract_task_id, coverage_val)
                c_eval = AnswerContractEvaluator.evaluate(
                    contract,
                    task_coverage,
                    claim_validation,
                    repair_status,
                    task_id=contract_task_id,
                )
                contract_evaluations.append(c_eval.as_dict())
            if contract_evaluations:
                runtime_artifacts["contract_evaluation"] = contract_evaluations[0]
                runtime_artifacts["contract_evaluations"] = contract_evaluations
                aggregate_status = self._aggregate_contract_status(contract_evaluations)
                task_status_text = ", ".join(
                    f"{item.get('task_id')}: {item.get('status')}"
                    for item in contract_evaluations
                )
                print(
                    "[MultiIntentContractAggregation] "
                    f"task_statuses={{{task_status_text}}} "
                    f"aggregate_status={aggregate_status}"
                )
            self._evaluate_agent_answer_compliance(final_answer, runtime_artifacts, answer_contracts)
            self._record_final_answer_artifact(
                runtime_artifacts,
                final_answer,
                source="repaired" if repair_status == "ATTEMPTED_IMPROVED" else "original",
                repair_status=repair_status,
            )

        return final_answer, claim_validation, coverage_val, repair_status

    @staticmethod
    def _coverage_topic_statuses(coverage_val) -> Dict[str, str]:
        if hasattr(coverage_val, "topic_statuses") and coverage_val.topic_statuses:
            return dict(coverage_val.topic_statuses)
        statuses = {}
        for topic in getattr(coverage_val, "missing_topics", []) or []:
            statuses[topic] = "MISSING"
        for topic in getattr(coverage_val, "partial_topics", []) or []:
            statuses[topic] = "PARTIAL"
        for topic in getattr(coverage_val, "uncertain_topics", []) or []:
            statuses[topic] = "UNCERTAIN"
        return statuses

    @staticmethod
    def _topic_evidence_strength(score: float) -> str:
        if score >= 0.65:
            return "STRONG"
        if score >= 0.45:
            return "ADEQUATE"
        if score > 0.1:
            return "WEAK"
        return "UNSUPPORTED"

    @staticmethod
    def _aggregate_contract_status(contract_evaluations: List[Dict[str, Any]]) -> str:
        statuses = [str(item.get("status") or "UNKNOWN").upper() for item in contract_evaluations or []]
        if any(status == "FAIL" for status in statuses):
            return "FAIL"
        if any(status == "WARN" for status in statuses):
            return "WARN"
        if statuses and all(status == "PASS" for status in statuses):
            return "PASS"
        return "UNKNOWN"

    @staticmethod
    def _unresolved_topic_count(coverage_val) -> int:
        if coverage_val is None:
            return 0
        statuses = RAGOrchestrator._coverage_topic_statuses(coverage_val)
        return sum(1 for item_status in statuses.values() if item_status in {"UNCERTAIN", "PARTIAL", "MISSING"})

    @staticmethod
    def _build_answer_repair_prompt(topics_to_repair: List[str], coverage_val) -> str:
        reasons = []
        topic_reasons = getattr(coverage_val, "topic_reasons", {}) or {}
        for topic in topics_to_repair:
            if topic in topic_reasons:
                reasons.append(f"- {topic}: {topic_reasons[topic]}")
        reason_block = "\n".join(reasons) if reasons else "- No additional diagnostic reason."
        return (
            "ANSWER COVERAGE REPAIR INSTRUCTION\n"
            f"Target topics only: {', '.join(topics_to_repair)}.\n"
            "Revise only what is necessary to clearly express these topics.\n"
            "Use only the structured evidence already provided in this prompt.\n"
            "Do not retrieve more context. Do not call tools. Do not add unsupported numeric data.\n"
            "Do not change source attribution. Preserve already-valid content.\n"
            "Validation diagnostics:\n"
            f"{reason_block}\n"
        )

    @staticmethod
    def _evaluate_agent_answer_compliance(final_answer: str, runtime_artifacts: dict | None, answer_contracts) -> None:
        if runtime_artifacts is None:
            return
        compliance_input = AgentAnswerComplianceInputBuilder.build(
            final_answer_text=final_answer,
            runtime_artifacts=runtime_artifacts,
            answer_contracts=answer_contracts,
        )
        result = AgentAnswerComplianceGate.evaluate(compliance_input)
        runtime_artifacts["agent_answer_compliance"] = result.as_dict()

    def _claim_validated_stream(self, stream, evidence_bundles, answer_contracts, runtime_artifacts=None):
        answer = ""
        for chunk in stream:
            answer += str(chunk or "")
            yield chunk
        answer_hash = self._answer_sha256(answer)
        print(f"[FinalValidation] sha256={answer_hash[:12]} chars={len(answer or '')}")
        claim_validation = self.claim_evidence_validator.validate(answer, evidence_bundles, answer_contracts)
        
        from src.services.evidence.answer_coverage import AnswerCoverageValidator
        from src.services.evidence.evidence_pipeline import AnswerContractEvaluator
        
        all_required_topics = []
        for contract in answer_contracts:
            plan = getattr(contract, "synthesis_coverage_plan", None)
            if plan:
                all_required_topics.extend(plan.required_topics)
                
        coverage_val = AnswerCoverageValidator.evaluate(answer, all_required_topics) if all_required_topics else None
        
        contract_evaluations = []
        for contract in answer_contracts:
            contract_task_id = getattr(contract, "task_id", "") or "task"
            task_topics = []
            plan = getattr(contract, "synthesis_coverage_plan", None)
            if plan:
                task_topics = list(getattr(plan, "required_topics", []) or [])
            task_coverage = AnswerCoverageValidator.evaluate(answer, task_topics) if task_topics else coverage_val
            c_eval = AnswerContractEvaluator.evaluate(
                contract,
                task_coverage,
                claim_validation,
                repair_status="NOT_ATTEMPTED",
                task_id=contract_task_id,
            )
            contract_evaluations.append(c_eval.as_dict())
            
        if runtime_artifacts is not None:
            runtime_artifacts["claim_validation"] = claim_validation.as_dict()
            if coverage_val is not None and hasattr(coverage_val, "as_dict"):
                runtime_artifacts["answer_coverage"] = coverage_val.as_dict()
            if contract_evaluations:
                runtime_artifacts["contract_evaluation"] = contract_evaluations[0]
                runtime_artifacts["contract_evaluations"] = contract_evaluations
                aggregate_status = self._aggregate_contract_status(contract_evaluations)
                task_status_text = ", ".join(
                    f"{item.get('task_id')}: {item.get('status')}"
                    for item in contract_evaluations
                )
                print(
                    "[MultiIntentContractAggregation] "
                    f"task_statuses={{{task_status_text}}} "
                    f"aggregate_status={aggregate_status}"
                )
            self._evaluate_agent_answer_compliance(answer, runtime_artifacts, answer_contracts)
            self._record_final_answer_artifact(
                runtime_artifacts,
                answer,
                source="streamed",
                repair_status="NOT_ATTEMPTED",
            )

    @staticmethod
    def _answer_sha256(answer: str) -> str:
        return hashlib.sha256(str(answer or "").encode("utf-8", errors="ignore")).hexdigest()

    def _record_final_answer_artifact(
        self,
        runtime_artifacts: dict | None,
        content: str,
        source: str,
        repair_status: str = "NOT_ATTEMPTED",
    ) -> None:
        if runtime_artifacts is None:
            return
        answer_hash = self._answer_sha256(content)
        runtime_artifacts["final_answer_artifact"] = {
            "content": str(content or ""),
            "source": source,
            "repair_status": repair_status,
            "chars": len(content or ""),
            "sha256": answer_hash,
        }
        print(
            "[FinalAnswerSelection] "
            f"source={source} chars={len(content or '')} "
            f"sha256={answer_hash[:12]}"
        )

    def _evidence_contract_stream(self, query: str, structured_prompt: str, history):
        if hasattr(self.llm_service, "generate_evidence_contract_stream"):
            return self.llm_service.generate_evidence_contract_stream(query, structured_prompt, history)
        return self.llm_service.generate_multihop_stream(query, structured_prompt, history)

    @staticmethod
    def _annotate_sources_with_evidence_status(sources: List[Dict], decision_context) -> None:
        evidence = decision_context.evidence_sufficiency or {}
        status = str(evidence.get("status") or "")
        
        for source in sources or []:
            if not isinstance(source, dict):
                continue
            metadata = source.setdefault("metadata", {})
            if status:
                metadata["evidence_sufficiency_status"] = status
                reason = ",".join(evidence.get("missing_roles", []) or evidence.get("warnings", []) or [])
                if reason:
                    metadata["evidence_reason"] = reason

    def _context_acquisition_executor(
        self,
        use_knowledge_v3: bool,
        fallback_to_legacy: bool,
        enable_reranker: Optional[bool],
    ) -> ContextAcquisitionExecutor:
        executor = getattr(self, "context_acquisition_executor", None)
        if executor is None:
            market_adapter = getattr(self, "market_adapter", None)
            if market_adapter is None and getattr(self, "live_service", None) is not None:
                market_adapter = ExistingMarketDataAdapter(self.live_service)
                self.market_adapter = market_adapter
            calendar_adapter = getattr(self, "calendar_adapter", None)
            if calendar_adapter is None and getattr(self, "live_service", None) is not None:
                calendar_adapter = ExistingEconomicCalendarAdapter(self.live_service)
                self.calendar_adapter = calendar_adapter
            technical_adapter = getattr(getattr(self, "decision_context_builder", None), "technical_adapter", None)
            executor = ContextAcquisitionExecutor(
                retrieval_adapter=getattr(self, "retrieval_adapter", None),
                reranker_module=getattr(self, "reranker_module", None),
                market_adapter=market_adapter,
                calendar_adapter=calendar_adapter,
                technical_adapter=technical_adapter,
                live_service=getattr(self, "live_service", None),
            )
            self.context_acquisition_executor = executor
        executor.retrieval_adapter = getattr(self, "retrieval_adapter", None)
        executor.reranker_module = getattr(self, "reranker_module", None)
        executor.live_service = getattr(self, "live_service", None)
        executor.use_v3 = use_knowledge_v3
        executor.knowledge_use_v3 = Config.SEMANTIC_CONTEXT_KNOWLEDGE_USE_V3
        executor.knowledge_fallback_to_legacy = Config.SEMANTIC_CONTEXT_KNOWLEDGE_FALLBACK_TO_LEGACY
        executor.fallback_to_legacy = fallback_to_legacy
        executor.enable_reranker = enable_reranker
        return executor

    def _build_agent_runtime_artifacts(self, orchestrator_output, decision_context) -> Dict[str, Any]:
        registry = getattr(self, "agent_runtime_registry", None) or AgentRuntimeRegistry()
        dispatcher = getattr(self, "agent_dispatcher", None) or AgentDispatcher(registry)
        plan = AgentExecutionPlanBuilder(registry).build(
            orchestrator_output,
            decision_context,
            request_id=getattr(decision_context, "request_id", "") or "agent_request",
        )
        runtime_context = AgentRuntimeContext(
            query_plan_ref=getattr(decision_context, "query_plan", None),
            decision_context_ref=decision_context,
            task_context_refs={
                str(item.get("task_id") or ""): item
                for item in (getattr(decision_context, "task_context_views", []) or [])
                if isinstance(item, dict)
            },
            acquisition_result_refs={
                str(item.get("result_id") or f"{item.get('capability', '')}:{item.get('target', '') or 'default'}"): item
                for item in (getattr(decision_context, "acquisition_results", []) or [])
                if isinstance(item, dict)
            },
            evidence_refs={
                str(item.get("task_id") or ""): item
                for item in (getattr(decision_context, "evidence_bundles", []) or [])
                if isinstance(item, dict)
            },
        )
        results = dispatcher.execute(plan, runtime_context) if plan.tasks else []
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        return {
            "execution_plan": plan.as_dict(),
            "results": [result.as_dict() for result in results],
            "aggregated_result": aggregate.as_dict(),
            "handoff": handoff.as_dict(),
        }

    @staticmethod
    def _append_agent_handoff_to_prompt(structured_prompt: str, agent_runtime_artifacts: Dict[str, Any]) -> str:
        results = ((agent_runtime_artifacts or {}).get("handoff") or {}).get("agent_results") or []
        lines = []
        total_chars = 0
        for result in results:
            if result.get("agent_type") != "MarketContextAgent" or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            raw_payload = result.get("structured_payload") or {}
            payload = compact_agent_payload("MarketContextAgent", raw_payload)
            assessment_ref = payload.get("assessment_ref", "")
            market_state = payload.get("market_state") or {}
            uncertainty = payload.get("uncertainty") or {}
            dominant = payload.get("dominant_factors") or []
            conflicts = payload.get("conflicting_signals") or []
            parent_task_id = result.get("parent_task_id") or result.get("task_id")
            block = (
                f"AGENT HANDOFF CONTEXT — task_id={parent_task_id} (analysis only; not evidence)\n"
                f"task_id: {parent_task_id}\n"
                f"assessment_ref: {assessment_ref}\n"
                f"symbol: {payload.get('symbol', '')}\n"
                f"as_of: {payload.get('as_of', '')}\n"
                f"market_state: {market_state}\n"
                f"dominant_factors: {dominant[:3]}\n"
                f"conflicting_signals: {conflicts[:3]}\n"
                f"confirmation_conditions: {payload.get('confirmation_conditions', {})}\n"
                f"uncertainty: confidence={uncertainty.get('confidence')} "
                f"missing_context={uncertainty.get('missing_context', [])} "
                f"limitations={uncertainty.get('limitations', [])}\n"
                f"source_refs: {result.get('source_refs', [])}\n"
                f"evidence_refs: {result.get('evidence_refs', [])}\n"
                "Boundary: analysis only. Factual claims still require evidence; no execution.\n"
                f"END AGENT HANDOFF CONTEXT — task_id={parent_task_id}\n"
            )
            total_chars += len(block)
            lines.append(block)
            print(
                "[PromptCompression] "
                f"task_id={parent_task_id} agent_type=MarketContextAgent "
                f"before_chars={len(json.dumps(raw_payload, ensure_ascii=False, default=str))} "
                f"after_chars={len(block)} "
                "included_sections=[market_state,dominant_factors,conflicting_signals,confirmation_conditions,uncertainty,refs]"
            )
            print(
                "[AgentPromptEnrichment] "
                f"task_id={parent_task_id} agent_type=MarketContextAgent "
                f"assessment_ref={assessment_ref} chars={len(block)} "
                "included_sections=[market_state,dominant_factors,conflicting_signals,confirmation_conditions,uncertainty]"
            )
        if not lines:
            return structured_prompt
        print(
            "[AgentPromptEnrichment] "
            f"market_context_assessment=true "
            f"assessment_ref={','.join(str((item.get('structured_payload') or {}).get('assessment_ref', '')) for item in results if item.get('agent_type') == 'MarketContextAgent' and item.get('status') in {'SUCCESS', 'PARTIAL'})} "
            f"chars={total_chars} "
            "included_sections=[market_state,dominant_factors,conflicting_signals,confirmation_conditions,uncertainty]"
        )
        strategy_chars = 0
        for result in results:
            if result.get("agent_type") != "StrategyAgent" or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            raw_payload = result.get("structured_payload") or {}
            payload = compact_agent_payload("StrategyAgent", raw_payload)
            parent_task_id = result.get("parent_task_id") or result.get("task_id")
            confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
            block = (
                f"AGENT HANDOFF CONTEXT — task_id={parent_task_id} — StrategyThesis (analysis only; not evidence)\n"
                f"task_id: {parent_task_id}\n"
                f"thesis_ref: {payload.get('thesis_ref', '')}\n"
                f"thesis_type: {payload.get('thesis_type', '')}\n"
                f"thesis_direction: {payload.get('thesis_direction', '')}\n"
                f"summary: {payload.get('thesis_summary', '')}\n"
                f"supporting_factors: {(payload.get('supporting_factors') or [])[:3]}\n"
                f"conflicting_factors: {(payload.get('conflicting_factors') or [])[:3]}\n"
                f"activation_conditions: {(payload.get('activation_conditions') or [])[:3]}\n"
                f"invalidation_conditions: {(payload.get('invalidation_conditions') or [])[:3]}\n"
                f"limitations: {payload.get('limitations', [])}\n"
                f"confidence: value={confidence.get('value')} ceiling={confidence.get('ceiling')}\n"
                f"evidence_refs: {result.get('evidence_refs', [])}\n"
                f"market_context_refs: {payload.get('market_context_refs', [])}\n"
                "Boundary: analysis only; evidence remains authoritative; no execution.\n"
                f"END AGENT HANDOFF CONTEXT — task_id={parent_task_id} — StrategyThesis\n"
            )
            strategy_chars += len(block)
            lines.append(block)
            print(
                "[PromptCompression] "
                f"task_id={parent_task_id} agent_type=StrategyAgent "
                f"before_chars={len(json.dumps(raw_payload, ensure_ascii=False, default=str))} "
                f"after_chars={len(block)} "
                "included_sections=[thesis_type,thesis_direction,supporting_factors,conflicting_factors,activation_conditions,invalidation_conditions,confidence,refs]"
            )
            print(
                "[StrategyPromptEnrichment] "
                f"task_id={parent_task_id} strategy_thesis=true "
                f"thesis_ref={payload.get('thesis_ref', '')} chars={len(block)} "
                "included_sections=[thesis_type,thesis_direction,supporting_factors,conflicting_factors,activation_conditions,invalidation_conditions,confidence]"
            )
        if strategy_chars:
            total_chars += strategy_chars
        risk_chars = 0
        for result in results:
            if result.get("agent_type") != "RiskAgent" or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            raw_payload = result.get("structured_payload") or {}
            payload = compact_agent_payload("RiskAgent", raw_payload)
            parent_task_id = result.get("parent_task_id") or result.get("task_id")
            adjustment = payload.get("confidence_adjustment") if isinstance(payload.get("confidence_adjustment"), dict) else {}
            block = (
                f"AGENT HANDOFF CONTEXT — task_id={parent_task_id} — RiskAssessment (analysis only; not evidence)\n"
                f"task_id: {parent_task_id}\n"
                f"risk_ref: {payload.get('risk_ref', '')}\n"
                f"overall_risk_level: {payload.get('overall_risk_level', '')}\n"
                f"risk_posture: {payload.get('risk_posture', '')}\n"
                f"confidence_adjustment: {adjustment}\n"
                f"key_risks: {(payload.get('key_risks') or [])[:3]}\n"
                f"thesis_fragility: {payload.get('thesis_fragility', {})}\n"
                f"conflicting_factors: {(payload.get('conflicting_factors') or [])[:3]}\n"
                f"missing_or_weak_context: {payload.get('missing_or_weak_context', [])}\n"
                f"confirmation_requirements: {(payload.get('confirmation_requirements') or [])[:3]}\n"
                f"invalidation_risks: {(payload.get('invalidation_risks') or [])[:3]}\n"
                f"limitations: {payload.get('limitations', [])}\n"
                f"evidence_refs: {result.get('evidence_refs', [])}\n"
                f"market_context_refs: {payload.get('market_context_refs', [])}\n"
                f"strategy_thesis_refs: {payload.get('strategy_thesis_refs', [])}\n"
                "Boundary: analysis only; not evidence, sizing, or execution.\n"
                f"END AGENT HANDOFF CONTEXT — task_id={parent_task_id} — RiskAssessment\n"
            )
            risk_chars += len(block)
            lines.append(block)
            print(
                "[PromptCompression] "
                f"task_id={parent_task_id} agent_type=RiskAgent "
                f"before_chars={len(json.dumps(raw_payload, ensure_ascii=False, default=str))} "
                f"after_chars={len(block)} "
                "included_sections=[overall_risk_level,risk_posture,confidence_adjustment,key_risks,thesis_fragility,confirmation_requirements,invalidation_risks,refs]"
            )
            print(
                "[RiskPromptEnrichment] "
                f"task_id={parent_task_id} risk_assessment=true "
                f"risk_ref={payload.get('risk_ref', '')} chars={len(block)} "
                "included_sections=[overall_risk_level,risk_posture,confidence_adjustment,key_risks,thesis_fragility,confirmation_requirements,invalidation_risks]"
            )
        if risk_chars:
            total_chars += risk_chars
        consistency_chars = 0
        for result in results:
            if result.get("agent_type") != "StrategyRiskConsistencyAgent" or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            raw_payload = result.get("structured_payload") or {}
            payload = compact_agent_payload("StrategyRiskConsistencyAgent", raw_payload)
            parent_task_id = result.get("parent_task_id") or result.get("task_id")
            confidence = payload.get("confidence_reconciliation") if isinstance(payload.get("confidence_reconciliation"), dict) else {}
            block = (
                f"AGENT HANDOFF CONTEXT — task_id={parent_task_id} — StrategyRiskConsistency (analysis only; not evidence)\n"
                f"task_id: {parent_task_id}\n"
                f"consistency_ref: {payload.get('consistency_ref', '')}\n"
                f"consistency_status: {payload.get('consistency_status', '')}\n"
                f"final_presentation_mode: {payload.get('final_presentation_mode', '')}\n"
                f"thesis_strength_after_risk: {payload.get('thesis_strength_after_risk', '')}\n"
                f"confidence_reconciliation: {confidence}\n"
                f"agreement_points: {(payload.get('agreement_points') or [])[:3]}\n"
                f"contradiction_points: {(payload.get('contradiction_points') or [])[:3]}\n"
                f"required_final_answer_emphasis: {payload.get('required_final_answer_emphasis', [])}\n"
                f"prohibited_final_answer_patterns: {payload.get('prohibited_final_answer_patterns', [])}\n"
                f"final_synthesis_guidance: {payload.get('final_synthesis_guidance', '')}\n"
                f"limitations: {payload.get('limitations', [])}\n"
                f"evidence_refs: {result.get('evidence_refs', [])}\n"
                f"market_context_refs: {payload.get('market_context_refs', [])}\n"
                f"strategy_thesis_refs: {payload.get('strategy_thesis_refs', [])}\n"
                f"risk_assessment_refs: {payload.get('risk_assessment_refs', [])}\n"
                "Boundary: analysis only; not evidence, sizing, or execution.\n"
                f"END AGENT HANDOFF CONTEXT — task_id={parent_task_id} — StrategyRiskConsistency\n"
            )
            consistency_chars += len(block)
            lines.append(block)
            print(
                "[PromptCompression] "
                f"task_id={parent_task_id} agent_type=StrategyRiskConsistencyAgent "
                f"before_chars={len(json.dumps(raw_payload, ensure_ascii=False, default=str))} "
                f"after_chars={len(block)} "
                "included_sections=[consistency_status,final_presentation_mode,thesis_strength_after_risk,confidence_reconciliation,agreement_points,contradiction_points,required_final_answer_emphasis,refs]"
            )
            print(
                "[ConsistencyPromptEnrichment] "
                f"task_id={parent_task_id} consistency_assessment=true "
                f"consistency_ref={payload.get('consistency_ref', '')} chars={len(block)} "
                "included_sections=[consistency_status,final_presentation_mode,thesis_strength_after_risk,confidence_reconciliation,agreement_points,contradiction_points,required_final_answer_emphasis]"
            )
        if consistency_chars:
            total_chars += consistency_chars
        return f"{structured_prompt}\n\n" + "\n".join(lines)

    def _align_tools_to_query_plan(self, tools_to_run: List[Dict], query_plan) -> List[Dict]:
        tools = [dict(tool) for tool in (tools_to_run or []) if isinstance(tool, dict)]
        plans = list(getattr(query_plan, "child_plans", []) or []) or [query_plan]
        intents = {getattr(plan, "primary_intent", "unknown") for plan in plans if plan is not None}
        symbols = [
            symbol
            for plan in plans
            for symbol in getattr(getattr(plan, "entities", None), "symbols", [])
        ]

        def has_tool(name: str) -> bool:
            return any(tool.get("tool") == name for tool in tools)

        needs_static = bool(intents & {
            "book_concept_explanation",
            "macro_report_summary",
            "macro_market_impact",
            "market_state_analysis",
            "multi_intent",
        })
        needs_live = bool(intents & {
            "macro_market_impact",
            "market_state_analysis",
            "trade_opportunity_analysis",
            "position_sizing",
        })

        if needs_static and not has_tool("VectorDB_Search"):
            tools.append({"tool": "VectorDB_Search", "args": {}})
        if needs_live and not has_tool("Live_API"):
            tools.append({
                "tool": "Live_API",
                "args": {
                    "symbol": symbols[0] if symbols else "XAUUSD",
                    "timeframe": "1h",
                    "limit": 100,
                },
            })
        return tools

    def _agent_tool_selector(self, query: str, current_time_str: str) -> List[Dict]:
        """Sử dụng LLM để tự quyết định công cụ cần gọi dựa trên câu hỏi."""
        prompt = f"""Bạn là một AI Controller. Bạn có 3 công cụ trong tay:
1. "VectorDB_Search": Dùng khi câu hỏi cần tìm lý thuyết (SMC, FVG), phân tích vĩ mô tĩnh trong quá khứ, báo cáo cũ.
2. "Live_API": Dùng khi câu hỏi cần lấy BẤT KỲ DỮ LIỆU GIÁ, NẾN NÀO hoặc yêu cầu PHÂN TÍCH XU HƯỚNG THỰC TẾ, CÁC CHỈ BÁO KỸ THUẬT (bao gồm: giá hiện tại, giá hôm qua, biểu đồ nến, trung bình động EMA, SMA, chỉ báo RSI, MACD...). Hỗ trợ truyền tham số: symbol (mặc định luôn là "XAUUSD" nếu người dùng không nhắc tên mã), timeframe (ví dụ: 1m, 5m, 15m, 1h, 4h, 1d), limit (số lượng nến), target_date (mốc thời gian cụ thể cần tra cứu, định dạng YYYY-MM-DD HH:MM:SS, nếu có), indicators (mảng cấu hình chỉ báo nếu người dùng yêu cầu, ví dụ: [{{"name": "ema", "period": 50}}, {{"name": "rsi", "period": 14}}]). LƯU Ý: Nếu người dùng hỏi giá tại một THỜI ĐIỂM CỤ THỂ mà KHÔNG nói rõ khung thời gian, BẮT BUỘC gán timeframe là "1m".
3. "Search_Chat_History": Dùng khi người dùng chủ động hỏi vặn, nhắc lại hoặc hồi tưởng về một chi tiết cụ thể nằm trong cuộc trò chuyện ở quá khứ. TUYỆT ĐỐI KHÔNG GỌI công cụ này nếu câu hỏi không mang tính chất lục lọi quá khứ.

THÔNG TIN BỐI CẢNH QUAN TRỌNG:
Thời gian hiện tại của hệ thống: {current_time_str}
Hãy dùng thời gian này để tính toán nếu người dùng hỏi những câu như "10 phút trước", "hôm qua", "vào ngày 12/06/2026 01:30" để truyền target_date, limit và timeframe cho phù hợp.

Nhiệm vụ: CÂU HỎI dưới đây cần gọi công cụ nào? Bạn có thể gọi 1 công cụ hoặc kết hợp nhiều công cụ cùng lúc. Trả về mảng rỗng [] nếu câu hỏi chỉ là chào hỏi xã giao hoặc không cần gọi công cụ.
Output BẮT BUỘC phải là mảng JSON hợp lệ chứa các object. Mỗi object gồm trường "tool" (tên công cụ) và "args" (các tham số cần thiết, nếu không cần tham số thì để trống). Không xuất thêm bất cứ text nào khác.
Ví dụ:
[
  {{"tool": "Live_API", "args": {{"symbol": "XAUUSD", "timeframe": "1m", "limit": 10, "target_date": "2026-06-12 01:30:00"}}}},
  {{"tool": "VectorDB_Search", "args": {{}}}}
]
hoặc []

CÂU HỎI: {query}"""
        try:
            from src.core.llm_client import LLMClient
            openrouter_client = LLMClient(provider_override="groq")
            resp = openrouter_client.chat([{"role": "user", "content": prompt}], stream=False, temperature=0.0)
            clean_resp = resp["message"]["content"].replace("```json", "").replace("```", "").strip()
            tools = json.loads(clean_resp)
            if isinstance(tools, list):
                return tools
        except Exception as e:
            print(f"⚠️ [Agent Tool Selector] Lỗi parse JSON: {e} -> Fallback dùng VectorDB_Search.")
        return [{"tool": "VectorDB_Search", "args": {}}]

    def _agent_reflector(self, original_query: str, feedback: str, previous_query: str) -> str:
        """LLM đọc Feedback từ Evaluator và tự sinh Query mới để tìm bù thông tin."""
        prompt = f"""Hệ thống vừa bị từ chối kết quả với LÝ DO: {feedback}
CÂU HỎI GỐC CỦA NGƯỜI DÙNG: {original_query}
CÂU TRUY VẤN LẦN TRƯỚC BẠN DÙNG: {previous_query}

Nhiệm vụ: Hãy đọc LÝ DO bị từ chối, và viết ra MỘT câu truy vấn TỪ KHÓA MỚI để tìm đúng đoạn kiến thức còn thiếu đó.
CHỈ output câu truy vấn mới, tuyệt đối không giải thích."""
        try:
            from src.core.llm_client import LLMClient
            openrouter_client = LLMClient(provider_override="groq")
            new_q = openrouter_client.chat([{"role": "user", "content": prompt}], stream=False, temperature=0.3)
            return new_q["message"]["content"].strip('"').strip()
        except Exception:
            return f"{previous_query} {feedback}"

    @staticmethod
    def _static_stream(text: str) -> Iterator[str]:
        """Giả lập streaming cho câu trả lời đã tạo sẵn, giúp giao diện UI mượt mà."""
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def _self_correction_pipeline(
        self,
        query: str,
        context: str,
        history: List[Dict],
        sources: List[Dict],
    ) -> Iterator[str]:
        """
        Stream trực tiếp lên UI (Non-blocking), đồng thời thu thập text.
        Sau khi luồng chính kết thúc mới chạy kiểm tra ngầm và đính chính.
        """
        print("⚡ [Pipeline] Đang stream kết quả trực tiếp...")
        full_answer = ""
        for token in self.llm_service.generate_multihop_stream(query, context, history):
            full_answer += token
            yield token

        print("🔍 [SelfCorrect] Chạy kiểm tra ngầm (Background Task)...")
        correction_note = self.llm_service.self_correct(full_answer, context)

        if correction_note and "[OK]" not in correction_note:
            print("⚠️ [SelfCorrect] Phát hiện sai sót, đang thêm đính chính...")
            yield correction_note

    def _find_cache_match(self, query: str) -> Optional[Dict]:
        """
        Tìm kiếm Cache dựa trên cơ sở So khớp mờ (Fuzzy Keyword Match).
        Tránh Cache Miss cứng nhắc do sai khác một vài từ không quan trọng.
        """
        current_time = time.time()

        # Lọc từ khóa: bỏ dấu câu và stop words cơ bản
        def get_keywords(text: str) -> set:
            import re
            clean_text = re.sub(r'[^\w\s]', '', text.lower())
            words = clean_text.split()
            stop_words = {"của", "và", "như", "thế", "nào", "đến", "các", "có", "là", "gì", "cho", "việc", "thì", "sao", "đi", "về", "đâu"}
            return set(w for w in words if w not in stop_words and len(w) > 1)

        q_words = get_keywords(query)
        if not q_words:
            return None

        for cached_q, data in list(self._context_cache.items()):
            if current_time - data["timestamp"] > self._CACHE_TTL:
                del self._context_cache[cached_q]
                continue

            c_words = get_keywords(cached_q)
            if not c_words:
                continue

            # Tính tỷ lệ Overlap (trùng khớp)
            intersection = q_words.intersection(c_words)
            overlap_ratio = len(intersection) / max(len(q_words), len(c_words))

            if overlap_ratio >= 0.75:  # Trùng > 75% từ khóa
                return data

        return None

if __name__ == "__main__":
    print("=== KIỂM THỬ TÍCH HỢP TOÀN PIPELINE ===")
    orch = RAGOrchestrator()

    test_cases = [
        ("Xin chào!",                    "GREETING"),
        ("jdjdjdjddđ",                   "TRASH"),
        ("cách nấu phở",                 "TRASH"),
        ("Lạm phát ảnh hưởng gì đến XAUUSD?", "FINANCIAL_RAG"),
    ]

    for query, expected in test_cases:
        stream, sources, intent, artifacts = orch.query_financial_advisor(query)
        tokens = list(stream)
        answer_preview = "".join(tokens)[:100]
        status = "✅" if intent == expected else "⚠️"
        print(f"\n{status} [{intent}] '{query}'")
        print(f"   Preview: {answer_preview}...")

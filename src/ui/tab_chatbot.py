"""Chatbot tab UI.

This module renders chat messages, delegates business logic to the orchestrator,
and displays retrieved sources. It does not call V3 services, Qdrant, Cohere,
or catalog code directly.
"""

import hashlib
import html
import json
import logging
import re
import time
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation

import streamlit as st

try:
    import plotly.graph_objects as go

    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

from src.config import Config
from src.services.agents.evaluation_registry import register_evaluation_record
from src.services.agents.journal_review import record_journal_review
from src.services.trading.decision.conversational_authorization import (
    ConversationalTradingRequest,
    StrategyCompletionState,
    apply_strategy_completion,
    build_strategy_completion_state,
    parse_conversational_trading_request,
)
from src.services.semantic.conversational_context import (
    ConversationalIntentContext,
    resolve_conversational_context,
)
from src.services.semantic.resolved_semantics import (
    OHLCV_INTEGER_FIELDS,
    ResolvedSemanticState,
    SemanticCompletionPatch,
    SemanticFieldUpdate,
)
from src.services.trading.market.live_feature_service import LiveFeatureService
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.provider_registry import ProviderRegistry
from src.services.trading.reasoning.strategy_evidence import plan_strategy_data
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
)
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    EditableTradeDraftCandidateService,
    draft_candidate_source_reference,
)
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraft,
    EditableTradeDraftService,
    EditableTradeDraftStore,
    TradeDraftError,
    TradeParameterPatch,
    market_evidence_from_live_result,
    semantic_prerequisite_blockers,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    TradingAuthorityOperatorService,
)
from src.services.trading.human_confirmed_management import (
    HumanConfirmedManagementProposal,
    HumanConfirmedManagementService,
    ManagementProposalPatch,
)
from src.ui.runtime_flags import get_knowledge_v3_flags
from src.ui.autonomous_candidate_review import (
    clear_autonomous_decision_run_result,
    get_autonomous_decision_run_result,
    render_autonomous_candidate_confirmation_controls,
    render_autonomous_candidate_review_card,
    store_autonomous_decision_run_result,
)
from src.ui.tab_dashboard import (
    _operator_candidate_review_controller,
    _render_autonomous_decision_review_card,
)
from src.ui.theme import render_section_heading


LOGGER = logging.getLogger(__name__)

PRESENTATION_TEXT = "TEXT"
PRESENTATION_TRADING_REQUEST = "TRADING_REQUEST"
PRESENTATION_POSITION_READ = "POSITION_READ"
PRESENTATION_MANAGEMENT = "MANAGEMENT_PROPOSAL"
PRESENTATION_BLOCKER = "BLOCKER"
PRESENTATION_LEGACY = "LEGACY_COMPATIBILITY"


class _AnswerStreamLogger:
    """Track final answer streaming without changing Streamlit rendering."""

    def __init__(
        self,
        query: str,
        request_id: str | None = None,
        provider_model: tuple[str, str] | None = None,
        finish_reason_getter=None,
    ):
        self.query = query
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self.provider_model = provider_model
        self.finish_reason_getter = finish_reason_getter
        self.chunk_count = 0
        self.char_count = 0
        self._sha256 = hashlib.sha256()
        self._tail = ""
        self._started_at = 0.0
        self._stream_ref = None
        self.finish_reason = "UNKNOWN"
        self.completeness = None
        self.done_logged = False
        self.error_logged = False

    def wrap(self, stream):
        """Yield stream chunks unchanged while collecting completion stats."""
        self._stream_ref = stream
        iterable = [stream] if isinstance(stream, str) else stream
        iterator = iter(iterable)
        try:
            try:
                first_chunk = next(iterator)
            except StopIteration:
                self._log_start()
                return
            except Exception as exc:
                self._log_start()
                self.log_error(exc)
                raise

            self._log_start()
            self._record_chunk(first_chunk)
            yield first_chunk

            for chunk in iterator:
                self._record_chunk(chunk)
                yield chunk
        except Exception as exc:
            self.log_error(exc)
            raise

    def log_done(self, full_answer=None, min_chars: int = 200, intent: str | None = None, query: str | None = None, sources=None, runtime_artifacts=None):
        """Log completion after st.write_stream returns."""
        if self.done_logged or self.error_logged:
            return self.completeness
        if self.chunk_count == 0 and full_answer:
            self._record_chunk(full_answer)

        self.finish_reason = self._resolve_finish_reason()
        completeness_input = full_answer or self._tail
        completeness_hash = _answer_sha256(completeness_input)
        if runtime_artifacts is not None:
            selected_artifact = runtime_artifacts.get("final_answer_artifact") or {}
            selected_hash = selected_artifact.get("sha256")
            runtime_artifacts["completeness_input_artifact"] = {
                "chars": len(completeness_input or ""),
                "sha256": completeness_hash,
                "matches_selected": (not selected_hash) or selected_hash == completeness_hash,
            }
            print(
                "[CompletenessInput] "
                f"chars={len(completeness_input or '')} sha256={completeness_hash[:12]} "
                f"matches_selected={str(((not selected_hash) or selected_hash == completeness_hash)).lower()}"
            )
        self.completeness = check_answer_completeness(
            completeness_input,
            self.finish_reason,
            min_chars=min_chars,
            intent=intent,
            query=query or self.query,
            sources=sources or [],
            runtime_artifacts=runtime_artifacts,
        )
        seconds = time.perf_counter() - self._started_at
        print(
            "[AnswerStream] DONE "
            f"request_id={self.request_id} "
            f"chunks={self.chunk_count} "
            f"chars={self.char_count} "
            f"seconds={seconds:.2f} "
            f"sha256={self._sha256.hexdigest()[:12]} "
            f"finish_reason={self.finish_reason} "
            f"output_complete={str(self.completeness['complete']).lower()} "
            f"tail={_sanitize_log_value(self._tail, 120)}"
        )
        self.done_logged = True
        return self.completeness

    def log_error(self, exc: Exception):
        """Log partial stats for a failed stream."""
        if self.error_logged or self.done_logged:
            return
        self.finish_reason = "ERROR"
        print(
            "[AnswerStream] ERROR "
            f"request_id={self.request_id} "
            f"chunks={self.chunk_count} "
            f"chars={self.char_count} "
            f"error={_sanitize_log_value(exc, 240)}"
        )
        self.error_logged = True

    def _log_start(self):
        provider, model = self.provider_model or _configured_llm_provider_model()
        self._started_at = time.perf_counter()
        print(
            "[AnswerStream] START "
            f"request_id={self.request_id} "
            f"model={_sanitize_log_value(model, 80)} "
            f"provider={_sanitize_log_value(provider, 40)} "
            f"query={_sanitize_log_value(self.query, 120)}"
        )

    def _record_chunk(self, chunk):
        text = _coerce_stream_text(chunk)
        if not text:
            return
        self.chunk_count += 1
        self.char_count += len(text)
        self._sha256.update(text.encode("utf-8", errors="replace"))
        self._tail = (self._tail + text)[-120:]

    def _resolve_finish_reason(self) -> str:
        for value in [
            _stream_finish_reason(self._stream_ref),
            self.finish_reason_getter() if self.finish_reason_getter else None,
            self.finish_reason,
        ]:
            reason = _normalize_finish_reason(value)
            if reason != "UNKNOWN":
                return reason
        return "UNKNOWN"


def render(orchestrator, feature_flags: dict):
    """Render the chatbot tab."""
    render_section_heading(
        "Advisory",
        "Conversation-led research with authoritative trading context and controls.",
    )
    knowledge_v3_flags = get_knowledge_v3_flags(st.session_state)
    if knowledge_v3_flags["use_knowledge_v3"]:
        st.warning("Knowledge V3 experimental retrieval enabled")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "intent" in msg:
                st.markdown(_render_badge(msg["intent"]), unsafe_allow_html=True)
            st.markdown(msg["content"])

            if msg["role"] == "assistant":
                _render_runtime_presentation(msg)
                _render_sources(msg.get("sources", []), intent=msg.get("intent"))
                metrics = _extract_metrics(msg["content"]) if msg.get("intent") not in {"RESEARCH_BRIEF", "COMPUTATIONAL_SPECIFICATION"} else {}
                if metrics:
                    _render_trade_chart(metrics)

    user_query = st.chat_input("Hoi ve xu huong vang, chien luoc SMC, du lieu vi mo...")
    latest_trading_request, latest_trading_state = _latest_trading_authorization(
        st.session_state.messages
    )
    if latest_trading_request is not None and not user_query:
        _render_conversational_trading_authorization(
            orchestrator,
            latest_trading_request,
            latest_trading_state,
        )
    if not user_query:
        _render_goal_research(orchestrator)
        _render_computational_specification_completion(orchestrator)
        _render_research_readiness(orchestrator)

    if user_query:
        previous_structured_context = _latest_resolved_semantic_state(st.session_state.messages)
        conversational_context = None
        trading_request = None
        user_msg = {"role": "user", "content": user_query}
        from src.services.history_service import HistoryService

        history_svc = HistoryService()
        if len(st.session_state.messages) == 0:
            auto_title = user_query[:30] + "..." if len(user_query) > 30 else user_query
            history_svc.rename_session(st.session_state.current_session_id, auto_title)

        st.session_state.messages.append(user_msg)
        history_svc.append_message(st.session_state.current_session_id, user_msg)
        with st.chat_message("user"):
            st.markdown(user_query)

        chat_history = st.session_state.messages[-(Config.MEMORY_WINDOW * 2):]

        memory_save_allowed = False
        completion_result = None
        with st.chat_message("assistant"):
            stream_logger = None
            try:
                Config.ENABLE_QUERY_REWRITING = feature_flags["query_rewriting"]

                stream, sources, intent, runtime_artifacts = orchestrator.query_financial_advisor(
                    user_query,
                    chat_history=chat_history,
                    session_id=st.session_state.current_session_id,
                    enable_self_correction=feature_flags["self_correction"],
                    enable_reranker=feature_flags["reranker"],
                    use_knowledge_v3=knowledge_v3_flags["use_knowledge_v3"],
                    knowledge_v3_fallback_to_legacy=knowledge_v3_flags["knowledge_v3_fallback_to_legacy"],
                    previous_structured_context=previous_structured_context,
                )
                _capture_management_proposal(runtime_artifacts)

                trading_request, conversational_context = _trading_request_from_runtime_artifacts(
                    runtime_artifacts,
                    user_query=user_query,
                    conversation_id=st.session_state.current_session_id,
                    messages=st.session_state.messages,
                )

                st.markdown(_render_badge(intent), unsafe_allow_html=True)
                stream_logger = _AnswerStreamLogger(
                    user_query,
                    provider_model=_active_llm_provider_model(orchestrator),
                    finish_reason_getter=lambda: _active_llm_finish_reason(orchestrator),
                )
                if runtime_artifacts and runtime_artifacts.get("is_bounded_response"):
                    stream_logger.finish_reason = "BOUNDED_RESPONSE"
                canonical_answer = str(st.write_stream(stream_logger.wrap(stream)) or "")
                display_answer = _sanitize_user_facing_answer(canonical_answer)
                full_answer = canonical_answer
                if runtime_artifacts is not None:
                    selected_artifact = runtime_artifacts.get("final_answer_artifact") or {}
                    delivery_artifact = _build_answer_delivery_artifact(
                        canonical_answer=canonical_answer,
                        display_answer=display_answer,
                        selected_artifact=selected_artifact,
                    )
                    runtime_artifacts["answer_delivery_artifact"] = delivery_artifact
                    if delivery_artifact["presentation_transformed"]:
                        print(
                            "[DeliveryTransform] "
                            "transform=user_facing_sanitize "
                            f"before_chars={delivery_artifact['canonical_chars']} "
                            f"after_chars={delivery_artifact['display_chars']} "
                            f"before_sha256={delivery_artifact['canonical_sha256'][:12]} "
                            f"after_sha256={delivery_artifact['display_sha256'][:12]}"
                        )
                    print(
                        "[AnswerDelivery] "
                        f"chars={delivery_artifact['canonical_chars']} "
                        f"sha256={delivery_artifact['canonical_sha256'][:12]} "
                        f"canonical_sha256={delivery_artifact['canonical_sha256'][:12]} "
                        f"display_sha256={delivery_artifact['display_sha256'][:12]} "
                        f"matches_selected={str(delivery_artifact['matches_selected']).lower()}"
                    )
                min_chars = 300 if intent == "FINANCIAL_RAG" else 1
                completion_result = stream_logger.log_done(
                    full_answer,
                    min_chars=min_chars,
                    intent=intent,
                    query=user_query,
                    sources=sources,
                    runtime_artifacts=runtime_artifacts,
                )
                completion_level = completion_result["level"] if completion_result else "fail"
                memory_save_allowed = completion_level in {"pass", "warn"}
                _log_answer_completeness(stream_logger.request_id, completion_result)
                if completion_level == "fail":
                    print(f"[AnswerStream] INCOMPLETE request_id={stream_logger.request_id} reason={completion_result['reason']}")
                    st.warning("Cau tra loi co the chua hoan tat hoac thieu cau truc toi thieu. Vui long thu lai.")
                elif completion_level == "warn":
                    st.warning("Cau tra loi da hoan tat nhung co the hoi ngan hoac thieu mot phan cau truc.")
                _render_sources(sources, intent=intent, query=user_query)
                if runtime_artifacts:
                    _render_runtime_presentation(runtime_artifacts)

                metrics = _extract_metrics(full_answer) if intent not in {"RESEARCH_BRIEF", "COMPUTATIONAL_SPECIFICATION"} else {}
                if metrics:
                    _render_trade_chart(metrics)

            except Exception as exc:
                import traceback

                full_answer = f"Loi xu ly: {exc}"
                sources = []
                intent = "ERROR"
                if stream_logger is not None:
                    stream_logger.log_error(exc)
                    completion_result = check_answer_completeness(full_answer, "ERROR", min_chars=1)
                    _log_answer_completeness(stream_logger.request_id, completion_result)
                st.error(full_answer)
                st.code(traceback.format_exc())

        assistant_msg = {
            "role": "assistant",
            "content": full_answer,
            "sources": [source for source in sources] if sources else [],
            "intent": intent,
            "answer_complete": completion_result["level"] if completion_result else False,
        }
        if completion_result:
            assistant_msg["completion_reason"] = completion_result["reason"]
            assistant_msg["finish_reason"] = completion_result["finish_reason"]
            if completion_result["level"] == "warn":
                assistant_msg["quality_status"] = "DEGRADED"
        if trading_request is not None:
            assistant_msg["trading_request"] = trading_request.to_public_dict()
        if conversational_context is not None:
            assistant_msg["conversational_context"] = conversational_context.as_dict()
        if runtime_artifacts is not None:
            _store_runtime_presentation(assistant_msg, runtime_artifacts)
            query_plan_payload = runtime_artifacts.get("query_plan")
            semantic_context = (
                query_plan_payload.get("semantic_context")
                if isinstance(query_plan_payload, dict)
                else None
            )
            if isinstance(semantic_context, dict):
                assistant_msg["resolved_semantic_state"] = semantic_context
            if intent == "RESEARCH_BRIEF":
                assistant_msg["research_brief"] = runtime_artifacts["research_brief"]
        st.session_state.messages.append(assistant_msg)
        HistoryService().append_message(
            st.session_state.current_session_id,
            assistant_msg,
            include_vector_memory=memory_save_allowed,
        )
        if memory_save_allowed:
            memory_hash = _answer_sha256(full_answer)
            memory_matches_selected = True
            if runtime_artifacts is not None:
                selected_artifact = runtime_artifacts.get("final_answer_artifact") or {}
                selected_hash = selected_artifact.get("sha256")
                memory_matches_selected = (not selected_hash) or selected_hash == memory_hash
                runtime_artifacts["memory_candidate_artifact"] = {
                    "chars": len(full_answer or ""),
                    "sha256": memory_hash,
                    "matches_selected": memory_matches_selected,
                }
                print(
                    "[MemoryCandidate] "
                    f"chars={len(full_answer or '')} sha256={memory_hash[:12]} "
                    f"matches_selected={str(memory_matches_selected).lower()}"
                )
            else:
                print(f"[MemoryCandidate] chars={len(full_answer or '')} sha256={memory_hash[:12]}")
            if not memory_matches_selected:
                print("[MemoryPolicy] answer_quality=FAIL action=skip reason=final_artifact_inconsistency")
                record_journal_review(
                    full_answer,
                    runtime_artifacts,
                    completion_result,
                    memory_policy_action="skip:final_artifact_inconsistency",
                    user_query=user_query,
                )
                _store_evaluation_runtime_artifacts(runtime_artifacts)
                return
            quality = "DEGRADED" if completion_result and completion_result["level"] == "warn" else "PASS"
            print(f"[MemoryPolicy] answer_quality={quality} action=stored_with_quality_flag")
            record_journal_review(
                full_answer,
                runtime_artifacts,
                completion_result,
                memory_policy_action="stored_with_quality_flag",
                user_query=user_query,
            )
            _store_evaluation_runtime_artifacts(runtime_artifacts)
        else:
            request_id = stream_logger.request_id if stream_logger is not None else "unknown"
            reason = completion_result["reason"] if completion_result else "stream_error"
            print(f"[MemoryPolicy] answer_quality=FAIL action=skip reason={reason}")
            artifacts_for_review = runtime_artifacts if "runtime_artifacts" in locals() else None
            record_journal_review(
                full_answer,
                artifacts_for_review,
                completion_result,
                memory_policy_action=f"skip:{reason}",
                user_query=user_query,
            )
            _store_evaluation_runtime_artifacts(artifacts_for_review)

        request_to_render, state_to_render = _latest_trading_authorization(
            st.session_state.messages
        )
        if request_to_render is not None:
            _render_conversational_trading_authorization(
                orchestrator,
                request_to_render,
                state_to_render,
            )
        elif intent == "COMPUTATIONAL_SPECIFICATION":
            _render_computational_specification_completion(orchestrator)
        elif intent == "RESEARCH_BRIEF":
            _render_goal_research(orchestrator)


def _render_goal_research(orchestrator) -> None:
    messages = st.session_state.messages
    session_id = st.session_state.current_session_id
    if not session_id or not messages or messages[-1].get("intent") != "RESEARCH_BRIEF":
        return
    try:
        view = orchestrator.inspect_goal_research(session_id, expected_tail=messages[-1])
        if st.session_state.current_session_id != session_id:
            return
        key, proposal = view["key"], view["proposal"]
        st.subheader("Research hypothesis")
        if proposal is None:
            if view["status"] == "NOT_GENERATED":
                if st.button("Generate testable hypothesis", key=f"research_generate_{key}"):
                    orchestrator.generate_goal_research(session_id, key)
                    st.rerun()
            else:
                st.warning(f"{view['status']} | {view['reason']}")
                confirmed = st.checkbox(
                    "I confirm this generation was interrupted and is not running in another instance",
                    key=f"research_recover_confirm_{key}_{view['generation_token']}",
                )
                if st.button("Retry / recover hypothesis generation", disabled=not confirmed,
                             key=f"research_retry_{key}_{view['generation_token']}"):
                    orchestrator.generate_goal_research(
                        session_id, key, retry=True, expected_generation=view["generation_token"],
                    )
                    st.rerun()
            return
        proof = None
        if st.button("Attach / check approved historical evidence", key=f"research_evidence_{key}"):
            proof = orchestrator.attach_goal_research_evidence(session_id, key, proposal.head.revision_id)
            if st.session_state.current_session_id != session_id:
                return
            proposal = orchestrator.inspect_goal_research(session_id, expected_tail=messages[-1])["proposal"]
        st.text(f"Proposal: {proposal.proposal_id}")
        st.text(f"Revision: {proposal.head.revision_id} | Origin: {proposal.origin}")
        st.text(f"Review: {proposal.review_status(proposal.head.revision_id)}")
        evidence_status = "EVIDENCE_PENDING" if proposal.head.evidence_status() != "VALIDATED" else "VALIDATED_DATA_ONLY"
        st.text(f"Evidence: {evidence_status} (no claim support or research approval inferred)")
        if proof:
            st.text(f"Independent data check: {proof['outcome']} | {proof['reason']}")
        st.caption("AI-suggested research only. Not evaluated; no trading or research execution authorization.")
        st.json(proposal.brief.model_dump(mode="json"))
        for limitation in proposal.head.content.limitations:
            st.text(limitation)
        st.text("Suggested timeframes: " + ", ".join(proposal.head.content.timeframes))
        with st.form(f"research_revision_{key}_{proposal.head.revision_id}"):
            hypothesis = st.text_area("Testable hypothesis", value=proposal.head.content.hypothesis, max_chars=500)
            save = st.form_submit_button("Save hypothesis revision")
        if save:
            orchestrator.revise_goal_research(session_id, key, proposal.head.revision_id, hypothesis)
            st.rerun()
        if st.button("Develop testable strategy", key=f"research_develop_{key}_{proposal.head.revision_id}"):
            orchestrator.develop_goal_research(session_id, key, proposal.head.revision_id)
            st.rerun()
        development = proposal.head.content.development
        if development is not None:
            st.subheader("Strategy specification and test plan")
            review = development.review()
            st.text(f"{review['status']} | NON_EXECUTABLE | Data: {review['data_status']}")
            st.caption("Revision authorship applies to these proposed rules. Canonical user constraints above remain unchanged.")
            st.json(development.model_dump(mode="json"))
            for label in ("missing_information", "conflicts", "unsupported"):
                if review[label]:
                    st.warning(label.replace("_", " ").capitalize() + ": " + "; ".join(review[label]))
            with st.form(f"research_specification_{key}_{proposal.head.revision_id}"):
                specification_json = st.text_area("Edit structured specification and test plan (JSON)",
                    value=development.model_dump_json(indent=2), height=320)
                save_specification = st.form_submit_button("Save specification revision")
            if save_specification:
                orchestrator.develop_goal_research(session_id, key, proposal.head.revision_id,
                                                   development_json=specification_json)
                st.rerun()
            _render_goal_historical_data(orchestrator, session_id, key, proposal)
        with st.expander("Revision history"):
            for revision in proposal.revisions:
                st.text(f"{revision.revision_id} | {revision.author} | {proposal.review_status(revision.revision_id)}")
                st.text(revision.content.hypothesis)
                if revision.content.development is not None:
                    st.json(revision.content.development.model_dump(mode="json"))
    except (ValueError, RuntimeError, OSError) as exc:
        reason = str(exc)
        st.warning(reason if re.fullmatch(r"[A-Z][A-Z0-9_]{2,90}", reason) else "RESEARCH_STATE_INVALID_OR_UNAVAILABLE")


def _render_goal_historical_data(orchestrator, session_id, key, proposal) -> None:
    import json

    development = proposal.head.content.development
    window = development.historical_window
    st.subheader("Historical research data")
    with st.form(f"research_window_{key}_{proposal.head.revision_id}"):
        start = st.text_input("Evaluation start (UTC, inclusive)", value=window.start.isoformat() if window and window.start else "")
        end = st.text_input("Evaluation end (UTC, exclusive)", value=window.end.isoformat() if window and window.end else "")
        split = st.text_input("IS/OOS boundary (UTC)", value=window.split.isoformat() if window and window.split else "")
        policies = [None, "UTC_WEEKDAYS_CONSERVATIVE_V1", "CONTINUOUS_UTC_V1"]
        policy = st.selectbox("Historical session policy", policies,
                              index=policies.index(window.session_policy) if window else 0,
                              format_func=lambda value: value or "Not specified")
        save_window = st.form_submit_button("Save historical window revision")
    if save_window:
        payload = development.model_dump(mode="json")
        payload["historical_window"] = {"start": start or None, "end": end or None, "split": split or None, "session_policy": policy}
        orchestrator.develop_goal_research(session_id, key, proposal.head.revision_id, development_json=json.dumps(payload))
        st.rerun()
    with st.form(f"research_costs_{key}_{proposal.head.revision_id}"):
        costs = []
        names = ("spread", "commission", "swap", "slippage")
        for name in names:
            existing = next((c for c in development.transaction_costs if c.name and c.name.casefold() == name), None)
            value = st.text_input(name.capitalize() + " value", value=str(existing.value) if existing and existing.value is not None else "")
            unit = st.text_input(name.capitalize() + " unit", value=existing.unit if existing and existing.unit else "")
            source = st.text_input(name.capitalize() + " source / assumption", value=existing.definition if existing and existing.definition else "")
            costs.append((name, value, unit, source))
        save_costs = st.form_submit_button("Save cost assumptions revision")
    if save_costs:
        payload = development.model_dump(mode="json")
        retained = [c.model_dump(mode="json") for c in development.transaction_costs if not c.name or c.name.casefold() not in names]
        try:
            payload["transaction_costs"] = retained + [
                {"name": name, "value": json.loads(value) if value else None, "unit": unit or None, "definition": source or None}
                for name, value, unit, source in costs]
        except ValueError:
            raise ValueError("RESEARCH_COST_VALUE_INVALID") from None
        orchestrator.develop_goal_research(session_id, key, proposal.head.revision_id, development_json=json.dumps(payload))
        st.rerun()
    view = orchestrator.inspect_goal_historical_data(session_id)
    st.text(f"{view['status']} | IS/OOS: {view['is_oos']}")
    with st.expander("Raw data and derived computation dependencies", expanded=True):
        st.json(view["dependencies"])
    st.json({"trading_cost_readiness": view["costs"]})
    for blocker in view["blockers"]:
        st.warning(blocker)
    for report in view["requests"]:
        request_id = report["request_id"]
        suffix = f"{key}_{proposal.head.revision_id}_{request_id}"
        with st.expander(f"{report['request']['export']['canonical_symbol']} / {report['request']['export']['timeframe']} historical input", expanded=True):
            st.json(report)
            if report["acquisition"] != "ACQUIRED":
                confirmed = st.checkbox("I request this exact read-only DEMO historical export", key="history_acquire_confirm_" + suffix)
                if st.button("Acquire historical DEMO data", disabled=not confirmed, key="history_acquire_" + suffix):
                    orchestrator.acquire_goal_history(session_id, key, proposal.head.revision_id, request_id,
                                                      retry=report["acquisition"] != "NOT_ACQUIRED")
                    st.rerun()
            elif report["approval"] == "NOT_APPROVED":
                approved = st.checkbox("I approve only this exact dataset and checksum for read-only research", key="history_approve_confirm_" + suffix)
                source_eligible = isinstance(report["coverage"], dict) and report["coverage"].get("status") == "VERIFIED"
                if st.button("Approve dataset source and verify R2", disabled=not approved or not source_eligible, key="history_approve_" + suffix):
                    orchestrator.approve_goal_history(session_id, key, proposal.head.revision_id, request_id, report["manifest_sha256"])
                    st.rerun()
            if report["approval"] == "SOURCE_APPROVED_ONLY":
                if report.get("R2", {}).get("reference_status") != "VALIDATED":
                    if st.button("Reverify R2 for current revision", key="history_reverify_" + suffix):
                        orchestrator.approve_goal_history(session_id, key, proposal.head.revision_id, request_id, report["manifest_sha256"])
                        st.rerun()
                if proposal.review_status(proposal.head.revision_id) == "READY_FOR_REVIEW":
                    reviewed = st.checkbox("I accept this exact research revision for the next research stage only", key="history_review_confirm_" + suffix)
                    if st.button("Accept research revision", disabled=not reviewed, key="history_review_" + suffix):
                        orchestrator.review_goal_research(session_id, key, proposal.head.revision_id)
                        st.rerun()
                if st.button("Prepare IS/OOS input package", key="history_prepare_" + suffix,
                             disabled=bool(report["blockers"]) or proposal.review_status(proposal.head.revision_id) != "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"):
                    orchestrator.prepare_goal_evaluation_input(session_id, key, proposal.head.revision_id, request_id)
                    st.rerun()
                if st.button("Prepare feature-only input", key="history_feature_prepare_" + suffix,
                             disabled=any(code != "RESEARCH_COST_ASSUMPTIONS_REQUIRED" for code in report["blockers"])
                             or proposal.review_status(proposal.head.revision_id) != "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"):
                    orchestrator.prepare_goal_evaluation_input(session_id, key, proposal.head.revision_id, request_id, feature_only=True)
                    st.rerun()
    _render_goal_research_features(orchestrator, session_id, key, proposal.head.revision_id)


def _render_goal_research_features(orchestrator, session_id, key, revision_id):
    view = orchestrator.inspect_goal_research_features(session_id)
    with st.expander("Historical research features", expanded=True):
        st.text(view["status"])
        st.json({"available": view.get("supported", []), "blocked": view.get("blocked", [])})
        if view.get("reason"):
            st.warning(view["reason"])
        request = view.get("request")
        if request:
            st.json(request)
            suffix = f"{key}_{revision_id}_{request['request_sha256']}"
            if view["status"] in {"READY_FOR_EXPLICIT_COMPUTATION_APPROVAL", "FAILED"}:
                approved = st.checkbox("I authorize only these pinned historical feature calculations, not a backtest or trade",
                                       key="feature_approval_" + suffix)
                if st.button("Compute research features", disabled=not approved, key="feature_compute_" + suffix):
                    orchestrator.compute_goal_research_features(session_id, key, revision_id, request["request_sha256"],
                                                               approved=approved, retry=view["status"] == "FAILED")
                    st.rerun()
        if view.get("result"):
            result = view["result"]
            st.json({"result_sha256": view["result_sha256"], "status": result["status"],
                     "numeric_encoding": result["numeric_encoding"], "strategy_evaluated": False})
            for series in result["series"]:
                st.markdown(f"**{series['name']} / {series['timeframe']}**")
                st.json({"parameters": series["parameters"], "output": series["output_field"],
                         "formula_version": series["formula_version"], "seed_open_time": series["seed_open_time"]})
                st.dataframe(series["rows"], use_container_width=True)
            for partition, observations in result["aligned_partitions"].items():
                st.markdown(f"**{partition} completed-bar alignment**")
                st.json(observations, expanded=False)


def _render_research_readiness(orchestrator) -> None:
    session_id = st.session_state.current_session_id
    if not session_id:
        return
    key = hashlib.sha256(session_id.encode()).hexdigest()
    with st.expander("Research readiness"):
        inspect_revision = st.button("Inspect existing research revision", key=f"research_readiness_{key}")
        inspect_result = st.button("Inspect verified result", key=f"research_result_{key}")
        if not inspect_revision and not inspect_result:
            return
        from src.services.history_service import HistoryService

        sessions = HistoryService().get_all_sessions()
        if not sessions or not any(session["_id"] == session_id for session in sessions):
            st.warning("NOT_CHECKED: conversation is unavailable.")
            return
        report = (orchestrator.inspect_research_result(session_id) if inspect_result
                  else orchestrator.inspect_research_readiness(session_id))
        if st.session_state.current_session_id != session_id:
            return
        if inspect_result:
            st.markdown("**Descriptive historical research**")
            st.text(f"{report['status']} | {report['reason']}")
            if report["status"] != "VERIFIED":
                return
            result = report["result"]
            st.text(report["objective"])
            st.text(f"Algorithm: {result['algorithm']} | Formula: {result['formula']}")
            st.text(f"Proposal: {result['proposal']['proposal_id']}")
            st.text(f"Revision: {result['proposal']['revision_id']}")
            dataset = result["dataset"]
            st.text(f"{dataset['symbol']} / {dataset['broker_symbol']} | {dataset['timeframe']}")
            st.text(f"UTC window: {result['window']['start_inclusive']} to {result['window']['end_exclusive']} (end-exclusive)")
            st.text(f"Dataset: {dataset['dataset_id']} | Provenance: {dataset['source']} | {dataset['account_environment']}")
            st.text(f"Input SHA-256: {result['input_sha256']}")
            st.text(f"Result SHA-256: {report['result_sha256']}")
            st.text(f"Verified observations: {result['row_count']} | Range unit: source price unit")
            st.dataframe(report["observations"], hide_index=True, use_container_width=True)
            st.caption("Descriptive historical observations only. Not a strategy, signal, backtest, forecast or profitability finding. "
                       "No new computation or execution authority. Hash/provenance inspection does not rerun the arithmetic.")
            return
        proposal, evidence = report["proposal"], report["evidence"]
        st.markdown("**Proposal revision**")
        st.text(f"{proposal['status']} | {proposal['reason']}")
        if "revision_id" in proposal:
            st.text(f"Revision: {proposal['revision_id']} | Recorded readiness: {proposal['readiness']}")
        st.markdown("**Historical evidence**")
        st.text(f"{evidence['outcome']} | {evidence['reason']}")
        if "checked_at" in evidence:
            st.text(f"Integrity: {evidence['integrity']} | Provenance: {evidence['provenance']} | "
                    f"Dataset quality: {evidence['coverage']}")
            if evidence["symbol"] and evidence["timeframe"]:
                st.text(f"Observed: {evidence['symbol']} / {evidence['timeframe']}")
            if evidence["window"]:
                st.text("Requested window: " + " to ".join(evidence["window"]))
            for limitation in evidence["limitations"]:
                st.text(limitation)
            st.caption(f"Checked at {evidence['checked_at']}")
        st.caption("Read-only. This does not authorize execution or assess research performance.")


def _render_computational_specification_completion(orchestrator) -> None:
    session_id = st.session_state.current_session_id
    messages = st.session_state.messages
    if not session_id or not messages or messages[-1].get("intent") != "COMPUTATIONAL_SPECIFICATION":
        return
    tail, count = messages[-1], len(messages)
    try:
        state = ResolvedSemanticState.from_dict(tail.get("resolved_semantic_state"))
    except ValueError:
        st.warning("Clarification unavailable: the current specification could not be reloaded.")
        return
    fields, unsupported = orchestrator.computational_specification_completion_fields(state)
    if unsupported:
        st.caption("Not editable in this form: " + ", ".join(unsupported) + ". Clarify these in a new message.")
    if not fields:
        return
    digest = hashlib.sha256(json.dumps((session_id, count, tail), sort_keys=True).encode()).hexdigest()
    slot = st.empty()
    with slot.container():
        field = st.selectbox(
            "Field to clarify", list(fields), index=0 if len(fields) == 1 else None,
            format_func=lambda path: fields[path][0], key=f"spec_field_{digest}",
        )
        if field is None:
            return
        label, choices = fields[field]
        with st.form(f"spec_completion_{digest}_{field}"):
            if choices:
                answer = st.selectbox(label, choices, index=None)
            else:
                hint = 'Use a JSON number, true/false, or quoted text.' if field.endswith(".value") else None
                key = field.rsplit(".", 1)[-1]
                if key in OHLCV_INTEGER_FIELDS:
                    unit = "seconds" if key == "max_age_seconds" else "bars"
                    hint = f"Enter a whole number of {unit}."
                answer = st.text_input(label, max_chars=1200, help=hint)
            submitted = st.form_submit_button("Apply clarification")
    if not submitted:
        return
    try:
        message = orchestrator.complete_computational_specification(state, field, answer or "")
        from src.services.history_service import HistoryService

        if st.session_state.current_session_id != session_id or not HistoryService().append_message_if_current(
            session_id, count, tail, message,
        ):
            st.warning("This review is stale or its conversation was deleted. Reopen the conversation before clarifying.")
            return
    except (ValueError, RuntimeError) as exc:
        st.warning(f"Clarification not saved: {exc}")
        return
    messages.append(message)
    slot.empty()
    st.rerun()


def _runtime_presentation(runtime_artifacts) -> tuple[str, dict | None]:
    """Select one primary typed presentation without interpreting raw language."""

    if not isinstance(runtime_artifacts, dict):
        return PRESENTATION_LEGACY, None
    management = runtime_artifacts.get("management_proposal")
    if (
        isinstance(management, dict)
        and management.get("schema_version") == "human-confirmed-management-proposal/v1"
    ):
        return PRESENTATION_MANAGEMENT, management
    position = runtime_artifacts.get("position_read_model")
    if (
        isinstance(position, dict)
        and position.get("schema_version") == "position-read-model/v1"
    ):
        return PRESENTATION_POSITION_READ, position
    trading = runtime_artifacts.get("trading_request")
    if isinstance(trading, dict) and trading.get("intent_type") == "TRADING_AUTHORIZATION_REQUEST":
        return PRESENTATION_TRADING_REQUEST, trading
    blockers = _runtime_blockers(runtime_artifacts)
    if blockers:
        return PRESENTATION_BLOCKER, {"blockers": blockers}
    return PRESENTATION_TEXT, None


def _runtime_blockers(runtime_artifacts: dict) -> list[str]:
    blockers = runtime_artifacts.get("blockers")
    if isinstance(blockers, (list, tuple)):
        return [str(value) for value in blockers if str(value).strip()]
    gate = runtime_artifacts.get("response_gate")
    if isinstance(gate, dict) and gate.get("normal_synthesis_allowed") is False:
        return [str(value) for value in gate.get("missing_context") or () if str(value).strip()]
    return []


def _render_runtime_presentation(runtime_artifacts) -> None:
    kind, payload = _runtime_presentation(runtime_artifacts)
    if kind == PRESENTATION_MANAGEMENT:
        _render_management_proposal_card(payload)
    elif kind == PRESENTATION_POSITION_READ:
        _render_position_read_card(payload)
    elif kind == PRESENTATION_BLOCKER:
        st.warning("Blocked: " + ", ".join(payload["blockers"]))


def _store_runtime_presentation(message: dict, runtime_artifacts: dict) -> None:
    kind, payload = _runtime_presentation(runtime_artifacts)
    message["presentation_kind"] = kind
    if kind == PRESENTATION_MANAGEMENT:
        message["management_proposal"] = payload
    elif kind == PRESENTATION_POSITION_READ:
        message["position_read_model"] = payload


def _render_position_read_card(payload) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "position-read-model/v1":
        return
    st.subheader("Trading State")
    blockers = list(payload.get("blockers") or [])
    if blockers:
        st.warning("Position state unavailable: " + ", ".join(blockers))
        return
    columns = st.columns(3)
    columns[0].metric("Open positions", len(payload.get("open_positions") or []))
    columns[1].metric("Pending orders", len(payload.get("pending_orders") or []))
    columns[2].metric("Recent closes", len(payload.get("history") or []))
    for heading, key in (
        ("Open Positions", "open_positions"),
        ("Pending Orders", "pending_orders"),
        ("Recent History", "history"),
    ):
        rows = list(payload.get(key) or [])
        if not rows:
            continue
        st.markdown(f"**{heading}**")
        for row in rows:
            if not isinstance(row, dict):
                continue
            pnl = row.get("unrealized_pnl")
            if pnl is None:
                pnl = row.get("realized_pnl")
            st.write(
                f"{row.get('canonical_symbol', '')} {row.get('direction', '')} | "
                f"state={row.get('state', '')} | volume={row.get('volume')} | "
                f"entry={row.get('entry_price')} | current={row.get('current_price')} | "
                f"P/L={pnl} | SL={row.get('stop_loss')} | TP={row.get('take_profit')}"
            )
    st.caption("Authoritative read-only broker/lifecycle projection. NON_EXECUTABLE.")


def _capture_management_proposal(runtime_artifacts) -> None:
    if not isinstance(runtime_artifacts, dict):
        return
    proposal = runtime_artifacts.pop("management_proposal_protected", None)
    if not isinstance(proposal, HumanConfirmedManagementProposal):
        return
    st.session_state.setdefault("management_proposals", {})[proposal.proposal_id] = proposal


def _render_management_proposal_card(payload) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "human-confirmed-management-proposal/v1":
        return
    st.markdown("#### Position Management")
    blockers = tuple(payload.get("blockers") or ())
    if blockers:
        st.warning("Management blocked: " + ", ".join(blockers))
        return
    proposal_id = str(payload.get("proposal_id") or "")
    proposal = st.session_state.get("management_proposals", {}).get(proposal_id)
    if not isinstance(proposal, HumanConfirmedManagementProposal):
        st.warning("Management proposal unavailable after session reload; create a fresh proposal.")
        return
    columns = st.columns(4)
    columns[0].metric("Symbol", proposal.canonical_symbol)
    columns[1].metric("Action", proposal.semantic_intent)
    columns[2].metric("Current volume", proposal.backend_proposal.current_observed_volume)
    columns[3].metric("Revision", proposal.revision)
    st.caption(
        f"broker={proposal.broker_symbol} | state={proposal.backend_proposal.lifecycle_state} | "
        f"target={proposal.target_reference[:12]}... | mode={proposal.mode} | NON_EXECUTABLE"
    )
    if proposal.semantic_intent == "MODIFY_POSITION_PROTECTION":
        _render_management_protection_editor(proposal)
    elif proposal.semantic_intent == "PARTIAL_CLOSE":
        _render_management_partial_close_editor(proposal)
    else:
        _render_management_confirmation(proposal)


def _render_management_protection_editor(proposal: HumanConfirmedManagementProposal) -> None:
    backend = proposal.backend_proposal
    with st.form(f"management_edit_{proposal.proposal_id}_{proposal.revision}"):
        columns = st.columns(2)
        stop_loss = columns[0].number_input(
            "New stop loss",
            value=float(backend.requested_stop_loss) if backend.requested_stop_loss is not None else None,
            placeholder="Unchanged / not set",
            format="%.8f",
        )
        take_profit = columns[1].number_input(
            "New take profit",
            value=float(backend.requested_take_profit) if backend.requested_take_profit is not None else None,
            placeholder="Unchanged / not set",
            format="%.8f",
        )
        update = st.form_submit_button("Update Proposal", use_container_width=True)
    if update:
        _apply_management_patch(
            proposal,
            ManagementProposalPatch(
                requested_stop_loss=_ui_decimal(stop_loss),
                requested_take_profit=_ui_decimal(take_profit),
            ),
        )
        return
    _render_management_confirmation(proposal)


def _render_management_partial_close_editor(proposal: HumanConfirmedManagementProposal) -> None:
    backend = proposal.backend_proposal
    with st.form(f"management_edit_{proposal.proposal_id}_{proposal.revision}"):
        if proposal.close_amount is not None:
            edited = st.number_input(
                "Close amount", min_value=0.0, value=float(proposal.close_amount), format="%.8f"
            )
            patch = ManagementProposalPatch(close_amount=_ui_decimal(edited))
        elif proposal.close_fraction is not None:
            edited = st.number_input(
                "Close fraction", min_value=0.01, max_value=0.99,
                value=float(proposal.close_fraction), step=0.01, format="%.4f",
            )
            patch = ManagementProposalPatch(close_fraction=_ui_decimal(edited))
        else:
            edited = st.number_input(
                "Resulting volume",
                min_value=0.0,
                value=float(backend.requested_resulting_volume or 0),
                format="%.8f",
            )
            patch = ManagementProposalPatch(resulting_volume=_ui_decimal(edited))
        st.caption(
            f"Resulting volume: {backend.requested_resulting_volume}"
        )
        update = st.form_submit_button("Update Proposal", use_container_width=True)
    if update:
        _apply_management_patch(proposal, patch)
        return
    _render_management_confirmation(proposal)


def _apply_management_patch(
    proposal: HumanConfirmedManagementProposal,
    patch: ManagementProposalPatch,
) -> None:
    outcome = HumanConfirmedManagementService().revise(proposal, patch)
    if outcome.proposal is None:
        st.warning("Management update blocked: " + ", ".join(outcome.blockers))
        return
    proposals = st.session_state.setdefault("management_proposals", {})
    proposals.pop(proposal.proposal_id, None)
    proposals[outcome.proposal.proposal_id] = outcome.proposal
    _replace_management_payload(proposal.proposal_id, outcome.to_public_dict())
    st.rerun()


def _render_management_confirmation(proposal: HumanConfirmedManagementProposal) -> None:
    phrase = proposal.confirmation_phrase
    st.info(f"Type exactly: {phrase}")
    with st.form(f"management_confirm_{proposal.proposal_id}_{proposal.revision}"):
        typed = st.text_input("Management confirmation", type="password")
        columns = st.columns(2)
        confirm = columns[0].form_submit_button("Confirm Management", use_container_width=True)
        cancel = columns[1].form_submit_button(
            "Keep Order" if proposal.semantic_intent == "CANCEL_PENDING_ORDER" else "Cancel",
            use_container_width=True,
        )
    if cancel:
        st.session_state.setdefault("management_proposals", {}).pop(proposal.proposal_id, None)
        cancelled = proposal.to_public_dict()
        cancelled.update(status="CANCELLED", confirmation_required=False)
        _replace_management_payload(proposal.proposal_id, cancelled)
        st.rerun()
    if not confirm:
        return
    receipt = HumanConfirmedManagementService().confirm_and_manage(
        proposal,
        typed_confirmation=typed,
    )
    if receipt.status == "BLOCKED":
        st.warning(f"Management blocked: {receipt.reason}")
    elif receipt.status == "UNKNOWN":
        st.warning("Management result unknown; reconciliation is required and retry is prohibited.")
    else:
        st.success(f"Management result: {receipt.status}")


def _replace_management_payload(proposal_id: str, payload: dict) -> None:
    for message in st.session_state.get("messages", []):
        current = message.get("management_proposal") if isinstance(message, dict) else None
        if isinstance(current, dict) and current.get("proposal_id") == proposal_id:
            message["management_proposal"] = payload


def _ui_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _latest_trading_authorization(
    messages,
) -> tuple[ConversationalTradingRequest | None, ResolvedSemanticState | None]:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("intent") in {"RESEARCH_BRIEF", "COMPUTATIONAL_SPECIFICATION"}:
            return None, None
        payload = message.get("trading_request") if isinstance(message, dict) else None
        if not isinstance(payload, dict):
            continue
        try:
            request = ConversationalTradingRequest.from_public_dict(payload)
        except ValueError:
            return None, None
        state_payload = message.get("resolved_semantic_state")
        if not isinstance(state_payload, dict):
            return request, None
        try:
            return request, ResolvedSemanticState.from_dict(state_payload)
        except ValueError:
            return request, None
    return None, None


def _latest_conversational_context(messages) -> ConversationalIntentContext | None:
    for message in reversed(messages):
        payload = message.get("conversational_context") if isinstance(message, dict) else None
        if not isinstance(payload, dict):
            continue
        try:
            return ConversationalIntentContext.from_dict(payload)
        except ValueError:
            return None
    return None


def _latest_resolved_semantic_state(messages) -> ResolvedSemanticState | None:
    for message in reversed(messages):
        payload = message.get("resolved_semantic_state") if isinstance(message, dict) else None
        if not isinstance(payload, dict):
            continue
        try:
            return ResolvedSemanticState.from_dict(payload)
        except ValueError:
            return None
    return None


def _trading_request_from_runtime_artifacts(
    runtime_artifacts,
    *,
    user_query: str,
    conversation_id: str,
    messages,
) -> tuple[ConversationalTradingRequest | None, ConversationalIntentContext | None]:
    """Use a valid semantic plan as the UI's trading authority before legacy fallback."""
    trading_payload = runtime_artifacts.get("trading_request") if isinstance(runtime_artifacts, dict) else None
    if isinstance(trading_payload, dict):
        return ConversationalTradingRequest.from_public_dict(trading_payload), None
    if isinstance(runtime_artifacts, dict):
        return None, None

    previous_context = _latest_conversational_context(messages)
    conversational_context = resolve_conversational_context(user_query, previous_context)
    return (
        parse_conversational_trading_request(
            user_query,
            conversation_id=conversation_id,
            context=conversational_context,
        ),
        conversational_context,
    )


def _render_conversational_trading_authorization(
    orchestrator,
    request: ConversationalTradingRequest,
    semantic_state: ResolvedSemanticState | None = None,
) -> None:
    completion = build_strategy_completion_state(request, semantic_state)
    if completion is not None:
        _render_strategy_completion_form(request, semantic_state, completion)
        return
    mandate_setup_with_account_binding_pending = (
        request.requested_mode == "autonomous_live"
        and set(request.blockers) == {"DEMO_ACCOUNT_SCOPE_REQUIRED"}
    )
    if (
        request.trade_action in {"OPEN_POSITION", "GENERIC_TRADE"}
        and request.requested_mode == "human_confirmed_live"
        and st.session_state.get("current_session_id")
        and (request.strategy is not None or (request.trade_parameters is not None and not request.blockers))
    ):
        _render_editable_trade_draft(request, orchestrator=orchestrator)
        return

    heading = (
        "#### Strategy Completion Required"
        if request.response_format == "STRATEGY_COMPLETION_REQUIRED_CARD"
        and not mandate_setup_with_account_binding_pending
        else "#### MT5 Trading Authorization"
    )
    st.markdown(heading)
    st.caption(
        f"mode={request.requested_mode} | confirmation={request.confirmation_policy} | "
        f"symbol={request.canonical_symbol} | broker={request.broker_symbol} | "
        f"profile={','.join(request.timeframe_profile)} | NON_EXECUTABLE"
    )
    if request.strategy is not None:
        strategy = request.strategy
        st.caption(
            f"Strategy={strategy.identity.strategy_id} | version={strategy.identity.strategy_version} | "
            f"hash={strategy.identity.normalized_strategy_hash[:12]}"
        )
        st.caption(
            "Indicators: "
            + ", ".join(
                f"{item.indicator_id}({','.join(f'{key}={value:g}' for key, value in item.parameters)})@{item.timeframe}"
                for item in strategy.indicators
            )
        )
        if strategy.entry_rules:
            st.caption(
                "Rules: "
                + "; ".join(
                    f"{item.left} {item.operator} {item.right or ','.join(f'{value:g}' for value in item.constants)}"
                    for item in strategy.entry_rules
                )
            )
    if request.blockers:
        st.warning("Completion blockers: " + ", ".join(request.blockers))
        if not mandate_setup_with_account_binding_pending:
            st.info("Provide the missing strategy fields in the next message. This specification remains NON_EXECUTABLE.")
            return
        st.info(
            "Standing Mandate setup remains NON_EXECUTABLE until authoritative demo-account binding succeeds."
        )
    if request.requested_mode == "advisory_only":
        st.info(
            "Advisory-only request: analysis is available, but Confirm, mandate, "
            "MT5 authorization, and submission are unavailable."
        )
        return
    elif request.requested_mode == "human_confirmed_live":
        st.info(
            "Human-confirmed request: demo MT5 access is separate from exact candidate "
            "confirmation and any later one-shot submission authorization."
        )
    else:
        st.info(
            "Autonomous request: execution requires a current bounded Standing Trading "
            "Mandate; per-trade human confirmation is not authority in this mode."
        )
    _render_autonomous_decision_review_card(
        orchestrator,
        request.canonical_symbol,
        request.timeframe_profile,
        requested_mode=request.requested_mode,
        generation_request_id=request.request_id,
        show_manual_proposal=False,
        key_prefix=f"chat_trade_{request.request_id}_",
        strategy=request.strategy,
        order_family="MARKET" if request.trade_action == "OPEN_POSITION" else "",
        strategy_direction=request.trade_direction,
        strategy_action=request.trade_action,
    )


def _render_strategy_completion_form(
    request: ConversationalTradingRequest,
    semantic_state: ResolvedSemanticState | None,
    completion: StrategyCompletionState,
) -> None:
    """Render structured semantic edits before evidence, Draft, or Candidate."""

    st.markdown("#### Strategy Completion Required")
    st.caption(
        f"action={completion.action or 'UNRESOLVED'} | "
        f"direction={completion.direction or 'UNRESOLVED'} | "
        f"symbol={completion.canonical_symbol or 'UNRESOLVED'} | "
        f"broker={completion.broker_symbol or 'UNRESOLVED'} | NON_EXECUTABLE"
    )
    st.caption(
        f"mode={completion.requested_mode} | "
        f"confirmation={completion.confirmation_policy}"
    )
    sources = dict(completion.field_sources)
    for index, indicator in enumerate(completion.strategy.indicators):
        parameters = ", ".join(
            f"{name}={value:g} [{sources.get(f'indicators[{index}].parameters.{name}', 'USER_EXPLICIT')}]"
            for name, value in indicator.parameters
        )
        timeframe = (
            f"{indicator.timeframe} [{sources.get(f'indicators[{index}].timeframe', 'USER_EXPLICIT')}]"
            if indicator.timeframe
            else "REQUIRED / unresolved"
        )
        st.caption(
            f"Indicator {index + 1}: {indicator.indicator_id} | "
            f"parameters={parameters or 'REQUIRED / unresolved'} | timeframe={timeframe}"
        )
    if completion.strategy.entry_rules:
        st.caption(
            "Condition: "
            + "; ".join(
                f"{rule.left} {rule.operator} "
                f"{rule.right or ','.join(f'{value:g}' for value in rule.constants)}"
                for rule in completion.strategy.entry_rules
            )
        )
    st.warning("Required semantic fields: " + ", ".join(completion.unresolved_fields))
    st.info(
        "Suggestions are not strategy facts until explicitly accepted. "
        "Evidence status: NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED."
    )
    if semantic_state is None:
        st.warning("Completion unavailable: authoritative semantic state is missing.")
        return

    suggestions = {item.field_path: item for item in completion.suggestions}
    selected: list[tuple[str, object, str]] = []
    prefix = f"strategy_completion_{completion.request_id}_"
    with st.form(prefix + "form"):
        for ordinal, field in enumerate(completion.unresolved_fields):
            suggestion = suggestions.get(field)
            suggested_label = (
                f"{suggestion.value:g} (suggested)"
                if suggestion is not None and isinstance(suggestion.value, (int, float))
                else f"{suggestion.value} (suggested)" if suggestion is not None else ""
            )
            if field.endswith(".timeframe"):
                values = ["Select..."]
                if suggested_label:
                    values.append(suggested_label)
                values.extend(
                    value
                    for value in ("M1", "M5", "M15", "H1", "H4", "D1", "Custom")
                    if value != (str(suggestion.value) if suggestion else "")
                )
                choice = st.selectbox(
                    field,
                    values,
                    key=prefix + f"choice_{ordinal}",
                )
                custom = (
                    st.text_input(
                        f"Custom value for {field}",
                        key=prefix + f"custom_{ordinal}",
                    )
                    if choice == "Custom"
                    else ""
                )
                value = custom.strip() if choice == "Custom" else choice.split(" ", 1)[0]
            else:
                values = ["Select..."]
                if suggested_label:
                    values.append(suggested_label)
                values.extend(("21", "Custom"))
                choice = st.selectbox(
                    field,
                    values,
                    key=prefix + f"choice_{ordinal}",
                )
                custom = (
                    st.text_input(
                        f"Custom value for {field}",
                        key=prefix + f"custom_{ordinal}",
                    )
                    if choice == "Custom"
                    else ""
                )
                raw = custom.strip() if choice == "Custom" else choice.split(" ", 1)[0]
                try:
                    value = float(raw)
                except ValueError:
                    value = None
            if value not in (None, "", "Select..."):
                source = (
                    "USER_CONFIRMED_SUGGESTION"
                    if choice == suggested_label
                    else "USER_EXPLICIT"
                )
                selected.append((field, value, source))
        apply_changes = st.form_submit_button(
            "Apply Strategy Completion",
            use_container_width=True,
        )
    if not apply_changes:
        return
    if not selected:
        st.warning("Select at least one unresolved strategy field.")
        return
    try:
        updated_request, updated_state = apply_strategy_completion(
            request,
            semantic_state,
            SemanticCompletionPatch(
                tuple(
                    SemanticFieldUpdate(field, value, source)
                    for field, value, source in selected
                )
            ),
        )
        message = {
            "role": "assistant",
            "content": "Strategy completion updated from explicit structured form input.",
            "trading_request": updated_request.to_public_dict(),
            "resolved_semantic_state": updated_state.as_dict(),
        }
        st.session_state.messages.append(message)
        from src.services.history_service import HistoryService

        HistoryService().append_message(
            st.session_state.current_session_id,
            message,
            include_vector_memory=False,
        )
        st.success("Strategy completion saved and revalidated.")
        st.rerun()
    except (TypeError, ValueError) as exc:
        st.error(f"Strategy completion blocked: {exc}")


def _render_editable_trade_draft(
    request: ConversationalTradingRequest, *, orchestrator=None
) -> None:
    """Render one persisted non-executable draft; domain code owns all calculations."""
    conversation_id = str(st.session_state.current_session_id)
    store = EditableTradeDraftStore()
    service = EditableTradeDraftService(store=store)
    existing = store.latest_for_conversation(conversation_id)
    evidence = None
    evidence_error = ""
    if existing is None or existing.source_request_id != request.request_id:
        evidence, evidence_error = _load_trade_draft_evidence(request)
    try:
        draft = service.build_or_load(
            request,
            conversation_id=conversation_id,
            evidence=evidence,
        )
    except TradeDraftError as exc:
        st.error(f"Trade draft unavailable: {exc}")
        return

    st.markdown("#### Editable Trade Draft")
    st.caption(
        f"Draft={draft.draft_id} | revision={draft.revision} | NON_EXECUTABLE | "
        f"evidence={draft.market_evidence_timestamp or 'UNAVAILABLE'}"
    )
    semantic_unresolved = tuple(
        getattr(request.strategy, "semantic_unresolved_fields", ())
        if request.strategy is not None
        else ()
    )
    if semantic_unresolved:
        st.info("Semantic input unresolved: " + ", ".join(semantic_unresolved))
    symbol = dict(draft.symbol.value or {})
    entry = dict(draft.entry.value or {})
    stop = dict(draft.stop.value or {})
    target = dict(draft.target.value or {})
    risk = dict(draft.risk.value or {})
    sizing = dict(draft.sizing.value or {})
    headline = st.columns(4)
    headline[0].metric("Symbol", symbol.get("canonical_symbol") or "MISSING")
    headline[1].metric("Broker", symbol.get("broker_symbol") or "MISSING")
    headline[2].metric("Direction", draft.direction.value or "MISSING")
    headline[3].metric("Revision", draft.revision)
    st.caption(
        f"Timeframes={','.join(symbol.get('timeframes') or ()) or 'MISSING'} | "
        f"action={draft.action.value or 'MISSING'} | mode={draft.mode.value or 'MISSING'} | "
        f"confirmation={draft.confirmation_policy.value or 'MISSING'}"
    )
    st.caption(
        "Entry rule: "
        + (_entry_rule_text(entry.get("rules") or ()) or ("IMMEDIATE" if entry.get("immediate_entry") else "MISSING"))
        + f" | reference={_display_decimal(entry.get('reference_price'))}"
    )
    proposal = st.columns(4)
    proposal[0].metric("Stop loss", _display_decimal(stop.get("price")))
    proposal[1].metric("Take profit", _display_decimal(target.get("price")))
    proposal[2].metric("Risk fraction", _display_decimal(risk.get("fraction")))
    proposal[3].metric("Volume", _display_decimal(sizing.get("proposed_volume")))
    st.caption(
        f"Stop={stop.get('method') or 'MISSING'} ({draft.stop.source}) | "
        f"Target={target.get('method') or 'MISSING'} ({draft.target.source}) | "
        f"Sizing={sizing.get('method') or 'MISSING'} ({draft.sizing.source})"
    )
    st.caption(
        f"Estimated risk={_display_decimal(sizing.get('actual_risk_amount'))} | "
        f"actual fraction={_display_decimal(sizing.get('actual_risk_fraction'))} | "
        "execution_authority=false | executable=false"
    )
    if evidence_error == "NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED":
        st.info("Evidence status: NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED")
    elif evidence_error:
        st.warning(f"Evidence warning: {evidence_error}")
    nonsemantic_blockers = tuple(
        blocker for blocker in draft.blockers if not blocker.startswith("SEMANTIC_UNRESOLVED:")
    )
    if nonsemantic_blockers:
        st.warning("Draft blockers: " + ", ".join(nonsemantic_blockers))
    else:
        st.success("Draft validation: BLOCKED_NON_EXECUTABLE" if draft.blockers else "Draft validation: VALID_NON_EXECUTABLE")
    if draft.warnings:
        st.caption("Warnings: " + ", ".join(draft.warnings))

    with st.expander("Edit risk parameters", expanded=False):
        _render_trade_draft_patch_form(service, draft, request)
    _render_trade_draft_refresh_action(service, draft, request)
    _render_draft_candidate_action(orchestrator, store, draft, request)
    st.info(
        "Applying changes creates a new immutable draft revision. It does not create "
        "a candidate, confirm a trade, grant submission authority, or send an order."
    )


def _render_trade_draft_patch_form(
    service: EditableTradeDraftService,
    draft: EditableTradeDraft,
    request: ConversationalTradingRequest,
) -> None:
    stop = dict(draft.stop.value or {})
    target = dict(draft.target.value or {})
    risk = dict(draft.risk.value or {})
    sizing = dict(draft.sizing.value or {})
    prefix = f"trade_draft_{draft.draft_id}_{draft.revision}_"
    stop_methods = ("USER_EXPLICIT", "ATR_MULTIPLE", "RECENT_STRUCTURE")
    target_methods = ("USER_EXPLICIT", "REWARD_RISK_RATIO", "RECENT_STRUCTURE")
    with st.form(prefix + "patch"):
        stop_method = st.selectbox(
            "Stop method",
            stop_methods,
            index=stop_methods.index(stop.get("method")) if stop.get("method") in stop_methods else 1,
            key=prefix + "stop_method",
        )
        stop_loss = st.text_input("Stop price", value=_input_decimal(stop.get("price")), key=prefix + "stop_loss")
        atr_multiplier = st.text_input("ATR multiplier", value=_input_decimal(stop.get("atr_multiplier")), key=prefix + "atr")
        target_method = st.selectbox(
            "Target method",
            target_methods,
            index=target_methods.index(target.get("method")) if target.get("method") in target_methods else 1,
            key=prefix + "target_method",
        )
        take_profit = st.text_input("Take-profit price", value=_input_decimal(target.get("price")), key=prefix + "take_profit")
        reward_risk_ratio = st.text_input("Reward/risk ratio", value=_input_decimal(target.get("reward_risk_ratio")), key=prefix + "rr")
        risk_fraction = st.text_input("Risk fraction (0.01 = 1%)", value=_input_decimal(risk.get("fraction")), key=prefix + "risk")
        requested_volume = st.text_input("Requested volume (optional)", value=_input_decimal(sizing.get("requested_volume")), key=prefix + "volume")
        apply_changes = st.form_submit_button("Apply Parameter Changes", use_container_width=True)
    if not apply_changes:
        return
    try:
        patch = TradeParameterPatch(
            expected_revision=draft.revision,
            stop_method=stop_method if stop_method != stop.get("method") else None,
            stop_loss=_changed_decimal(stop_loss, stop.get("price")),
            atr_multiplier=_changed_decimal(atr_multiplier, stop.get("atr_multiplier")),
            target_method=target_method if target_method != target.get("method") else None,
            take_profit=_changed_decimal(take_profit, target.get("price")),
            reward_risk_ratio=_changed_decimal(reward_risk_ratio, target.get("reward_risk_ratio")),
            risk_fraction=_changed_decimal(risk_fraction, risk.get("fraction")),
            requested_volume=_changed_decimal(requested_volume, sizing.get("requested_volume")),
        )
        if all(getattr(patch, name) is None for name in (
            "stop_loss", "stop_method", "atr_multiplier", "take_profit", "target_method",
            "reward_risk_ratio", "risk_fraction", "requested_volume", "direction",
        )):
            st.info("No parameter changes detected.")
            return
        evidence, evidence_error = _load_trade_draft_evidence(request)
        if evidence_error:
            st.warning(f"Evidence warning: {evidence_error}")
        updated = service.apply_patch(draft.draft_id, patch, evidence=evidence)
        clear_autonomous_decision_run_result(st.session_state)
        st.success(f"Draft revision {updated.revision} created.")
        st.rerun()
    except (TradeDraftError, InvalidOperation) as exc:
        st.error(f"Parameter update blocked: {exc}")


def _render_trade_draft_refresh_action(
    service: EditableTradeDraftService,
    draft: EditableTradeDraft,
    request: ConversationalTradingRequest,
) -> None:
    result_key = f"editable_draft_{draft.draft_id}_market_refresh_result"
    result = st.session_state.pop(result_key, None)
    if result is not None:
        st.success(
            "Market evidence refreshed | "
            f"revision: {result['from_revision']} -> {result['to_revision']} | "
            f"observed_at: {result['observed_at']} | "
            f"Draft validation: {result['validation']}"
        )

    if not st.button(
        "Refresh Market Evidence",
        key=f"editable_draft_{draft.draft_id}_{draft.revision}_refresh_market_evidence",
        use_container_width=True,
    ):
        return

    evidence, evidence_error = _load_trade_draft_evidence(request)
    if evidence is None:
        st.warning(f"Market evidence refresh blocked: {evidence_error or 'EVIDENCE_UNAVAILABLE'}")
        return
    try:
        updated = service.apply_patch(
            draft.draft_id,
            TradeParameterPatch(expected_revision=draft.revision),
            evidence=evidence,
        )
    except (TradeDraftError, InvalidOperation) as exc:
        st.error(f"Market evidence refresh blocked: {exc}")
        return

    clear_autonomous_decision_run_result(st.session_state)
    st.session_state[result_key] = {
        "from_revision": draft.revision,
        "to_revision": updated.revision,
        "observed_at": updated.market_evidence_timestamp or "UNAVAILABLE",
        "validation": (
            "BLOCKED_NON_EXECUTABLE" if updated.blockers else "VALID_NON_EXECUTABLE"
        ),
    }
    st.rerun()


def _render_draft_candidate_action(
    orchestrator,
    store: EditableTradeDraftStore,
    draft: EditableTradeDraft,
    request: ConversationalTradingRequest,
) -> None:
    """Create a Candidate only after an explicit action for this exact Draft revision."""
    key_prefix = f"editable_draft_{draft.draft_id}_{draft.revision}"
    outcome_key = key_prefix + "_candidate_outcome"
    if st.button(
        "Create Candidate",
        key=key_prefix + "_create_candidate",
        use_container_width=True,
    ):
        if orchestrator is None or getattr(orchestrator, "live_service", None) is None:
            st.error("Candidate creation unavailable: runtime service missing.")
        else:
            authority_service = TradingAuthorityOperatorService()
            try:
                status = authority_service.status(refresh_runtime=False)
            except Exception as exc:
                st.warning(f"Candidate creation unavailable: {type(exc).__name__}")
                return
            finally:
                authority_service.close()
            service = EditableTradeDraftCandidateService(
                store,
                AuthoritativeAutonomousInputAssembler(
                    orchestrator.live_service,
                    mode=str(status.get("mode") or "NOT_SET"),
                ),
                AutonomousDecisionOrchestrator(),
            )
            outcome = service.create(
                draft.draft_id,
                draft.revision,
                strategy=request.strategy,
                authoritative_mode=str(status.get("mode") or "NOT_SET"),
                account_environment=str(status.get("account_environment") or "UNKNOWN"),
                mode_integrity_valid=status.get("mode_integrity_valid") is True,
            )
            st.session_state[outcome_key] = outcome
            if outcome.run_result is not None:
                store_autonomous_decision_run_result(st.session_state, outcome.run_result)

    outcome = st.session_state.get(outcome_key)
    if outcome is not None:
        if outcome.status == "CANDIDATE_CREATED":
            st.success(
                "Candidate created for this immutable Draft revision. "
                "It remains non-executable."
            )
        elif outcome.status == "CANDIDATE_ALREADY_EXISTS":
            st.info("Candidate already exists for this immutable Draft revision.")
        else:
            st.warning(
                "Candidate creation blocked: "
                + (outcome.blocker or outcome.status)
            )
            if outcome.blocker == "DRAFT_MODE_AUTHORITY_MISMATCH":
                st.info(
                    f"This Draft requires authoritative mode {draft.mode.value}. "
                    "Use the existing DEMO mode authorization control to grant that mode, "
                    "then retry Create Candidate."
                )

    run_result = get_autonomous_decision_run_result(st.session_state)
    candidate = run_result.candidate if run_result is not None else None
    if (
        candidate is not None
        and candidate.proposal_source == EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE
        and candidate.proposal_source_reference == draft_candidate_source_reference(draft)
    ):
        render_autonomous_candidate_review_card(candidate, run_result.validation)
        if candidate.operating_mode == "human_confirmed_live":
            render_autonomous_candidate_confirmation_controls(
                candidate.candidate_reference,
                _operator_candidate_review_controller(),
                key_prefix=key_prefix + "_",
            )


def _load_trade_draft_evidence(request: ConversationalTradingRequest):
    if semantic_prerequisite_blockers(request):
        return None, "NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED"
    try:
        provider = ProviderRegistry.build_provider()
        feature_service = LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(provider)
        )
        strategy = request.strategy
        if strategy is not None:
            plan = plan_strategy_data(strategy)
            result = feature_service.build_features(
                request.canonical_symbol,
                strategy.timeframes,
                plan.candle_counts(),
                strategy=strategy,
                data_plan=plan,
            )
        else:
            result = feature_service.build_features(
                request.canonical_symbol,
                request.timeframe_profile,
            )
        account = provider.get_account()
        authority_service = TradingAuthorityOperatorService()
        try:
            authority = authority_service.status(refresh_runtime=False)
        finally:
            authority_service.close()
        primary = (strategy.timeframes if strategy else request.timeframe_profile)[0]
        return market_evidence_from_live_result(
            result,
            account,
            primary_timeframe=primary,
            account_environment=str(authority.get("account_environment") or "UNKNOWN"),
        ), ""
    except ValueError:
        LOGGER.warning("Trade draft evidence validation failed")
        return None, "EVIDENCE_VALIDATION_FAILED"
    except Exception:
        LOGGER.warning("Trade draft evidence acquisition failed")
        return None, "EVIDENCE_ACQUISITION_FAILED"


def _entry_rule_text(rules) -> str:
    output = []
    for rule in rules:
        values = rule.get("constants") or ()
        output.append(
            f"{rule.get('left')} {rule.get('operator')} "
            f"{rule.get('right') or ','.join(str(item) for item in values)}"
        )
    return "; ".join(output)


def _display_decimal(value) -> str:
    return _input_decimal(value) or "MISSING"


def _input_decimal(value) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
        text = format(number, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    except InvalidOperation:
        return str(value)


def _changed_decimal(text: str, current) -> Decimal | None:
    value = str(text or "").strip()
    if not value:
        return None
    number = Decimal(value)
    return number if current in (None, "") or number != Decimal(str(current)) else None


def _store_evaluation_runtime_artifacts(runtime_artifacts: dict | None) -> None:
    """Expose review-safe evaluation artifacts to the dashboard tab."""
    if runtime_artifacts is None:
        return

    st.session_state.latest_runtime_artifacts = runtime_artifacts
    try:
        for record_type, artifact_key in (
            ("journal_review", "journal_review"),
            ("backtest_evaluation", "backtest_evaluation"),
            ("paper_trading_evaluation", "paper_trading_evaluation"),
        ):
            record = runtime_artifacts.get(artifact_key)
            if record:
                register_evaluation_record(record, record_type, runtime_artifacts, replace=True)
        registry = runtime_artifacts.get("evaluation_registry")
        if registry:
            st.session_state.evaluation_registry = registry
    except Exception as exc:  # pragma: no cover - dashboard bridge must not affect chat delivery
        print(f"[EvaluationDashboard] action=session_registry status=WARN error={_sanitize_log_value(exc, 160)}")


def _configured_llm_provider_model():
    """Return configured provider/model names for stream observability."""
    provider = getattr(Config, "LLM_PROVIDER", "unknown")
    model_by_provider = {
        "google": getattr(Config, "GOOGLE_MODEL_NAME", ""),
        "groq": getattr(Config, "GROQ_MODEL_NAME", ""),
        "openrouter": getattr(Config, "OPENROUTER_MODEL_NAME", ""),
        "ollama": getattr(Config, "LLM_MODEL_NAME", ""),
    }
    model = model_by_provider.get(provider, getattr(Config, "LLM_MODEL_NAME", "unknown"))
    return provider or "unknown", model or "unknown"


def _active_llm_provider_model(orchestrator):
    """Read the active LLM client provider/model when the orchestrator exposes it."""
    llm_client = getattr(getattr(orchestrator, "llm_service", None), "llm_client", None)
    if llm_client is None:
        return _configured_llm_provider_model()

    provider = getattr(llm_client, "provider", "") or "unknown"
    model_by_provider = {
        "google": getattr(llm_client, "google_model", ""),
        "groq": getattr(llm_client, "groq_model", ""),
        "openrouter": getattr(llm_client, "openrouter_model", ""),
        "ollama": getattr(llm_client, "ollama_model", ""),
    }
    model = model_by_provider.get(provider) or getattr(llm_client, "ollama_model", "") or "unknown"
    return provider, model


def _active_llm_finish_reason(orchestrator):
    """Read the latest LLM stream finish reason when available."""
    llm_client = getattr(getattr(orchestrator, "llm_service", None), "llm_client", None)
    return getattr(llm_client, "last_finish_reason", "UNKNOWN") if llm_client is not None else "UNKNOWN"


def _stream_finish_reason(stream):
    """Read finish reason metadata attached to a stream object."""
    if stream is None:
        return "UNKNOWN"
    reason = getattr(stream, "finish_reason", None)
    if reason:
        return reason
    metadata = getattr(stream, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get("finish_reason", "UNKNOWN")
    return "UNKNOWN"


def _normalize_finish_reason(reason) -> str:
    if reason is None:
        return "UNKNOWN"
    normalized = str(reason).strip().upper()
    mapping = {
        "STOP": "STOP",
        "FINISH_REASON_STOP": "STOP",
        "LENGTH": "MAX_TOKENS",
        "MAX_TOKEN": "MAX_TOKENS",
        "MAX_TOKENS": "MAX_TOKENS",
        "TOKEN_LIMIT": "MAX_TOKENS",
        "SAFETY": "SAFETY",
        "CONTENT_FILTER": "SAFETY",
        "RECITATION": "RECITATION",
        "LANGUAGE": "LANGUAGE",
        "ERROR": "ERROR",
        "UNKNOWN": "UNKNOWN",
        "BOUNDED_RESPONSE": "BOUNDED_RESPONSE",
    }
    return mapping.get(normalized, normalized if normalized in {"OTHER", "BOUNDED_RESPONSE"} else "OTHER")


def check_answer_completeness(
    answer: str,
    finish_reason: str | None,
    min_chars: int = 200,
    intent: str | None = None,
    query: str = "",
    sources=None,
    runtime_artifacts: dict | None = None,
) -> dict:
    """Deterministic stream and RAG answer completion check; no LLM calls."""
    text = str(answer or "").strip()
    reason = _normalize_finish_reason(finish_reason)
    chars = len(text)
    ends_with_sentence = _ends_with_sentence(text)
    mode = intent or "UNKNOWN"
    is_rag = mode == "FINANCIAL_RAG"
    is_lightweight_mode = mode in {"GREETING", "GENERAL_CHAT", "EARLY_EXIT", "TRASH"}
    source_terms = _source_reference_terms(sources or [])
    required_report_terms = _required_report_terms_for_query(query, sources)
    source_policy = _source_policy(runtime_artifacts)
    has_source_reference, detected_report_title = _has_source_reference(text, source_terms, required_report_terms)
    has_enough_structure = _has_enough_answer_structure(text)
    has_summary_or_conclusion = _has_summary_or_conclusion(text)
    task_coverage = _check_task_coverage(text, query, sources or [])
    format_status = "PASS"
    evidence_status = "UNKNOWN"
    contract_status = "UNKNOWN"
    evidence_reason = ""

    if runtime_artifacts and runtime_artifacts.get("is_bounded_response"):
        reason = "BOUNDED_RESPONSE"

    if runtime_artifacts:
        suff = runtime_artifacts.get("evidence_sufficiency")
        if suff:
            evidence_status = suff.get("status", "UNKNOWN").upper() if isinstance(suff, dict) else getattr(suff, "status", "UNKNOWN").upper()
            evidence_reason = ",".join(
                suff.get("missing_roles", []) or suff.get("warnings", []) or [] if isinstance(suff, dict) 
                else getattr(suff, "missing_roles", []) or getattr(suff, "warnings", []) or []
            )
        ce = runtime_artifacts.get("contract_evaluation")
        if ce:
            contract_status = ce.get("status", "UNKNOWN").upper() if isinstance(ce, dict) else getattr(ce, "status", "UNKNOWN").upper()
            result_reason_codes = ce.get("reason_codes", []) if isinstance(ce, dict) else getattr(ce, "reason_codes", [])
            repair_status = ce.get("repair_status", "NOT_ATTEMPTED") if isinstance(ce, dict) else getattr(ce, "repair_status", "NOT_ATTEMPTED")
        delivery_artifact = runtime_artifacts.get("answer_delivery_artifact")
    else:
        for source in sources or []:
            if isinstance(source, dict) and "metadata" in source:
                meta = source["metadata"]
                if meta.get("evidence_sufficiency_status"):
                    evidence_status = meta["evidence_sufficiency_status"].upper()
                if meta.get("evidence_reason"):
                    evidence_reason = meta["evidence_reason"]
                if meta.get("evidence_contract_status"):
                    contract_status = meta["evidence_contract_status"].upper()

    result = {
        "complete": False,
        "level": "fail",
        "mode": mode,
        "reason": "",
        "chars": chars,
        "ends_with_sentence": ends_with_sentence,
        "finish_reason": reason,
        "has_source_reference": has_source_reference,
        "source_policy": source_policy,
        "has_enough_bullets_or_sections": has_enough_structure,
        "has_summary_or_conclusion": has_summary_or_conclusion,
        "detected_report_title": detected_report_title,
        "task_coverage": task_coverage,
        "format_status": format_status,
        "evidence_status": evidence_status,
        "evidence_reason": evidence_reason,
        "coverage_status": "UNKNOWN",
        "claim_status": "UNKNOWN",
        "contract_status": contract_status,
        "agent_answer_compliance_status": "UNKNOWN",
        "overall_status": "UNKNOWN",
        "repair_status": repair_status if 'repair_status' in locals() else "NOT_ATTEMPTED",
        "reason_codes": result_reason_codes if 'result_reason_codes' in locals() else [],
    }

    if runtime_artifacts:
        selected_artifact = runtime_artifacts.get("final_answer_artifact") or {}
        selected_hash = selected_artifact.get("sha256") if isinstance(selected_artifact, dict) else None
        input_hash = _answer_sha256(answer)
        runtime_artifacts.setdefault(
            "completeness_input_artifact",
            {
                "chars": len(str(answer or "")),
                "sha256": input_hash,
                "matches_selected": (not selected_hash) or selected_hash == input_hash,
            },
        )
        artifacts_to_check = [
            runtime_artifacts.get("answer_delivery_artifact"),
            runtime_artifacts.get("completeness_input_artifact"),
            runtime_artifacts.get("memory_candidate_artifact"),
        ]
        for artifact in artifacts_to_check:
            if isinstance(artifact, dict) and artifact.get("matches_selected") is False:
                result["reason"] = "final_artifact_inconsistency"
                result["overall_status"] = "FAIL"
                return result
        if selected_hash and selected_hash != input_hash:
            result["reason"] = "final_artifact_inconsistency"
            result["overall_status"] = "FAIL"
            return result
    
    coverage_warnings = []
    if is_rag and runtime_artifacts:
        contracts = runtime_artifacts.get("answer_contracts", [])
        required_topics = set()
        for c in contracts:
            req_sec = c.get("required_sections", []) if isinstance(c, dict) else getattr(c, "required_sections", [])
            for sec in req_sec:
                required_topics.add(sec)
                
        if required_topics:
            from src.services.evidence.answer_coverage import AnswerCoverageValidator
            coverage_val = AnswerCoverageValidator.evaluate(text, list(required_topics))
            result["coverage_status"] = coverage_val.status
            if coverage_val.status != "PASS":
                if result["contract_status"] == "UNKNOWN":
                    result["contract_status"] = "WARN"
                coverage_warnings.extend(coverage_val.warnings)
                if not result["evidence_reason"]:
                    result["evidence_reason"] = ", ".join(coverage_val.warnings)
                else:
                    result["evidence_reason"] += "; " + ", ".join(coverage_val.warnings)
        
        cv = runtime_artifacts.get("claim_validation")
        if cv:
            result["claim_status"] = cv.get("status", "UNKNOWN").upper() if isinstance(cv, dict) else getattr(cv, "status", "UNKNOWN").upper()
        compliance = runtime_artifacts.get("agent_answer_compliance")
        if compliance:
            result["agent_answer_compliance_status"] = (
                compliance.get("status", "UNKNOWN").upper()
                if isinstance(compliance, dict)
                else getattr(compliance, "status", "UNKNOWN").upper()
            )


    if reason == "BOUNDED_RESPONSE":
        result["complete"] = True
        result["level"] = "pass"
        result["format_status"] = "PASS"
        result["evidence_status"] = evidence_status if evidence_status != "UNKNOWN" else "INSUFFICIENT"
        result["coverage_status"] = "UNKNOWN"
        result["contract_status"] = "PASS"
        result["overall_status"] = "PASS"
        result["reason"] = "bounded_pass"
        return result

    if not text:
        result["reason"] = "empty_answer"
        result["overall_status"] = "FAIL"
        return result
    if reason != "STOP" and not (is_lightweight_mode and reason == "UNKNOWN"):
        result["reason"] = f"finish_reason:{reason}"
        result["overall_status"] = "FAIL"
        return result

    if is_lightweight_mode:
        lightweight_min_chars = 20
        if chars < lightweight_min_chars:
            result["reason"] = f"too_short:{chars}<{lightweight_min_chars}"
            return result
        result["complete"] = True
        result["level"] = "pass"
        result["overall_status"] = "PASS"
        result["reason"] = "normal_stop_short_response"
        return result

    if chars < min_chars:
        result["reason"] = f"too_short:{chars}<{min_chars}"
        result["overall_status"] = "FAIL"
        return result
    if _ends_with_incomplete_connector(text):
        result["reason"] = "ends_with_incomplete_connector"
        result["overall_status"] = "FAIL"
        return result
    if not ends_with_sentence:
        result["reason"] = "missing_sentence_ending"
        result["overall_status"] = "FAIL"
        return result

    if is_rag:
        if chars < 300:
            result["reason"] = f"too_short:{chars}<300"
            result["format_status"] = "FAIL"
            result["overall_status"] = "FAIL"
            return result
        missing_required_report = _missing_required_report_reference(text, required_report_terms)
        if missing_required_report and _requires_named_source_reference(source_policy):
            result["reason"] = f"missing_required_report_reference:{missing_required_report}"
            result["format_status"] = "FAIL"
            result["overall_status"] = "FAIL"
            return result
        if not has_source_reference and _requires_named_source_reference(source_policy):
            result["reason"] = "missing_source_reference"
            result["format_status"] = "FAIL"
            result["overall_status"] = "FAIL"
            return result
        if not has_enough_structure:
            result["reason"] = "missing_rag_structure"
            result["format_status"] = "FAIL"
            result["overall_status"] = "FAIL"
            return result
        if task_coverage["total_tasks"] > 1 and task_coverage["missing_tasks"]:
            result["reason"] = f"missing_task_coverage:{','.join(task_coverage['missing_tasks'])}"
            result["format_status"] = "FAIL"
            result["overall_status"] = "FAIL"
            return result

        if evidence_status in {"FAIL", "INSUFFICIENT", "BLOCKED"}:
            result["reason"] = evidence_reason or "evidence_sufficiency_failed"
            result["overall_status"] = "FAIL"
            return result
        if contract_status == "FAIL":
            result["reason"] = "evidence_contract_failed"
            result["overall_status"] = "FAIL"
            return result
        if result["claim_status"] == "FAIL":
            result["reason"] = "claim_validation_failed"
            result["overall_status"] = "FAIL"
            return result
        if result["agent_answer_compliance_status"] == "FAIL":
            result["reason"] = "agent_answer_compliance_failed"
            result["overall_status"] = "FAIL"
            return result

        warnings = []
        if evidence_status in {"WARN", "DEGRADED"}:
            warnings.append(evidence_reason or "evidence_degraded")
        if result["coverage_status"] in {"WARN", "DEGRADED"}:
            warnings.extend(coverage_warnings if coverage_warnings else ["coverage_degraded"])
        if result["contract_status"] == "WARN":
            if result.get("reason_codes"):
                warnings.extend(result["reason_codes"])
            else:
                warnings.append("contract_degraded")
        if result["agent_answer_compliance_status"] == "WARN":
            warnings.append("agent_answer_compliance_warn")
        if chars < 600:
            warnings.append("short_rag_answer")
            result["format_status"] = "WARN"
        if not has_summary_or_conclusion:
            warnings.append("missing_summary_or_conclusion")
            result["format_status"] = "WARN"
        if warnings:
            result["complete"] = True
            result["level"] = "warn"
            result["overall_status"] = "WARN"
            result["reason"] = ",".join(warnings)
            return result

    result["complete"] = True
    result["level"] = "pass"
    result["overall_status"] = "PASS"
    result["reason"] = "normal_stop"
    return result


def _log_answer_completeness(request_id: str, result: dict | None):
    if not result:
        return
    status = result.get("level", "fail").upper()
    print(
        f"[AnswerCompleteness] {status} "
        f"request_id={request_id} "
        f"mode={result.get('mode', 'UNKNOWN')} "
        f"reason={_sanitize_log_value(result['reason'], 120)} "
        f"chars={result['chars']} "
        f"finish_reason={result['finish_reason']} "
        f"ends_with_sentence={str(result['ends_with_sentence']).lower()} "
        f"has_source_reference={str(result.get('has_source_reference', False)).lower()} "
        f"source_policy={result.get('source_policy', 'unknown')} "
        f"has_enough_structure={str(result.get('has_enough_bullets_or_sections', False)).lower()} "
        f"has_summary_or_conclusion={str(result.get('has_summary_or_conclusion', False)).lower()} "
        f"detected_report_title={_sanitize_log_value(result.get('detected_report_title') or '', 80)} "
        f"task_coverage={result.get('task_coverage', {}).get('answered_tasks', 0)}/{result.get('task_coverage', {}).get('total_tasks', 0)} "
        f"format_status={result.get('format_status', 'UNKNOWN')} "
        f"evidence_status={result.get('evidence_status', 'UNKNOWN')} "
        f"coverage_status={result.get('coverage_status', 'UNKNOWN')} "
        f"claim_status={result.get('claim_status', 'UNKNOWN')} "
        f"contract_status={result.get('contract_status', 'UNKNOWN')} "
        f"agent_answer_compliance_status={result.get('agent_answer_compliance_status', 'UNKNOWN')} "
        f"overall_status={result.get('overall_status', 'UNKNOWN')}"
    )


def _ends_with_sentence(text: str) -> bool:
    return bool(text.rstrip().endswith((".", "!", "?", "…", "。", "！", "？")))


def _ends_with_incomplete_connector(text: str) -> bool:
    stripped = re.sub(r"[\s\.,;:!\?…。！？]+$", "", str(text or "").lower())
    connectors = (
        "vì",
        "nhưng",
        "bao gồm",
        "gồm",
        "như",
        "là",
        "và",
        "hoặc",
        "cụ thể",
        "for example",
        "such as",
        "including",
        "because",
        "and",
        "or",
    )
    return any(stripped == connector or stripped.endswith(f" {connector}") for connector in connectors)


def _ends_with_sentence(text: str) -> bool:
    stripped = _strip_trailing_symbols_for_sentence(text)
    return bool(stripped.endswith((".", "!", "?", "...", ".)", ".'", ".”", "’", "…", "。", "！", "？")))


def _strip_trailing_symbols_for_sentence(text: str) -> str:
    stripped = str(text or "").rstrip()
    while stripped:
        last = stripped[-1]
        category = unicodedata.category(last)
        if category.startswith("S") or category in {"Mn", "Me"}:
            stripped = stripped[:-1].rstrip()
            continue
        break
    return stripped


def _semantic_terminal_text(text: str) -> str:
    """Return validation-only text with harmless trailing presentation markers removed."""
    stripped = str(text or "").rstrip()
    if not stripped:
        return ""

    closing_tag = re.compile(r"(?:</(?:em|strong|b|i|code|span)>)+\s*$", re.IGNORECASE)
    while True:
        before = stripped
        stripped = closing_tag.sub("", stripped).rstrip()
        stripped = _strip_trailing_symbols_for_sentence(stripped)
        while stripped and stripped[-1] in "*_`~)]}'\"”’":
            stripped = stripped[:-1].rstrip()
            stripped = _strip_trailing_symbols_for_sentence(stripped)
        if stripped == before:
            return stripped


def _ends_with_sentence(text: str) -> bool:
    stripped = _semantic_terminal_text(text)
    return bool(stripped.endswith((".", "!", "?", "...", "…", "。", "！", "？")))


def _ends_with_incomplete_connector(text: str) -> bool:
    stripped = re.sub(r"[\s\.,;:!\?…。！？]+$", "", _normalize_text_for_match(text))
    connectors = (
        "vi",
        "nhung",
        "bao gom",
        "gom",
        "nhu",
        "la",
        "va",
        "hoac",
        "vi du",
        "for example",
        "such as",
        "including",
        "because",
        "but",
        "and",
        "or",
        "which",
        "that",
    )
    if _ends_with_unfinished_specific_pattern(text):
        return True
    return any(stripped == connector or stripped.endswith(f" {connector}") for connector in connectors)


def _ends_with_unfinished_specific_pattern(text: str) -> bool:
    normalized = _normalize_text_for_match(text)
    compact = re.sub(r"\s+", " ", normalized).strip()
    explicit_openers = (
        "cu the:",
        "cu the la",
        "cu the gom",
        "cu the bao gom",
        "vi du:",
    )
    return any(compact.endswith(opener) for opener in explicit_openers)


def _normalize_text_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _check_task_coverage(answer: str, query: str, sources) -> dict:
    tasks = _split_query_tasks(query)
    if len(tasks) <= 1:
        return {
            "total_tasks": len(tasks) or 1,
            "answered_tasks": len(tasks) or 1,
            "grounded_tasks": len(tasks) or 1,
            "missing_tasks": [],
            "partially_answered_tasks": [],
        }

    answer_text = _normalize_text_for_match(answer)
    source_text = _normalize_text_for_match(" ".join(_source_reference_terms(sources or [])))
    evidence_text = f"{answer_text} {source_text}".strip()
    missing_tasks = []
    partial_tasks = []
    answered = 0
    grounded = 0

    for index, task in enumerate(tasks, start=1):
        groups = _task_term_groups(task)
        task_id = f"task_{index}"
        if not groups:
            groups = [[_normalize_text_for_match(task)[:40]]]
        task_answered = all(any(term and term in answer_text for term in group) for group in groups)
        if task_answered and _task_denies_coverage(task, answer_text):
            task_answered = False
        task_grounded = task_answered and all(any(term and term in evidence_text for term in group) for group in groups)
        if task_answered:
            answered += 1
        else:
            missing_tasks.append(task_id)
        if task_grounded:
            grounded += 1
        elif task_answered:
            partial_tasks.append(task_id)

    return {
        "total_tasks": len(tasks),
        "answered_tasks": answered,
        "grounded_tasks": grounded,
        "missing_tasks": missing_tasks,
        "partially_answered_tasks": partial_tasks,
    }


def _split_query_tasks(query: str) -> list[str]:
    raw_parts = re.split(r"(?:\n+|[?？]+|\d+[\.)]\s+)", str(query or ""))
    return [part.strip() for part in raw_parts if len(part.strip()) >= 6]


def _task_term_groups(task: str) -> list[list[str]]:
    normalized = _normalize_text_for_match(task)
    groups = []
    if "cpi" in normalized or "inflation" in normalized or "lam phat" in normalized:
        groups.append(["cpi", "us cpi report", "bls", "inflation", "lam phat"])
    if any(term in normalized for term in ["xauusd", "gold", "vang"]):
        groups.append(["xauusd", "gold", "vang"])
    if any(term in normalized for term in ["hien tai", "current", "right now", "tac dong", "driver", "yeu to"]):
        groups.append([
            "hien tai",
            "current",
            "right now",
            "realtime",
            "live",
            "gia live",
            "du lieu gia",
            "ohlcv",
            "market snapshot",
            "trong ngay",
        ])

    author_terms = {
        "al brooks": ["al brooks", "price action", "bar by bar"],
        "anna coulling": ["anna coulling", "volume", "vpa"],
        "van tharp": ["van tharp", "position sizing", "r multiple", "risk"],
        "mark douglas": ["mark douglas", "discipline", "psychology"],
        "john murphy": ["john murphy", "moving average", "indicator", "technical"],
        "michael covel": ["michael covel", "trend following"],
    }
    for author, terms in author_terms.items():
        if author in normalized:
            groups.append([author])
            groups.append(terms)
    return groups


def _task_denies_coverage(task: str, answer_text: str) -> bool:
    normalized_task = _normalize_text_for_match(task)
    asks_current_market = any(
        term in normalized_task
        for term in ["hien tai", "current", "right now", "driver", "yeu to", "tac dong"]
    ) and any(term in normalized_task for term in ["xauusd", "gold", "vang"])
    if not asks_current_market:
        return False

    denial_patterns = (
        "khong xem du lieu gia live",
        "khong co du lieu live",
        "khong co gia realtime",
        "khong co du lieu realtime",
        "chua co du lieu live",
        "chua co gia realtime",
        "khong phai du lieu thi truong realtime",
        "khong du de tra loi toan bo",
        "chua du de tra loi toan bo",
    )
    return any(pattern in answer_text for pattern in denial_patterns)


def _source_reference_terms(sources) -> list[str]:
    terms = [
        "theo bao cao",
    ]
    for src in sources:
        metadata = src.get("metadata", {}) if isinstance(src, dict) and isinstance(src.get("metadata"), dict) else {}
        for key in ("title", "organization", "author", "source"):
            value = metadata.get(key) or (src.get(key) if isinstance(src, dict) else None)
            if value:
                terms.append(str(value))
    return _dedupe_terms(terms)


def _required_report_terms_for_query(query: str, sources: list = None) -> dict[str, list[str]]:
    q = _normalize_text_for_match(query)
    cases = {
        "Commodity Markets Outlook": (("commodity markets outlook", "commodity outlook", "commodities", "hang hoa", "commodity market"), ["commodity markets outlook", "world bank"]),
        "Gold Market Commentary": (("gold market report", "gold market commentary", "world gold council", "wgc"), ["gold market commentary", "world gold council"]),
        "US GDP Report": (("gdp",), ["us gdp report", "bea"]),
        "World Economic Outlook": (("world economic outlook",), ["world economic outlook", "imf"]),
        "US CPI Report": (("cpi",), ["us cpi report", "bls"]),
        "US Nonfarm Payrolls": (("nfp", "nonfarm payroll", "nonfarm payrolls"), ["us nonfarm payrolls", "bls"]),
        "FOMC": (("fomc",), ["fomc statement", "fomc minutes", "summary of economic projections", "federal reserve"]),
    }
    for label, (triggers, accepted_terms) in cases.items():
        if any(trigger in q for trigger in triggers):
            return {label: accepted_terms}
    return {}


def _missing_required_report_reference(answer: str, required_terms: dict[str, list[str]]) -> str | None:
    if not required_terms:
        return None
    answer_text = _normalize_text_for_match(answer)
    for label, accepted_terms in required_terms.items():
        if not any(_normalize_text_for_match(term) in answer_text for term in accepted_terms):
            return label
    return None


def _source_policy(runtime_artifacts: dict | None) -> str:
    """Choose provenance validation policy from the final answer contract."""
    contracts = []
    if runtime_artifacts:
        contracts = runtime_artifacts.get("answer_contracts", []) or []
    required_refs = []
    required_roles = set()
    answer_types = set()
    named_source_roles = {
        "direct_book_passage",
        "book_passage",
        "static_knowledge",
        "official_report",
        "official_report_passage",
        "market_commentary_passage",
    }
    dynamic_roles = {
        "market_snapshot",
        "ohlcv",
        "ohlcv_summary",
        "technical_snapshot",
        "economic_event",
        "economic_event_record",
    }

    for contract in contracts:
        if isinstance(contract, dict):
            required_refs.extend(contract.get("required_source_refs", []) or [])
            required_roles.update(contract.get("required_evidence_roles", []) or [])
            answer_types.add(str(contract.get("answer_type", "") or ""))
        else:
            required_refs.extend(getattr(contract, "required_source_refs", []) or [])
            required_roles.update(getattr(contract, "required_evidence_roles", []) or [])
            answer_types.add(str(getattr(contract, "answer_type", "") or ""))

    if required_roles & named_source_roles:
        return "named_source_required"
    if required_roles and required_roles <= dynamic_roles:
        return "dynamic_provenance"
    if "market_analysis" in answer_types and not required_refs:
        return "dynamic_provenance"
    if required_refs:
        return "named_source_required"
    return "named_source_required"


def _requires_named_source_reference(source_policy: str) -> bool:
    return source_policy in {"named_source_required", "static_named_source", "official_report_source"}


def _has_source_reference(answer: str, source_terms: list[str], required_terms: dict[str, list[str]]):
    answer_text = _normalize_text_for_match(answer)
    for label, accepted_terms in required_terms.items():
        for term in accepted_terms:
            normalized = _normalize_text_for_match(term)
            if normalized and normalized in answer_text:
                return True, label
    for term in source_terms:
        normalized = _normalize_text_for_match(term)
        if normalized and normalized in answer_text:
            return True, term
    return False, None


def _has_enough_answer_structure(answer: str) -> bool:
    lines = [line.strip() for line in str(answer or "").splitlines() if line.strip()]
    bullet_count = sum(1 for line in lines if re.match(r"^[-*•]\s+", line))
    numbered_count = sum(1 for line in lines if re.match(r"^\d+[\.\)]\s+", line))
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", str(answer or "")) if len(part.strip()) >= 80]
    return bullet_count >= 2 or numbered_count >= 2 or len(paragraphs) >= 3


def _has_summary_or_conclusion(answer: str) -> bool:
    text = _normalize_text_for_match(answer)
    markers = (
        "tom lai",
        "ket luan",
        "noi ngan gon",
        "nhin chung",
        "do do",
        "vi vay",
        "overall",
        "in short",
        "in summary",
        "conclusion",
        "therefore",
    )
    return any(marker in text for marker in markers)


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen = set()
    result = []
    for term in terms:
        normalized = _normalize_text_for_match(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(str(term))
    return result


def _coerce_stream_text(chunk) -> str:
    """Best-effort text extraction for stats while preserving original chunks."""
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return str(chunk)


def _answer_sha256(answer: str) -> str:
    return hashlib.sha256(str(answer or "").encode("utf-8", errors="ignore")).hexdigest()


def _build_answer_delivery_artifact(canonical_answer: str, display_answer: str | None = None, selected_artifact: dict | None = None) -> dict:
    """Represent semantic delivery identity separately from optional display cleanup."""
    canonical_text = str(canonical_answer or "")
    display_text = canonical_text if display_answer is None else str(display_answer or "")
    canonical_hash = _answer_sha256(canonical_text)
    display_hash = _answer_sha256(display_text)
    selected_hash = (selected_artifact or {}).get("sha256") if isinstance(selected_artifact or {}, dict) else None
    return {
        "chars": len(canonical_text),
        "sha256": canonical_hash,
        "canonical_chars": len(canonical_text),
        "canonical_sha256": canonical_hash,
        "display_chars": len(display_text),
        "display_sha256": display_hash,
        "presentation_transformed": canonical_text != display_text,
        "matches_selected": (not selected_hash) or selected_hash == canonical_hash,
    }


def _sanitize_log_value(value, limit: int | None = None) -> str:
    """Keep logs single-line and bounded."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit] if limit is not None else text


def _sanitize_user_facing_answer(answer: str) -> str:
    """Remove internal document identifiers from answer text before storage."""
    text = str(answer or "")
    text = re.sub(
        r"\s*\(?\s*(?:Doc\s*ID|doc_id)\s*[:：]\s*[A-Za-z0-9_.:/\\-]+(?:\s*\))?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(?:report|book)_[a-z0-9][a-z0-9_]*_v\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _render_badge(intent: str):
    """Render intent badge."""
    badge_map = {
        "COMPUTATIONAL_SPECIFICATION": ("badge-rag", "SPECIFICATION REVIEW"),
        "RESEARCH_BRIEF": ("badge-rag", "RESEARCH BRIEF"),
        "FINANCIAL_RAG": ("badge-rag", "RAG PIPELINE"),
        "TRASH": ("badge-trash", "NGOAI PHAM VI"),
        "GREETING": ("badge-greet", "GREETING"),
        "ERROR": ("badge-trash", "ERROR"),
    }
    cls, label = badge_map.get(intent, ("badge-rag", "RAG"))
    return f'<span class="badge {cls}">{label}</span>'


def _extract_metrics(text: str):
    """Extract Entry/SL/TP numbers from an answer for optional chart rendering."""
    metrics = {}
    for label in ["Entry", "SL", "TP", "Stop Loss", "Take Profit"]:
        pattern = rf"{label}[:\s]*[\$]?([\d,]+\.?\d*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            key = label.replace("Stop Loss", "SL").replace("Take Profit", "TP").split()[-1]
            try:
                metrics[key] = float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return metrics


def _render_trade_chart(metrics: dict):
    """Render a compact Plotly position chart when Entry/SL/TP are present."""
    if not _HAS_PLOTLY:
        return
    if not all(key in metrics for key in ["Entry", "SL", "TP"]):
        return

    entry = metrics["Entry"]
    sl = metrics["SL"]
    tp = metrics["TP"]
    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
    is_long = tp > entry

    fig = go.Figure()
    fig.add_hrect(
        y0=sl,
        y1=entry,
        fillcolor="rgba(239,68,68,0.15)",
        line_width=0,
        annotation_text="SL Zone",
        annotation_position="right",
    )
    fig.add_hrect(
        y0=entry,
        y1=tp,
        fillcolor="rgba(34,197,94,0.15)",
        line_width=0,
        annotation_text="TP Zone",
        annotation_position="right",
    )

    for y, color, name, dash in [
        (entry, "#60a5fa", f"Entry: {entry:,.1f}", "solid"),
        (sl, "#f87171", f"SL: {sl:,.1f}", "dash"),
        (tp, "#4ade80", f"TP: {tp:,.1f}", "dash"),
    ]:
        fig.add_hline(
            y=y,
            line_color=color,
            line_dash=dash,
            line_width=2,
            annotation_text=name,
            annotation_position="left",
            annotation_font_color=color,
        )

    direction = "LONG" if is_long else "SHORT"
    fig.update_layout(
        title=f"So do vi the - {direction} | R:R = 1:{rr:.1f}",
        yaxis_title="Gia XAUUSD (USD/oz)",
        xaxis_visible=False,
        height=320,
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="Inter"),
        title_font_size=14,
        margin=dict(l=10, r=120, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_sources(sources, intent: str | None = None, query: str = ""):
    """Render source cards for retrieved documents."""
    if not sources:
        return
    mode = _source_panel_mode(sources)
    has_official_report = _has_official_report_source(sources)
    print(
        "[SourcePanel] "
        f"rendered_sources={len(sources)} "
        f"mode={mode} "
        f"has_official_report={str(has_official_report).lower()}"
    )
    with st.expander(f"Tai lieu doi chieu ({len(sources)} nguon)"):
        if _should_show_static_data_notice(sources, intent):
            for notice in _static_data_notice_lines(query):
                st.caption(notice)
        for i, src in enumerate(sources, 1):
            source_name, doc_type, text_preview, score = _normalize_source_for_display(src)
            detail_lines = _source_metadata_lines(src)
            source_name = html.escape(str(source_name))
            doc_type_label = f" <em>({html.escape(str(_friendly_source_type(src) or doc_type))})</em>" if (doc_type or _friendly_source_type(src)) else ""
            text_preview = html.escape(str(text_preview))
            details_html = "<br>".join(html.escape(line) for line in detail_lines)
            if details_html:
                details_html = f'<div class="source-meta">{details_html}</div>'
            st.markdown(
                f'<div class="source-card">'
                f'<strong>#{i} {source_name}</strong>{doc_type_label} '
                f'<span style="color:#68d391">score {score:.3f}</span>'
                f'{details_html}<br>'
                f'{text_preview}...'
                f'</div>',
                unsafe_allow_html=True,
            )


def _normalize_source_for_display(src: dict):
    """Support V3 metadata, current reranker docs, and older legacy source payloads."""
    metadata = src.get("metadata", {}) if isinstance(src.get("metadata"), dict) else {}
    title = metadata.get("title") or metadata.get("source") or src.get("source") or src.get("file_name")
    author = metadata.get("author") or ""
    organization = metadata.get("organization") or ""
    display_owner = organization if organization and (metadata.get("knowledge_type") == "report" or not author) else author
    page = metadata.get("page")
    chapter = metadata.get("chapter")
    location = metadata.get("location")

    if title and display_owner:
        source_name = f"{title} - {display_owner}"
    else:
        source_name = title or "Tai lieu he thong"
    if page not in {None, ""}:
        source_name = f"{source_name} (p. {page})"
    elif chapter:
        source_name = f"{source_name} ({chapter})"
    elif location:
        source_name = f"{source_name} ({location})"

    doc_type = metadata.get("doc_type") or src.get("doc_type") or ""
    text = (
        src.get("content")
        or src.get("parent_text")
        or src.get("child_text")
        or src.get("text")
        or ""
    )
    score = src.get("rerank_score", src.get("score", 0.0))

    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0

    return source_name, doc_type, text[:300], score


def _friendly_source_type(src: dict) -> str:
    """Return a user-facing source type without exposing internal schema details."""
    metadata = src.get("metadata", {}) if isinstance(src, dict) and isinstance(src.get("metadata"), dict) else {}
    top_level_doc_type = src.get("doc_type") if isinstance(src, dict) else ""
    knowledge_type = str(metadata.get("knowledge_type") or "").strip().lower()
    document_type = str(metadata.get("document_type") or metadata.get("doc_type") or top_level_doc_type or "").strip().lower()

    if knowledge_type == "report":
        return "Official report" if str(metadata.get("source_tier", "")).lower() == "tier1" else "Report"
    if knowledge_type == "book" or document_type in {"book", "epub"}:
        return "Book"
    if document_type == "pdf":
        return "PDF"
    return ""


def _source_panel_mode(sources) -> str:
    modes = []
    for src in sources or []:
        metadata = src.get("metadata", {}) if isinstance(src, dict) and isinstance(src.get("metadata"), dict) else {}
        mode = metadata.get("retrieval_mode")
        if mode:
            modes.append(str(mode))
    unique_modes = sorted(set(modes))
    return unique_modes[0] if len(unique_modes) == 1 else ("mixed" if unique_modes else "unknown")


def _has_official_report_source(sources) -> bool:
    for src in sources or []:
        metadata = src.get("metadata", {}) if isinstance(src, dict) and isinstance(src.get("metadata"), dict) else {}
        if metadata.get("knowledge_type") == "report" and str(metadata.get("source_tier", "")).lower() == "tier1":
            return True
    return False


def _should_show_static_data_notice(sources, intent: str | None) -> bool:
    if intent != "FINANCIAL_RAG":
        return False
    for src in sources or []:
        metadata = src.get("metadata", {}) if isinstance(src, dict) and isinstance(src.get("metadata"), dict) else {}
        if metadata.get("collection") == "knowledge_current" or metadata.get("retrieval_mode") == "v3":
            return True
        if metadata.get("knowledge_type") in {"book", "report"}:
            return True
    return False


def _static_data_notice_lines(query: str = "") -> list[str]:
    lines = [
        "Dữ liệu trên được trích từ tài liệu đã ingest trong Knowledge V3, không phải dữ liệu thị trường realtime."
    ]
    if _is_trading_impact_query(query):
        lines.append(
            "Để ra quyết định giao dịch thực tế, cần kết hợp thêm giá realtime, forecast/consensus, previous revision, DXY, lợi suất trái phiếu và tin tức hiện tại."
        )
    return lines


def _is_trading_impact_query(query: str = "") -> bool:
    normalized = _normalize_text_for_match(query)
    triggers = (
        "anh huong",
        "impact",
        "market",
        "thi truong",
        "vang",
        "gold",
        "xauusd",
        "usd",
        "dxy",
        "yield",
        "loi suat",
        "entry",
        "sl",
        "tp",
        "giao dich",
    )
    return any(trigger in normalized for trigger in triggers)


def _source_metadata_lines(src: dict):
    """Build readable source metadata lines without changing the source shape."""
    metadata = src.get("metadata", {}) if isinstance(src.get("metadata"), dict) else {}
    lines = []

    title = metadata.get("title") or metadata.get("source") or src.get("source") or src.get("file_name")
    author = metadata.get("author")
    organization = metadata.get("organization")
    page = metadata.get("page")
    chapter = metadata.get("chapter")
    section = metadata.get("section")
    location = metadata.get("location")
    spine_index = metadata.get("spine_index")
    href = metadata.get("href")
    domain = metadata.get("domain")
    subdomain = metadata.get("subdomain")
    source_tier = metadata.get("source_tier")
    doc_type = metadata.get("doc_type") or src.get("doc_type")
    retrieval_mode = metadata.get("retrieval_mode")
    collection = metadata.get("collection")
    event_type = metadata.get("event_type")
    published_date = metadata.get("published_date")
    period = metadata.get("period")
    country = metadata.get("country")
    asset_focus = metadata.get("asset_focus")
    source_role = metadata.get("source_role")
    source_usage_reasons = metadata.get("source_usage_reasons")
    grounding_status = metadata.get("answer_grounding_status")

    if title:
        lines.append(f"Title: {title}")
    if author:
        lines.append(f"Author: {author}")
    if organization:
        lines.append(f"Organization: {organization}")
    source_type = _friendly_source_type(src)
    if source_type:
        lines.append(f"Type: {source_type}")
    if source_role:
        lines.append(f"Used as: {_friendly_source_role(source_role)}")
    if source_usage_reasons:
        if isinstance(source_usage_reasons, list):
            reason_text = ", ".join(_friendly_source_reason(reason) for reason in source_usage_reasons)
        else:
            reason_text = _friendly_source_reason(str(source_usage_reasons))
        lines.append(f"Why used: {reason_text}")
    if grounding_status:
        lines.append(f"Grounding: {grounding_status}")
    if page not in {None, ""}:
        lines.append(f"Page: {page}")
    if chapter:
        lines.append(f"Chapter: {chapter}")
    if section:
        lines.append(f"Section: {section}")
    if location:
        lines.append(f"Location: {location}")
    if spine_index not in {None, ""}:
        lines.append(f"Spine index: {spine_index}")
    if href:
        lines.append(f"Href: {href}")
    if domain or subdomain:
        routing = f"{domain or ''}/{subdomain or ''}".strip("/")
        lines.append(f"Domain: {routing}")
    if event_type:
        lines.append(f"Event type: {event_type}")
    if published_date:
        lines.append(f"Published date: {published_date}")
    if period:
        lines.append(f"Period: {period}")
    if country:
        lines.append(f"Country: {country}")
    if asset_focus:
        lines.append(f"Asset focus: {asset_focus}")
    if source_tier:
        lines.append(f"Source tier: {source_tier}")
    if doc_type and not source_type:
        lines.append(f"Doc type: {doc_type}")
    if retrieval_mode:
        lines.append(f"Retrieval mode: {retrieval_mode}")
    if collection:
        lines.append(f"Collection: {collection}")

    return lines


def _friendly_source_role(role: str) -> str:
    mapping = {
        "primary_source": "Primary source",
        "supporting_source": "Supporting source",
        "retrieved_context": "Retrieved context",
    }
    return mapping.get(str(role), str(role).replace("_", " ").title())


def _friendly_source_reason(reason: str) -> str:
    mapping = {
        "primary_source": "primary source",
        "supporting_source": "supporting source",
        "official_report": "official report",
        "matched_author_or_organization": "matched author/organization",
        "matched_event_type": "matched event type",
        "matched_domain": "matched domain",
        "matched_subdomain": "matched subdomain",
    }
    return mapping.get(str(reason), str(reason).replace("_", " "))

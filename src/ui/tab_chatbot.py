"""Chatbot tab UI.

This module renders chat messages, delegates business logic to the orchestrator,
and displays retrieved sources. It does not call V3 services, Qdrant, Cohere,
or catalog code directly.
"""

import hashlib
import html
import re
import time
import unicodedata
import uuid

import streamlit as st

try:
    import plotly.graph_objects as go

    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

from src.config import Config
from src.ui.runtime_flags import get_knowledge_v3_flags


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
    knowledge_v3_flags = get_knowledge_v3_flags(st.session_state)
    if knowledge_v3_flags["use_knowledge_v3"]:
        st.warning("Knowledge V3 experimental retrieval enabled")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "intent" in msg:
                st.markdown(_render_badge(msg["intent"]), unsafe_allow_html=True)
            st.markdown(msg["content"])

            if msg["role"] == "assistant":
                _render_sources(msg.get("sources", []), intent=msg.get("intent"))
                metrics = _extract_metrics(msg["content"])
                if metrics:
                    _render_trade_chart(metrics)

    if user_query := st.chat_input("Hoi ve xu huong vang, chien luoc SMC, du lieu vi mo..."):
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

                metrics = _extract_metrics(full_answer)
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
        st.session_state.messages.append(assistant_msg)
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
                return
            HistoryService().append_message(st.session_state.current_session_id, assistant_msg)
            quality = "DEGRADED" if completion_result and completion_result["level"] == "warn" else "PASS"
            print(f"[MemoryPolicy] answer_quality={quality} action=stored_with_quality_flag")
        else:
            request_id = stream_logger.request_id if stream_logger is not None else "unknown"
            reason = completion_result["reason"] if completion_result else "stream_error"
            print(f"[MemoryPolicy] answer_quality=FAIL action=skip reason={reason}")


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


def _evidence_status_for_sources(sources) -> tuple[str, str]:
    statuses = []
    reasons = []
    for source in sources or []:
        metadata = source.get("metadata", {}) if isinstance(source, dict) else {}
        evidence_status = (
            metadata.get("evidence_status")
            or metadata.get("evidence_sufficiency_status")
            or metadata.get("evidence_contract_status")
        )
        if evidence_status:
            statuses.append(str(evidence_status).upper())
        reason = metadata.get("evidence_reason") or metadata.get("evidence_warning")
        if reason:
            reasons.append(str(reason))
    if any(status in {"FAIL", "INSUFFICIENT", "BLOCKED"} for status in statuses):
        return "FAIL", reasons[0] if reasons else "evidence_sufficiency_failed"
    if any(status in {"WARN", "DEGRADED"} for status in statuses):
        return "WARN", reasons[0] if reasons else "evidence_degraded"
    return "PASS", ""


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

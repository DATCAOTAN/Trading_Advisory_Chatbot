"""
Tab Dashboard — Isolated Component: Bảng theo dõi trạng thái hệ thống & dữ liệu thời gian thực.

Component-Based Architecture:
  - Hiển thị: trạng thái Qdrant, giá live, lịch kinh tế, thống kê kho tri thức.
  - Giao tiếp với orchestrator qua dependency injection (tham số).
  - Có thể rút bỏ hoàn toàn mà không ảnh hưởng tab Chatbot hay Settings.
"""

import streamlit as st
from src.config import Config


import json
import secrets
from datetime import datetime, timezone
import streamlit as st
from src.config import Config
from src.services.trading.calendar import CalendarContextBuilder
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    ManualOperatorProposalInput,
    operator_timeframe_profile,
)
from src.services.trading.decision.autonomous_runtime import AutonomousMonitorProcess
from src.services.trading.execution import (
    DryRunConfirmationService,
    ExecutionAdapterRegistry,
    ExecutionJournalStore,
    LiveExecutionBlockJournalStore,
    LiveExecutionPreflightReportStore,
    LiveExecutionPreflightService,
    LiveOrderContractSkeletonJournalStore,
    LiveOrderContractSkeletonService,
    LiveOrderIntentJournalStore,
    LiveOrderIntentService,
    LiveOrderParameterPolicyJournalStore,
    LiveOrderParameterPolicyService,
    LiveOrderParameterSourceBoundaryService,
    LiveOrderParameterSourceJournalStore,
    HumanReviewedLiveParameterDraftJournalStore,
    HumanReviewedLiveParameterDraftService,
    ControlledLiveParameterValueProposalJournalStore,
    ControlledLiveParameterValueProposalService,
    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    HumanValueApprovalLockJournalStore,
    HumanValueApprovalLockService,
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    LiveOrderContractFinalReviewJournalStore,
    LiveOrderContractFinalReviewService,
    LiveOrderContractParameterizationJournalStore,
    LiveOrderContractParameterizationService,
    LivePermissionGateService,
    LivePermissionJournalStore,
    LivePermissionPolicy,
    MT5ExecutionSkeletonService,
    MT5DryRunPayloadValidationJournalStore,
    MT5OrderRequestDryRunPayloadValidationService,
    MT5RequestDraftJournalStore,
    MT5RequestDraftService,
    MT5RequestDraftFinalApprovalJournalStore,
    MT5RequestDraftFinalApprovalService,
    MT5RequestDictDryRunBuilderJournalStore,
    MT5RequestDictDryRunBuilderService,
    MT5RequestDictFinalValidationJournalStore,
    MT5RequestDictFinalValidationService,
    MT5BridgeWriteSkeletonService,
    MT5LiveAdapterPreSubmitService,
    MT5PreSubmitJournalStore,
    PreMT5OrderRequestMappingJournalStore,
    PreMT5OrderRequestMappingService,
    SimulatedExecutionJournalStore,
    SimulatedExecutionService,
)
from src.services.trading.execution.live_design import (
    LiveExecutionDesignReportStore,
    LiveExecutionDesignSpecService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_artifact_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    PendingArtifactExportError,
    write_pending_candidate_handoff,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    MandateGrantCommand,
    TradingAuthorityOperatorService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.decision.autonomous_candidate_monitor import (
    DEFAULT_MONITOR_JOURNAL_PATH,
    AutonomousCandidateMonitorError,
    AutonomousCandidateMonitorJournal,
    monitor_profile_id,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionJournal,
    AutonomousDecisionJournalError,
    AutonomousDecisionOrchestrator,
)
from src.services.trading.market.live_feature_service import LiveFeatureService
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.regime_detector import MarketRegimeDetector
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.proposal import (
    HumanProposalConfirmationService,
    ProposalBoundaryFormatter,
    ProposalBoundaryPolicy,
    ProposalDraftJournalStore,
    ProposalDraftService,
    ProposalIntentJournalStore,
)
from src.ui.autonomous_candidate_review import (
    OperatorCandidateReviewController,
    get_autonomous_decision_run_result,
    clear_autonomous_decision_run_result,
    render_autonomous_candidate_review_card,
    render_autonomous_candidate_confirmation_controls,
    render_reasoning_evidence_summary,
)
from src.ui.operator_candidate_generation import (
    OperatorCandidateGenerationController,
)


@st.cache_data(ttl=5)
def load_tracker_state():
    """Đọc Ingestion State từ ổ cứng và cache lại để tránh nghẽn luồng Stream."""
    if Config.INGESTION_STATE_FILE.exists():
        try:
            with open(Config.INGESTION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                files = data.get("files", {})
                print(f"📋 [Tracker Cache] Đã load state: {len(files)} file vào RAM.")
                return files
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

# =============================================================================
# PUBLIC API — Được gọi từ app.py Main Shell
# =============================================================================
def render(orchestrator):
    """
    Render toàn bộ giao diện Dashboard trong tab hiện tại.

    Args:
        orchestrator: RAGOrchestrator instance (dependency injection)
    """
    st.markdown("### 📊 Dashboard Tổng Quan")
    st.markdown("---")

    # ── Hàng 1: Trạng thái hệ thống AI ──────────────────────────────────
    st.markdown("#### 🤖 Trạng Thái Hệ Thống AI")
    col1, col2, col3, col4 = st.columns(4)

    embedding_model_name = "Cohere Embed (v3.0)" if Config.COHERE_API_KEY else "BGE-M3 (Local)"

    if Config.LLM_PROVIDER == "openrouter":
        active_llm_name = Config.OPENROUTER_MODEL_NAME
    elif Config.LLM_PROVIDER == "google":
        active_llm_name = Config.GOOGLE_MODEL_NAME
    elif Config.LLM_PROVIDER == "groq":
        active_llm_name = Config.GROQ_MODEL_NAME
    else:
        active_llm_name = Config.LLM_MODEL_NAME

    col1.metric("🧠 LLM", active_llm_name, help="Mô hình ngôn ngữ chính")
    col2.metric("📐 Embedding", embedding_model_name, help="Mô hình nhúng vector 1024d")
    col3.metric("🎯 Reranker", "Cohere API" if Config.ENABLE_RERANKER else "Tắt", help="Chấm điểm lại top chunks")
    col4.metric("💾 Vector DB", "Qdrant Local", help="Cơ sở dữ liệu vector")

    st.markdown("---")

    # ── Hàng 2: Thống kê kho tri thức ───────────────────────────────────
    st.markdown("#### 📚 Kho Tri Thức")

    try:
        client = orchestrator.vector_service.client
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if Config.VECTOR_COLLECTION_NAME in collection_names:
            # Lấy state từ hàm Cache thay vì gọi IngestionTracker trực tiếp
            state = load_tracker_state()
            real_points_count = sum(info.get("chunk_count", 0) for info in state.values())

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("📦 Collection", Config.VECTOR_COLLECTION_NAME)
            col_b.metric("🔢 Tổng Chunks", f"{real_points_count:,}")
            col_c.metric("📏 Vector Dim", "1024d")

            # Hiển thị trạng thái ingestion
            _render_ingestion_state()
        else:
            st.warning("⚠️ Chưa có collection nào trong Qdrant. Hãy nạp PDF trước!")

    except Exception as e:
        st.error(f"❌ Lỗi kết nối Qdrant: {e}")

    st.markdown("---")

    # ── Hàng 3: Dữ liệu thời gian thực ─────────────────────────────────
    st.markdown("#### 📡 Dữ Liệu Thời Gian Thực")

    selected_symbol, selected_timeframes = _render_runtime_profile_selector()
    _render_market_data_provider_status(orchestrator, selected_symbol, selected_timeframes)
    _render_autonomous_decision_review_card(
        orchestrator, selected_symbol, selected_timeframes
    )

    col_live1, col_live2 = st.columns(2)

    with col_live1:
        st.markdown(f"**💰 Giá {selected_symbol} Live**")
        if st.button("🔄 Cập nhật giá", use_container_width=True, key="dash_price"):
            with st.spinner("Đang lấy giá..."):
                price_info = orchestrator.live_service.get_live_price(selected_symbol)
                st.info(price_info)

    with col_live2:
        st.markdown("**📅 Lịch Kinh Tế**")
        if st.button("🔄 Xem lịch tuần này", use_container_width=True, key="dash_calendar"):
            with st.spinner("Đang tải lịch kinh tế..."):
                calendar_info = orchestrator.live_service.get_economic_calendar()
                st.info(calendar_info)

    _render_dry_run_execution_gate_status()
    _render_proposal_boundary_confirmation_status()
    _render_non_executable_proposal_draft_status()
    _render_simulated_execution_adapter_status()
    _render_mt5_live_execution_hard_block_status()
    _render_live_execution_design_spec_status()
    _render_live_execution_preflight_status()
    _render_live_permission_gate_status()
    _render_live_order_intent_builder_status()
    _render_live_order_contract_skeleton_status()
    _render_live_order_parameter_policy_status()
    _render_live_order_parameter_source_boundary_status()
    _render_human_reviewed_live_parameter_draft_status()
    _render_controlled_live_parameter_value_proposal_status()
    _render_human_value_approval_lock_status()
    _render_live_order_contract_parameterization_status()
    _render_live_order_contract_final_review_status()
    _render_pre_mt5_order_request_mapping_status()
    _render_mt5_dry_run_payload_validator_status()
    _render_mt5_request_draft_boundary_status()
    _render_mt5_request_draft_final_approval_status()
    _render_mt5_request_dict_dry_run_builder_status()
    _render_mt5_request_dict_final_validation_and_bridge_skeleton_status()
    _render_mt5_live_adapter_disabled_pre_submit_status()

    st.markdown("---")

    # ── Hàng 4: Cấu hình đường dẫn ─────────────────────────────────────
    st.markdown("#### 📂 Đường Dẫn Hệ Thống")
    st.code(
        f"📁 Project Root:  {Config.BASE_DIR}\n"
        f"📁 PDF Static:    {Config.STATIC_PDF_DIR}\n"
        f"📁 PDF Dynamic:   {Config.DYNAMIC_PDF_DIR}\n"
        f"📁 Qdrant DB:     {Config.QDRANT_DIR}\n"
        f"📁 Logs:          {Config.LOGS_DIR}",
        language="text",
    )


# =============================================================================
# HELPERS NỘI BỘ
# =============================================================================
def _render_runtime_profile_selector() -> tuple[str, tuple[str, ...]]:
    selected_symbol = st.selectbox(
        "Canonical symbol",
        ("XAUUSD", "BTCUSD"),
        index=0 if Config.MARKET_DEFAULT_SYMBOL != "BTCUSD" else 1,
        key="autonomous_candidate_symbol",
    )
    btc_profile_active = selected_symbol == "BTCUSD"
    st.checkbox(
        "Use BTCUSD M1 acceptance profile",
        value=btc_profile_active,
        disabled=True,
        key=f"autonomous_candidate_btc_m1_acceptance_{selected_symbol}",
    )
    selected_timeframes = operator_timeframe_profile(selected_symbol)
    st.caption(
        f"Active profile: {selected_symbol} -> {broker_symbol_for(selected_symbol)} | "
        f"{','.join(selected_timeframes)}"
    )
    return selected_symbol, selected_timeframes
def _render_autonomous_decision_review_card(
    orchestrator,
    selected_symbol,
    selected_timeframes,
    *,
    requested_mode=None,
    generation_request_id=None,
    show_manual_proposal=True,
    key_prefix="",
    strategy=None,
):
    monitor_row = _latest_monitor_row(selected_symbol, selected_timeframes)
    active_mode = _render_trading_runtime_controls(
        selected_symbol,
        selected_timeframes,
        monitor_row,
        requested_mode=requested_mode,
        mode_idempotency_key=generation_request_id,
        key_prefix=key_prefix,
    )
    mode_ui = _mode_ui_capabilities(requested_mode or active_mode)
    actions = st.columns(2)
    generation_active = st.session_state.get("autonomous_candidate_generation_active") is True
    if actions[0].button(
        "Generate Candidate",
        key=f"{key_prefix}generate_autonomous_candidate",
        disabled=(
            generation_active
            or bool(requested_mode and active_mode != requested_mode)
        ),
        use_container_width=True,
    ):
        controller = OperatorCandidateGenerationController(
            AuthoritativeAutonomousInputAssembler(
                orchestrator.live_service, mode=active_mode
            )
        )
        with st.spinner("Building authoritative runtime context..."):
            outcome = controller.generate(
                st.session_state,
                generation_request_id or secrets.token_hex(16),
                symbol=selected_symbol,
                timeframes=selected_timeframes,
                strategy=strategy,
            )
        st.session_state["autonomous_candidate_generation_outcome"] = outcome
    if actions[1].button(
        "Clear Current Candidate",
        key=f"{key_prefix}clear_autonomous_candidate",
        use_container_width=True,
    ):
        clear_autonomous_decision_run_result(st.session_state)
        st.session_state.pop("autonomous_candidate_generation_outcome", None)

    outcome = st.session_state.get("autonomous_candidate_generation_outcome")
    if outcome is not None:
        if outcome.status == "GENERATED":
            st.success(
                f"Generation={outcome.status} | intent={outcome.intent} | "
                f"candidate={outcome.candidate_reference}"
            )
        elif outcome.status == "BLOCKED":
            st.warning(f"Generation blocked: {outcome.blocker}")
        else:
            st.info(f"Generation={outcome.status} | reason={outcome.blocker}")
            render_reasoning_evidence_summary(
                getattr(outcome, "reasoning_evidence_summary", "")
            )

    if monitor_row:
        st.caption(
            "Monitor | "
            f"status={monitor_row['status']} | intent={monitor_row['intent'] or 'NONE'} | "
            f"closed_bar={monitor_row['closed_bar_time']} | execution_authority=false"
        )

    if requested_mode and active_mode != requested_mode:
        st.info("Grant the requested authoritative mode before candidate generation.")
    if show_manual_proposal:
        _render_manual_operator_candidate_form(orchestrator, active_mode)
    run_result = get_autonomous_decision_run_result(st.session_state)
    candidate = run_result.candidate if run_result else None
    validation = run_result.validation if run_result else None
    if candidate is None and monitor_row and monitor_row["status"] == "GENERATED":
        try:
            journal = AutonomousDecisionJournal(
                Config.TRADING_AUTONOMOUS_DECISION_JOURNAL_PATH,
                Config.TRADING_AUTONOMOUS_DECISION_MAX_READ_RECORDS,
            )
            candidate = journal.load_candidate(monitor_row["candidate_reference"])
            if candidate is not None:
                validation = AutonomousDecisionOrchestrator().validate_candidate(candidate)
        except AutonomousDecisionJournalError:
            st.warning("Monitored candidate journal is unavailable or invalid.")
    render_autonomous_candidate_review_card(candidate, validation)
    if candidate is not None and mode_ui["human_confirmation"]:
        render_autonomous_candidate_confirmation_controls(
            candidate.candidate_reference,
            _operator_candidate_review_controller(),
            key_prefix=key_prefix,
        )
    elif candidate is not None and active_mode == "advisory_only":
        st.info("Advisory-only mode cannot confirm or submit a candidate.")
    elif candidate is not None and active_mode == "autonomous_live":
        st.info("Autonomous mode uses Standing Trading Mandate authority, not per-trade confirmation.")
    if mode_ui["human_confirmation"]:
        _render_pending_candidate_handoff(run_result, key_prefix=key_prefix)


def _latest_monitor_row(symbol: str, timeframes: tuple[str, ...]):
    try:
        return AutonomousCandidateMonitorJournal(DEFAULT_MONITOR_JOURNAL_PATH).latest(
            monitor_profile_id(symbol, timeframes)
        )
    except AutonomousCandidateMonitorError:
        st.warning("Candidate monitor journal is unavailable or invalid.")
        return None


@st.cache_resource
def _trading_authority_service():
    return TradingAuthorityOperatorService()


@st.cache_resource
def _autonomous_monitor_process():
    return AutonomousMonitorProcess(Config.BASE_DIR)


def _mode_ui_capabilities(mode: str) -> dict[str, bool]:
    return {
        "human_confirmation": mode == "human_confirmed_live",
        "mandate_controls": mode == "autonomous_live",
    }


def _render_trading_runtime_controls(
    symbol,
    timeframes,
    monitor_row,
    *,
    requested_mode=None,
    mode_idempotency_key=None,
    key_prefix="",
) -> str:
    with st.expander("Trading Authority and Runtime Supervisor", expanded=True):
        st.caption(
            "Protected demo-account authority and bounded completed-bar supervision. "
            "No control here bypasses execution, kill-switch, idempotency, or bridge checks."
        )
        service = _trading_authority_service()
        try:
            st.button(
                "Refresh Runtime Health",
                key=f"{key_prefix}refresh_trading_runtime_health",
            )
            status = service.status(refresh_runtime=True)
        except Exception as exc:
            st.warning(f"Trading authority unavailable: {type(exc).__name__}")
            return "UNKNOWN"

        lifecycle = status["lifecycle"]
        columns = st.columns(6)
        columns[0].metric("Account", status["account_environment"])
        columns[1].metric("Mode", status["mode"])
        columns[2].metric("Lifecycle", lifecycle["supervisor_status"])
        columns[3].metric("Account match", str(lifecycle["account_context_match"]).lower())
        columns[4].metric("Discrepancies", lifecycle["discrepancy_count"])
        columns[5].metric("Unresolved", status["unresolved_execution_count"])
        st.caption(
            f"bridge_available={str(lifecycle['bridge_available']).lower()} | "
            f"account_match={str(lifecycle['account_context_match']).lower()} | "
            f"terminal_trade_allowed={str(lifecycle['terminal_trade_allowed']).lower()} | "
            f"account_trade_allowed={str(lifecycle['account_trade_allowed']).lower()} | "
            f"positions={lifecycle['active_position_count']} | trades_today={lifecycle['trades_today']} | "
            f"account_redacted={str(status['metadata_redacted']).lower()}"
        )
        pre_submit = status["pre_submit"]
        permissions = status["permission_state"]
        st.caption(
            f"pre_submit={pre_submit['latest_status'] or 'none'} | "
            f"execution_states={status['execution_state_counts'] or {}} | "
            f"reconciliation_states={status['reconciliation_state_counts'] or {}}"
        )
        st.caption(
            f"live_adapter={str(permissions['live_adapter_enabled']).lower()} | "
            f"live_submission={str(permissions['live_submission_allowed']).lower()} | "
            f"order_send={str(permissions['order_send_allowed']).lower()} | "
            f"controlled_execution={str(permissions['controlled_execution_enabled']).lower()} | "
            f"pending_submission={str(permissions['pending_submission_enabled']).lower()} | "
            f"execution_kill_switch={str(permissions['execution_kill_switch_engaged']).lower()}"
        )
        st.caption(
            f"policy_gate={str(permissions['autonomous_policy_gate_enabled']).lower()} | "
            f"open_eligibility={str(permissions['autonomous_open_eligibility_enabled']).lower()} | "
            f"management_eligibility={str(permissions['autonomous_management_eligibility_enabled']).lower()} | "
            f"controlled_management={str(permissions['controlled_management_enabled']).lower()} | "
            f"cancel_allowed={str(permissions['cancel_allowed']).lower()} | "
            f"protection_modification={str(permissions['protection_modification_allowed']).lower()} | "
            f"position_close={str(permissions['position_close_allowed']).lower()} | "
            f"management_kill_switch={str(permissions['management_kill_switch_engaged']).lower()}"
        )
        runtime_blockers = []
        if status["account_environment"] != "DEMO":
            runtime_blockers.append("ACCOUNT_ENVIRONMENT_NOT_DEMO")
        if not status["mode_integrity_valid"]:
            runtime_blockers.append("MODE_INTEGRITY_INVALID")
        if lifecycle["supervisor_status"] != "HEALTHY":
            runtime_blockers.append(lifecycle["health_reason"])
        if not lifecycle["bridge_available"]:
            runtime_blockers.append("BRIDGE_UNAVAILABLE")
        if not lifecycle["account_context_match"]:
            runtime_blockers.append("ACCOUNT_CONTEXT_MISMATCH")
        if lifecycle["discrepancy_count"]:
            runtime_blockers.append("RECONCILIATION_DISCREPANCY")
        if runtime_blockers:
            st.warning("Runtime blockers: " + ", ".join(dict.fromkeys(runtime_blockers)))
        if status["unresolved_execution_count"]:
            st.error("Unknown execution result requires reconciliation and blocks new work.")
        if pre_submit["warnings"]:
            st.error("Pre-submit journal is unavailable or corrupt.")

        mode_help = {
            "advisory_only": (
                "Advisory only: analysis and non-executable candidate generation are available; "
                "confirmation, mandates, and MT5 submission are unavailable."
            ),
            "human_confirmed_live": (
                "Human-confirmed live: every actionable candidate requires exact operator "
                "confirmation and a separate protected one-shot submission authorization."
            ),
            "autonomous_live": (
                "Autonomous live: per-trade confirmation is unavailable; execution requires an "
                "active in-scope Standing Trading Mandate and all kill-switch checks to pass."
            ),
        }
        st.info(mode_help.get(status["mode"], "Operating mode is unavailable."))
        mode_ui = _mode_ui_capabilities(requested_mode or status["mode"])

        with st.form(f"{key_prefix}authoritative_mode_form"):
            if requested_mode:
                mode = requested_mode
                st.caption(f"Requested authoritative mode: {requested_mode}")
            else:
                mode = st.selectbox(
                    "Authoritative operating mode",
                    ("advisory_only", "human_confirmed_live", "autonomous_live"),
                    index=None,
                    placeholder="Select mode",
                    key=f"{key_prefix}authoritative_operating_mode",
                )
            grant_mode = st.checkbox(
                "I explicitly authorize this demo-account mode change",
                key=f"{key_prefix}authorize_demo_mode_change",
            )
            mode_action = (
                "Grant MT5 Demo Access"
                if requested_mode == "human_confirmed_live"
                else "Set Authoritative Mode"
            )
            if st.form_submit_button(mode_action):
                try:
                    service.set_mode(
                        mode,
                        operator_grant=grant_mode,
                        idempotency_key=mode_idempotency_key,
                    )
                    st.success("Authoritative mode updated.")
                    st.rerun()
                except Exception as exc:
                    st.warning(f"Mode change blocked: {str(exc)}")

        if not mode_ui["mandate_controls"]:
            return status["mode"]

        with st.form(f"{key_prefix}standing_mandate_form"):
            st.markdown("**Standing Trading Mandate**")
            mandate_id = st.text_input("Mandate ID", key=f"{key_prefix}mandate_id")
            mandate_version = st.number_input(
                "Mandate version", min_value=1, step=1, key=f"{key_prefix}mandate_version"
            )
            symbols = tuple(
                st.multiselect(
                    "Canonical symbols",
                    ("XAUUSD", "BTCUSD"),
                    key=f"{key_prefix}mandate_symbols",
                )
            )
            broker_symbols = tuple(
                st.multiselect(
                    "Broker symbols",
                    ("XAUUSDm", "BTCUSDm"),
                    key=f"{key_prefix}mandate_broker_symbols",
                )
            )
            order_families = tuple(
                st.multiselect(
                    "Order families",
                    ("MARKET", "PENDING"),
                    key=f"{key_prefix}mandate_order_families",
                )
            )
            management_actions = tuple(
                st.multiselect(
                    "Management actions",
                    ("OBSERVE", "NO_ACTION", "CANCEL_PENDING", "MODIFY_PROTECTION", "CLOSE_POSITION"),
                    key=f"{key_prefix}mandate_management_actions",
                )
            )
            limit_columns = st.columns(5)
            maximum_volume = limit_columns[0].text_input(
                "Max volume", key=f"{key_prefix}mandate_max_volume"
            )
            maximum_risk = limit_columns[1].text_input(
                "Max risk/trade", key=f"{key_prefix}mandate_max_risk"
            )
            maximum_positions = limit_columns[2].number_input(
                "Max positions", min_value=1, step=1, key=f"{key_prefix}mandate_max_positions"
            )
            maximum_trades = limit_columns[3].number_input(
                "Max trades/day", min_value=1, step=1, key=f"{key_prefix}mandate_max_trades"
            )
            maximum_loss = limit_columns[4].text_input(
                "Max loss/day", key=f"{key_prefix}mandate_max_loss"
            )
            active_from = st.text_input(
                "Active from (UTC ISO-8601)", key=f"{key_prefix}mandate_active_from"
            )
            active_until = st.text_input(
                "Active until (UTC ISO-8601)", key=f"{key_prefix}mandate_active_until"
            )
            expires_at = st.text_input(
                "Expires at (UTC ISO-8601)", key=f"{key_prefix}mandate_expires_at"
            )
            mandate_kill_switch = st.checkbox(
                "Mandate kill switch engaged",
                value=True,
                key=f"{key_prefix}mandate_kill_switch",
            )
            grant_mandate = st.checkbox(
                "I explicitly grant this bounded demo-account mandate",
                key=f"{key_prefix}grant_mandate",
            )
            if st.form_submit_button("Grant Standing Mandate"):
                try:
                    service.grant_mandate(
                        MandateGrantCommand(
                            mandate_id=mandate_id,
                            mandate_version=int(mandate_version),
                            permitted_symbols=symbols,
                            permitted_broker_symbols=broker_symbols,
                            permitted_order_families=order_families,
                            permitted_management_actions=management_actions,
                            maximum_volume=maximum_volume,
                            maximum_risk_per_trade=maximum_risk,
                            maximum_concurrent_positions=int(maximum_positions),
                            maximum_trades_per_day=int(maximum_trades),
                            maximum_loss_per_day=maximum_loss,
                            active_from=active_from,
                            active_until=active_until,
                            expires_at=expires_at,
                            kill_switch_engaged=mandate_kill_switch,
                        ),
                        operator_grant=grant_mandate,
                    )
                    st.success("Standing mandate stored with protected integrity.")
                except Exception as exc:
                    st.warning(f"Mandate grant blocked: {str(exc)}")

        mandate_ids = tuple(item["mandate_id"] for item in status["mandates"])
        command_columns = st.columns(2)
        with command_columns[0]:
            revoke_id = st.selectbox(
                "Mandate to revoke",
                mandate_ids,
                index=None,
                key=f"{key_prefix}revoke_mandate_id",
            )
            revoke_grant = st.checkbox(
                "I explicitly revoke this mandate", key=f"{key_prefix}revoke_mandate_grant"
            )
            if st.button(
                "Revoke Mandate",
                disabled=revoke_id is None,
                key=f"{key_prefix}revoke_mandate",
            ):
                try:
                    service.revoke_mandate(revoke_id, operator_grant=revoke_grant)
                    st.success("Mandate revoked.")
                except Exception as exc:
                    st.warning(f"Mandate revocation blocked: {str(exc)}")
        with command_columns[1]:
            process = _autonomous_monitor_process()
            process_status = process.status()
            monitor_mandate = st.selectbox(
                "Supervisor mandate",
                mandate_ids,
                index=None,
                key=f"{key_prefix}supervisor_mandate",
            )
            start, stop = st.columns(2)
            if start.button(
                "Start Supervisor",
                disabled=process_status["running"],
                key=f"{key_prefix}start_supervisor",
            ):
                process_status = process.start(
                    symbol=symbol,
                    timeframes=timeframes,
                    mandate_id=monitor_mandate or "",
                )
            if stop.button(
                "Stop Supervisor",
                disabled=not process_status["running"],
                key=f"{key_prefix}stop_supervisor",
            ):
                process_status = process.stop()
            st.caption(
                f"supervisor_running={str(process_status['running']).lower()} | "
                f"profile={symbol}:{','.join(timeframes)}"
            )
            if monitor_row:
                st.caption(
                    f"latest={monitor_row['status']} | blocker={monitor_row['blocker'] or 'none'}"
                )
        return status["mode"]


def _render_manual_operator_candidate_form(orchestrator, active_mode: str) -> None:
    with st.expander("Manual Operator Proposal", expanded=False):
        st.caption(
            "Creates one protected, non-executable candidate from values entered here. "
            "It does not call the LLM, confirm, export, submit, or grant execution permission."
        )
        with st.form("manual_operator_proposal_form"):
            symbol = st.selectbox(
                "Canonical symbol",
                ("XAUUSD", "BTCUSD"),
                index=None,
                placeholder="Select symbol",
                key="manual_operator_symbol",
            )
            order_type = st.selectbox(
                "Order type",
                (
                    "BUY",
                    "SELL",
                    "BUY_LIMIT",
                    "SELL_LIMIT",
                    "BUY_STOP",
                    "SELL_STOP",
                    "BUY_STOP_LIMIT",
                    "SELL_STOP_LIMIT",
                ),
                index=None,
                placeholder="Select order type",
                key="manual_operator_order_type",
            )
            pending = bool(order_type and order_type not in {"BUY", "SELL"})
            stop_limit = bool(order_type and order_type.endswith("STOP_LIMIT"))
            entry_price = st.text_input(
                "Entry price",
                disabled=not pending or stop_limit,
                key="manual_operator_entry_price",
            )
            trigger_price = st.text_input(
                "Trigger price",
                disabled=not stop_limit,
                key="manual_operator_trigger_price",
            )
            limit_price = st.text_input(
                "Limit price",
                disabled=not stop_limit,
                key="manual_operator_limit_price",
            )
            stop_loss = st.text_input(
                "Stop loss", key="manual_operator_stop_loss"
            )
            take_profit = st.text_input(
                "Take profit", key="manual_operator_take_profit"
            )
            proposed_volume = st.text_input(
                "Proposed volume", key="manual_operator_volume"
            )
            submitted = st.form_submit_button(
                "Validate and Create Manual Candidate",
                use_container_width=True,
            )
        if submitted:
            if not symbol or not order_type:
                st.session_state["manual_operator_candidate_outcome"] = (
                    "BLOCKED",
                    "MANUAL_PROPOSAL_SELECTION_MISSING",
                )
            else:
                controller = OperatorCandidateGenerationController(
                    AuthoritativeAutonomousInputAssembler(
                        orchestrator.live_service,
                        mode=active_mode,
                    )
                )
                with st.spinner("Validating authoritative manual proposal..."):
                    outcome = controller.generate(
                        st.session_state,
                        secrets.token_hex(16),
                        symbol=symbol,
                        operator_proposal=ManualOperatorProposalInput(
                            order_type=order_type,
                            entry_price=entry_price,
                            trigger_price=trigger_price,
                            limit_price=limit_price,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            proposed_volume=proposed_volume,
                        ),
                    )
                st.session_state["manual_operator_candidate_outcome"] = (
                    outcome.status,
                    outcome.blocker,
                    outcome.candidate_reference,
                )
        manual_outcome = st.session_state.get("manual_operator_candidate_outcome")
        if manual_outcome:
            status, blocker, *candidate = manual_outcome
            if status == "GENERATED":
                st.success(
                    f"Manual candidate created: {candidate[0]} | non-executable=true"
                )
            else:
                st.warning(f"Manual candidate blocked: {blocker}")


def _operator_candidate_review_controller() -> OperatorCandidateReviewController:
    candidate_journal = AutonomousDecisionJournal(
        Config.TRADING_AUTONOMOUS_DECISION_JOURNAL_PATH,
        Config.TRADING_AUTONOMOUS_DECISION_MAX_READ_RECORDS,
    )

    def account_context_provider():
        payload = MT5LiveAdapterDisabled().capture_account_context()
        payload["status"] = "OK"
        capture = ProtectedAccountContextCapture.from_read_only_payload(
            payload, datetime.now(timezone.utc)
        )
        return capture, capture.account_context_fingerprint

    return OperatorCandidateReviewController(
        HumanProposalConfirmationService(), candidate_journal, account_context_provider
    )


def _render_pending_candidate_handoff(run_result, *, key_prefix=""):
    if run_result is None or run_result.candidate.action != "PENDING":
        return
    st.caption(
        "Protected validation-only handoff. This action does not submit, call MT5, "
        "or grant execution permission."
    )
    st.caption(f"Required phrase: `{EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE}`")
    review = st.session_state.get("human_review_artifact")
    confirmation = st.session_state.get("human_confirmed_proposal_intent")
    ready = (
        run_result.order_market_snapshot is not None
        and review is not None
        and confirmation is not None
    )
    phrase = st.text_input(
        "Export-only confirmation",
        key=f"{key_prefix}pending_candidate_export_confirmation",
        type="password",
        disabled=not ready,
    )
    if st.button(
        "Export Protected Pending Candidate",
        key=f"{key_prefix}export_protected_pending_candidate",
        disabled=not ready,
    ):
        try:
            result = write_pending_candidate_handoff(
                run_result=run_result,
                review_artifact=review,
                confirmation_intent=confirmation,
                output_dir="data/trading/protected_requests/pending-candidates",
                confirmation_phrase=phrase,
            )
            st.success(
                f"Pending candidate handoff {result.export_status}: "
                f"{result.candidate_reference_redacted}"
            )
            st.caption(
                f"schema={result.schema_version} | order_type={result.order_type} | "
                f"validation={result.validation_status} | path={result.artifact_path}"
            )
        except PendingArtifactExportError as exc:
            st.warning(f"Pending candidate handoff blocked: {str(exc)}")


def _market_runtime_projection(result, symbol: str, timeframes: tuple[str, ...]) -> dict:
    bundle = result.bundle
    quality = result.quality_report
    tick = bundle.tick
    expected_broker_symbol = broker_symbol_for(symbol)
    blockers = [
        f"{issue.code}:{issue.timeframe}" if issue.timeframe else issue.code
        for issue in quality.issues
    ]
    if bundle.symbol != symbol or bundle.broker_symbol != expected_broker_symbol:
        blockers.append("SYMBOL_PROFILE_MISMATCH")
    missing_metadata = bool(
        tick is None
        or any(
            getattr(tick, name, None) is None
            for name in (
                "digits", "point", "tick_size", "minimum_distance_points",
                "volume_min", "volume_max", "volume_step", "tick_value", "contract_size",
            )
        )
    )
    if missing_metadata:
        blockers.append("SYMBOL_CAPABILITY_INCOMPLETE")
    return {
        "canonical_symbol": bundle.symbol,
        "broker_symbol": bundle.broker_symbol,
        "timeframes": tuple(timeframes),
        "provider_health": getattr(bundle.provider_health, "status", "UNAVAILABLE"),
        "quality_status": quality.status,
        "tick_timestamp": tick.timestamp if tick else "n/a",
        "bar_timestamps": {
            timeframe: quality.latest_timestamp_by_timeframe.get(timeframe, "n/a")
            for timeframe in timeframes
        },
        "symbol_capability": "COMPLETE" if not missing_metadata else "INCOMPLETE",
        "blockers": tuple(dict.fromkeys(blockers)),
    }


def _render_market_data_provider_status(orchestrator, symbol, timeframes):
    try:
        service = orchestrator.live_service
        feature_service = LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(service.provider)
        )
        result = feature_service.build_features(
            symbol, timeframes, Config.MARKET_DEFAULT_CANDLE_COUNT
        )
        state = _market_runtime_projection(result, symbol, timeframes)
        cols = st.columns(5)
        cols[0].metric("Provider", getattr(service.provider, "provider_name", "unknown"))
        cols[1].metric("Health", state["provider_health"])
        cols[2].metric("Canonical", state["canonical_symbol"])
        cols[3].metric("Broker", state["broker_symbol"])
        cols[4].metric("Profile", "/".join(state["timeframes"]))
        st.caption(
            f"tick={state['tick_timestamp']} | quality={state['quality_status']} | "
            f"symbol_capability={state['symbol_capability']}"
        )
        st.caption(
            "Completed bars: "
            + " | ".join(
                f"{timeframe}={state['bar_timestamps'][timeframe]}"
                for timeframe in state["timeframes"]
            )
        )
        features = result.feature_snapshot
        feature_cols = st.columns(5)
        feature_cols[0].metric("Data quality", features.data_quality_status)
        feature_cols[1].metric("Trend", features.trend_direction)
        feature_cols[2].metric("Strength", f"{features.trend_strength:.2f}")
        feature_cols[3].metric("Volatility", features.volatility_state)
        feature_cols[4].metric("Spread", features.spread_state)
        st.caption(
            f"Momentum={features.momentum_state} | Pullback={features.pullback_detected} | "
            f"Range/chop={features.range_chop_score:.2f}"
        )
        try:
            calendar_context = CalendarContextBuilder(service.calendar_provider).build(symbol)
            regime = MarketRegimeDetector().detect(features, calendar_context)
            regime_cols = st.columns(4)
            regime_cols[0].metric("Calendar risk", calendar_context.calendar_risk_state)
            next_event = calendar_context.next_high_impact_event
            regime_cols[1].metric("Next event", next_event.title[:28] if next_event else "n/a")
            minutes = calendar_context.minutes_to_next_high_impact_event
            regime_cols[2].metric("Minutes", f"{minutes:.0f}" if minutes is not None else "n/a")
            regime_cols[3].metric("Regime", regime.primary_regime)
            st.caption(
                f"Regime confidence={regime.confidence:.2f} | "
                f"Secondary={', '.join(regime.secondary_regimes) or 'n/a'}"
            )
            if regime.blockers:
                st.warning("Regime blockers: " + ", ".join(regime.blockers[:5]))
        except Exception as exc:
            st.caption(f"Calendar/regime snapshot unavailable: {type(exc).__name__}")
        if state["blockers"]:
            st.warning("Market blockers: " + ", ".join(state["blockers"][:8]))
    except Exception as exc:
        st.warning(f"Market data provider status unavailable: {type(exc).__name__}")


def _render_dry_run_execution_gate_status():
    st.markdown("#### Dry-Run Execution Gate")
    st.caption("Dry-run only. No live order is sent. executed=false.")
    try:
        store = ExecutionJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Dry-runs", summary.total_dry_runs)
        cols[1].metric("Allowed", summary.total_allowed)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Duplicates", summary.total_duplicates)
        if summary.latest_receipt_id:
            st.caption(
                f"Latest gate={summary.latest_gate_action} | "
                f"artifact_hash={summary.latest_artifact_hash[:12]} | "
                f"receipt={summary.latest_receipt_id}"
            )
        if summary.warnings:
            st.caption("Journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Dry-run journal unavailable: {type(exc).__name__}")

    artifact = st.session_state.get("human_review_artifact")
    card = st.session_state.get("human_review_card")
    if artifact is None:
        st.info("No HumanReviewArtifact in session. Generate a review card before running the dry-run gate.")
        st.button("Run Dry-Run Gate", disabled=True, use_container_width=True, key="dash_dry_run_gate_disabled")
        return

    if st.button("Run Dry-Run Gate", use_container_width=True, key="dash_dry_run_gate"):
        try:
            result = DryRunConfirmationService().run(artifact, card=card)
            receipt = result.receipt
            st.session_state["execution_gate_decision"] = result.gate_decision
            st.session_state["dry_run_execution_receipt"] = receipt
            st.session_state["execution_journal_record"] = result.journal_record
            st.success(
                "Dry-run gate evaluated. "
                f"gate_action={result.gate_decision.action}, "
                f"dry_run_only={receipt.dry_run_only}, executed={receipt.executed}"
            )
            if result.journal_record:
                st.caption(f"Journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Dry-run gate unavailable: {type(exc).__name__}")


def _render_proposal_boundary_confirmation_status():
    st.markdown("#### Proposal Boundary Confirmation")
    st.caption(
        "Proposal workflow confirmation only. No live order is sent. "
        "dry_run_only=true. executable=false. Future execution requires a separate adapter and gate."
    )
    try:
        store = ProposalIntentJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Intents", summary.total_intents)
        cols[1].metric("Confirmed", summary.total_confirmed)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Duplicates", summary.total_duplicates)
        if summary.latest_intent_id:
            st.caption(f"Latest proposal intent={summary.latest_intent_id} | status={summary.latest_status}")
        if summary.warnings:
            st.caption("Proposal journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Proposal intent journal unavailable: {type(exc).__name__}")

    artifact = st.session_state.get("human_review_artifact")
    receipt = st.session_state.get("dry_run_execution_receipt")
    execution_record = st.session_state.get("execution_journal_record")
    if artifact is not None:
        st.caption(f"Latest review status={artifact.review_status} | readiness_action={artifact.readiness_action}")
    if receipt is not None:
        st.caption(
            f"Latest dry-run receipt={receipt.receipt_id} | gate_action={receipt.gate_action} | "
            f"dry_run_only={receipt.dry_run_only} | executed={receipt.executed}"
        )

    phrase = ProposalBoundaryPolicy.from_config().confirmation_phrase
    st.caption(f"Required phrase: `{phrase}`")
    acknowledgement = st.text_input(
        "Type the required phrase to confirm proposal workflow",
        key="dash_proposal_boundary_phrase",
    )
    disabled = artifact is None or receipt is None or execution_record is None
    if disabled:
        st.info("Run the dry-run gate first so the proposal boundary can verify the receipt and journal record.")
    if st.button(
        "Confirm Proposal Workflow",
        disabled=disabled,
        use_container_width=True,
        key="dash_confirm_proposal_workflow",
    ):
        try:
            result = HumanProposalConfirmationService().confirm_with_journal(
                artifact,
                receipt,
                execution_journal_record=execution_record,
                user_acknowledgement_text=acknowledgement,
            )
            intent = result.intent
            st.session_state["human_confirmed_proposal_intent"] = intent
            st.session_state["proposal_intent_journal_record"] = result.journal_record
            st.info(
                "Proposal boundary evaluated. "
                f"status={intent.proposal_boundary_status}, "
                f"proposal_workflow_allowed={intent.proposal_workflow_allowed}, "
                f"dry_run_only={intent.dry_run_only}, executable={intent.executable}"
            )
            if result.journal_record:
                st.caption(f"Proposal intent journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
            card = ProposalBoundaryFormatter().to_card(intent)
            st.caption(f"Source refs={card.source_section.get('source_refs_count', 0)}")
        except Exception as exc:
            st.warning(f"Proposal boundary unavailable: {type(exc).__name__}")


def _render_non_executable_proposal_draft_status():
    st.markdown("#### Non-Executable Proposal Draft")
    st.caption(
        "This is a non-executable proposal draft. It is not a trade signal, "
        "does not contain order parameters, sends no live order, and executable=false."
    )
    try:
        store = ProposalDraftJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Drafts", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Waiting", summary.total_waiting)
        cols[3].metric("Blocked", summary.total_blocked)
        if summary.latest_draft_id:
            st.caption(f"Latest draft={summary.latest_draft_id} | status={summary.latest_status}")
        if summary.warnings:
            st.caption("Draft journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Proposal draft journal unavailable: {type(exc).__name__}")

    intent = st.session_state.get("human_confirmed_proposal_intent")
    artifact = st.session_state.get("human_review_artifact")
    score_report = st.session_state.get("signal_score_report")
    method_selection = st.session_state.get("method_selection_result")
    context_pack = st.session_state.get("runtime_context_pack")
    calendar_context = st.session_state.get("calendar_context")
    regime = st.session_state.get("market_regime_snapshot")
    features = st.session_state.get("feature_snapshot")
    disabled = not all([intent, artifact, score_report, method_selection, context_pack])
    if disabled:
        st.info("Structured proposal inputs are not in session yet. Build the upstream review/proposal boundary first.")

    if st.button(
        "Build Non-Executable Proposal Draft",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_non_executable_proposal_draft",
    ):
        try:
            result = ProposalDraftService().build(
                intent,
                artifact,
                score_report,
                method_selection,
                context_pack,
                calendar_context=calendar_context,
                regime_snapshot=regime,
                feature_snapshot=features,
            )
            draft = result.draft
            st.session_state["non_executable_trade_proposal_draft"] = draft
            st.session_state["proposal_draft_card"] = result.card
            st.session_state["proposal_draft_journal_record"] = result.journal_record
            st.info(
                "Non-executable proposal draft built. "
                f"status={draft.status}, non_executable={draft.non_executable}, executable={draft.executable}"
            )
            st.caption(
                f"Method={draft.primary_method_id} | Regime={draft.primary_regime} | "
                f"Calendar={draft.calendar_risk_state} | Source refs={len(draft.source_refs)}"
            )
            if result.journal_record:
                st.caption(f"Proposal draft journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Proposal draft unavailable: {type(exc).__name__}")


def _render_simulated_execution_adapter_status():
    st.markdown("#### Simulated Execution Adapter Contract")
    st.caption(
        "Simulated adapter contract only. No live order is sent, no order parameters exist, "
        "executable=false, executed=false."
    )
    try:
        health = ExecutionAdapterRegistry().health_check()
        store = SimulatedExecutionJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Adapter", health.adapter_type)
        cols[1].metric("Health", health.status)
        cols[2].metric("Accepted", summary.total_accepted)
        cols[3].metric("Rejected", summary.total_rejected)
        if summary.latest_receipt_id:
            st.caption(
                f"Latest contract={summary.latest_contract_id} | receipt={summary.latest_receipt_id} | "
                f"status={summary.latest_contract_status}"
            )
        if summary.warnings:
            st.caption("Simulated journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Simulated adapter status unavailable: {type(exc).__name__}")

    draft = st.session_state.get("non_executable_trade_proposal_draft")
    intent = st.session_state.get("human_confirmed_proposal_intent")
    dry_run_receipt = st.session_state.get("dry_run_execution_receipt")
    execution_record = st.session_state.get("execution_journal_record")
    draft_record = st.session_state.get("proposal_draft_journal_record")
    if draft is not None:
        st.caption(
            f"Latest draft={draft.draft_id} | status={draft.status} | "
            f"non_executable={draft.non_executable} | executable={draft.executable}"
        )
    disabled = draft is None
    if disabled:
        st.info("Build a non-executable proposal draft before running the simulated adapter contract.")

    if st.button(
        "Run Simulated Adapter Contract",
        disabled=disabled,
        use_container_width=True,
        key="dash_run_simulated_adapter_contract",
    ):
        try:
            result = SimulatedExecutionService().run(
                draft,
                intent=intent,
                dry_run_receipt=dry_run_receipt,
                execution_journal_record=execution_record,
                proposal_draft_journal_record=draft_record,
            )
            receipt = result.receipt
            st.session_state["simulated_order_contract"] = result.contract
            st.session_state["simulated_execution_receipt"] = receipt
            st.session_state["simulated_execution_journal_record"] = result.journal_record
            st.info(
                "Simulated adapter contract evaluated. "
                f"contract_status={result.contract.contract_status}, "
                f"accepted_by_adapter={receipt.accepted_by_adapter}, "
                f"simulated_only={receipt.simulated_only}, executable={receipt.executable}, executed={receipt.executed}"
            )
            if result.journal_record:
                st.caption(f"Simulated execution journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Simulated adapter unavailable: {type(exc).__name__}")


def _render_mt5_live_execution_hard_block_status():
    st.markdown("#### MT5 Live Execution Capability - Hard Blocked")
    st.caption(
        "Live execution is hard-blocked. This section only checks capability and records a blocked receipt. "
        "No live order is sent. order_sent=false, executed=false, order submission is disabled."
    )
    try:
        store = LiveExecutionBlockJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Skeleton", "HARD_BLOCKED")
        cols[1].metric("Live supported", "false")
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Records", summary.total_records)
        if summary.latest_receipt_id:
            st.caption(f"Latest blocked receipt={summary.latest_receipt_id} | reason={summary.latest_block_reason}")
        if summary.warnings:
            st.caption("Live-block journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live-block journal unavailable: {type(exc).__name__}")

    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")
    simulated_record = st.session_state.get("simulated_execution_journal_record")
    if contract is not None:
        st.caption(
            f"Latest simulated contract={contract.contract_id} | status={contract.contract_status} | "
            f"artifact_hash={contract.artifact_hash[:12]}"
        )
    disabled = contract is None or simulated_receipt is None
    if disabled:
        st.info("Run the simulated adapter contract before checking the MT5 live execution skeleton.")

    if st.button(
        "Check MT5 Live Execution Capability",
        disabled=disabled,
        use_container_width=True,
        key="dash_check_mt5_live_execution_capability",
    ):
        try:
            result = MT5ExecutionSkeletonService().run(contract, simulated_receipt, simulated_record)
            report = result.capability_report
            receipt = result.blocked_receipt
            st.session_state["live_execution_capability_report"] = report
            st.session_state["live_execution_blocked_receipt"] = receipt
            st.session_state["live_execution_block_journal_record"] = result.journal_record
            st.info(
                "MT5 live execution capability checked and hard-blocked. "
                f"skeleton_status={report.skeleton_status}, "
                f"live_execution_supported={report.live_execution_supported}, "
                f"live_execution_enabled={report.live_execution_enabled}, "
                f"order_sent={receipt.order_sent}, executed={receipt.executed}"
            )
            if result.journal_record:
                st.caption(f"Live-block journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 live execution skeleton unavailable: {type(exc).__name__}")


def _render_live_execution_design_spec_status():
    st.markdown("#### Live Execution Design Spec & Threat Model")
    st.caption(
        "Design spec only. Threat model only. Live execution remains disabled. "
        "No live order is sent. order_sent=false, executed=false."
    )
    try:
        store = LiveExecutionDesignReportStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Design reports", summary.total_records)
        cols[1].metric("Design-only", summary.total_design_only)
        cols[2].metric("Invalid", summary.total_invalid)
        cols[3].metric("Live allowed", "false")
        if summary.latest_report_id:
            st.caption(f"Latest design report={summary.latest_report_id} | status={summary.latest_design_status}")
        if summary.warnings:
            st.caption("Design journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live design report journal unavailable: {type(exc).__name__}")

    capability = st.session_state.get("live_execution_capability_report")
    blocked_receipt = st.session_state.get("live_execution_blocked_receipt")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    disabled = capability is None or blocked_receipt is None
    if disabled:
        st.info("Check MT5 live execution capability first so the design spec can use hard-block artifacts.")

    if st.button(
        "Build Live Execution Design Spec",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_live_execution_design_spec",
    ):
        try:
            result = LiveExecutionDesignSpecService().build_and_record(
                capability,
                blocked_receipt,
                contract=contract,
                simulated_receipt=simulated_receipt,
                draft=draft,
            )
            report = result.report
            st.session_state["live_execution_readiness_spec_report"] = report
            st.session_state["live_execution_design_journal_record"] = result.journal_record
            critical_or_high = sum(1 for item in report.threats if item.severity in {"CRITICAL", "HIGH"})
            st.info(
                "Live execution design spec built. "
                f"status={report.design_status}, live_execution_allowed={report.live_execution_allowed}, "
                f"hard_live_block_required={report.hard_live_block_required}, "
                f"threats={len(report.threats)}, critical_or_high={critical_or_high}"
            )
            if result.journal_record:
                st.caption(f"Live design journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live execution design spec unavailable: {type(exc).__name__}")


def _render_live_execution_preflight_status():
    st.markdown("#### Live Execution Preflight Readiness Harness")
    st.caption(
        "Preflight only. Live execution remains disabled. No live order is sent. "
        "order_sent=false, executed=false. This does not permit live trading yet."
    )
    try:
        store = LiveExecutionPreflightReportStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Preflight reports", summary.total_records)
        cols[1].metric("Passed", summary.total_pass)
        cols[2].metric("Failed", summary.total_fail)
        cols[3].metric("Live allowed", "false")
        if summary.latest_report_id:
            st.caption(
                f"Latest preflight report={summary.latest_report_id} | "
                f"status={summary.latest_preflight_status} | "
                f"blocking_failures={summary.latest_blocking_failures}"
            )
        if summary.warnings:
            st.caption("Preflight journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live preflight journal unavailable: {type(exc).__name__}")

    design_report = st.session_state.get("live_execution_readiness_spec_report")
    capability = st.session_state.get("live_execution_capability_report")
    blocked_receipt = st.session_state.get("live_execution_blocked_receipt")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")
    live_block_record = st.session_state.get("live_execution_block_journal_record")
    disabled = design_report is None or capability is None or blocked_receipt is None
    if disabled:
        st.info("Build the live execution design spec first so preflight can scan hard-block artifacts.")

    if st.button(
        "Run Live Execution Preflight",
        disabled=disabled,
        use_container_width=True,
        key="dash_run_live_execution_preflight",
    ):
        try:
            result = LiveExecutionPreflightService().run(
                design_report,
                capability,
                blocked_receipt,
                simulated_contract=contract,
                simulated_receipt=simulated_receipt,
                live_block_journal_record=live_block_record,
            )
            report = result.report
            st.session_state["live_execution_preflight_readiness_report"] = report
            st.session_state["live_execution_preflight_journal_record"] = result.journal_record
            st.info(
                "Live execution preflight completed. "
                f"status={report.preflight_status}, live_execution_allowed={report.live_execution_allowed}, "
                f"hard_live_block_required={report.hard_live_block_required}, total_checks={report.total_checks}, "
                f"blocking_failures={report.blocking_failures}"
            )
            if result.journal_record:
                st.caption(f"Preflight journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live execution preflight unavailable: {type(exc).__name__}")


def _render_live_permission_gate_status():
    st.markdown("#### Human-Confirmed Live Permission Gate")
    st.caption(
        "This only permits live order intent preparation. It does not send a trade. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = LivePermissionJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Permission records", summary.total_records)
        cols[1].metric("Granted", summary.total_granted)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Live allowed", "false")
        if summary.latest_intent_id:
            st.caption(
                f"Latest permission intent={summary.latest_intent_id} | "
                f"status={summary.latest_permission_status} | decision={summary.latest_decision_id}"
            )
        if summary.warnings:
            st.caption("Permission journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live permission journal unavailable: {type(exc).__name__}")

    policy = LivePermissionPolicy.from_config()
    st.caption(f"Required phrase: `{policy.confirmation_phrase}`")
    acknowledgement = st.text_input(
        "Type the required phrase to confirm live order intent preparation",
        key="dash_live_permission_phrase",
    )
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    design_report = st.session_state.get("live_execution_readiness_spec_report")
    capability = st.session_state.get("live_execution_capability_report")
    blocked_receipt = st.session_state.get("live_execution_blocked_receipt")
    contract = st.session_state.get("simulated_order_contract")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    if preflight_report is not None:
        st.caption(
            f"Latest preflight status={preflight_report.preflight_status} | "
            f"live_execution_allowed={preflight_report.live_execution_allowed} | "
            f"hard_live_block_required={preflight_report.hard_live_block_required}"
        )
    disabled = preflight_report is None or design_report is None or capability is None or blocked_receipt is None
    if disabled:
        st.info("Run live preflight first so the permission gate can verify the latest hard-block artifacts.")

    if st.button(
        "Confirm Live Order Intent Preparation",
        disabled=disabled,
        use_container_width=True,
        key="dash_confirm_live_order_intent_preparation",
    ):
        try:
            result = LivePermissionGateService(policy=policy).run(
                preflight_report,
                design_report,
                capability,
                blocked_receipt,
                simulated_contract=contract,
                proposal_draft=draft,
                user_acknowledgement_text=acknowledgement,
            )
            intent = result.intent
            decision = result.decision
            st.session_state["live_permission_intent"] = intent
            st.session_state["live_permission_gate_decision"] = decision
            st.session_state["live_permission_journal_record"] = result.journal_record
            st.info(
                "Live permission gate evaluated. "
                f"permission_status={intent.permission_status}, confirmation_state={intent.confirmation_state}, "
                f"gate_allowed={decision.gate_allowed}, "
                f"order_intent_workflow_allowed={decision.order_intent_workflow_allowed}, "
                f"live_execution_allowed={decision.live_execution_allowed}, "
                f"order_send_allowed={decision.order_send_allowed}, execution_allowed={decision.execution_allowed}"
            )
            if result.journal_record:
                st.caption(f"Live permission journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live permission gate unavailable: {type(exc).__name__}")


def _render_live_order_intent_builder_status():
    st.markdown("#### Live Order Intent Builder")
    st.caption(
        "This only builds a live order intent for the next contract workflow. It does not send a trade, "
        "does not contain side, price, or size, and live execution remains disabled. "
        "order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = LiveOrderIntentJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Intent records", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Live allowed", "false")
        if summary.latest_intent_id:
            st.caption(
                f"Latest live order intent={summary.latest_intent_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Live order intent journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live order intent journal unavailable: {type(exc).__name__}")

    permission_intent = st.session_state.get("live_permission_intent")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")
    if permission_decision is not None:
        st.caption(
            f"Permission gate allowed={permission_decision.gate_allowed} | "
            f"order_intent_workflow_allowed={permission_decision.order_intent_workflow_allowed}"
        )
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")
    if draft is not None:
        st.caption(
            f"Proposal draft={draft.draft_id} | status={draft.status} | "
            f"non_executable={draft.non_executable} | executable={draft.executable}"
        )
    if contract is not None:
        st.caption(
            f"Simulated contract={contract.contract_id} | status={contract.contract_status} | "
            f"simulated_only={contract.simulated_only} | executable={contract.executable}"
        )
    disabled = (
        permission_intent is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Complete the permission gate, preflight, proposal draft, and simulated contract before building a live order intent.")

    if st.button(
        "Build Live Order Intent",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_live_order_intent",
    ):
        try:
            result = LiveOrderIntentService().run(
                permission_intent,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            intent = result.intent
            validation_report = result.validation_report
            st.session_state["live_order_intent"] = intent
            st.session_state["live_order_intent_validation_report"] = validation_report
            st.session_state["live_order_intent_journal_record"] = result.journal_record
            st.info(
                "Live order intent evaluated for contract workflow preparation only. "
                f"status={intent.status}, validation_valid={validation_report.valid}, "
                f"order_contract_workflow_allowed={validation_report.order_contract_workflow_allowed}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            if result.journal_record:
                st.caption(f"Live order intent journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live order intent builder unavailable: {type(exc).__name__}")


def _render_live_order_contract_skeleton_status():
    st.markdown("#### Live Order Contract Skeleton")
    st.caption(
        "This only builds a live order contract skeleton for future parameter validation. It does not send a trade, "
        "does not contain side, price, or size, and does not create an MT5 payload. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = LiveOrderContractSkeletonJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Skeleton records", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Live allowed", "false")
        if summary.latest_contract_skeleton_id:
            st.caption(
                f"Latest contract skeleton={summary.latest_contract_skeleton_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Contract skeleton journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live order contract skeleton journal unavailable: {type(exc).__name__}")

    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")
    if live_order_intent is not None:
        st.caption(
            f"Live order intent={live_order_intent.intent_id} | status={live_order_intent.status} | "
            f"contract_workflow_allowed={live_order_intent.order_contract_workflow_allowed}"
        )
    if live_order_intent_validation is not None:
        st.caption(f"Intent validation valid={live_order_intent_validation.valid}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")
    if draft is not None:
        st.caption(f"Proposal draft status={draft.status} | non_executable={draft.non_executable} | executable={draft.executable}")
    if contract is not None:
        st.caption(
            f"Simulated contract status={contract.contract_status} | simulated_only={contract.simulated_only} | "
            f"executable={contract.executable}"
        )
    disabled = (
        live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a valid live order intent before creating the contract skeleton.")

    if st.button(
        "Build Live Order Contract Skeleton",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_live_order_contract_skeleton",
    ):
        try:
            result = LiveOrderContractSkeletonService().run(
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            skeleton = result.skeleton
            validation_report = result.validation_report
            st.session_state["live_order_contract_skeleton"] = skeleton
            st.session_state["live_order_contract_skeleton_validation_report"] = validation_report
            st.session_state["live_order_contract_skeleton_journal_record"] = result.journal_record
            st.info(
                "Live order contract skeleton evaluated for future parameter validation only. "
                f"status={skeleton.status}, validation_valid={validation_report.valid}, "
                f"contract_parameter_validation_allowed={validation_report.contract_parameter_validation_allowed}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Required parameter groups={', '.join(skeleton.required_parameter_groups)} | "
                f"Missing parameter groups={', '.join(skeleton.missing_parameter_groups)}"
            )
            if result.journal_record:
                st.caption(f"Live order contract skeleton journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live order contract skeleton unavailable: {type(exc).__name__}")


def _render_live_order_parameter_policy_status():
    st.markdown("#### Live Order Parameter Policy Validator")
    st.caption(
        "This only validates parameter policies. It does not create actual order parameters, does not contain side, "
        "price, protection, volume, or risk values, and does not create an MT5 payload. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = LiveOrderParameterPolicyJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Policy records", summary.total_records)
        cols[1].metric("Validated", summary.total_validated)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Actual values", "false")
        if summary.latest_policy_spec_id:
            st.caption(
                f"Latest parameter policy={summary.latest_policy_spec_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Parameter policy journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live order parameter policy journal unavailable: {type(exc).__name__}")

    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if contract_skeleton is not None:
        st.caption(
            f"Contract skeleton={contract_skeleton.contract_skeleton_id} | status={contract_skeleton.status} | "
            f"parameter_validation_allowed={contract_skeleton.contract_parameter_validation_allowed}"
        )
    if contract_skeleton_validation is not None:
        st.caption(f"Skeleton validation valid={contract_skeleton_validation.valid}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")
    if draft is not None:
        st.caption(f"Proposal draft status={draft.status} | non_executable={draft.non_executable} | executable={draft.executable}")
    if contract is not None:
        st.caption(
            f"Simulated contract status={contract.contract_status} | simulated_only={contract.simulated_only} | "
            f"executable={contract.executable}"
        )
    disabled = (
        contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a valid live order contract skeleton before validating parameter policies.")

    if st.button(
        "Validate Live Order Parameter Policies",
        disabled=disabled,
        use_container_width=True,
        key="dash_validate_live_order_parameter_policies",
    ):
        try:
            result = LiveOrderParameterPolicyService().run(
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            policy_spec = result.policy_spec
            validation_report = result.validation_report
            st.session_state["live_order_parameter_policy_spec"] = policy_spec
            st.session_state["live_order_parameter_policy_validation_report"] = validation_report
            st.session_state["live_order_parameter_policy_journal_record"] = result.journal_record
            st.info(
                "Live order parameter policies evaluated for future source-boundary preparation only. "
                f"status={policy_spec.status}, validation_valid={validation_report.valid}, "
                f"parameter_source_boundary_allowed={validation_report.parameter_source_boundary_allowed}, "
                f"resolved_parameter_values_present={validation_report.resolved_parameter_values_present}, "
                f"actual_order_values_present={validation_report.actual_order_values_present}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Policy groups={', '.join(policy_spec.required_parameter_groups)} | "
                f"Policy rules={len(policy_spec.policy_rules)} | Unresolved groups={len(policy_spec.unresolved_parameter_groups)}"
            )
            if result.journal_record:
                st.caption(f"Live order parameter policy journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live order parameter policy validator unavailable: {type(exc).__name__}")


def _render_live_order_parameter_source_boundary_status():
    st.markdown("#### Live Order Parameter Source Boundary")
    st.caption(
        "This only defines allowed future parameter sources. It does not create actual order parameters, "
        "does not contain side, price, protection, volume, or risk values, and does not create an MT5 payload. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = LiveOrderParameterSourceJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Source records", summary.total_records)
        cols[1].metric("Validated", summary.total_validated)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Actual values", "false")
        if summary.latest_boundary_id:
            st.caption(
                f"Latest parameter source boundary={summary.latest_boundary_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Parameter source journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Live order parameter source journal unavailable: {type(exc).__name__}")

    policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if policy_spec is not None:
        st.caption(
            f"Parameter policy={policy_spec.policy_spec_id} | status={policy_spec.status} | "
            f"source_boundary_allowed={policy_spec.parameter_source_boundary_allowed}"
        )
    if policy_validation is not None:
        st.caption(f"Parameter policy validation valid={policy_validation.valid}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")
    disabled = (
        policy_spec is None
        or policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Validate live order parameter policies before building the parameter source boundary.")

    if st.button(
        "Build Live Order Parameter Source Boundary",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_live_order_parameter_source_boundary",
    ):
        try:
            result = LiveOrderParameterSourceBoundaryService().run(
                policy_spec,
                policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            boundary = result.boundary
            validation_report = result.validation_report
            st.session_state["live_order_parameter_source_boundary"] = boundary
            st.session_state["live_order_parameter_source_validation_report"] = validation_report
            st.session_state["live_order_parameter_source_journal_record"] = result.journal_record
            st.info(
                "Live order parameter source boundary evaluated for future human-reviewed parameter draft only. "
                f"status={boundary.status}, validation_valid={validation_report.valid}, "
                f"human_reviewed_parameter_draft_allowed={validation_report.human_reviewed_parameter_draft_allowed}, "
                f"source_candidates_count={validation_report.source_candidates_count}, "
                f"missing_sources_count={validation_report.missing_sources_count}, "
                f"resolved_parameter_values_present={validation_report.resolved_parameter_values_present}, "
                f"actual_order_values_present={validation_report.actual_order_values_present}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Required source types={', '.join(boundary.required_source_types)} | "
                f"Missing source types={', '.join(boundary.missing_source_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Live order parameter source journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live order parameter source boundary unavailable: {type(exc).__name__}")


def _render_human_reviewed_live_parameter_draft_status():
    st.markdown("#### Human-Reviewed Live Parameter Draft")
    st.caption(
        "This only builds unresolved human-review parameter slots. It does not create actual order parameters, "
        "does not contain side, price, protection, volume, or risk values, and does not create an MT5 payload. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = HumanReviewedLiveParameterDraftJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Draft records", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Actual values", "false")
        if summary.latest_draft_id:
            st.caption(
                f"Latest human-reviewed parameter draft={summary.latest_draft_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Parameter draft journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Human-reviewed parameter draft journal unavailable: {type(exc).__name__}")

    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if parameter_source_boundary is not None:
        st.caption(
            f"Parameter source boundary={parameter_source_boundary.boundary_id} | "
            f"status={parameter_source_boundary.status} | "
            f"human_review_allowed={parameter_source_boundary.human_reviewed_parameter_draft_allowed}"
        )
    if parameter_source_validation is not None:
        st.caption(f"Parameter source validation valid={parameter_source_validation.valid}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    disabled = (
        parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build the live order parameter source boundary before building unresolved parameter draft slots.")

    if st.button(
        "Build Human-Reviewed Parameter Draft",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_human_reviewed_parameter_draft",
    ):
        try:
            result = HumanReviewedLiveParameterDraftService().run(
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            parameter_draft = result.draft
            validation_report = result.validation_report
            st.session_state["human_reviewed_live_parameter_draft"] = parameter_draft
            st.session_state["human_reviewed_live_parameter_draft_validation_report"] = validation_report
            st.session_state["human_reviewed_live_parameter_draft_journal_record"] = result.journal_record
            st.info(
                "Human-reviewed live parameter draft evaluated for future controlled value proposals only. "
                f"status={parameter_draft.status}, validation_valid={validation_report.valid}, "
                f"value_proposal_workflow_allowed={validation_report.value_proposal_workflow_allowed}, "
                f"slots_count={validation_report.slots_count}, "
                f"unresolved_slots_count={validation_report.unresolved_slots_count}, "
                f"resolved_slots_count={validation_report.resolved_slots_count}, "
                f"missing_slots_count={validation_report.missing_slots_count}, "
                f"resolved_parameter_values_present={validation_report.resolved_parameter_values_present}, "
                f"actual_order_values_present={validation_report.actual_order_values_present}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Slot types={', '.join(parameter_draft.required_slot_types)} | "
                f"Missing slots={', '.join(parameter_draft.missing_slot_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Human-reviewed parameter draft journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Human-reviewed live parameter draft unavailable: {type(exc).__name__}")


def _render_controlled_live_parameter_value_proposal_status():
    st.markdown("#### Controlled Live Parameter Value Proposal")
    st.caption(
        "This only builds a controlled value proposal boundary. It does not send a trade, does not create an MT5 payload, "
        "and does not create an executable order. Human approval and value lock are still required. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = ControlledLiveParameterValueProposalJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Proposal records", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Contract ready", "false")
        if summary.latest_proposal_id:
            st.caption(
                f"Latest controlled value proposal={summary.latest_proposal_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Controlled value proposal journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Controlled value proposal journal unavailable: {type(exc).__name__}")

    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if parameter_draft is not None:
        st.caption(
            f"Parameter draft={parameter_draft.draft_id} | status={parameter_draft.status} | "
            f"value_proposal_workflow_allowed={parameter_draft.value_proposal_workflow_allowed}"
        )
    if parameter_draft_validation is not None:
        st.caption(f"Parameter draft validation valid={parameter_draft_validation.valid}")
    if parameter_source_boundary is not None:
        st.caption(f"Parameter source boundary status={parameter_source_boundary.status}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    disabled = (
        parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a human-reviewed parameter draft before building the controlled value proposal boundary.")

    if st.button(
        "Build Controlled Value Proposal",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_controlled_value_proposal",
    ):
        try:
            result = ControlledLiveParameterValueProposalService().run(
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            proposal = result.proposal
            validation_report = result.validation_report
            st.session_state["controlled_live_parameter_value_proposal"] = proposal
            st.session_state["controlled_live_parameter_value_proposal_validation_report"] = validation_report
            st.session_state["controlled_live_parameter_value_proposal_journal_record"] = result.journal_record
            st.info(
                "Controlled live parameter value proposal evaluated for future human value approval only. "
                f"status={proposal.status}, validation_valid={validation_report.valid}, "
                f"human_value_approval_allowed={validation_report.human_value_approval_allowed}, "
                f"value_slots_count={validation_report.value_slots_count}, "
                f"review_required_slots_count={validation_report.review_required_slots_count}, "
                f"approved_slots_count={validation_report.approved_slots_count}, "
                f"rejected_slots_count={validation_report.rejected_slots_count}, "
                f"missing_slots_count={validation_report.missing_slots_count}, "
                f"value_lock_required={validation_report.value_lock_required}, "
                f"human_review_required={validation_report.human_review_required}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Value slot types={', '.join(proposal.required_value_slot_types)} | "
                f"Missing slots={', '.join(proposal.missing_value_slot_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Controlled value proposal journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Controlled live parameter value proposal unavailable: {type(exc).__name__}")


def _render_human_value_approval_lock_status():
    st.markdown("#### Human Value Approval and Lock Boundary")
    st.caption(
        "This only locks human approval for future contract parameterization. It does not send a trade, "
        "does not create an MT5 payload, does not create an executable order, and does not mark order contract ready. "
        "Live execution remains disabled, order submission remains disabled, executed=false, order_sent=false."
    )
    try:
        store = HumanValueApprovalLockJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Approval locks", summary.total_records)
        cols[1].metric("Locked", summary.total_locked)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Raw values", "false")
        if summary.latest_approval_lock_id:
            st.caption(
                f"Latest human value approval lock={summary.latest_approval_lock_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Human value approval lock journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Human value approval lock journal unavailable: {type(exc).__name__}")

    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if value_proposal is not None:
        st.caption(
            f"Controlled value proposal={value_proposal.proposal_id} | status={value_proposal.status} | "
            f"human_value_approval_allowed={value_proposal.human_value_approval_allowed}"
        )
    if value_proposal_validation is not None:
        st.caption(f"Controlled value proposal validation valid={value_proposal_validation.valid}")
    if parameter_draft is not None:
        st.caption(f"Parameter draft status={parameter_draft.status}")
    if parameter_source_boundary is not None:
        st.caption(f"Parameter source boundary status={parameter_source_boundary.status}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    st.caption(f"Required exact phrase: `{EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE}`")
    confirmation_phrase = st.text_input(
        "Type the exact phrase to build a future-parameterization-only approval lock",
        key="dash_human_value_approval_lock_phrase",
    )
    disabled = (
        value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a controlled value proposal before building the human value approval lock boundary.")

    if st.button(
        "Build Human Value Approval Lock",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_human_value_approval_lock",
    ):
        try:
            result = HumanValueApprovalLockService().run(
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
                confirmation_phrase=confirmation_phrase,
            )
            approval_lock = result.approval_lock
            validation_report = result.validation_report
            st.session_state["human_value_approval_lock"] = approval_lock
            st.session_state["human_value_approval_lock_validation_report"] = validation_report
            st.session_state["human_value_approval_lock_journal_record"] = result.journal_record
            st.info(
                "Human value approval lock evaluated for future contract parameterization only. "
                f"status={approval_lock.status}, validation_valid={validation_report.valid}, "
                f"contract_parameterization_workflow_allowed={validation_report.contract_parameterization_workflow_allowed}, "
                f"confirmation_phrase_valid={validation_report.confirmation_phrase_valid}, "
                f"slot_locks_count={validation_report.slot_locks_count}, "
                f"locked_slots_count={validation_report.locked_slots_count}, "
                f"rejected_slots_count={validation_report.rejected_slots_count}, "
                f"missing_slots_count={validation_report.missing_slots_count}, "
                f"value_lock_required={validation_report.value_lock_required}, "
                f"human_review_required={validation_report.human_review_required}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Slot lock types={', '.join(approval_lock.required_slot_lock_types)} | "
                f"Missing slot locks={', '.join(approval_lock.missing_slot_lock_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Human value approval lock journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Human value approval lock unavailable: {type(exc).__name__}")


def _render_live_order_contract_parameterization_status():
    st.markdown("#### Live Order Contract Parameterization Boundary")
    st.caption(
        "This only builds a contract parameterization boundary for future validation. It does not send a trade, "
        "does not create an MT5 payload, does not create an executable order, does not allow broker order request mapping yet, "
        "and does not mark order contract ready. Live execution remains disabled, order_send remains disabled, "
        "executed=false, order_sent=false."
    )
    try:
        store = LiveOrderContractParameterizationJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Parameterizations", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Order mapping", "false")
        if summary.latest_parameterization_id:
            st.caption(
                f"Latest contract parameterization={summary.latest_parameterization_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Contract parameterization journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Contract parameterization journal unavailable: {type(exc).__name__}")

    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if approval_lock is not None:
        st.caption(
            f"Approval lock={approval_lock.approval_lock_id} | status={approval_lock.status} | "
            f"contract_parameterization_workflow_allowed={approval_lock.contract_parameterization_workflow_allowed}"
        )
    if approval_lock_validation is not None:
        st.caption(f"Approval lock validation valid={approval_lock_validation.valid}")
    if value_proposal is not None:
        st.caption(f"Controlled value proposal status={value_proposal.status}")
    if parameter_draft is not None:
        st.caption(f"Parameter draft status={parameter_draft.status}")
    if parameter_source_boundary is not None:
        st.caption(f"Parameter source boundary status={parameter_source_boundary.status}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    disabled = (
        approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a human value approval lock before building the contract parameterization boundary.")

    if st.button(
        "Build Contract Parameterization Boundary",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_contract_parameterization_boundary",
    ):
        try:
            result = LiveOrderContractParameterizationService().run(
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            parameterization = result.parameterization
            validation_report = result.validation_report
            st.session_state["live_order_contract_parameterization"] = parameterization
            st.session_state["live_order_contract_parameterization_validation_report"] = validation_report
            st.session_state["live_order_contract_parameterization_journal_record"] = result.journal_record
            st.info(
                "Live order contract parameterization evaluated for future contract validation only. "
                f"status={parameterization.status}, validation_valid={validation_report.valid}, "
                f"contract_validation_workflow_allowed={validation_report.contract_validation_workflow_allowed}, "
                f"contract_slots_count={validation_report.contract_slots_count}, "
                f"parameterized_slots_count={validation_report.parameterized_slots_count}, "
                f"missing_slots_count={validation_report.missing_slots_count}, "
                f"invalid_slots_count={validation_report.invalid_slots_count}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Contract slot types={', '.join(parameterization.required_contract_slot_types)} | "
                f"Missing contract slots={', '.join(parameterization.missing_contract_slot_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Contract parameterization journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Live order contract parameterization unavailable: {type(exc).__name__}")


def _render_live_order_contract_final_review_status():
    st.markdown("#### Contract Parameter Validation and Final Human Review")
    st.caption(
        "This only validates the contract parameterization for a future Pre-MT5 mapping boundary. "
        "It does not send a trade, does not create an MT5 payload, does not create an executable order, "
        "does not create broker mapping, does not allow order request mapping in this sprint, "
        "and does not mark order contract ready. Live execution remains disabled, order_send remains disabled, "
        "executed=false, order_sent=false."
    )
    try:
        store = LiveOrderContractFinalReviewJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Final reviews", summary.total_records)
        cols[1].metric("Approved", summary.total_approved)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Broker mapping", "false")
        if summary.latest_final_review_id:
            st.caption(
                f"Latest contract final review={summary.latest_final_review_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Contract final review journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Contract final review journal unavailable: {type(exc).__name__}")

    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if parameterization is not None:
        st.caption(
            f"Contract parameterization={parameterization.parameterization_id} | status={parameterization.status} | "
            f"contract_validation_workflow_allowed={parameterization.contract_validation_workflow_allowed}"
        )
    if parameterization_validation is not None:
        st.caption(f"Contract parameterization validation valid={parameterization_validation.valid}")
    if approval_lock is not None:
        st.caption(f"Approval lock status={approval_lock.status}")
    if value_proposal is not None:
        st.caption(f"Controlled value proposal status={value_proposal.status}")
    if parameter_draft is not None:
        st.caption(f"Parameter draft status={parameter_draft.status}")
    if parameter_source_boundary is not None:
        st.caption(f"Parameter source boundary status={parameter_source_boundary.status}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    st.caption(f"Required exact phrase: `{EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE}`")
    confirmation_phrase = st.text_input(
        "Type the exact phrase to build a future Pre-MT5 mapping-boundary-only final review",
        key="dash_contract_final_review_phrase",
    )
    disabled = (
        parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a contract parameterization boundary before building the contract final review.")

    if st.button(
        "Build Contract Final Review",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_contract_final_review",
    ):
        try:
            result = LiveOrderContractFinalReviewService().run(
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
                confirmation_phrase=confirmation_phrase,
            )
            final_review = result.final_review
            validation_report = result.validation_report
            st.session_state["live_order_contract_final_review"] = final_review
            st.session_state["live_order_contract_final_review_validation_report"] = validation_report
            st.session_state["live_order_contract_final_review_journal_record"] = result.journal_record
            st.info(
                "Contract final review evaluated for a future Pre-MT5 mapping boundary only. "
                f"status={final_review.status}, validation_valid={validation_report.valid}, "
                f"pre_mt5_mapping_boundary_workflow_allowed={validation_report.pre_mt5_mapping_boundary_workflow_allowed}, "
                f"confirmation_phrase_valid={validation_report.confirmation_phrase_valid}, "
                f"slot_validations_count={validation_report.slot_validations_count}, "
                f"passed_slot_validations_count={validation_report.passed_slot_validations_count}, "
                f"blocked_slot_validations_count={validation_report.blocked_slot_validations_count}, "
                f"missing_slot_validations_count={validation_report.missing_slot_validations_count}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, mt5_payload_created={validation_report.mt5_payload_created}, "
                f"order_sent={validation_report.order_sent}, hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Slot validation types={', '.join(final_review.required_slot_validation_types)} | "
                f"Missing slot validations={', '.join(final_review.missing_slot_validation_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Contract final review journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Contract final review unavailable: {type(exc).__name__}")


def _render_pre_mt5_order_request_mapping_status():
    st.markdown("#### Pre-MT5 Order Request Mapping Boundary")
    st.caption(
        "This only builds a Pre-MT5 mapping boundary for a future dry-run payload validator. "
        "It does not send a trade, does not create MT5 payload, does not create an MT5 request dictionary, "
        "does not create an executable order, does not create broker submission mapping, "
        "and does not mark order contract ready. Live execution remains disabled, order_send remains disabled, "
        "executed=false, order_sent=false."
    )
    try:
        store = PreMT5OrderRequestMappingJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Mapping boundaries", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("MT5 payload", "false")
        if summary.latest_mapping_boundary_id:
            st.caption(
                f"Latest Pre-MT5 mapping boundary={summary.latest_mapping_boundary_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("Pre-MT5 mapping journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"Pre-MT5 mapping journal unavailable: {type(exc).__name__}")

    final_review = st.session_state.get("live_order_contract_final_review")
    final_review_validation = st.session_state.get("live_order_contract_final_review_validation_report")
    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if final_review is not None:
        st.caption(
            f"Contract final review={final_review.final_review_id} | status={final_review.status} | "
            f"pre_mt5_mapping_boundary_workflow_allowed={final_review.pre_mt5_mapping_boundary_workflow_allowed}"
        )
    if final_review_validation is not None:
        st.caption(f"Contract final review validation valid={final_review_validation.valid}")
    if parameterization is not None:
        st.caption(f"Contract parameterization status={parameterization.status}")
    if approval_lock is not None:
        st.caption(f"Approval lock status={approval_lock.status}")
    if value_proposal is not None:
        st.caption(f"Controlled value proposal status={value_proposal.status}")
    if parameter_draft is not None:
        st.caption(f"Parameter draft status={parameter_draft.status}")
    if parameter_source_boundary is not None:
        st.caption(f"Parameter source boundary status={parameter_source_boundary.status}")
    if parameter_policy_spec is not None:
        st.caption(f"Parameter policy status={parameter_policy_spec.status}")
    if contract_skeleton is not None:
        st.caption(f"Contract skeleton status={contract_skeleton.status}")
    if live_order_intent is not None:
        st.caption(f"Live order intent status={live_order_intent.status}")
    if permission_decision is not None:
        st.caption(f"Permission gate allowed={permission_decision.gate_allowed}")
    if preflight_report is not None:
        st.caption(f"Preflight status={preflight_report.preflight_status}")

    disabled = (
        final_review is None
        or final_review_validation is None
        or parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a contract final review before building the Pre-MT5 mapping boundary.")

    if st.button(
        "Build Pre-MT5 Mapping Boundary",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_pre_mt5_mapping_boundary",
    ):
        try:
            result = PreMT5OrderRequestMappingService().run(
                final_review,
                final_review_validation,
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            boundary = result.mapping_boundary
            validation_report = result.validation_report
            st.session_state["pre_mt5_order_request_mapping_boundary"] = boundary
            st.session_state["pre_mt5_order_request_mapping_validation_report"] = validation_report
            st.session_state["pre_mt5_order_request_mapping_journal_record"] = result.journal_record
            st.info(
                "Pre-MT5 mapping boundary evaluated for a future dry-run payload validator only. "
                f"status={boundary.status}, validation_valid={validation_report.valid}, "
                f"mt5_dry_run_payload_validation_workflow_allowed="
                f"{validation_report.mt5_dry_run_payload_validation_workflow_allowed}, "
                f"mapping_slots_count={validation_report.mapping_slots_count}, "
                f"mapped_slots_count={validation_report.mapped_slots_count}, "
                f"missing_slots_count={validation_report.missing_slots_count}, "
                f"invalid_slots_count={validation_report.invalid_slots_count}, "
                f"mt5_request_dict_created={validation_report.mt5_request_dict_created}, "
                f"mt5_payload_created={validation_report.mt5_payload_created}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, order_sent={validation_report.order_sent}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Mapping slot types={', '.join(boundary.required_mapping_slot_types)} | "
                f"Missing mapping slots={', '.join(boundary.missing_mapping_slot_types) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"Pre-MT5 mapping journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"Pre-MT5 mapping boundary unavailable: {type(exc).__name__}")


def _render_mt5_dry_run_payload_validator_status():
    st.markdown("#### MT5 Order Request Dry-Run Payload Validator")
    st.caption(
        "This only validates MT5 dry-run payload shape. It does not create a real MT5 payload, "
        "does not create an MT5 request dictionary, does not create an executable order, and does not call MT5. "
        "Live execution remains disabled and order_send remains disabled."
    )
    try:
        store = MT5DryRunPayloadValidationJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Dry-run validations", summary.total_records)
        cols[1].metric("Validated", summary.total_validated)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("MT5 constants", "false")
        if summary.latest_dry_run_validation_id:
            st.caption(
                f"Latest MT5 dry-run validation={summary.latest_dry_run_validation_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("MT5 dry-run payload validation journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 dry-run payload validation journal unavailable: {type(exc).__name__}")

    pre_mt5_mapping = st.session_state.get("pre_mt5_order_request_mapping_boundary")
    pre_mt5_mapping_validation = st.session_state.get("pre_mt5_order_request_mapping_validation_report")
    final_review = st.session_state.get("live_order_contract_final_review")
    final_review_validation = st.session_state.get("live_order_contract_final_review_validation_report")
    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if pre_mt5_mapping is not None:
        st.caption(
            f"Pre-MT5 mapping={pre_mt5_mapping.mapping_boundary_id} | status={pre_mt5_mapping.status} | "
            f"mt5_dry_run_payload_validation_workflow_allowed="
            f"{pre_mt5_mapping.mt5_dry_run_payload_validation_workflow_allowed}"
        )
    if pre_mt5_mapping_validation is not None:
        st.caption(f"Pre-MT5 mapping validation valid={pre_mt5_mapping_validation.valid}")

    disabled = (
        pre_mt5_mapping is None
        or pre_mt5_mapping_validation is None
        or final_review is None
        or final_review_validation is None
        or parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build a Pre-MT5 mapping boundary before validating MT5 dry-run payload shape.")

    if st.button(
        "Validate MT5 Dry-Run Payload Shape",
        disabled=disabled,
        use_container_width=True,
        key="dash_validate_mt5_dry_run_payload_shape",
    ):
        try:
            result = MT5OrderRequestDryRunPayloadValidationService().run(
                pre_mt5_mapping,
                pre_mt5_mapping_validation,
                final_review,
                final_review_validation,
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            dry_run_validation = result.dry_run_validation
            validation_report = result.validation_report
            st.session_state["mt5_order_request_dry_run_payload_validation"] = dry_run_validation
            st.session_state["mt5_order_request_dry_run_payload_validation_report"] = validation_report
            st.session_state["mt5_order_request_dry_run_payload_validation_journal_record"] = result.journal_record
            st.info(
                "MT5 dry-run payload shape evaluated for a future request draft boundary only. "
                f"status={dry_run_validation.status}, validation_valid={validation_report.valid}, "
                f"mt5_request_draft_workflow_allowed={validation_report.mt5_request_draft_workflow_allowed}, "
                f"field_validations_count={validation_report.field_validations_count}, "
                f"validated_fields_count={validation_report.validated_fields_count}, "
                f"missing_fields_count={validation_report.missing_fields_count}, "
                f"invalid_fields_count={validation_report.invalid_fields_count}, "
                f"mt5_payload_created={validation_report.mt5_payload_created}, "
                f"mt5_request_dict_created={validation_report.mt5_request_dict_created}, "
                f"mt5_constants_used={validation_report.mt5_constants_used}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, order_sent={validation_report.order_sent}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Field categories={', '.join(dry_run_validation.required_field_categories)} | "
                f"Missing fields={', '.join(dry_run_validation.missing_field_categories) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"MT5 dry-run payload validation journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 dry-run payload validator unavailable: {type(exc).__name__}")


def _render_mt5_request_draft_boundary_status():
    st.markdown("#### MT5 Request Draft Boundary")
    st.caption(
        "This only builds an MT5 request draft boundary. It does not create a real MT5 payload, "
        "does not create an MT5 request dictionary, does not use MT5 constants, does not create an executable order, "
        "and does not call MT5. Live execution remains disabled and order_send remains disabled."
    )
    try:
        store = MT5RequestDraftJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Request drafts", summary.total_records)
        cols[1].metric("Created", summary.total_created)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Broker submission", "false")
        if summary.latest_request_draft_id:
            st.caption(
                f"Latest request draft={summary.latest_request_draft_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("MT5 request draft journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 request draft journal unavailable: {type(exc).__name__}")

    dry_run_validation = st.session_state.get("mt5_order_request_dry_run_payload_validation")
    dry_run_validation_report = st.session_state.get("mt5_order_request_dry_run_payload_validation_report")
    pre_mt5_mapping = st.session_state.get("pre_mt5_order_request_mapping_boundary")
    pre_mt5_mapping_validation = st.session_state.get("pre_mt5_order_request_mapping_validation_report")
    final_review = st.session_state.get("live_order_contract_final_review")
    final_review_validation = st.session_state.get("live_order_contract_final_review_validation_report")
    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if dry_run_validation is not None:
        st.caption(
            f"Dry-run payload validation={dry_run_validation.dry_run_validation_id} | "
            f"status={dry_run_validation.status} | "
            f"mt5_request_draft_workflow_allowed={dry_run_validation.mt5_request_draft_workflow_allowed}"
        )
    if dry_run_validation_report is not None:
        st.caption(f"Dry-run payload validation report valid={dry_run_validation_report.valid}")

    disabled = (
        dry_run_validation is None
        or dry_run_validation_report is None
        or pre_mt5_mapping is None
        or pre_mt5_mapping_validation is None
        or final_review is None
        or final_review_validation is None
        or parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Validate the MT5 dry-run payload shape before building the MT5 request draft boundary.")

    if st.button(
        "Build MT5 Request Draft Boundary",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_mt5_request_draft_boundary",
    ):
        try:
            result = MT5RequestDraftService().run(
                dry_run_validation,
                dry_run_validation_report,
                pre_mt5_mapping,
                pre_mt5_mapping_validation,
                final_review,
                final_review_validation,
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            request_draft = result.request_draft
            validation_report = result.validation_report
            st.session_state["mt5_request_draft_boundary"] = request_draft
            st.session_state["mt5_request_draft_validation_report"] = validation_report
            st.session_state["mt5_request_draft_journal_record"] = result.journal_record
            st.info(
                "MT5 request draft boundary evaluated for a future final approval workflow only. "
                f"status={request_draft.status}, validation_valid={validation_report.valid}, "
                f"mt5_request_draft_final_approval_workflow_allowed="
                f"{validation_report.mt5_request_draft_final_approval_workflow_allowed}, "
                f"draft_fields_count={validation_report.draft_fields_count}, "
                f"created_draft_fields_count={validation_report.created_draft_fields_count}, "
                f"missing_draft_fields_count={validation_report.missing_draft_fields_count}, "
                f"invalid_draft_fields_count={validation_report.invalid_draft_fields_count}, "
                f"mt5_payload_created={validation_report.mt5_payload_created}, "
                f"mt5_request_dict_created={validation_report.mt5_request_dict_created}, "
                f"mt5_constants_used={validation_report.mt5_constants_used}, "
                f"broker_submission_created={validation_report.broker_submission_created}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, "
                f"execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, order_sent={validation_report.order_sent}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Draft field categories={', '.join(request_draft.required_draft_field_categories)} | "
                f"Missing draft fields={', '.join(request_draft.missing_draft_field_categories) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"MT5 request draft journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 request draft boundary unavailable: {type(exc).__name__}")


def _render_mt5_request_draft_final_approval_status():
    st.markdown("#### MT5 Request Draft Final Approval Boundary")
    st.caption(
        "This only approves the MT5 request draft for a future dry-run request dictionary builder. "
        "It does not create a real MT5 payload, does not create an MT5 request dictionary, "
        "does not use MT5 constants, does not create broker submission, does not create an executable order, "
        "and does not call MT5. Live execution remains disabled and order_send remains disabled."
    )
    try:
        store = MT5RequestDraftFinalApprovalJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Final approvals", summary.total_records)
        cols[1].metric("Approved", summary.total_approved)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Broker submission", "false")
        if summary.latest_final_approval_id:
            st.caption(
                f"Latest final approval={summary.latest_final_approval_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("MT5 request draft final approval journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 request draft final approval journal unavailable: {type(exc).__name__}")

    request_draft = st.session_state.get("mt5_request_draft_boundary")
    request_draft_validation_report = st.session_state.get("mt5_request_draft_validation_report")
    dry_run_validation = st.session_state.get("mt5_order_request_dry_run_payload_validation")
    dry_run_validation_report = st.session_state.get("mt5_order_request_dry_run_payload_validation_report")
    pre_mt5_mapping = st.session_state.get("pre_mt5_order_request_mapping_boundary")
    pre_mt5_mapping_validation = st.session_state.get("pre_mt5_order_request_mapping_validation_report")
    final_review = st.session_state.get("live_order_contract_final_review")
    final_review_validation = st.session_state.get("live_order_contract_final_review_validation_report")
    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if request_draft is not None:
        st.caption(
            f"Request draft={request_draft.request_draft_id} | status={request_draft.status} | "
            f"mt5_request_draft_final_approval_workflow_allowed="
            f"{request_draft.mt5_request_draft_final_approval_workflow_allowed}"
        )
    if request_draft_validation_report is not None:
        st.caption(f"Request draft validation report valid={request_draft_validation_report.valid}")

    approval_phrase = st.text_input(
        "Final approval phrase",
        type="password",
        key="dash_mt5_request_draft_final_approval_phrase",
    )
    disabled = (
        request_draft is None
        or request_draft_validation_report is None
        or dry_run_validation is None
        or dry_run_validation_report is None
        or pre_mt5_mapping is None
        or pre_mt5_mapping_validation is None
        or final_review is None
        or final_review_validation is None
        or parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Build the MT5 request draft boundary before approving it for the future dry-run request dictionary builder.")

    if st.button(
        "Approve MT5 Request Draft for Dry-Run Builder",
        disabled=disabled,
        use_container_width=True,
        key="dash_approve_mt5_request_draft_final_approval",
    ):
        try:
            result = MT5RequestDraftFinalApprovalService().run(
                request_draft,
                request_draft_validation_report,
                dry_run_validation,
                dry_run_validation_report,
                pre_mt5_mapping,
                pre_mt5_mapping_validation,
                final_review,
                final_review_validation,
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
                confirmation_phrase=approval_phrase,
            )
            final_approval = result.final_approval
            validation_report = result.validation_report
            st.session_state["mt5_request_draft_final_approval"] = final_approval
            st.session_state["mt5_request_draft_final_approval_validation_report"] = validation_report
            st.session_state["mt5_request_draft_final_approval_journal_record"] = result.journal_record
            st.info(
                "MT5 request draft final approval evaluated for a future dry-run request dictionary builder only. "
                f"status={final_approval.status}, validation_valid={validation_report.valid}, "
                f"confirmation_phrase_valid={validation_report.confirmation_phrase_valid}, "
                f"mt5_request_dict_dry_run_builder_workflow_allowed="
                f"{validation_report.mt5_request_dict_dry_run_builder_workflow_allowed}, "
                f"approved_fields_count={validation_report.approved_fields_count}, "
                f"approved_fields_valid_count={validation_report.approved_fields_valid_count}, "
                f"missing_approved_fields_count={validation_report.missing_approved_fields_count}, "
                f"invalid_approved_fields_count={validation_report.invalid_approved_fields_count}, "
                f"mt5_payload_created={validation_report.mt5_payload_created}, "
                f"mt5_request_dict_created={validation_report.mt5_request_dict_created}, "
                f"mt5_constants_used={validation_report.mt5_constants_used}, "
                f"broker_submission_created={validation_report.broker_submission_created}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, "
                f"execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, order_sent={validation_report.order_sent}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Approved field categories={', '.join(final_approval.required_approved_field_categories)} | "
                f"Missing approved fields={', '.join(final_approval.missing_approved_field_categories) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"MT5 request draft final approval journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 request draft final approval unavailable: {type(exc).__name__}")


def _render_mt5_request_dict_dry_run_builder_status():
    st.markdown("#### MT5 Request Dict Dry-Run Builder Boundary")
    st.caption(
        "This only builds a dry-run request-dict boundary for future validation. "
        "It does not create a real MT5 payload. It does not create a broker-submittable MT5 request dictionary. "
        "It does not use MT5 constants. It does not create broker submission. It does not create an executable order. "
        "It does not call MT5. Live execution remains disabled and order_send remains disabled."
    )
    try:
        store = MT5RequestDictDryRunBuilderJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Dry-run request dicts", summary.total_records)
        cols[1].metric("Ready for validation", summary.total_ready)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Broker-submittable", "false")
        if summary.latest_dry_run_request_dict_id:
            st.caption(
                f"Latest dry-run request dict={summary.latest_dry_run_request_dict_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("MT5 request dict dry-run builder journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 request dict dry-run builder journal unavailable: {type(exc).__name__}")

    final_approval = st.session_state.get("mt5_request_draft_final_approval")
    final_approval_validation = st.session_state.get("mt5_request_draft_final_approval_validation_report")
    request_draft = st.session_state.get("mt5_request_draft_boundary")
    request_draft_validation = st.session_state.get("mt5_request_draft_validation_report")
    dry_run_validation = st.session_state.get("mt5_order_request_dry_run_payload_validation")
    dry_run_validation_report = st.session_state.get("mt5_order_request_dry_run_payload_validation_report")
    pre_mt5_mapping = st.session_state.get("pre_mt5_order_request_mapping_boundary")
    pre_mt5_mapping_validation = st.session_state.get("pre_mt5_order_request_mapping_validation_report")
    final_review = st.session_state.get("live_order_contract_final_review")
    final_review_validation = st.session_state.get("live_order_contract_final_review_validation_report")
    parameterization = st.session_state.get("live_order_contract_parameterization")
    parameterization_validation = st.session_state.get("live_order_contract_parameterization_validation_report")
    approval_lock = st.session_state.get("human_value_approval_lock")
    approval_lock_validation = st.session_state.get("human_value_approval_lock_validation_report")
    value_proposal = st.session_state.get("controlled_live_parameter_value_proposal")
    value_proposal_validation = st.session_state.get("controlled_live_parameter_value_proposal_validation_report")
    parameter_draft = st.session_state.get("human_reviewed_live_parameter_draft")
    parameter_draft_validation = st.session_state.get("human_reviewed_live_parameter_draft_validation_report")
    parameter_source_boundary = st.session_state.get("live_order_parameter_source_boundary")
    parameter_source_validation = st.session_state.get("live_order_parameter_source_validation_report")
    parameter_policy_spec = st.session_state.get("live_order_parameter_policy_spec")
    parameter_policy_validation = st.session_state.get("live_order_parameter_policy_validation_report")
    contract_skeleton = st.session_state.get("live_order_contract_skeleton")
    contract_skeleton_validation = st.session_state.get("live_order_contract_skeleton_validation_report")
    live_order_intent = st.session_state.get("live_order_intent")
    live_order_intent_validation = st.session_state.get("live_order_intent_validation_report")
    permission_decision = st.session_state.get("live_permission_gate_decision")
    preflight_report = st.session_state.get("live_execution_preflight_readiness_report")
    draft = st.session_state.get("non_executable_trade_proposal_draft")
    contract = st.session_state.get("simulated_order_contract")
    simulated_receipt = st.session_state.get("simulated_execution_receipt")

    if final_approval is not None:
        st.caption(
            f"Draft final approval={final_approval.final_approval_id} | status={final_approval.status} | "
            f"mt5_request_dict_dry_run_builder_workflow_allowed="
            f"{final_approval.mt5_request_dict_dry_run_builder_workflow_allowed}"
        )
    if final_approval_validation is not None:
        st.caption(f"Draft final approval validation report valid={final_approval_validation.valid}")

    disabled = (
        final_approval is None
        or final_approval_validation is None
        or request_draft is None
        or request_draft_validation is None
        or dry_run_validation is None
        or dry_run_validation_report is None
        or pre_mt5_mapping is None
        or pre_mt5_mapping_validation is None
        or final_review is None
        or final_review_validation is None
        or parameterization is None
        or parameterization_validation is None
        or approval_lock is None
        or approval_lock_validation is None
        or value_proposal is None
        or value_proposal_validation is None
        or parameter_draft is None
        or parameter_draft_validation is None
        or parameter_source_boundary is None
        or parameter_source_validation is None
        or parameter_policy_spec is None
        or parameter_policy_validation is None
        or contract_skeleton is None
        or contract_skeleton_validation is None
        or live_order_intent is None
        or live_order_intent_validation is None
        or permission_decision is None
        or preflight_report is None
        or draft is None
        or contract is None
    )
    if disabled:
        st.info("Approve the MT5 request draft for the future dry-run request-dict builder before building this boundary.")

    if st.button(
        "Build MT5 Request Dict Dry-Run Boundary",
        disabled=disabled,
        use_container_width=True,
        key="dash_build_mt5_request_dict_dry_run_builder_boundary",
    ):
        try:
            result = MT5RequestDictDryRunBuilderService().run(
                final_approval,
                final_approval_validation,
                request_draft,
                request_draft_validation,
                dry_run_validation,
                dry_run_validation_report,
                pre_mt5_mapping,
                pre_mt5_mapping_validation,
                final_review,
                final_review_validation,
                parameterization,
                parameterization_validation,
                approval_lock,
                approval_lock_validation,
                value_proposal,
                value_proposal_validation,
                parameter_draft,
                parameter_draft_validation,
                parameter_source_boundary,
                parameter_source_validation,
                parameter_policy_spec,
                parameter_policy_validation,
                contract_skeleton,
                contract_skeleton_validation,
                live_order_intent,
                live_order_intent_validation,
                permission_decision,
                preflight_report,
                draft,
                contract,
                simulated_receipt=simulated_receipt,
            )
            boundary = result.boundary
            validation_report = result.validation_report
            st.session_state["mt5_request_dict_dry_run_builder_boundary"] = boundary
            st.session_state["mt5_request_dict_dry_run_builder_validation_report"] = validation_report
            st.session_state["mt5_request_dict_dry_run_builder_journal_record"] = result.journal_record
            st.info(
                "MT5 request dict dry-run builder boundary evaluated for future final validation only. "
                f"status={boundary.status}, validation_valid={validation_report.valid}, "
                f"mt5_request_dict_final_validation_workflow_allowed="
                f"{validation_report.mt5_request_dict_final_validation_workflow_allowed}, "
                f"dry_run_fields_count={validation_report.dry_run_fields_count}, "
                f"created_dry_run_fields_count={validation_report.created_dry_run_fields_count}, "
                f"missing_dry_run_fields_count={validation_report.missing_dry_run_fields_count}, "
                f"invalid_dry_run_fields_count={validation_report.invalid_dry_run_fields_count}, "
                f"real_mt5_payload_created={validation_report.real_mt5_payload_created}, "
                f"broker_submittable_request_dict_created="
                f"{validation_report.broker_submittable_request_dict_created}, "
                f"mt5_constants_used={validation_report.mt5_constants_used}, "
                f"broker_submission_created={validation_report.broker_submission_created}, "
                f"raw_values_stored={validation_report.raw_values_stored}, "
                f"executable_order_created={validation_report.executable_order_created}, "
                f"broker_mapping_created={validation_report.broker_mapping_created}, "
                f"order_request_mapping_allowed={validation_report.order_request_mapping_allowed}, "
                f"order_contract_ready={validation_report.order_contract_ready}, "
                f"live_execution_allowed={validation_report.live_execution_allowed}, "
                f"order_send_allowed={validation_report.order_send_allowed}, "
                f"execution_allowed={validation_report.execution_allowed}, "
                f"executable={validation_report.executable}, order_sent={validation_report.order_sent}, "
                f"hard_live_block_required={validation_report.hard_live_block_required}"
            )
            st.caption(
                f"Dry-run key labels={', '.join(field.dry_run_key_label for field in boundary.dry_run_fields)} | "
                f"Missing dry-run fields={', '.join(boundary.missing_dry_run_field_categories) or 'none'}"
            )
            if result.journal_record:
                st.caption(f"MT5 request dict dry-run builder journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 request dict dry-run builder unavailable: {type(exc).__name__}")


def _render_mt5_request_dict_final_validation_and_bridge_skeleton_status():
    st.markdown("#### MT5 Request Dict Final Validation + Bridge Write Skeleton")
    st.caption(
        "This validates the dry-run request dict boundary and checks that the bridge write skeleton is reachable "
        "but hard-blocked. It does not send an order."
    )
    try:
        store = MT5RequestDictFinalValidationJournalStore()
        summary = store.summarize()
        cols = st.columns(4)
        cols[0].metric("Final validations", summary.total_records)
        cols[1].metric("Passed", summary.total_passed)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Execution", "false")
        if summary.latest_final_validation_id:
            st.caption(
                f"Latest final validation={summary.latest_final_validation_id} | "
                f"status={summary.latest_status} | validation={summary.latest_validation_report_id}"
            )
        if summary.warnings:
            st.caption("MT5 request dict final validation journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 request dict final validation journal unavailable: {type(exc).__name__}")

    dry_run_boundary = st.session_state.get("mt5_request_dict_dry_run_builder_boundary")
    dry_run_report = st.session_state.get("mt5_request_dict_dry_run_builder_validation_report")
    final_validation = st.session_state.get("mt5_request_dict_final_validation")
    final_validation_report = st.session_state.get("mt5_request_dict_final_validation_report")
    bridge_check = st.session_state.get("mt5_bridge_write_skeleton_check")

    if dry_run_boundary is not None:
        st.caption(
            f"Dry-run request dict={dry_run_boundary.dry_run_request_dict_id} | status={dry_run_boundary.status} | "
            f"mt5_request_dict_final_validation_workflow_allowed="
            f"{dry_run_boundary.mt5_request_dict_final_validation_workflow_allowed}"
        )
    if final_validation_report is not None:
        st.caption(
            f"Final validation status={final_validation.status if final_validation else 'n/a'} | "
            f"bridge_write_skeleton_check_allowed={final_validation_report.bridge_write_skeleton_check_allowed} | "
            f"validated_fields_count={final_validation_report.validated_fields_count} | "
            f"missing_fields_count={final_validation_report.missing_fields_count} | "
            f"invalid_fields_count={final_validation_report.invalid_fields_count} | "
            f"live_execution_allowed={final_validation_report.live_execution_allowed} | "
            f"order_send_allowed={final_validation_report.order_send_allowed} | "
            f"execution_allowed={final_validation_report.execution_allowed} | "
            f"order_sent={final_validation_report.order_sent} | "
            f"hard_live_block_required={final_validation_report.hard_live_block_required}"
        )
    if bridge_check is not None:
        st.caption(
            f"Bridge write skeleton reachable={bridge_check.reachable} | status={bridge_check.status} | "
            f"write_skeleton_available={bridge_check.write_skeleton_available} | "
            f"live_execution_allowed={bridge_check.live_execution_allowed} | "
            f"order_send_allowed={bridge_check.order_send_allowed} | "
            f"execution_allowed={bridge_check.execution_allowed} | "
            f"order_sent={bridge_check.order_sent} | hard_live_block_required={bridge_check.hard_live_block_required}"
        )

    validation_disabled = dry_run_boundary is None or dry_run_report is None
    if validation_disabled:
        st.info("Build the MT5 request dict dry-run boundary before running final validation.")

    if st.button(
        "Validate MT5 Request Dict Boundary",
        disabled=validation_disabled,
        use_container_width=True,
        key="dash_validate_mt5_request_dict_boundary",
    ):
        try:
            result = MT5RequestDictFinalValidationService().run(dry_run_boundary, dry_run_report)
            st.session_state["mt5_request_dict_final_validation"] = result.final_validation
            st.session_state["mt5_request_dict_final_validation_report"] = result.validation_report
            st.session_state["mt5_request_dict_final_validation_journal_record"] = result.journal_record
            st.info(
                "MT5 request dict final validation evaluated for bridge write skeleton check only. "
                f"status={result.final_validation.status}, validation_valid={result.validation_report.valid}, "
                f"bridge_write_skeleton_check_allowed={result.validation_report.bridge_write_skeleton_check_allowed}, "
                f"validated_fields_count={result.validation_report.validated_fields_count}, "
                f"missing_fields_count={result.validation_report.missing_fields_count}, "
                f"invalid_fields_count={result.validation_report.invalid_fields_count}, "
                f"live_execution_allowed={result.validation_report.live_execution_allowed}, "
                f"order_send_allowed={result.validation_report.order_send_allowed}, "
                f"execution_allowed={result.validation_report.execution_allowed}, "
                f"order_sent={result.validation_report.order_sent}, "
                f"hard_live_block_required={result.validation_report.hard_live_block_required}"
            )
            if result.journal_record:
                st.caption(f"MT5 request dict final validation journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 request dict final validation unavailable: {type(exc).__name__}")

    bridge_disabled = final_validation_report is None or not getattr(final_validation_report, "bridge_write_skeleton_check_allowed", False)
    if st.button(
        "Check MT5 Bridge Write Skeleton",
        disabled=bridge_disabled,
        use_container_width=True,
        key="dash_check_mt5_bridge_write_skeleton",
    ):
        try:
            result = MT5BridgeWriteSkeletonService().run()
            st.session_state["mt5_bridge_write_skeleton_check"] = result.check
            st.session_state["mt5_bridge_write_skeleton_validation"] = result.validation
            st.info(
                "MT5 bridge write skeleton checked. "
                f"reachable={result.check.reachable}, status={result.check.status}, "
                f"write_skeleton_available={result.check.write_skeleton_available}, "
                f"live_execution_allowed={result.check.live_execution_allowed}, "
                f"order_send_allowed={result.check.order_send_allowed}, "
                f"execution_allowed={result.check.execution_allowed}, "
                f"order_sent={result.check.order_sent}, ticket={result.check.ticket}, deal={result.check.deal}, "
                f"hard_live_block_required={result.check.hard_live_block_required}"
            )
            if not result.validation.passed:
                st.warning("Bridge write skeleton blocked-response validation failed: " + ", ".join(result.validation.issues))
        except Exception as exc:
            st.warning(f"MT5 bridge write skeleton check unavailable: {type(exc).__name__}")


def _render_mt5_live_adapter_disabled_pre_submit_status():
    st.markdown("#### MT5 Live Adapter Disabled + Pre-Submit Gate")
    st.caption(
        "This runs a disabled pre-submit safety check only. It does not send an order. "
        "Live submission and order_send remain disabled."
    )
    try:
        summary = MT5PreSubmitJournalStore().summarize()
        cols = st.columns(4)
        cols[0].metric("Pre-submit checks", summary.total_records)
        cols[1].metric("Valid", summary.total_valid)
        cols[2].metric("Blocked", summary.total_blocked)
        cols[3].metric("Live submission", "false")
        if summary.latest_report_id:
            st.caption(f"Latest pre-submit report={summary.latest_report_id} | status={summary.latest_status}")
        if summary.warnings:
            st.caption("MT5 pre-submit journal warnings: " + ", ".join(summary.warnings[:3]))
    except Exception as exc:
        st.caption(f"MT5 pre-submit journal unavailable: {type(exc).__name__}")

    final_validation = st.session_state.get("mt5_request_dict_final_validation")
    final_validation_report = st.session_state.get("mt5_request_dict_final_validation_report")
    pre_submit_report = st.session_state.get("mt5_pre_submit_gate_report")
    adapter_receipt = st.session_state.get("mt5_live_adapter_disabled_receipt")
    bridge_check = st.session_state.get("mt5_pre_submit_bridge_write_skeleton_check")

    if pre_submit_report is not None:
        st.caption(
            f"adapter_status={adapter_receipt.adapter_status if adapter_receipt else 'n/a'} | "
            f"pre_submit_gate_status={pre_submit_report.status} | "
            f"controlled_demo_integration_workflow_allowed="
            f"{pre_submit_report.controlled_demo_integration_workflow_allowed} | "
            f"live_submission_allowed={pre_submit_report.live_submission_allowed} | "
            f"bridge_write_skeleton_reachable={pre_submit_report.bridge_write_skeleton_reachable} | "
            f"bridge_write_skeleton_status={pre_submit_report.bridge_write_skeleton_status} | "
            f"kill_switch_engaged={pre_submit_report.kill_switch_engaged} | "
            f"idempotency_status={pre_submit_report.idempotency_status} | "
            f"live_execution_allowed={pre_submit_report.live_execution_allowed} | "
            f"order_send_allowed={pre_submit_report.order_send_allowed} | "
            f"execution_allowed={pre_submit_report.execution_allowed} | "
            f"executable={pre_submit_report.executable} | order_sent={pre_submit_report.order_sent} | "
            f"hard_live_block_required={pre_submit_report.hard_live_block_required}"
        )
    if bridge_check is not None:
        st.caption(f"Bridge skeleton check id={bridge_check.check_id} | status={bridge_check.status}")

    disabled = final_validation is None or final_validation_report is None
    if disabled:
        st.info("Run MT5 request dict final validation before the disabled pre-submit safety check.")

    if st.button(
        "Run MT5 Pre-Submit Safety Check",
        disabled=disabled,
        use_container_width=True,
        key="dash_run_mt5_pre_submit_safety_check",
    ):
        try:
            result = MT5LiveAdapterPreSubmitService().run(final_validation, final_validation_report)
            st.session_state["mt5_pre_submit_gate_report"] = result.report
            st.session_state["mt5_live_adapter_disabled_receipt"] = result.adapter_receipt
            st.session_state["mt5_pre_submit_bridge_write_skeleton_check"] = result.bridge_check
            st.session_state["mt5_kill_switch_check"] = result.kill_switch_check
            st.session_state["mt5_pre_submit_idempotency_check"] = result.idempotency_check
            st.session_state["mt5_pre_submit_journal_record"] = result.journal_record
            st.info(
                "MT5 disabled pre-submit safety check evaluated. "
                f"adapter_status={result.adapter_receipt.adapter_status}, "
                f"pre_submit_status={result.report.status}, valid={result.report.valid}, "
                f"controlled_demo_integration_workflow_allowed="
                f"{result.report.controlled_demo_integration_workflow_allowed}, "
                f"live_submission_allowed={result.report.live_submission_allowed}, "
                f"bridge_write_skeleton_reachable={result.report.bridge_write_skeleton_reachable}, "
                f"bridge_write_skeleton_status={result.report.bridge_write_skeleton_status}, "
                f"kill_switch_engaged={result.report.kill_switch_engaged}, "
                f"idempotency_status={result.report.idempotency_status}, "
                f"live_execution_allowed={result.report.live_execution_allowed}, "
                f"order_send_allowed={result.report.order_send_allowed}, "
                f"execution_allowed={result.report.execution_allowed}, executable={result.report.executable}, "
                f"order_sent={result.report.order_sent}, ticket={result.report.ticket}, deal={result.report.deal}, "
                f"hard_live_block_required={result.report.hard_live_block_required}"
            )
            if result.journal_record:
                st.caption(f"MT5 pre-submit journal record: {result.journal_record.journal_record_id}")
            if result.warning:
                st.warning(result.warning)
        except Exception as exc:
            st.warning(f"MT5 disabled pre-submit safety check unavailable: {type(exc).__name__}")


def _render_ingestion_state():
    """Hiển thị trạng thái file đã index từ ingestion_state.json."""
    try:
        state = load_tracker_state()

        if state:
            with st.expander(f"📋 Chi tiết file đã index ({len(state)} file)"):
                for fname, info in state.items():
                    chunks = info.get("chunk_count", "?")
                    indexed_at = info.get("indexed_at", "?")
                    st.markdown(
                        f"- **{fname}** — `{chunks} chunks` — _{indexed_at}_"
                    )
        else:
            st.caption("📋 Chưa có file nào được index.")
    except Exception:
        st.caption("📋 Không thể đọc trạng thái ingestion.")

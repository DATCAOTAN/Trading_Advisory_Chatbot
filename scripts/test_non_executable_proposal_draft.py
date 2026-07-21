from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.proposal import (
    HumanConfirmedProposalIntent,
    NonExecutableProposalDraftBuilder,
    ProposalDraftFormatter,
    ProposalDraftJournalService,
    ProposalDraftJournalStore,
    ProposalDraftPolicy,
    ProposalDraftService,
    ProposalDraftValidator,
)
from src.services.trading.proposal.draft_models import (
    NonExecutableTradeProposalDraft,
    ProposalDraftJournalRecord,
    now_utc_iso,
)
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.review.models import HumanReviewArtifact
from src.services.trading.scoring.models import SignalScoreReport


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_policy_loads_defaults():
    policy = ProposalDraftPolicy()
    assert policy.enabled is True
    assert policy.non_executable_only is True


def test_policy_require_confirmed_intent_blocks_unconfirmed():
    builder = NonExecutableProposalDraftBuilder(policy=ProposalDraftPolicy(require_confirmed_intent=True))
    draft = builder.build(_intent(status="BLOCKED", allowed=False), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    assert draft.status == "BLOCKED"


def test_builder_creates_draft_from_confirmed_intent():
    draft = _builder().build(_intent(), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    assert draft.status == "DRAFT_CREATED"


def test_builder_creates_blocked_draft_from_blocked_intent_when_allowed():
    draft = _builder().build(_intent(status="BLOCKED", allowed=False), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    assert draft.status == "BLOCKED"


def test_builder_creates_waiting_draft_from_waiting_context_when_allowed():
    draft = _builder().build(_intent(), _artifact(review_status="WAITING", readiness_action="WAIT"), _score(), _selection(), _context(), _calendar(), _regime())
    assert draft.status == "WAITING"


def test_draft_has_non_executable_true():
    assert _draft().non_executable is True


def test_draft_has_executable_false():
    assert _draft().executable is False


def test_draft_preserves_source_ids():
    draft = _draft()
    assert draft.source_intent_id == "intent_fixture"
    assert draft.source_score_report_id == "score_fixture"


def test_draft_preserves_source_refs():
    assert SOURCE_REF in _draft().source_refs


def test_draft_includes_method_thesis_summary():
    assert "vpa_effort_vs_result" in _draft().method_thesis_summary


def test_draft_includes_market_context_summary():
    assert "Regime=BREAKOUT_CANDIDATE" in _draft().market_context_summary


def test_draft_includes_calendar_context_summary():
    assert "Calendar risk=CLEAR" in _draft().calendar_context_summary


def test_draft_includes_score_summary():
    assert _draft().score_summary["final_context_score"] == 0.72


def test_draft_includes_required_human_checks():
    assert _draft().required_human_checks


def test_draft_includes_blockers_warnings():
    draft = _builder().build(_intent(warnings=["boundary_warning"]), _artifact(warnings=["review_warning"]), _score(warnings=["score_warning"]), _selection(), _context(), _calendar(), _regime())
    assert "boundary_warning" in draft.warnings
    assert "review_warning" in draft.warnings
    assert "score_warning" in draft.warnings


def test_draft_excludes_raw_candles():
    assert "raw_candles" not in json.dumps(_draft().as_dict()).lower()


def test_draft_excludes_full_raw_book_report_text():
    payload = json.dumps(_draft().as_dict()).lower()
    assert "full_raw_book" not in payload
    assert "full_raw_report" not in payload


def test_draft_excludes_account_id_credentials():
    payload = json.dumps(_draft().as_dict()).lower()
    assert "account_id" not in payload
    assert "api_key" not in payload
    assert "password" not in payload


def test_formatter_generates_json_safe_card():
    assert ProposalDraftFormatter().to_card(_draft()).as_dict()["status_label"] == "DRAFT_CREATED"


def test_formatter_generates_markdown_summary():
    assert "Non-Executable Proposal Draft" in ProposalDraftFormatter().to_markdown(_draft())


def test_formatter_markdown_has_no_forbidden_execution_markers():
    markdown = ProposalDraftFormatter().to_markdown(_draft()).lower()
    assert "order" + "_send" not in markdown
    assert "entry_price" not in markdown


def test_journal_store_appends_jsonl(tmp_path):
    path = tmp_path / "proposal_drafts.jsonl"
    ProposalDraftJournalStore(path=path).append(_record())
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_journal_store_reads_latest_records(tmp_path):
    store = ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl")
    for index in range(3):
        store.append(_record(draft_id=f"draft_{index}"))
    assert [item.draft_id for item in store.read_latest(2)] == ["draft_1", "draft_2"]


def test_journal_store_summarizes_records(tmp_path):
    store = ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl")
    store.append(_record(status="DRAFT_CREATED"))
    store.append(_record(status="BLOCKED"))
    summary = store.summarize()
    assert summary.total_created == 1
    assert summary.total_blocked == 1


def test_journal_store_summarizes_waiting_records(tmp_path):
    store = ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl")
    store.append(_record(status="WAITING"))
    assert store.summarize().total_waiting == 1


def test_corrupt_journal_line_returns_warning(tmp_path):
    path = tmp_path / "proposal_drafts.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = ProposalDraftJournalStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_validator_rejects_buy_sell():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["contains_" + "buy"])).passed
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["contains_" + "sell"])).passed


def test_validator_rejects_long_short():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["long"])).passed
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["short"])).passed


def test_validator_rejects_trade_side():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["trade_side"])).passed


def test_validator_rejects_price_and_size_markers():
    assert not ProposalDraftValidator().validate_draft(
        _draft(warnings=["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    ).passed


def test_validator_rejects_position_size():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["position_size"])).passed


def test_validator_rejects_order_submission_marker():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["order" + "_send"])).passed


def test_validator_rejects_executable_order_fields():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["real_order_id", "mt5_order_request", "executable_order"])).passed


def test_validator_rejects_raw_candles():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["raw_candles"])).passed


def test_validator_rejects_raw_full_book_report_text():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["full_raw_book", "full_raw_report"])).passed


def test_validator_rejects_account_id_credentials_markers():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["account_id", "api_key", "password"])).passed


def test_validator_rejects_metatrader_marker():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["Meta" + "Trader5"])).passed


def test_validator_rejects_llm_prompt_marker():
    assert not ProposalDraftValidator().validate_draft(_draft(warnings=["compact_prompt"])).passed


def test_validator_rejects_oversized_payload():
    assert not ProposalDraftValidator(max_payload_chars=100).validate_draft(_draft()).passed


def test_validator_accepts_clean_draft():
    assert ProposalDraftValidator().validate_draft(_draft()).passed


def test_validator_accepts_clean_journal_record():
    assert ProposalDraftValidator().validate_record(_record()).passed


def test_draft_service_builds_card_and_record(tmp_path):
    service = ProposalDraftService(
        journal=ProposalDraftJournalService(store=ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl"))
    )
    result = service.build(_intent(), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    assert result.card
    assert result.journal_record


def test_draft_service_returns_warning_when_journal_disabled(tmp_path):
    service = ProposalDraftService(
        journal=ProposalDraftJournalService(store=ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl"), enabled=False)
    )
    result = service.build(_intent(), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    assert result.journal_record is None
    assert result.warning == "proposal_draft_journal_disabled"


def test_journal_service_skips_write_when_disabled(tmp_path):
    service = ProposalDraftJournalService(store=ProposalDraftJournalStore(path=tmp_path / "proposal_drafts.jsonl"), enabled=False)
    assert service.append_draft(_draft(), _intent()) is None


def test_journal_record_forces_non_executable_and_executable_false():
    payload = _record().as_dict()
    assert payload["non_executable"] is True
    assert payload["executable"] is False


def test_runtime_journal_file_contains_no_forbidden_fields(tmp_path):
    path = tmp_path / "proposal_drafts.jsonl"
    ProposalDraftJournalStore(path=path).append(_record())
    payload = path.read_text(encoding="utf-8").lower()
    for marker in ["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk", "account_id"]:
        assert marker not in payload


def test_dashboard_code_does_not_add_confirm_trade_button():
    assert "confirm trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_execute_trade_button():
    assert "execute trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_place_order_button():
    assert "place order" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_buy_sell_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert 'st.button("Buy' not in text
    assert 'st.button("Sell' not in text


def test_dashboard_labels_draft_as_non_executable():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Non-Executable Proposal Draft" in text
    assert "executable=false" in text


def test_proposal_draft_code_does_not_call_llm_or_mt5_or_live_service():
    text = _proposal_source_text()
    assert "LLMReasoningAdapter" not in text
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text


def test_proposal_draft_code_has_no_order_submission_call_marker():
    assert "order" + "_send(" not in _proposal_source_text()


def test_gitignore_ignores_runtime_jsonl():
    assert "data/trading/execution_journal/*.jsonl" in Path(".gitignore").read_text(encoding="utf-8")


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def _builder() -> NonExecutableProposalDraftBuilder:
    return NonExecutableProposalDraftBuilder(policy=ProposalDraftPolicy(max_context_chars=20000))


def _draft(warnings: list[str] | None = None) -> NonExecutableTradeProposalDraft:
    draft = _builder().build(_intent(warnings=warnings or []), _artifact(), _score(), _selection(), _context(), _calendar(), _regime())
    if warnings:
        draft.warnings.extend(warnings)
        draft.payload_size_chars = len(json.dumps(draft.as_dict(), ensure_ascii=False, sort_keys=True))
    return draft


def _intent(status: str = "CONFIRMED_FOR_PROPOSAL_WORKFLOW", allowed: bool = True, warnings: list[str] | None = None) -> HumanConfirmedProposalIntent:
    return HumanConfirmedProposalIntent(
        intent_id="intent_fixture",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        proposal_boundary_status=status,
        human_confirmation_state="CONFIRMED_PROPOSAL_WORKFLOW" if allowed else "NOT_REQUESTED",
        proposal_workflow_allowed=allowed,
        dry_run_only=True,
        executable=False,
        review_status="READY_FOR_REVIEW" if allowed else "WAITING",
        readiness_action="REVIEW_READY" if allowed else "WAIT",
        gate_action="ALLOW_DRY_RUN" if allowed else "BLOCKED",
        dry_run_allowed=allowed,
        dry_run_executed=False,
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        dry_run_receipt_id="receipt_fixture",
        idempotency_key="idem123",
        source_review_artifact_id="artifact_fixture",
        source_gate_decision_id="gate_fixture",
        source_dry_run_receipt_id="receipt_fixture",
        source_execution_journal_record_id="execution_journal_fixture",
        source_refs=[SOURCE_REF],
        warnings=warnings or [],
    )


def _artifact(review_status: str = "READY_FOR_REVIEW", readiness_action: str = "REVIEW_READY", warnings: list[str] | None = None) -> HumanReviewArtifact:
    return HumanReviewArtifact(
        artifact_id="artifact_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        review_status=review_status,
        readiness_action=readiness_action,
        readiness_score=0.72,
        confidence=0.78,
        grade="GOOD",
        primary_method_id="vpa_effort_vs_result",
        selected_playbook_ids=["vpa_confirmation_v1"],
        primary_regime="BREAKOUT_CANDIDATE",
        calendar_risk_state="CLEAR",
        final_context_score=0.72,
        warnings=warnings or [],
        source_refs=[SOURCE_REF],
        source_readiness_decision_id="readiness_fixture",
        source_score_report_id="score_fixture",
        source_method_selection_id="method_selection_fixture",
        source_context_pack_id="context_fixture",
    )


def _score(warnings: list[str] | None = None) -> SignalScoreReport:
    return SignalScoreReport(
        score_report_id="score_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_method_id="vpa_effort_vs_result",
        selected_playbook_ids=["vpa_confirmation_v1"],
        final_context_score=0.72,
        grade="GOOD",
        warnings=warnings or [],
        scoring_summary="Context score is acceptable for review.",
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
        source_regime_snapshot_id="regime_fixture",
        source_context_pack_id="context_fixture",
        source_method_selection_id="method_selection_fixture",
        source_refs=[SOURCE_REF],
    )


def _selection() -> MethodSelectionResult:
    return MethodSelectionResult(
        result_id="method_selection_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        primary_method_id="vpa_effort_vs_result",
        supporting_method_ids=["risk_management_core"],
        selected_playbook_ids=["vpa_confirmation_v1"],
        overall_context_fit=0.8,
        confidence=0.8,
        reasoning_summary="Method context selected for review.",
        source_context_pack_id="context_fixture",
        source_refs=[SOURCE_REF],
    )


def _context() -> RuntimeContextPack:
    return RuntimeContextPack(
        context_pack_id="context_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={"data_quality_status": "COMPLETE"},
        calendar_context_summary={"calendar_risk_state": "CLEAR"},
        market_regime_summary={"primary_regime": "BREAKOUT_CANDIDATE", "confidence": 0.77},
        selected_method_cards=[{"method_id": "vpa_effort_vs_result", "summary": "Volume context"}],
        selected_playbooks=[{"playbook_id": "vpa_confirmation_v1"}],
        source_refs=[SOURCE_REF],
    )


def _calendar() -> CalendarContext:
    return CalendarContext(
        context_id="calendar_fixture",
        symbol="XAUUSD",
        created_at=now_utc_iso(),
        provider_name="forex_factory",
        calendar_risk_state="CLEAR",
        source="forex_factory",
    )


def _regime() -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        regime_snapshot_id="regime_fixture",
        created_at=now_utc_iso(),
        symbol="XAUUSD",
        primary_regime="BREAKOUT_CANDIDATE",
        confidence=0.77,
        volatility_state="HIGH",
        multi_timeframe_alignment="MIXED",
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
    )


def _record(draft_id: str = "draft_fixture", status: str = "DRAFT_CREATED") -> ProposalDraftJournalRecord:
    record = ProposalDraftJournalRecord(
        journal_record_id="proposal_draft_journal_fixture",
        created_at=now_utc_iso(),
        draft_id=draft_id,
        status=status,
        non_executable=True,
        executable=False,
        source_intent_id="intent_fixture",
        artifact_hash="abc123hash",
        primary_method_id="vpa_effort_vs_result",
        primary_regime="BREAKOUT_CANDIDATE",
        calendar_risk_state="CLEAR",
        readiness_action="REVIEW_READY",
        final_context_score=0.72,
        source_refs=[SOURCE_REF],
    )
    record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
    return record


def _proposal_source_text() -> str:
    root = Path("src/services/trading/proposal")
    return "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

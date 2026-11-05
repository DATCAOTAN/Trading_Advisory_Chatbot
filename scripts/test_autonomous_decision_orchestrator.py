from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.run_autonomous_decision_once import main as cli_main
from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_SCHEMA_VERSION,
    AutonomousDecisionConfig,
    AutonomousDecisionInputs,
    AutonomousDecisionIntent,
    AutonomousDecisionJournal,
    AutonomousDecisionJournalError,
    AutonomousDecisionOrchestrator,
    EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
    _canonical_json,
    _journal_row,
    _sha256,
)
from src.services.trading.decision.models import DecisionBlocker, TradeReadinessDecision
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
    MT5LifecycleState,
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport


NOW = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)
SOURCE_REF = "knowledge://method/source#section-1"
BROKER_HASH = "b" * 64


def test_contract_is_frozen_versioned_and_supported_intents_are_exact():
    candidate = build(tmp_path=None, inputs=make_inputs()).candidate
    assert candidate.schema_version == AUTONOMOUS_DECISION_SCHEMA_VERSION
    assert {item.value for item in AutonomousDecisionIntent} == {
        "NO_ACTION",
        "OPEN_POSITION",
        "CANCEL_PENDING_ORDER",
        "MODIFY_POSITION_PROTECTION",
        "CLOSE_POSITION",
        "REQUIRE_HUMAN_REVIEW",
    }
    with pytest.raises(Exception):
        candidate.intent = "OPEN_POSITION"


def test_valid_no_action_candidate(tmp_path):
    result = build(tmp_path, make_inputs(risk_action="NO_TRADE", requested_intent="AUTO"))
    assert result.validation.valid
    assert result.candidate.intent == "NO_ACTION"
    assert result.candidate.deterministic_eligibility_result == "NOT_ELIGIBLE"


def test_valid_open_position_candidate_from_structured_inputs(tmp_path):
    result = build(tmp_path, make_inputs())
    assert result.validation.valid
    assert result.candidate.intent == "OPEN_POSITION"
    assert result.candidate.deterministic_eligibility_result == "ELIGIBLE_CANDIDATE"


def test_missing_evidence_fails_closed(tmp_path):
    inputs = make_inputs()
    inputs.runtime_context.source_refs.clear()
    result = build(tmp_path, inputs)
    assert result.validation.valid
    assert result.candidate.intent in {"NO_ACTION", "REQUIRE_HUMAN_REVIEW"}
    assert "EVIDENCE_INSUFFICIENT" in result.candidate.blocked_reason_codes


def test_stale_market_context_fails_closed(tmp_path):
    inputs = make_inputs()
    inputs.runtime_context.created_at = (NOW - timedelta(hours=1)).isoformat()
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "STALE_MARKET_CONTEXT" in result.candidate.blocked_reason_codes


def test_conflicting_reasoning_and_score_fails_closed(tmp_path):
    inputs = make_inputs()
    inputs.score_report.primary_method_id = "different-method"
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "REASONING_SCORE_CONFLICT" in result.candidate.blocked_reason_codes


def test_risk_block_prevents_open_position(tmp_path):
    inputs = make_inputs(risk_action="BLOCKED")
    inputs.risk_result.blockers.append(DecisionBlocker(code="RISK_LIMIT"))
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "NO_ACTION"
    assert "RISK_RESULT_BLOCKED" in result.candidate.blocked_reason_codes


def test_human_confirmed_draft_method_regime_warning_does_not_veto_candidate(tmp_path):
    inputs = make_human_draft_advisory_block_inputs()

    result = build(tmp_path, inputs)

    assert result.candidate.intent == "OPEN_POSITION"
    assert result.candidate.deterministic_eligibility_result == "ELIGIBLE_CANDIDATE"
    assert "RISK_RESULT_BLOCKED" not in result.candidate.blocked_reason_codes
    assert "SCORING_RESULT_BLOCKED" not in result.candidate.blocked_reason_codes


def test_human_confirmed_draft_real_risk_block_remains_blocking(tmp_path):
    inputs = make_human_draft_advisory_block_inputs()
    inputs.risk_result.blockers.append(DecisionBlocker(code="RISK_LIMIT"))

    result = build(tmp_path, inputs)

    assert result.candidate.intent == "NO_ACTION"
    assert "RISK_RESULT_BLOCKED" in result.candidate.blocked_reason_codes


def test_unresolved_result_unknown_prevents_open_position(tmp_path):
    inputs = replace(make_inputs(), reconciliation_result=reconciliation_unknown())
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "RECONCILIATION_UNRESOLVED" in result.candidate.blocked_reason_codes


def test_unique_active_order_may_produce_cancel_candidate(tmp_path):
    inputs = make_management_inputs("CANCEL_PENDING_ORDER", MT5LifecycleState.ORDER_ACTIVE)
    result = build(tmp_path, inputs)
    assert result.validation.valid
    assert result.candidate.intent == "CANCEL_PENDING_ORDER"
    assert result.candidate.direction == ""


@pytest.mark.parametrize(
    ("intent", "effect"),
    [("MODIFY_POSITION_PROTECTION", "UNCHANGED"), ("CLOSE_POSITION", "REDUCE")],
)
def test_unique_open_position_may_produce_management_candidate(tmp_path, intent, effect):
    inputs = make_management_inputs(intent, MT5LifecycleState.POSITION_OPEN, effect=effect)
    result = build(tmp_path, inputs)
    assert result.validation.valid
    assert result.candidate.intent == intent


def test_ambiguous_lifecycle_evidence_fails_closed(tmp_path):
    inputs = make_management_inputs("CLOSE_POSITION", MT5LifecycleState.INCONSISTENT, effect="REDUCE")
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "LIFECYCLE_AMBIGUOUS" in result.candidate.blocked_reason_codes


def test_account_context_mismatch_fails_closed(tmp_path):
    inputs = replace(make_inputs(), lifecycle_status=lifecycle_status(account_match=False))
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "ACCOUNT_CONTEXT_MISMATCH" in result.candidate.blocked_reason_codes


def test_unsupported_intent_fails_closed(tmp_path):
    result = build(tmp_path, make_inputs(requested_intent="INVENT_NEW_ACTION"))
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "UNSUPPORTED_INTENT" in result.candidate.blocked_reason_codes


def test_identical_inputs_produce_identical_provenance_and_idempotency(tmp_path):
    orchestrator = service(tmp_path)
    first = orchestrator.build_candidate(make_inputs(), now=NOW)
    second = orchestrator.build_candidate(make_inputs(), now=NOW + timedelta(seconds=1))
    assert first.intent == second.intent
    assert first.blocked_reason_codes == second.blocked_reason_codes
    assert first.provenance_hash == second.provenance_hash
    assert first.decision_idempotency_key == second.decision_idempotency_key


def test_duplicate_generation_is_journal_idempotent(tmp_path):
    orchestrator = service(tmp_path)
    first = orchestrator.run_once(make_inputs(), now=NOW)
    second = orchestrator.run_once(make_inputs(), now=NOW + timedelta(seconds=1))
    assert first.journal_appended is True
    assert second.journal_appended is False
    assert len(orchestrator.journal.records()) == 1


def test_changed_structured_input_changes_provenance(tmp_path):
    orchestrator = service(tmp_path)
    first = orchestrator.build_candidate(make_inputs(score=0.82), now=NOW)
    second = orchestrator.build_candidate(make_inputs(score=0.91), now=NOW)
    assert first.provenance_hash != second.provenance_hash


def test_expired_candidate_is_invalid(tmp_path):
    orchestrator = service(tmp_path)
    candidate = orchestrator.build_candidate(make_inputs(), now=NOW)
    expired = replace(candidate, expires_at=(NOW - timedelta(seconds=1)).isoformat())
    validation = orchestrator.validate_candidate(expired, now=NOW)
    assert not validation.valid
    assert "CANDIDATE_EXPIRED" in validation.issues


def test_malformed_decision_journal_fails_closed(tmp_path):
    journal_path = tmp_path / "decisions.jsonl"
    journal_path.write_text("{not-json}\n", encoding="utf-8")
    result = service(tmp_path).run_once(make_inputs(), now=NOW)
    assert result.persistence_safe is False
    assert result.journal_appended is False
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "DECISION_JOURNAL_CORRUPT" in result.candidate.blocked_reason_codes


def test_public_output_is_redacted(tmp_path):
    result = build(
        tmp_path,
        make_management_inputs("CLOSE_POSITION", MT5LifecycleState.POSITION_OPEN, effect="REDUCE"),
    )
    payload = json.dumps(result.to_public_dict(), sort_keys=True)
    assert BROKER_HASH not in payload
    assert "semantic-ref-fixture" not in payload
    assert '"direction":' not in payload
    assert "password" not in payload.lower()


@pytest.mark.parametrize(
    ("intent", "state", "effect"),
    [
        ("NO_ACTION", None, "NONE"),
        ("OPEN_POSITION", None, "NONE"),
        ("CANCEL_PENDING_ORDER", MT5LifecycleState.ORDER_ACTIVE, "NONE"),
        ("MODIFY_POSITION_PROTECTION", MT5LifecycleState.POSITION_OPEN, "UNCHANGED"),
        ("CLOSE_POSITION", MT5LifecycleState.POSITION_OPEN, "REDUCE"),
    ],
)
def test_every_candidate_remains_non_executable(tmp_path, intent, state, effect):
    if intent == "NO_ACTION":
        inputs = make_inputs(risk_action="NO_TRADE")
    elif intent == "OPEN_POSITION":
        inputs = make_inputs()
    else:
        inputs = make_management_inputs(intent, state, effect=effect)
    candidate = build(tmp_path, inputs).candidate
    assert candidate.execution_authority is False
    assert candidate.human_confirmation_present is False
    assert candidate.execution_permission_requested is False
    assert candidate.live_submission_allowed is False
    assert candidate.live_execution_allowed is False
    assert candidate.order_send_allowed is False
    assert candidate.execution_allowed is False
    assert candidate.executable is False
    assert candidate.order_sent is False


def test_journal_is_restart_safe_and_contains_only_redacted_references(tmp_path):
    first = service(tmp_path)
    result = first.run_once(make_inputs(), now=NOW)
    second = AutonomousDecisionJournal(tmp_path / "decisions.jsonl")
    records = second.records()
    assert result.journal_appended
    assert len(records) == 1
    assert records[0]["metadata_redacted"] is True
    assert BROKER_HASH not in json.dumps(records[0], sort_keys=True)


def _write_candidate_row(path, row, *, rehash=True):
    if rehash:
        row.pop("record_hash", None)
        row["record_hash"] = _sha256(_canonical_json(row))
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return AutonomousDecisionJournal(path)


@pytest.mark.parametrize(
    "missing",
    (
        (),
        ("trading_scope",),
        ("strategy_id", "strategy_version", "normalized_strategy_hash",
         "reasoning_evidence_summary", "trading_scope"),
    ),
    ids=("current", "pre-scope", "original-legacy"),
)
def test_protected_candidate_schema_versions_reload_without_rewriting(tmp_path, missing):
    candidate = service(tmp_path).build_candidate(
        replace(
            make_inputs(), strategy_id="historical-strategy", strategy_version="v2",
            normalized_strategy_hash="a" * 64, reasoning_evidence_summary="{}",
            trading_scope="historical-scope",
        ),
        now=NOW,
    )
    row = _journal_row(candidate)
    for name in missing:
        row["protected_candidate"].pop(name)
    path = tmp_path / "historical.jsonl"
    journal = _write_candidate_row(path, row)
    before = path.read_bytes()

    loaded = journal.load_candidate(candidate.candidate_reference)

    assert loaded is not None
    assert loaded.candidate_reference == candidate.candidate_reference
    assert loaded.provenance_hash == candidate.provenance_hash
    assert loaded.decision_idempotency_key == candidate.decision_idempotency_key
    assert loaded.account_context_reference == candidate.account_context_reference
    for name in ("strategy_id", "strategy_version", "normalized_strategy_hash",
                 "reasoning_evidence_summary", "trading_scope"):
        assert getattr(loaded, name) == ("" if name in missing else getattr(candidate, name))
    assert loaded.execution_authority is loaded.executable is False
    assert journal.records()[0]["record_hash"] == row["record_hash"]
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "missing", (("intent",), ("strategy_id",), ("strategy_version", "trading_scope"))
)
def test_unrecognized_missing_candidate_fields_remain_corrupt(tmp_path, missing):
    candidate = service(tmp_path).build_candidate(make_inputs(), now=NOW)
    row = _journal_row(candidate)
    for name in missing:
        row["protected_candidate"].pop(name)
    journal = _write_candidate_row(tmp_path / "invalid.jsonl", row)

    with pytest.raises(AutonomousDecisionJournalError, match="DECISION_JOURNAL_CORRUPT"):
        journal.load_candidate(candidate.candidate_reference)


@pytest.mark.parametrize("mutation", ("extra", "tuple", "tampered"))
def test_invalid_or_tampered_legacy_candidate_fails_closed(tmp_path, mutation):
    candidate = service(tmp_path).build_candidate(make_inputs(), now=NOW)
    row = _journal_row(candidate)
    row["protected_candidate"].pop("trading_scope")
    if mutation == "extra":
        row["protected_candidate"]["unexpected_field"] = "not-allowed"
    elif mutation == "tuple":
        row["protected_candidate"]["timeframe_profile"] = "M1"
    journal = _write_candidate_row(
        tmp_path / "invalid.jsonl", row, rehash=mutation != "tampered"
    )
    before = journal.path.read_bytes()

    with pytest.raises(AutonomousDecisionJournalError, match="DECISION_JOURNAL_CORRUPT"):
        journal.load_candidate(candidate.candidate_reference)
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize(
    "field", ("candidate_reference", "provenance_hash", "decision_idempotency_key")
)
def test_legacy_candidate_correlation_conflicts_remain_rejected(tmp_path, field):
    candidate = service(tmp_path).build_candidate(make_inputs(), now=NOW)
    row = _journal_row(candidate)
    row["protected_candidate"].pop("trading_scope")
    row["protected_candidate"][field] = "f" * 64
    journal = _write_candidate_row(tmp_path / "conflict.jsonl", row)

    with pytest.raises(AutonomousDecisionJournalError, match="DECISION_JOURNAL_CONFLICT"):
        journal.load_candidate(candidate.candidate_reference)


def test_cli_runs_once_and_prints_only_safe_summary(tmp_path, capsys):
    inputs = make_inputs(risk_action="NO_TRADE")
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    inputs.runtime_context.created_at = fresh_timestamp
    inputs.method_selection.created_at = fresh_timestamp
    inputs.score_report.created_at = fresh_timestamp
    inputs.risk_result.created_at = fresh_timestamp
    inputs = replace(
        inputs,
        lifecycle_status=replace(
            inputs.lifecycle_status, last_successful_cycle=fresh_timestamp
        ),
    )
    payload = mapping_for_cli(inputs)
    input_path = tmp_path / "input.json"
    input_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    exit_code = cli_main(
        ["--input", str(input_path), "--journal", str(tmp_path / "cli-decisions.jsonl")]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "intent=NO_ACTION" in output
    assert "execution_authority=false" in output
    assert "semantic-ref-fixture" not in output
    assert BROKER_HASH not in output


def test_orchestrator_and_cli_have_no_mutation_calls_or_execution_authority_true():
    paths = [
        Path("src/services/trading/decision/autonomous_orchestrator.py"),
        Path("scripts/run_autonomous_decision_once.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    lowered = text.lower()
    assert "controlled" + "-submit" not in lowered
    assert "controlled" + "-manage" not in lowered
    assert ".order" + "_send(" not in text
    assert "Meta" + "Trader5" not in text
    assert "execution_authority=true" not in lowered.replace(" ", "")


def test_default_config_does_not_enable_execution():
    config = AutonomousDecisionConfig()
    assert config.enabled is True
    assert config.journal_path.endswith("autonomous_decisions.jsonl")
    source = Path("src/config.py").read_text(encoding="utf-8")
    assert 'TRADING_EXECUTION_AUTONOMOUS_ENABLED = _env_bool("TRADING_EXECUTION_AUTONOMOUS_ENABLED", False)' in source


def test_lifecycle_summary_reconciliation_required_fails_closed(tmp_path):
    status = replace(
        lifecycle_status(),
        lifecycle_state_counts={MT5LifecycleState.RECONCILIATION_REQUIRED.value: 1},
        records_inspected=1,
    )
    result = build(tmp_path, replace(make_inputs(), lifecycle_status=status))
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "LIFECYCLE_AMBIGUOUS" in result.candidate.blocked_reason_codes


def test_prohibited_exposure_behavior_reference_fails_closed(tmp_path):
    inputs = make_inputs()
    inputs = replace(
        inputs,
        semantic_parameter_references=("semantic-ref-fixture", "martingale-policy"),
    )
    result = build(tmp_path, inputs)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "PROHIBITED_EXPOSURE_BEHAVIOR" in result.candidate.blocked_reason_codes
def test_sensitive_reference_is_removed_and_fails_closed(tmp_path):
    inputs = make_inputs()
    inputs.runtime_context.source_refs = ["credential=must-not-survive"]
    result = build(tmp_path, inputs)
    serialized = json.dumps(result.candidate.to_public_dict(), sort_keys=True)
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "SENSITIVE_REFERENCE_NOT_ALLOWED" in result.candidate.blocked_reason_codes
    assert "must-not-survive" not in serialized


def test_append_failure_rebuilds_candidate_as_human_review(tmp_path):
    class FailingAppendJournal:
        def records(self):
            return []

        def append_idempotent(self, candidate):
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_UNAVAILABLE")

    orchestrator = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path=str(tmp_path / "decisions.jsonl")),
        journal=FailingAppendJournal(),
    )
    result = orchestrator.run_once(make_inputs(), now=NOW)
    assert result.persistence_safe is False
    assert result.journal_appended is False
    assert result.candidate.intent == "REQUIRE_HUMAN_REVIEW"
    assert "DECISION_JOURNAL_UNAVAILABLE" in result.candidate.blocked_reason_codes
def build(tmp_path, inputs):
    if tmp_path is None:
        config = AutonomousDecisionConfig(journal_path="unused.jsonl")
        orchestrator = AutonomousDecisionOrchestrator(
            config=config, journal=AutonomousDecisionJournal("unused.jsonl")
        )
        candidate = orchestrator.build_candidate(inputs, now=NOW)
        validation = orchestrator.validate_candidate(candidate, now=NOW)
        return type("BuildResult", (), {"candidate": candidate, "validation": validation})()
    return service(tmp_path).run_once(inputs, now=NOW)


def service(tmp_path):
    config = AutonomousDecisionConfig(
        ttl_seconds=300,
        input_max_age_seconds=300,
        journal_path=str(tmp_path / "decisions.jsonl"),
    )
    return AutonomousDecisionOrchestrator(config=config)


def make_inputs(
    *,
    score=0.82,
    risk_action="REVIEW_READY",
    requested_intent="OPEN_POSITION",
):
    created = NOW.isoformat()
    context = RuntimeContextPack(
        context_pack_id="context-fixture",
        created_at=created,
        mode="autonomous_candidate",
        symbol="TEST_SYMBOL",
        broker_symbol="TEST_SYMBOLm",
        feature_snapshot_summary={"data_quality_status": "COMPLETE"},
        calendar_context_summary={"calendar_risk_state": "CLEAR"},
        market_regime_summary={"primary_regime": "TREND"},
        selected_method_cards=[{"method_id": "method-fixture"}],
        source_refs=[SOURCE_REF],
    )
    method = MethodSelectionResult(
        result_id="reasoning-fixture",
        created_at=created,
        mode=context.mode,
        symbol=context.symbol,
        primary_method_id="method-fixture",
        selected_playbook_ids=["playbook-fixture"],
        overall_context_fit=score,
        confidence=score,
        candidate_assessments=[
            MethodCandidateAssessment(
                method_id="method-fixture",
                role="PRIMARY_CANDIDATE",
                compatibility_score=score,
                source_refs=[SOURCE_REF],
            )
        ],
        source_context_pack_id=context.context_pack_id,
        source_refs=[SOURCE_REF],
    )
    score_report = SignalScoreReport(
        score_report_id="score-fixture",
        created_at=created,
        mode=context.mode,
        symbol=context.symbol,
        broker_symbol=context.broker_symbol,
        primary_method_id=method.primary_method_id,
        selected_playbook_ids=["playbook-fixture"],
        final_context_score=score,
        grade="GOOD" if score >= 0.70 else "WEAK",
        source_feature_snapshot_id="feature-fixture",
        source_calendar_context_id="calendar-fixture",
        source_regime_snapshot_id="regime-fixture",
        source_context_pack_id=context.context_pack_id,
        source_method_selection_id=method.result_id,
        source_refs=[SOURCE_REF],
    )
    risk = TradeReadinessDecision(
        decision_id="risk-fixture",
        created_at=created,
        mode=context.mode,
        symbol=context.symbol,
        broker_symbol=context.broker_symbol,
        action=risk_action,
        readiness_score=score,
        confidence=score,
        grade="GOOD",
        primary_method_id=method.primary_method_id,
        source_score_report_id=score_report.score_report_id,
        source_feature_snapshot_id=score_report.source_feature_snapshot_id,
        source_calendar_context_id=score_report.source_calendar_context_id,
        source_regime_snapshot_id=score_report.source_regime_snapshot_id,
        source_context_pack_id=context.context_pack_id,
        source_method_selection_id=method.result_id,
        source_refs=[SOURCE_REF],
    )
    return AutonomousDecisionInputs(
        runtime_context=context,
        method_selection=method,
        score_report=score_report,
        risk_result=risk,
        lifecycle_status=lifecycle_status(),
        requested_intent=requested_intent,
        direction="BUY",
        semantic_parameter_references=("semantic-ref-fixture",),
        exposure_effect="NONE",
    )


def make_human_draft_advisory_block_inputs():
    inputs = make_inputs(risk_action="BLOCKED")
    for item in (
        inputs.runtime_context,
        inputs.method_selection,
        inputs.score_report,
        inputs.risk_result,
    ):
        item.mode = "human_confirmed_live"
    inputs.score_report.blockers.append("method_bad_regime:CHOPPY")
    inputs.risk_result.blockers.extend(
        (
            DecisionBlocker(code="method_bad_regime:CHOPPY", source="score_report"),
            DecisionBlocker(code="SCORING_BLOCKERS_PRESENT", source="score_report"),
        )
    )
    return replace(
        inputs,
        proposal_source=EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
        proposal_source_reference="editable_trade_draft_fixture",
    )


def lifecycle_status(*, account_match=True):
    return MT5RuntimeSupervisorStatus(
        supervisor_status="HEALTHY",
        last_successful_cycle=NOW.isoformat(),
        lifecycle_state_counts={},
        discrepancy_count=0,
        bridge_available=True,
        account_context_match=account_match,
        records_inspected=0,
        health_reason="OK",
    )


def lifecycle_observation(state):
    references = {"orders": [], "deals": [], "positions": []}
    if state == MT5LifecycleState.ORDER_ACTIVE:
        references["orders"] = [BROKER_HASH]
    elif state in {MT5LifecycleState.POSITION_OPEN, MT5LifecycleState.POSITION_PARTIALLY_REDUCED}:
        references["positions"] = [BROKER_HASH]
    return MT5LifecycleObservation(
        observation_id="lifecycle-fixture",
        protected_execution_reference="execution-fixture",
        lifecycle_state=state.value,
        previous_lifecycle_state=MT5LifecycleState.UNKNOWN.value,
        observation_timestamp=NOW.isoformat(),
        account_fingerprint_hash="a" * 64,
        evidence_classification="UNIQUE_MATCH",
        protected_broker_references=references,
        discrepancy_reason="LIFECYCLE_AMBIGUOUS" if state is MT5LifecycleState.INCONSISTENT else "",
        source_snapshot_reference="snapshot-fixture",
        observation_hash="c" * 64,
    )


def make_management_inputs(intent, state, *, effect="NONE"):
    inputs = make_inputs(risk_action="MANAGE_EXISTING_POSITION", requested_intent=intent)
    return replace(
        inputs,
        lifecycle_observation=lifecycle_observation(state),
        exposure_effect=effect,
        direction="SELL" if intent == "CLOSE_POSITION" else "",
        semantic_parameter_references=(
            ("semantic-ref-fixture",)
            if intent in {"MODIFY_POSITION_PROTECTION", "CLOSE_POSITION"}
            else ()
        ),
    )


def reconciliation_unknown():
    return MT5ReconciliationReceipt(
        status="BLOCKED",
        reconciliation_reference="reconciliation-fixture",
        evidence_classification="RESULT_UNKNOWN",
        original_execution_state="RESULT_UNKNOWN",
        resulting_execution_state="RESULT_UNKNOWN",
        retry_decision="RETRY_PROHIBITED",
        order_reference_present=False,
        deal_reference_present=False,
        position_reference_present=False,
    )


def mapping_for_cli(inputs):
    return {
        "runtime_context": inputs.runtime_context.as_dict(),
        "method_selection": inputs.method_selection.as_dict(),
        "score_report": inputs.score_report.as_dict(),
        "risk_result": inputs.risk_result.as_dict(),
        "lifecycle_status": inputs.lifecycle_status.to_safe_dict(),
        "requested_intent": inputs.requested_intent,
        "direction": inputs.direction,
        "semantic_parameter_references": list(inputs.semantic_parameter_references),
        "exposure_effect": inputs.exposure_effect,
    }

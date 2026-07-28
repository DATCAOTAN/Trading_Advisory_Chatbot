from __future__ import annotations

import json
import socket
from dataclasses import replace

import pytest

from scripts import run_offline_candidate_acceptance as cli
from scripts.test_controlled_pending_order_dry_run import (
    FINGERPRINT,
    account_context,
    confirmation_for,
    review_for,
)
from src.config import Config
from src.services.trading.decision import offline_candidate_acceptance as offline
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    autonomous_candidate_has_offline_provenance,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_artifact_export import (
    PendingArtifactExportError,
    write_pending_candidate_handoff,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    ControlledPendingOrderDryRunMapper,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
)


@pytest.mark.parametrize(
    ("scenario", "intent", "eligibility", "proposal_calls", "generation_count"),
    [
        ("fresh_no_action", "NO_PROPOSAL", "NOT_ELIGIBLE", 1, 0),
        ("fresh_human_review", "REQUIRE_HUMAN_REVIEW", "HUMAN_REVIEW_REQUIRED", 1, 1),
        ("fresh_market", "MARKET", "ELIGIBLE_CANDIDATE", 1, 1),
        ("fresh_pending", "PENDING", "ELIGIBLE_CANDIDATE", 1, 1),
        ("invalid_price_relation", "BLOCKED", "NOT_ELIGIBLE", 1, 0),
        ("invalid_volume", "BLOCKED", "NOT_ELIGIBLE", 1, 0),
        ("stale_market", "BLOCKED", "NOT_ELIGIBLE", 0, 0),
        ("source_reference_mismatch", "BLOCKED", "NOT_ELIGIBLE", 0, 0),
        ("account_context_mismatch", "BLOCKED", "NOT_ELIGIBLE", 0, 0),
        ("lifecycle_discrepancy", "BLOCKED", "NOT_ELIGIBLE", 0, 0),
        ("reconciliation_discrepancy", "BLOCKED", "NOT_ELIGIBLE", 0, 0),
        ("malformed_proposal", "BLOCKED", "NOT_ELIGIBLE", 1, 0),
        ("schema_invalid_proposal", "BLOCKED", "NOT_ELIGIBLE", 1, 0),
    ],
)
def test_natural_scenarios_are_deterministic_and_non_executable(
    scenario, intent, eligibility, proposal_calls, generation_count
):
    result = offline.run_offline_candidate_acceptance(scenario)

    assert result["natural_intent"] == intent
    assert result["eligibility"] == eligibility
    assert result["deterministic_proposal_adapter_invocation_count"] == proposal_calls
    assert result["external_proposal_provider_invocation_count"] == 0
    assert result["generation_count"] == generation_count
    assert result["offline_provenance"] == "offline_fixture"
    assert result["export_eligibility"] is False
    assert result["submission_eligibility"] is False
    assert result["protected_export_count"] == 0
    assert result["submission_count"] == 0
    assert result["broker_mutation_count"] == 0


def test_same_fixture_and_clock_produce_identical_output():
    first = offline.run_offline_candidate_acceptance("fresh_pending")
    second = offline.run_offline_candidate_acceptance("fresh_pending")
    assert first == second


@pytest.mark.parametrize("scenario", ["fresh_market", "fresh_pending"])
def test_actionable_candidate_is_persisted_once_with_stable_integrity(scenario):
    result = offline.run_offline_candidate_acceptance(scenario)
    assert result["candidate_admission_count"] == 1
    assert result["candidate_persistence_count"] == 1
    assert result["candidate_integrity_result"] == "VALID"
    assert result["candidate_provenance_result"] == "VALID"
    assert result["duplicate_admission_result"] == "REJECTED_IDEMPOTENTLY"


@pytest.mark.parametrize(
    ("scenario", "action", "order_type"),
    [("fresh_market", "MARKET", "BUY"), ("fresh_pending", "PENDING", "BUY_LIMIT")],
)
def test_actionable_candidate_uses_valid_volume_and_broker_metadata(
    monkeypatch, scenario, action, order_type
):
    captured = []
    original = AutonomousDecisionOrchestrator.run_once

    def spy(self, *args, **kwargs):
        run = original(self, *args, **kwargs)
        captured.append(run)
        return run

    monkeypatch.setattr(AutonomousDecisionOrchestrator, "run_once", spy)
    offline.run_offline_candidate_acceptance(scenario)
    run = captured[0]
    assert run.validation.valid is True
    assert run.candidate.action == action
    assert run.candidate.order_type == order_type
    assert run.candidate.proposed_volume == "0.01"
    assert run.order_market_snapshot.volume_min == 0.01
    assert run.order_market_snapshot.volume_max == 10.0
    assert run.order_market_snapshot.volume_step == 0.01
    assert run.candidate.structured_order_hash
    assert run.candidate.provenance_hash


def test_no_proposal_is_successful_and_creates_no_candidate():
    result = offline.run_offline_candidate_acceptance("fresh_no_action")
    assert result["validation_result"] is True
    assert result["ordered_blockers"] == []
    assert result["generation_count"] == 0
    assert result["candidate_persistence_count"] == 0


def test_fixed_clock_drives_generation_expiry_and_freshness():
    result = offline.run_offline_candidate_acceptance("fresh_market")
    assert result["reference_timestamp"] == offline.DEFAULT_REFERENCE_TIME
    assert result["generated_timestamp"] == offline.DEFAULT_REFERENCE_TIME
    assert result["expiry_timestamp"] == "2026-07-21T12:05:00+00:00"
    assert result["market_snapshot_timestamps"]["tick"] == offline.DEFAULT_REFERENCE_TIME
    assert result["freshness_result"] == "FRESH"


@pytest.mark.parametrize(
    ("scenario", "blockers"),
    [
        ("invalid_price_relation", ["STRUCTURED_PROPOSAL_MARKET_RELATION_INVALID"]),
        ("invalid_volume", ["STRUCTURED_PROPOSAL_PROPOSED_VOLUME_INVALID"]),
        ("stale_market", ["MARKET_SNAPSHOT_STALE"]),
        ("source_reference_mismatch", ["STRUCTURED_RUNTIME_REFERENCE_MISMATCH"]),
        ("account_context_mismatch", ["ACCOUNT_CONTEXT_MISMATCH"]),
        ("lifecycle_discrepancy", ["LIFECYCLE_CONFLICT"]),
        ("reconciliation_discrepancy", ["RECONCILIATION_UNRESOLVED"]),
        ("malformed_proposal", ["STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON"]),
        ("schema_invalid_proposal", ["STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID"]),
    ],
)
def test_blocker_order_is_stable(scenario, blockers):
    result = offline.run_offline_candidate_acceptance(scenario)
    assert result["ordered_reason_codes"] == blockers
    assert result["ordered_blockers"] == blockers


def test_stale_market_blocks_before_proposal_or_generation():
    result = offline.run_offline_candidate_acceptance("stale_market")
    assert result["freshness_result"] == "STALE"
    assert result["deterministic_proposal_adapter_invocation_count"] == 0
    assert result["generation_count"] == 0


def test_malformed_proposal_has_no_retry():
    result = offline.run_offline_candidate_acceptance("malformed_proposal")
    assert result["deterministic_proposal_adapter_invocation_count"] == 1
    assert result["generation_count"] == 0


@pytest.mark.parametrize(
    "scenario",
    [
        "invalid_price_relation",
        "invalid_volume",
        "stale_market",
        "source_reference_mismatch",
        "account_context_mismatch",
        "lifecycle_discrepancy",
        "reconciliation_discrepancy",
        "malformed_proposal",
        "schema_invalid_proposal",
    ],
)
def test_invalid_fixture_never_persists_candidate(scenario):
    result = offline.run_offline_candidate_acceptance(scenario)
    assert result["candidate_admission_count"] == 0
    assert result["candidate_persistence_count"] == 0


def test_strict_fixture_path_uses_explicit_reference_timestamp(tmp_path):
    fixture = tmp_path / "scenario.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": offline.OFFLINE_FIXTURE_SCHEMA,
                "scenario": "fresh_market",
                "reference_timestamp": "2030-01-02T03:04:05+00:00",
                "offline_provenance": "offline_fixture",
                "non_exportable": True,
                "non_submittable": True,
            }
        ),
        encoding="utf-8",
    )
    result = offline.run_offline_candidate_acceptance(fixture)
    assert result["reference_timestamp"] == "2030-01-02T03:04:05+00:00"
    assert result["generated_timestamp"] == "2030-01-02T03:04:05+00:00"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": offline.OFFLINE_FIXTURE_SCHEMA},
        {
            "schema_version": offline.OFFLINE_FIXTURE_SCHEMA,
            "scenario": "fresh_market",
            "reference_timestamp": offline.DEFAULT_REFERENCE_TIME,
            "offline_provenance": "live",
            "non_exportable": True,
            "non_submittable": True,
        },
    ],
)
def test_malformed_or_unsafe_fixture_fails_closed(tmp_path, payload):
    fixture = tmp_path / "invalid.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="OFFLINE_FIXTURE"):
        offline.run_offline_candidate_acceptance(fixture)


def test_missing_fixture_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="OFFLINE_FIXTURE_INVALID"):
        offline.run_offline_candidate_acceptance(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "flag",
    ["TRADING_MT5_ORDER_SEND_ENABLED", "MT5_BRIDGE_CONTROLLED_EXECUTION_ENABLED"],
)
def test_enabled_execution_setting_blocks_harness(monkeypatch, flag):
    monkeypatch.setattr(Config, flag, True)
    with pytest.raises(RuntimeError, match="OFFLINE_HARNESS_EXECUTION_FLAGS_ENABLED"):
        offline.run_offline_candidate_acceptance("fresh_market")


def test_no_network_or_bridge_call(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    result = offline.run_offline_candidate_acceptance("fresh_pending")
    assert result["natural_intent"] == "PENDING"
    assert result["broker_mutation_count"] == 0


def test_output_is_redacted_and_contains_no_execution_values():
    payload = json.dumps(offline.run_offline_candidate_acceptance("fresh_pending"))
    for marker in (
        "api_key",
        "password",
        "credential",
        "account_login",
        "ticket_id",
        "deal_id",
        "position_id",
    ):
        assert marker not in payload.lower()


def _capture_pending_run(monkeypatch):
    captured = []
    original = AutonomousDecisionOrchestrator.run_once

    def spy(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(AutonomousDecisionOrchestrator, "run_once", spy)
    report = offline.run_offline_candidate_acceptance("fresh_pending")
    assert report["generation_count"] == 1
    assert len(captured) == 1
    return captured[0]


def test_offline_candidate_is_rejected_by_protected_handoff(monkeypatch, tmp_path):
    run = _capture_pending_run(monkeypatch)
    review = review_for(run.candidate)
    confirmation = confirmation_for(run.candidate, review)

    with pytest.raises(PendingArtifactExportError, match="OFFLINE_PROVENANCE_NOT_EXECUTABLE"):
        write_pending_candidate_handoff(
            run_result=run,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir="handoff",
            confirmation_phrase=EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
            current_time=offline._timestamp(offline.DEFAULT_REFERENCE_TIME),
            protected_root=tmp_path,
        )
    assert not list(tmp_path.rglob("*.json"))


def test_offline_candidate_stops_before_controlled_request(monkeypatch, tmp_path):
    run = _capture_pending_run(monkeypatch)
    candidate = run.candidate
    review = review_for(candidate)
    confirmation = confirmation_for(candidate, review)
    orchestrator = AutonomousDecisionOrchestrator(
        offline.AutonomousDecisionConfig(journal_path=str(tmp_path / "validator.jsonl"))
    )
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=run.order_market_snapshot,
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=offline._timestamp(offline.DEFAULT_REFERENCE_TIME),
    )
    assert "OFFLINE_PROVENANCE_NOT_EXECUTABLE" in result.validation.blockers
    assert result.request_draft is None


def test_changing_only_mode_cannot_strip_offline_provenance(monkeypatch):
    run = _capture_pending_run(monkeypatch)
    changed = replace(run.candidate, operating_mode="autonomous_live")
    assert autonomous_candidate_has_offline_provenance(changed) is True


def test_cli_reports_malformed_fixture_without_traceback(tmp_path, capsys):
    code = cli.main([str(tmp_path / "missing.json")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "INVARIANT_BLOCKED"
    assert payload["broker_mutation_count"] == 0

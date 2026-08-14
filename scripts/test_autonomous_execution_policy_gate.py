from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.run_autonomous_decision_once import main as decision_cli_main
from scripts.run_autonomous_policy_once import main as policy_cli_main
from scripts.test_autonomous_decision_orchestrator import (
    BROKER_HASH,
    NOW,
    make_inputs,
    make_human_draft_advisory_block_inputs,
    make_management_inputs,
    reconciliation_unknown,
)
from src.services.trading.decision.autonomous_execution_policy import (
    AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION,
    AutonomousControlledBoundary,
    AutonomousExecutionPolicyConfig,
    AutonomousExecutionPolicyGate,
    AutonomousPolicyInputs,
    AutonomousPolicyJournal,
    AutonomousPolicyJournalError,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionConfig,
    AutonomousDecisionIntent,
    AutonomousDecisionOrchestrator,
)
from src.services.trading.decision.models import DecisionBlocker
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
    MT5LifecycleState,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)


ACCOUNT_REFERENCE = "a" * 64


def test_policy_contract_is_frozen_typed_and_versioned(tmp_path):
    result = run(tmp_path, policy_inputs()).policy_result
    assert result.schema_version == AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION
    with pytest.raises(Exception):
        result.decision = "BLOCK"


def test_default_policy_config_is_fail_closed():
    config = AutonomousExecutionPolicyConfig()
    assert config.enabled is False
    assert config.open_eligibility_enabled is False
    assert config.management_eligibility_enabled is False
    assert config.hard_block is True


def test_no_action_remains_terminal_non_action(tmp_path):
    inputs = policy_inputs(risk_action="NO_TRADE", requested_intent="AUTO")
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "BLOCK"
    assert result.target_controlled_boundary == "NONE"
    assert "NO_ACTION_TERMINAL" in result.deterministic_reason_codes


def test_human_review_candidate_remains_review_only(tmp_path):
    inputs = policy_inputs(requested_intent="REQUIRE_HUMAN_REVIEW")
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "REQUIRE_HUMAN_REVIEW"
    assert result.target_controlled_boundary == "NONE"


def test_valid_open_candidate_becomes_eligible_for_controlled_boundary(tmp_path):
    result = run(tmp_path, policy_inputs()).policy_result
    assert result.decision == "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
    assert result.target_controlled_boundary == "CONTROLLED_OPEN_POSITION"
    assert result.execution_authority is False


def test_non_deterministic_wait_remains_not_ready_for_open_policy(tmp_path):
    inputs = policy_inputs()
    inputs = replace(inputs, risk_result=replace(inputs.risk_result, action="WAIT"))

    result = run(tmp_path, inputs).policy_result

    assert result.decision == "BLOCK"
    assert "OPEN_POLICY_NOT_READY" in result.deterministic_reason_codes


def test_risk_blocked_candidate_is_blocked(tmp_path):
    inputs = policy_inputs()
    inputs.risk_result.blockers.append(DecisionBlocker(code="RISK_LIMIT"))
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "BLOCK"
    assert "RISK_RESULT_BLOCKED" in result.deterministic_reason_codes


def test_stale_candidate_is_blocked(tmp_path):
    inputs = policy_inputs()
    stale = replace(
        inputs.candidate,
        generated_at=(NOW - timedelta(hours=1)).isoformat(),
        expires_at=(NOW - timedelta(minutes=30)).isoformat(),
    )
    result = run(tmp_path, replace(inputs, candidate=stale)).policy_result
    assert result.decision == "BLOCK"
    assert "CANDIDATE_STALE_OR_EXPIRED" in result.deterministic_reason_codes


def test_invalid_provenance_hash_is_blocked(tmp_path):
    inputs = policy_inputs()
    invalid = replace(inputs.candidate, provenance_hash="0" * 64)
    result = run(tmp_path, replace(inputs, candidate=invalid)).policy_result
    assert result.decision == "BLOCK"
    assert "CANDIDATE_PROVENANCE_INVALID" in result.deterministic_reason_codes


def test_candidate_with_execution_authority_is_blocked(tmp_path):
    inputs = policy_inputs()
    unsafe = replace(inputs.candidate, execution_authority=True)
    result = run(tmp_path, replace(inputs, candidate=unsafe)).policy_result
    assert result.decision == "BLOCK"
    assert "CANDIDATE_EXECUTION_AUTHORITY_PRESENT" in result.deterministic_reason_codes


def test_unresolved_result_unknown_is_blocked(tmp_path):
    inputs = replace(policy_inputs(), reconciliation_result=reconciliation_unknown())
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "BLOCK"
    assert "RECONCILIATION_UNRESOLVED" in result.deterministic_reason_codes


def test_pending_inconclusive_reconciliation_is_blocked(tmp_path):
    pending = MT5ReconciliationReceipt(
        status="PENDING",
        reconciliation_reference="",
        evidence_classification="PENDING",
        original_execution_state="SUBMISSION_STARTED",
        resulting_execution_state="SUBMISSION_STARTED",
        retry_decision="RETRY_PROHIBITED",
        order_reference_present=False,
        deal_reference_present=False,
        position_reference_present=False,
    )
    result = run(tmp_path, replace(policy_inputs(), reconciliation_result=pending)).policy_result
    assert result.decision == "BLOCK"
    assert "RECONCILIATION_UNRESOLVED" in result.deterministic_reason_codes


def test_account_context_mismatch_is_blocked(tmp_path):
    result = run(
        tmp_path, replace(policy_inputs(), account_context_matches=False)
    ).policy_result
    assert result.decision == "BLOCK"
    assert "ACCOUNT_CONTEXT_CHANGED" in result.deterministic_reason_codes


@pytest.mark.parametrize(
    ("intent", "state", "effect", "target"),
    [
        (
            "CANCEL_PENDING_ORDER",
            MT5LifecycleState.ORDER_ACTIVE,
            "NONE",
            "CONTROLLED_CANCEL_PENDING_ORDER",
        ),
        (
            "MODIFY_POSITION_PROTECTION",
            MT5LifecycleState.POSITION_OPEN,
            "UNCHANGED",
            "CONTROLLED_MODIFY_POSITION_PROTECTION",
        ),
        (
            "CLOSE_POSITION",
            MT5LifecycleState.POSITION_OPEN,
            "REDUCE",
            "CONTROLLED_CLOSE_POSITION",
        ),
    ],
)
def test_unique_management_candidate_maps_to_existing_boundary(
    tmp_path, intent, state, effect, target
):
    inputs = management_policy_inputs(intent, state, effect)
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
    assert result.target_controlled_boundary == target


def test_ambiguous_lifecycle_target_is_blocked(tmp_path):
    inputs = management_policy_inputs(
        "CLOSE_POSITION", MT5LifecycleState.POSITION_OPEN, "REDUCE"
    )
    observation = replace(
        inputs.lifecycle_observation,
        protected_broker_references={
            "orders": [],
            "deals": [],
            "positions": [BROKER_HASH, "c" * 64],
        },
    )
    result = run(tmp_path, replace(inputs, lifecycle_observation=observation)).policy_result
    assert result.decision == "BLOCK"
    assert "LIFECYCLE_TARGET_INVALID" in result.deterministic_reason_codes


def test_exposure_increasing_management_candidate_is_blocked(tmp_path):
    inputs = management_policy_inputs(
        "MODIFY_POSITION_PROTECTION", MT5LifecycleState.POSITION_OPEN, "INCREASE"
    )
    result = run(tmp_path, inputs).policy_result
    assert result.decision == "BLOCK"
    assert "EXPOSURE_INCREASE_NOT_ALLOWED" in result.deterministic_reason_codes


def test_close_volume_cannot_exceed_observed_volume(tmp_path):
    inputs = management_policy_inputs(
        "CLOSE_POSITION", MT5LifecycleState.POSITION_OPEN, "REDUCE"
    )
    result = run(
        tmp_path,
        replace(inputs, requested_close_volume="2.0", observed_volume="1.0"),
    ).policy_result
    assert result.decision == "BLOCK"
    assert "CLOSE_VOLUME_INVALID" in result.deterministic_reason_codes


def test_conflicting_open_lifecycle_blocks_new_position(tmp_path):
    inputs = policy_inputs()
    conflicting = replace(inputs.candidate, lifecycle_status="POSITION_OPEN")
    result = run(tmp_path, replace(inputs, candidate=conflicting)).policy_result
    assert result.decision == "BLOCK"
    assert "LIFECYCLE_TARGET_CONFLICT" in result.deterministic_reason_codes


def test_identical_inputs_produce_identical_policy_hash(tmp_path):
    gate = service(tmp_path)
    first = gate.evaluate_candidate(policy_inputs(), now=NOW)
    second = gate.evaluate_candidate(policy_inputs(), now=NOW + timedelta(seconds=1))
    assert first.decision == second.decision
    assert first.target_controlled_boundary == second.target_controlled_boundary
    assert first.deterministic_reason_codes == second.deterministic_reason_codes
    assert first.policy_hash == second.policy_hash
    assert first.policy_idempotency_key == second.policy_idempotency_key


def test_changed_policy_input_changes_policy_hash(tmp_path):
    gate = service(tmp_path)
    first = gate.evaluate_candidate(policy_inputs(), now=NOW)
    changed = replace(policy_inputs(), semantic_proposal_complete=False)
    second = gate.evaluate_candidate(changed, now=NOW)
    assert first.policy_hash != second.policy_hash


def test_duplicate_evaluation_is_journal_idempotent(tmp_path):
    gate = service(tmp_path)
    first = gate.run_once(policy_inputs(), now=NOW)
    second = gate.run_once(policy_inputs(), now=NOW + timedelta(seconds=1))
    assert first.journal_appended is True
    assert second.journal_appended is False
    assert len(gate.journal.records()) == 1


def test_conflicting_duplicate_journal_record_fails_closed(tmp_path):
    gate = service(tmp_path)
    first = gate.run_once(policy_inputs(), now=NOW)
    row = gate.journal.records()[0]
    conflict = dict(row)
    conflict["policy_hash"] = "f" * 64
    conflict_without_hash = dict(conflict)
    conflict_without_hash.pop("record_hash")
    conflict["record_hash"] = sha(canonical_json(conflict_without_hash))
    with (tmp_path / "policy.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(conflict, sort_keys=True) + "\n")
    result = service(tmp_path).run_once(policy_inputs(), now=NOW)
    assert first.journal_appended is True
    assert result.persistence_safe is False
    assert result.policy_result.decision == "BLOCK"
    assert "POLICY_JOURNAL_CONFLICT" in result.policy_result.deterministic_reason_codes


def test_malformed_policy_journal_fails_closed(tmp_path):
    (tmp_path / "policy.jsonl").write_text("{broken-json}\n", encoding="utf-8")
    result = service(tmp_path).run_once(policy_inputs(), now=NOW)
    assert result.persistence_safe is False
    assert result.journal_appended is False
    assert result.policy_result.decision == "BLOCK"
    assert "POLICY_JOURNAL_CORRUPT" in result.policy_result.deterministic_reason_codes


def test_late_journal_failure_rebuilds_blocked_result(tmp_path):
    class FailingJournal:
        def records(self):
            return []

        def append_idempotent(self, result):
            raise AutonomousPolicyJournalError("POLICY_JOURNAL_UNAVAILABLE")

    gate = AutonomousExecutionPolicyGate(config=enabled_config(tmp_path), journal=FailingJournal())
    result = gate.run_once(policy_inputs(), now=NOW)
    assert result.persistence_safe is False
    assert result.policy_result.decision == "BLOCK"
    assert "POLICY_JOURNAL_UNAVAILABLE" in result.policy_result.deterministic_reason_codes


def test_public_output_is_redacted(tmp_path):
    inputs = management_policy_inputs(
        "CLOSE_POSITION", MT5LifecycleState.POSITION_OPEN, "REDUCE"
    )
    payload = json.dumps(run(tmp_path, inputs).to_public_dict(), sort_keys=True)
    assert ACCOUNT_REFERENCE not in payload
    assert BROKER_HASH not in payload
    assert "semantic-ref-fixture" not in payload
    assert "password" not in payload.lower()


@pytest.mark.parametrize(
    ("requested_intent", "risk_action"),
    [
        ("AUTO", "NO_TRADE"),
        ("REQUIRE_HUMAN_REVIEW", "REVIEW_READY"),
        ("OPEN_POSITION", "REVIEW_READY"),
    ],
)
def test_every_policy_result_remains_non_executable(
    tmp_path, requested_intent, risk_action
):
    result = run(
        tmp_path,
        policy_inputs(requested_intent=requested_intent, risk_action=risk_action),
    ).policy_result
    assert result.execution_authority is False
    assert result.human_confirmation_present is False
    assert result.execution_permission_requested is False
    assert result.live_submission_allowed is False
    assert result.live_execution_allowed is False
    assert result.order_send_allowed is False
    assert result.execution_allowed is False
    assert result.executable is False
    assert result.order_sent is False


def test_policy_result_expiry_is_validated(tmp_path):
    gate = service(tmp_path)
    result = gate.evaluate_candidate(policy_inputs(), now=NOW)
    expired = replace(result, expires_at=(NOW - timedelta(seconds=1)).isoformat())
    validation = gate.validate_policy_result(expired, now=NOW)
    assert not validation.valid
    assert "POLICY_RESULT_EXPIRED" in validation.issues


def test_human_confirmed_draft_method_regime_warning_reaches_controlled_boundary(tmp_path):
    source_inputs = make_human_draft_advisory_block_inputs()
    candidate = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path="unused.jsonl")
    ).build_candidate(source_inputs, now=NOW)
    inputs = AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=source_inputs.risk_result,
        account_context_reference=ACCOUNT_REFERENCE,
        account_context_created_at=NOW.isoformat(),
        account_context_matches=True,
        semantic_proposal_complete=True,
    )

    gate = AutonomousExecutionPolicyGate(
        config=replace(
            enabled_config(tmp_path),
            allowed_operating_modes=("human_confirmed_live",),
        )
    )
    result = gate.run_once(inputs, now=NOW).policy_result

    assert result.decision == "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
    assert result.target_controlled_boundary == "CONTROLLED_OPEN_POSITION"


def test_human_confirmed_draft_non_advisory_risk_block_still_fails_policy(tmp_path):
    source_inputs = make_human_draft_advisory_block_inputs()
    source_inputs.risk_result.blockers.append(DecisionBlocker(code="RISK_LIMIT"))
    candidate = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path="unused.jsonl")
    ).build_candidate(source_inputs, now=NOW)
    inputs = AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=source_inputs.risk_result,
        account_context_reference=ACCOUNT_REFERENCE,
        account_context_created_at=NOW.isoformat(),
        account_context_matches=True,
        semantic_proposal_complete=True,
    )

    result = run(tmp_path, inputs).policy_result

    assert result.decision == "BLOCK"
    assert "RISK_RESULT_BLOCKED" in result.deterministic_reason_codes


def test_default_cli_run_is_blocked_and_redacted(tmp_path, capsys):
    fresh_now = datetime.now(timezone.utc)
    inputs = policy_inputs(now=fresh_now)
    payload = mapping_for_cli(inputs)
    input_path = tmp_path / "policy-input.json"
    input_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    exit_code = policy_cli_main(
        ["--input", str(input_path), "--journal", str(tmp_path / "cli-policy.jsonl")]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "decision=BLOCK" in output
    assert "POLICY_GATE_DISABLED" in output
    assert "target_boundary=NONE" in output
    assert "execution_authority=false" in output
    assert "executable=false" in output
    assert ACCOUNT_REFERENCE not in output
    assert BROKER_HASH not in output


def test_policy_module_and_cli_have_zero_mutation_calls_or_authority_true():
    paths = [
        Path("src/services/trading/decision/autonomous_execution_policy.py"),
        Path("scripts/run_autonomous_policy_once.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    lowered = text.lower()
    assert "controlled" + "-submit" not in lowered
    assert "controlled" + "-manage" not in lowered
    assert ".order" + "_send(" not in text
    assert "Meta" + "Trader5" not in text
    assert "execution_authority=true" not in lowered.replace(" ", "")
    assert "human_confirmation_present=true" not in lowered.replace(" ", "")


def test_sprint39_orchestrator_behavior_remains_unchanged():
    orchestrator = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path="unused.jsonl")
    )
    candidate = orchestrator.build_candidate(make_inputs(), now=NOW)
    validation = orchestrator.validate_candidate(candidate, now=NOW)
    assert validation.valid
    assert candidate.intent == "OPEN_POSITION"
    assert candidate.execution_authority is False


def test_policy_reuses_existing_management_intents():
    source = Path(
        "src/services/trading/decision/autonomous_execution_policy.py"
    ).read_text(encoding="utf-8")
    assert "MT5ManagementIntent" in source
    assert "submit_management" not in source


def run(tmp_path, inputs):
    return service(tmp_path).run_once(inputs, now=NOW)


def service(tmp_path):
    return AutonomousExecutionPolicyGate(config=enabled_config(tmp_path))


def enabled_config(tmp_path):
    return AutonomousExecutionPolicyConfig(
        enabled=True,
        open_eligibility_enabled=True,
        management_eligibility_enabled=True,
        hard_block=False,
        journal_path=str(tmp_path / "policy.jsonl"),
    )


def policy_inputs(
    *,
    risk_action="REVIEW_READY",
    requested_intent="OPEN_POSITION",
    now=NOW,
):
    source_inputs = make_inputs(
        risk_action=risk_action, requested_intent=requested_intent
    )
    if now != NOW:
        timestamp = now.isoformat()
        source_inputs.runtime_context.created_at = timestamp
        source_inputs.method_selection.created_at = timestamp
        source_inputs.score_report.created_at = timestamp
        source_inputs.risk_result.created_at = timestamp
        source_inputs = replace(
            source_inputs,
            lifecycle_status=replace(
                source_inputs.lifecycle_status, last_successful_cycle=timestamp
            ),
        )
    orchestrator = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path="unused.jsonl")
    )
    candidate = orchestrator.build_candidate(source_inputs, now=now)
    return AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=source_inputs.risk_result,
        account_context_reference=ACCOUNT_REFERENCE,
        account_context_created_at=now.isoformat(),
        account_context_matches=True,
        semantic_proposal_complete=True,
    )


def management_policy_inputs(intent, state, effect):
    source_inputs = make_management_inputs(intent, state, effect=effect)
    orchestrator = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig(journal_path="unused.jsonl")
    )
    candidate = orchestrator.build_candidate(source_inputs, now=NOW)
    return AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=source_inputs.risk_result,
        account_context_reference=ACCOUNT_REFERENCE,
        account_context_created_at=NOW.isoformat(),
        account_context_matches=True,
        semantic_proposal_complete=True,
        lifecycle_observation=source_inputs.lifecycle_observation,
        management_exposure_effect=effect,
        requested_close_volume="0.5" if intent == "CLOSE_POSITION" else "1.0",
        observed_volume="1.0",
    )


def mapping_for_cli(inputs):
    return {
        "candidate": asdict(inputs.candidate),
        "risk_result": inputs.risk_result.as_dict() if inputs.risk_result else None,
        "account_context_reference": inputs.account_context_reference,
        "account_context_created_at": inputs.account_context_created_at,
        "account_context_matches": inputs.account_context_matches,
        "semantic_proposal_complete": inputs.semantic_proposal_complete,
        "lifecycle_observation": (
            inputs.lifecycle_observation.to_protected_dict()
            if inputs.lifecycle_observation
            else None
        ),
        "reconciliation_result": (
            json.loads(inputs.reconciliation_result.to_safe_json())
            if inputs.reconciliation_result
            else None
        ),
        "management_exposure_effect": inputs.management_exposure_effect,
        "requested_close_volume": inputs.requested_close_volume,
        "observed_volume": inputs.observed_volume,
    }


def canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

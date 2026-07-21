from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.test_live_order_contract_final_review import _config as _final_review_config
from scripts.test_live_order_contract_parameterization import _config as _parameterization_config
from scripts.test_live_order_contract_parameterization import _inputs as _parameterization_inputs
from scripts.test_mt5_request_dict_dry_run_builder import _config as _dry_run_config
from scripts.test_mt5_request_dict_dry_run_builder import _inputs as _dry_run_inputs
from src.services.trading.execution.live_order_contract_final_review.builder import (
    LiveOrderContractFinalReviewBuilder,
)
from src.services.trading.execution.live_order_contract_final_review.gate import (
    LiveOrderContractFinalReviewGate,
)
from src.services.trading.execution.live_order_contract_final_review.models import (
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
)
from src.services.trading.execution.live_order_contract_parameterization.builder import (
    LiveOrderContractParameterizationBuilder,
)
from src.services.trading.execution.live_order_contract_parameterization.gate import (
    LiveOrderContractParameterizationGate,
)
from src.services.trading.execution.live_value_approval_lock.models import (
    APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES,
    APPROVED_SEMANTIC_EXECUTION_SCHEMA_VERSION,
    ApprovedSemanticExecutionParameters,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.builder import (
    MT5RequestDictDryRunBuilder,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.gate import (
    MT5RequestDictDryRunBuilderGate,
)
from src.services.trading.execution.mt5_request_dict_final_validation.builder import (
    MT5RequestDictFinalValidationBuilder,
)
from src.services.trading.execution.mt5_request_dict_final_validation.gate import (
    MT5RequestDictFinalValidationGate,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import (
    MT5RequestDictFinalValidationConfig,
)


def _semantic_values(**overrides):
    values = {
        "action": "MARKET",
        "symbol": "SYNTHETIC_TEST_SYMBOL",
        "volume": "1.00",
        "order_type": "BUY",
        "price": "100.2500",
        "stop_loss": "99.5",
        "take_profit": "102.00",
        "deviation": 5,
        "magic": 34001,
        "comment": "synthetic-fixture-only",
        "idempotency": "fixture-idempotency",
        "audit": "fixture-audit-reference",
    }
    values.update(overrides)
    return values


def _contract(values=None, **metadata):
    refs = {
        "approval_artifact_ref": "approval-ref",
        "lock_artifact_ref": "lock-ref",
        "source_artifact_ref": "source-ref",
        "approved_at": "2026-07-21T00:00:00+00:00",
        "locked_at": "2026-07-21T00:00:01+00:00",
    }
    refs.update(metadata)
    return ApprovedSemanticExecutionParameters.from_mapping(values or _semantic_values(), **refs)


def _bind_contract(approval_lock, values=None):
    contract = ApprovedSemanticExecutionParameters.from_mapping(
        values or _semantic_values(),
        approval_artifact_ref=approval_lock.confirmation_id,
        lock_artifact_ref=approval_lock.approval_lock_id,
        source_artifact_ref=approval_lock.source_value_proposal_id,
        approved_at=approval_lock.created_at,
        locked_at=approval_lock.created_at,
    )
    approval_lock.approved_semantic_parameters = contract
    approval_lock.approved_semantic_values_hash = contract.canonical_values_hash
    approval_lock.approval_value_hash = contract.canonical_values_hash
    approval_lock.lock_value_hash = contract.canonical_values_hash
    approval_lock.artifact_hash = contract.canonical_values_hash
    return contract


def _parameterization_from_bound_lock(tmp_path: Path):
    inputs = _parameterization_inputs(tmp_path)
    contract = _bind_contract(inputs["approval_lock"])
    builder = LiveOrderContractParameterizationBuilder(_parameterization_config(tmp_path))
    parameterization = builder.build(
        **inputs,
        require_approved_semantic_values=True,
    )
    report = LiveOrderContractParameterizationGate(_parameterization_config(tmp_path)).validate(parameterization)
    return inputs, contract, parameterization, report


def test_contract_is_frozen_typed_and_contains_exact_allow_list():
    contract = _contract()
    assert contract.schema_version == APPROVED_SEMANTIC_EXECUTION_SCHEMA_VERSION
    assert tuple(contract._canonical_values_payload()) == APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES
    assert contract.volume == Decimal("1")
    assert contract.integrity_valid() is True
    with pytest.raises(FrozenInstanceError):
        contract.volume = Decimal("2")


def test_missing_and_extra_fields_are_rejected():
    missing = _semantic_values()
    missing.pop("price")
    with pytest.raises(ValueError, match="fields mismatch"):
        _contract(missing)
    with pytest.raises(ValueError, match="fields mismatch"):
        _contract(_semantic_values(unexpected="blocked"))


def test_canonical_numeric_ordering_and_hash_are_deterministic():
    first = _contract(_semantic_values(volume="1.00", price="100.2500"))
    second = _contract(_semantic_values(volume=Decimal("1.0"), price=Decimal("100.25")))
    assert first._canonical_values_payload() == second._canonical_values_payload()
    assert first.canonical_values_hash == second.canonical_values_hash


def test_any_value_change_changes_hash():
    original = _contract()
    changed = _contract(_semantic_values(price="100.2501"))
    assert changed.canonical_values_hash != original.canonical_values_hash


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", float("nan"), float("inf")])
def test_non_finite_numeric_values_are_rejected(bad):
    with pytest.raises(ValueError):
        _contract(_semantic_values(price=bad))


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"action": "PENDING"}, "unsupported semantic action"),
        ({"order_type": "HOLD"}, "unsupported semantic order type"),
        ({"volume": []}, "must be numeric"),
        ({"deviation": 1.5}, "non-negative integer"),
    ],
)
def test_unsupported_semantic_values_are_rejected(override, error):
    with pytest.raises((TypeError, ValueError), match=error):
        _contract(_semantic_values(**override))


def test_protected_round_trip_preserves_hash_and_redacted_view_hides_values():
    contract = _contract()
    restored = ApprovedSemanticExecutionParameters.from_protected_dict(contract.to_protected_dict())
    assert restored == contract
    assert restored.canonical_values_hash == contract.canonical_values_hash
    redacted = json.dumps(contract.as_redacted_dict(), sort_keys=True)
    assert "SYNTHETIC_TEST_SYMBOL" not in redacted
    assert "synthetic-fixture-only" not in redacted
    assert contract.canonical_values_hash in redacted
    assert "SYNTHETIC_TEST_SYMBOL" not in repr(contract)


def test_approval_and_lock_bind_same_hash_and_mutation_is_detected(tmp_path):
    inputs = _parameterization_inputs(tmp_path)
    approval_lock = inputs["approval_lock"]
    original = _bind_contract(approval_lock)
    assert approval_lock.approved_semantic_integrity_valid() is True
    assert approval_lock.approval_value_hash == original.canonical_values_hash
    assert approval_lock.lock_value_hash == original.canonical_values_hash

    approval_lock.approved_semantic_parameters = ApprovedSemanticExecutionParameters.from_mapping(
        _semantic_values(price="100.3"),
        approval_artifact_ref=approval_lock.confirmation_id,
        lock_artifact_ref=approval_lock.approval_lock_id,
        source_artifact_ref=approval_lock.source_value_proposal_id,
        approved_at=approval_lock.created_at,
        locked_at=approval_lock.created_at,
    )
    assert approval_lock.approved_semantic_integrity_valid() is False


def test_parameterization_consumes_contract_and_final_review_verifies_hash(tmp_path):
    inputs, contract, parameterization, parameterization_report = _parameterization_from_bound_lock(tmp_path)
    assert parameterization.status == "PARAMETERIZATION_BOUNDARY_CREATED"
    assert parameterization_report.valid is True
    assert parameterization.artifact_hash == contract.canonical_values_hash

    final_review = LiveOrderContractFinalReviewBuilder(_final_review_config(tmp_path)).build(
        parameterization=parameterization,
        parameterization_validation=parameterization_report,
        approval_lock=inputs["approval_lock"],
        approval_lock_validation=inputs["approval_lock_validation"],
        value_proposal=inputs["value_proposal"],
        value_proposal_validation=inputs["value_proposal_validation"],
        parameter_draft=inputs["parameter_draft"],
        parameter_draft_validation=inputs["parameter_draft_validation"],
        parameter_source_boundary=inputs["parameter_source_boundary"],
        parameter_source_validation=inputs["parameter_source_validation"],
        parameter_policy_spec=inputs["parameter_policy_spec"],
        parameter_policy_validation=inputs["parameter_policy_validation"],
        contract_skeleton=inputs["contract_skeleton"],
        contract_skeleton_validation=inputs["contract_skeleton_validation"],
        live_order_intent=inputs["live_order_intent"],
        live_order_intent_validation=inputs["live_order_intent_validation"],
        permission_decision=inputs["permission_decision"],
        preflight_report=inputs["preflight_report"],
        proposal_draft=inputs["proposal_draft"],
        simulated_contract=inputs["simulated_contract"],
        simulated_receipt=inputs["simulated_receipt"],
        confirmation_phrase=EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
        require_approved_semantic_values=True,
    )
    review_report = LiveOrderContractFinalReviewGate(_final_review_config(tmp_path)).validate(final_review)
    assert review_report.valid is True
    assert final_review.artifact_hash == contract.canonical_values_hash
    parameterization.artifact_hash = "changed-after-approval"
    changed = LiveOrderContractFinalReviewBuilder(_final_review_config(tmp_path)).build(
        parameterization=parameterization,
        parameterization_validation=parameterization_report,
        approval_lock=inputs["approval_lock"],
        approval_lock_validation=inputs["approval_lock_validation"],
        value_proposal=inputs["value_proposal"],
        value_proposal_validation=inputs["value_proposal_validation"],
        parameter_draft=inputs["parameter_draft"],
        parameter_draft_validation=inputs["parameter_draft_validation"],
        parameter_source_boundary=inputs["parameter_source_boundary"],
        parameter_source_validation=inputs["parameter_source_validation"],
        parameter_policy_spec=inputs["parameter_policy_spec"],
        parameter_policy_validation=inputs["parameter_policy_validation"],
        contract_skeleton=inputs["contract_skeleton"],
        contract_skeleton_validation=inputs["contract_skeleton_validation"],
        live_order_intent=inputs["live_order_intent"],
        live_order_intent_validation=inputs["live_order_intent_validation"],
        permission_decision=inputs["permission_decision"],
        preflight_report=inputs["preflight_report"],
        proposal_draft=inputs["proposal_draft"],
        simulated_contract=inputs["simulated_contract"],
        simulated_receipt=inputs["simulated_receipt"],
        confirmation_phrase=EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
        require_approved_semantic_values=True,
    )
    assert "APPROVED_SEMANTIC_VALUES_HASH_MISMATCH" in changed.blockers


def test_schema_only_legacy_artifact_is_not_silently_upgraded(tmp_path):
    inputs = _dry_run_inputs(tmp_path)
    boundary = MT5RequestDictDryRunBuilder(_dry_run_config(tmp_path)).build(
        **inputs,
        require_approved_semantic_values=True,
    )
    assert boundary.approved_semantic_values_present is False
    assert boundary.approved_semantic_values_verified is False
    assert "APPROVED_SEMANTIC_VALUES_REQUIRED" in boundary.blockers


def test_final_validation_recognizes_verified_values_without_enabling_execution(tmp_path):
    inputs = _dry_run_inputs(tmp_path)
    contract = _bind_contract(inputs["approval_lock"])
    for name in ("parameterization", "final_review", "request_draft", "draft_final_approval"):
        getattr(inputs[name], "__dict__")["artifact_hash"] = contract.canonical_values_hash

    dry_boundary = MT5RequestDictDryRunBuilder(_dry_run_config(tmp_path)).build(
        **inputs,
        require_approved_semantic_values=True,
    )
    dry_report = MT5RequestDictDryRunBuilderGate(_dry_run_config(tmp_path)).validate(dry_boundary)
    assert dry_report.valid is True
    assert dry_boundary.approved_semantic_values_verified is True
    assert dry_boundary.artifact_hash == contract.canonical_values_hash

    final_config = MT5RequestDictFinalValidationConfig(journal_enabled=False)
    final_boundary = MT5RequestDictFinalValidationBuilder(final_config).build(dry_boundary, dry_report)
    final_report = MT5RequestDictFinalValidationGate(final_config).validate(final_boundary)
    assert final_report.valid is True
    assert final_report.as_dict()["concrete_value_created"] is True
    assert final_boundary.live_execution_allowed is False
    assert final_boundary.order_send_allowed is False
    assert final_boundary.execution_allowed is False
    assert final_boundary.order_sent is False
    assert final_boundary.real_mt5_payload_created is False
    assert final_boundary.broker_submittable_request_dict_created is False


def test_contract_contains_no_mt5_constants_or_execution_permission():
    protected = json.dumps(_contract().to_protected_dict(), sort_keys=True)
    for marker in ("ORDER_TYPE_BUY", "ORDER_TYPE_SELL", "TRADE_ACTION_DEAL", "MetaTrader5"):
        assert marker not in protected
    for permission in ("execution_allowed", "order_send_allowed", "live_submission_allowed"):
        assert permission not in protected

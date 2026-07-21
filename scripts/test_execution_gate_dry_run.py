from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.trading.execution import (
    DryRunExecutionAdapter,
    ExecutionGate,
    ExecutionGatePolicy,
    ExecutionGateValidator,
    IdempotencyKeyBuilder,
    InMemoryIdempotencyStore,
    KillSwitchState,
    artifact_hash,
)
from src.services.trading.execution.models import EXECUTION_GATE_ACTIONS, EXECUTION_MODES
from src.services.trading.review.models import HumanReviewArtifact


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_execution_gate_policy_loads_defaults():
    policy = ExecutionGatePolicy.from_config()
    assert policy.mode == "REVIEW_ONLY"
    assert policy.dry_run_enabled is True
    assert policy.live_enabled is False


def test_default_mode_does_not_allow_live_execution():
    policy = ExecutionGatePolicy.from_config()
    assert policy.live_enabled is False
    assert policy.autonomous_enabled is False


def test_execution_mode_values_exist():
    assert {"DISABLED", "REVIEW_ONLY", "HUMAN_CONFIRMED_DRY_RUN", "HUMAN_CONFIRMED_LIVE_RESERVED", "AUTONOMOUS_DISABLED"}.issubset(EXECUTION_MODES)


def test_execution_gate_action_values_exist():
    assert {"ALLOW_DRY_RUN", "BLOCKED", "ARTIFACT_EXPIRED", "DUPLICATE_ARTIFACT", "INVALID_ARTIFACT", "EXECUTION_DISABLED"}.issubset(EXECUTION_GATE_ACTIONS)


def test_dry_run_enabled_can_allow_dry_run_for_valid_review_artifact():
    decision = _gate().evaluate(_artifact())
    receipt = DryRunExecutionAdapter().run(decision, _artifact())
    assert decision.action == "ALLOW_DRY_RUN"
    assert receipt.allowed is True
    assert receipt.executed is False
    assert receipt.dry_run_only is True


def test_live_execution_remains_disabled():
    decision = _gate().evaluate(_artifact(), mode="HUMAN_CONFIRMED_LIVE_RESERVED")
    assert decision.action == "EXECUTION_DISABLED"
    assert decision.allowed is False


def test_kill_switch_blocks_live_execution_but_warns_for_dry_run():
    gate = ExecutionGate(kill_switch=KillSwitchState(enabled=True, reason="manual_guard"))
    decision = gate.evaluate(_artifact())
    assert decision.action == "ALLOW_DRY_RUN"
    assert any("kill_switch_active" in warning for warning in decision.warnings)


def test_artifact_ttl_expiration_returns_expired():
    old = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    artifact = _artifact(created_at=old)
    decision = _gate(policy=ExecutionGatePolicy(artifact_ttl_seconds=300)).evaluate(artifact)
    assert decision.action == "ARTIFACT_EXPIRED"


def test_duplicate_artifact_returns_duplicate():
    store = InMemoryIdempotencyStore()
    gate = _gate(store=store)
    artifact = _artifact()
    assert gate.evaluate(artifact).action == "ALLOW_DRY_RUN"
    assert gate.evaluate(artifact).action == "DUPLICATE_ARTIFACT"


def test_missing_source_refs_blocks_when_required():
    artifact = _artifact(source_refs=[])
    decision = _gate().evaluate(artifact)
    assert decision.action == "INVALID_ARTIFACT"
    assert any("source" in blocker for blocker in decision.blockers)


def test_blocked_review_artifact_returns_blocked_receipt():
    artifact = _artifact(review_status="BLOCKED", readiness_action="BLOCKED", blockers=[{"code": "blocked"}])
    decision = _gate().evaluate(artifact)
    receipt = DryRunExecutionAdapter().run(decision, artifact)
    assert decision.action == "BLOCKED"
    assert receipt.allowed is False
    assert receipt.executed is False


def test_wait_review_artifact_returns_blocked_receipt():
    artifact = _artifact(review_status="WAITING", readiness_action="WAIT")
    decision = _gate().evaluate(artifact)
    receipt = DryRunExecutionAdapter().run(decision, artifact)
    assert decision.action == "BLOCKED"
    assert receipt.allowed is False


def test_ready_for_review_artifact_allows_dry_run_only():
    decision = _gate().evaluate(_artifact())
    assert decision.action == "ALLOW_DRY_RUN"
    assert decision.allowed is True
    assert decision.dry_run_only is True


def test_receipt_always_has_executed_false():
    receipt = DryRunExecutionAdapter().run(_gate().evaluate(_artifact()), _artifact())
    assert receipt.executed is False


def test_receipt_always_has_dry_run_only_true():
    receipt = DryRunExecutionAdapter().run(_gate().evaluate(_artifact()), _artifact())
    assert receipt.dry_run_only is True


def test_idempotency_key_is_stable():
    builder = IdempotencyKeyBuilder()
    assert builder.build("a", "b", "REVIEW_ONLY", "XAUUSD", "t") == builder.build("a", "b", "REVIEW_ONLY", "XAUUSD", "t")


def test_artifact_hash_is_stable():
    artifact = _artifact()
    assert artifact_hash(artifact) == artifact_hash(artifact)


def test_validator_rejects_buy_sell():
    receipt = _receipt()
    receipt.warnings.append("contains_" + "buy")
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_price_and_size_markers():
    receipt = _receipt()
    receipt.warnings.extend(["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_order_submission_marker():
    receipt = _receipt()
    receipt.warnings.append("order" + "_send")
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_executable_order_fields():
    receipt = _receipt()
    receipt.warnings.append("executable_order")
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_raw_candles():
    receipt = _receipt()
    receipt.warnings.append("raw_candles")
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_raw_full_book_or_report_text():
    receipt = _receipt()
    receipt.warnings.extend(["full_raw_book", "full_raw_report"])
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_validator_rejects_account_id_and_credentials():
    receipt = _receipt()
    receipt.warnings.extend(["account_id", "api_key", "password"])
    assert not ExecutionGateValidator().validate_receipt(receipt).passed


def test_session_limit_blocks_dry_run():
    store = InMemoryIdempotencyStore()
    store.dry_run_count = 20
    decision = _gate(store=store).evaluate(_artifact())
    assert decision.action == "BLOCKED"
    assert "dry_run_session_limit_exceeded" in decision.blockers


def test_dry_run_disabled_returns_execution_disabled():
    decision = _gate(policy=ExecutionGatePolicy(dry_run_enabled=False)).evaluate(_artifact())
    assert decision.action == "EXECUTION_DISABLED"


def test_receipt_preserves_source_ids_and_refs():
    receipt = _receipt()
    assert receipt.source_gate_decision_id
    assert receipt.source_review_artifact_id == "artifact_fixture"
    assert SOURCE_REF in receipt.source_refs


def test_gate_decision_payload_contains_no_forbidden_trade_outputs():
    payload = json.dumps(_gate().evaluate(_artifact()).as_dict()).lower()
    assert "buy" not in payload
    assert "sell" not in payload
    assert "order" + "_send" not in payload


def test_receipt_payload_contains_no_forbidden_trade_outputs():
    payload = json.dumps(_receipt().as_dict()).lower()
    assert "buy" not in payload
    assert "sell" not in payload
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_execution_gate_does_not_import_forbidden_runtime_dependencies():
    root = Path("src/services/trading/execution")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text
    assert "LLMReasoningAdapter" not in text


def test_execution_gate_has_no_order_submission_call_marker():
    root = Path("src/services/trading/execution")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "order" + "_send(" not in text


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def _gate(policy: ExecutionGatePolicy | None = None, store: InMemoryIdempotencyStore | None = None) -> ExecutionGate:
    return ExecutionGate(policy=policy or ExecutionGatePolicy(), idempotency_store=store or InMemoryIdempotencyStore())


def _receipt():
    artifact = _artifact()
    decision = _gate().evaluate(artifact)
    return DryRunExecutionAdapter().run(decision, artifact)


def _artifact(
    review_status: str = "READY_FOR_REVIEW",
    readiness_action: str = "REVIEW_READY",
    created_at: str | None = None,
    source_refs: list[str] | None = None,
    blockers: list[dict] | None = None,
) -> HumanReviewArtifact:
    return HumanReviewArtifact(
        artifact_id="artifact_fixture",
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        review_status=review_status,
        readiness_action=readiness_action,
        readiness_score=0.82,
        confidence=0.78,
        grade="GOOD",
        primary_method_id="al_brooks_trend_pullback",
        selected_playbook_ids=["trend_pullback_v1"],
        primary_regime="PULLBACK_UPTREND",
        calendar_risk_state="CLEAR",
        final_context_score=0.82,
        reasons=["score_above_review_ready_threshold"],
        warnings=[],
        blockers=blockers or [],
        source_refs=[SOURCE_REF] if source_refs is None else source_refs,
        source_readiness_decision_id="readiness_fixture",
        source_score_report_id="score_fixture",
        source_method_selection_id="method_selection_fixture",
        source_context_pack_id="context_fixture",
    )

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.test_approval_final_validation_pre_submit import _prepared
from scripts.test_autonomous_candidate_monitor import FeatureService
from scripts.test_operator_review_confirmation_lifecycle import NOW
from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitorJournal,
)
from src.services.trading.decision.autonomous_trading_coordinator import (
    AutonomousManagementEvaluation,
    AutonomousTradingCoordinator,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementReceipt,
    MT5ControlledManagementRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.human_confirmed_management import build_management_proposal
from src.services.trading.position_read_model import (
    PositionProvenance,
    PositionReadItem,
    PositionReadModel,
)
from tools.mt5_bridge.management import (
    ControlledMT5ManagementService,
    ControlledManagementConfig,
    ProtectedBridgeManagementRequest,
)


DASHBOARD_PATH = Path(__file__).parents[1] / "src" / "ui" / "tab_dashboard.py"


ACCOUNT = "a" * 64
TARGET = "b" * 64
EXECUTION = "execution-management-source"
STRATEGY = "strategy-autonomous-management"


@pytest.mark.parametrize(
    ("intent", "state", "values", "backend", "resulting"),
    [
        ("CANCEL_PENDING_ORDER", "ORDER_ACTIVE", {}, "CANCEL_PENDING_ORDER", None),
        (
            "MODIFY_POSITION_PROTECTION",
            "POSITION_OPEN",
            {"requested_stop_loss": Decimal("95")},
            "MODIFY_POSITION_PROTECTION",
            "1",
        ),
        (
            "PARTIAL_CLOSE",
            "POSITION_OPEN",
            {"close_fraction": Decimal("0.5")},
            "CLOSE_POSITION",
            "0.5",
        ),
        ("CLOSE_POSITION", "POSITION_OPEN", {}, "CLOSE_POSITION", "0"),
    ],
)
def test_active_mandate_authorizes_each_bounded_management_family(
    tmp_path, intent, state, values, backend, resulting
):
    fixture = _fixture(tmp_path, state=state)
    proposal = _proposal(fixture, intent, values)

    authorization = _authorize(fixture, proposal, intent)

    assert authorization.management_intent == intent
    assert authorization.backend_management_intent == backend
    assert proposal.requested_resulting_volume == resulting
    assert authorization.integrity_valid()
    assert authorization.to_public_dict()["target_redacted"] is True
    request = MT5ControlledManagementRequest.from_mandate_authorization(
        proposal, authorization, current_time=NOW
    )
    request.validate(NOW)
    assert request.authorization_source == "STANDING_MANDATE"
    assert request.human_confirmation_reference == ""


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ({"mandate_id": "missing"}, "MANDATE_INTEGRITY_INVALID"),
        ({"account_fingerprint": "c" * 64}, "MANDATE_ACCOUNT_MISMATCH"),
        ({"strategy_reference": "wrong-strategy"}, "MANDATE_STRATEGY_MISMATCH"),
        ({"current_kill_switch_engaged": True}, "KILL_SWITCH_ENGAGED"),
        ({"lifecycle_healthy": False}, "LIFECYCLE_NOT_HEALTHY"),
        ({"reconciliation_healthy": False}, "RECONCILIATION_NOT_HEALTHY"),
    ],
)
def test_management_authority_fails_closed_on_scope_and_runtime_mismatch(
    tmp_path, change, blocker
):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})

    with pytest.raises(TradingAuthorityError, match=blocker):
        _authorize(fixture, proposal, "CLOSE_POSITION", **change)


def test_intent_outside_mandate_and_symbol_mismatch_are_blocked(tmp_path):
    fixture = _fixture(
        tmp_path, permitted_management_actions=("CLOSE_POSITION",)
    )
    proposal = _proposal(fixture, "PARTIAL_CLOSE", {"close_fraction": Decimal("0.5")})
    with pytest.raises(
        TradingAuthorityError, match="MANDATE_MANAGEMENT_INTENT_NOT_ALLOWED"
    ):
        _authorize(fixture, proposal, "PARTIAL_CLOSE")

    symbol_fixture = _fixture(tmp_path / "symbol")
    symbol_proposal = _proposal(
        symbol_fixture, "PARTIAL_CLOSE", {"close_fraction": Decimal("0.5")}
    )
    changed_target = replace(symbol_fixture.target, canonical_symbol="BTCUSD")
    with pytest.raises(TradingAuthorityError, match="MANDATE_SYMBOL_NOT_ALLOWED"):
        symbol_fixture.authority.authorize_management(
            symbol_proposal,
            changed_target,
            **_authorization_kwargs(symbol_fixture, "PARTIAL_CLOSE"),
        )


def test_expired_and_revoked_mandate_block_before_and_after_proposal(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    with pytest.raises(TradingAuthorityError, match="MANDATE_EXPIRED_OR_INACTIVE"):
        _authorize(fixture, proposal, "CLOSE_POSITION", now=NOW + timedelta(hours=2))

    authorization = _authorize(fixture, proposal, "CLOSE_POSITION")
    fixture.authority.revoke_mandate(
        fixture.mandate.mandate_id,
        operator_grant=True,
        revocation_nonce="revoke-management",
        now=NOW + timedelta(seconds=1),
    )
    blockers = _validate(
        fixture, authorization.authorization_id, proposal, now=NOW + timedelta(seconds=2)
    )
    assert "MANDATE_REVOKED" in blockers


def test_current_target_and_lifecycle_are_revalidated_before_management(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    authorization = _authorize(fixture, proposal, "CLOSE_POSITION")

    changed_target = replace(fixture.target, volume=Decimal("0.5"))
    blockers = fixture.authority.validate_management_authorization(
        authorization.authorization_id,
        proposal,
        changed_target,
        **_validation_kwargs(),
        now=NOW,
    )
    assert "POSITION_VOLUME_CHANGED" in blockers


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ({"concurrent_positions": 6}, "MANDATE_POSITION_LIMIT_EXCEEDED"),
        ({"trades_today": 11}, "MANDATE_TRADE_LIMIT_EXCEEDED"),
        ({"loss_today": "10"}, "MANDATE_DAILY_LOSS_LIMIT_EXHAUSTED"),
    ],
)
def test_management_authority_preserves_mandate_limits(tmp_path, change, blocker):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    with pytest.raises(TradingAuthorityError, match=blocker):
        _authorize(fixture, proposal, "CLOSE_POSITION", **change)


def test_stale_management_request_is_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    authorization = _authorize(fixture, proposal, "CLOSE_POSITION")
    with pytest.raises(ValueError, match="LIFECYCLE_OBSERVATION_STALE"):
        MT5ControlledManagementRequest.from_mandate_authorization(
            proposal, authorization, current_time=NOW + timedelta(minutes=6)
        )


def test_bridge_independently_reloads_mandate_authority(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    authorization = _authorize(fixture, proposal, "CLOSE_POSITION")
    request = MT5ControlledManagementRequest.from_mandate_authorization(
        proposal, authorization, current_time=NOW
    )
    bridge_request = ProtectedBridgeManagementRequest.from_payload(
        request.as_protected_dict()
    )
    service = ControlledMT5ManagementService(
        SimpleNamespace(),
        config=ControlledManagementConfig(
            authority_journal_path=str(fixture.authority.store.path)
        ),
        mt5_module=SimpleNamespace(),
    )

    service._validate_mandate_authority(bridge_request, NOW)

    fixture.authority.revoke_mandate(
        fixture.mandate.mandate_id,
        operator_grant=True,
        revocation_nonce="bridge-revocation",
        now=NOW,
    )
    with pytest.raises(ValueError, match="MANDATE_(?:REVOKED|NOT_CURRENT)"):
        service._validate_mandate_authority(bridge_request, NOW)


def test_duplicate_management_authorization_is_idempotent(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "CLOSE_POSITION", {})
    first = _authorize(fixture, proposal, "CLOSE_POSITION")
    second = _authorize(fixture, proposal, "CLOSE_POSITION")
    rows = fixture.authority.store.read_strict()
    assert first.authorization_id == second.authorization_id
    assert sum(row["event_type"] == "MANAGEMENT_AUTHORIZED" for row in rows) == 1


def test_autonomous_coordinator_reuses_single_management_boundary_and_unknown_never_retries(
    tmp_path,
):
    fixture = _fixture(tmp_path)
    adapter = _ManagementAdapter(status="UNKNOWN")
    position_service = _PositionService(fixture.model, fixture.observation)
    coordinator = _coordinator(fixture, position_service, adapter, tmp_path)

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "RESULT_UNKNOWN"
    assert result.intent == "CLOSE_POSITION"
    assert result.generation_count == 0
    assert len(adapter.calls) == 1
    assert adapter.calls[0].authorization_source == "STANDING_MANDATE"
    assert adapter.calls[0].human_confirmation_phrase == ""


def test_management_no_action_stops_before_opening_candidate_generation(tmp_path):
    fixture = _fixture(tmp_path)
    adapter = _ManagementAdapter()
    position_service = _PositionService(fixture.model, fixture.observation)
    coordinator = _coordinator(
        fixture,
        position_service,
        adapter,
        tmp_path,
        evaluation=AutonomousManagementEvaluation(decision="NO_ACTION"),
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "NO_ACTION"
    assert result.generation_count == 0
    assert adapter.calls == []


def test_revocation_immediately_before_adapter_blocks_with_zero_writes(tmp_path):
    fixture = _fixture(tmp_path)
    adapter = _ManagementAdapter()
    position_service = _PositionService(fixture.model, fixture.observation)

    def context(evaluation, target, inputs):
        fixture.authority.revoke_mandate(
            fixture.mandate.mandate_id,
            operator_grant=True,
            revocation_nonce="revoke-before-management",
            now=NOW,
        )
        return _management_context(fixture)

    coordinator = _coordinator(
        fixture, position_service, adapter, tmp_path, context_provider=context
    )
    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "BLOCKED"
    assert result.blocker == "MANDATE_REVOKED"
    assert adapter.calls == []


def test_confirmed_management_simulation_updates_the_shared_position_read_model(
    tmp_path,
):
    fixture = _fixture(tmp_path)
    position_service = _PositionService(fixture.model, fixture.observation)
    adapter = _ManagementAdapter(
        on_call=lambda: position_service.apply_closed_position()
    )
    coordinator = _coordinator(fixture, position_service, adapter, tmp_path)

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))
    refreshed = position_service.read(
        query_type="CURRENT", canonical_symbol="XAUUSD", singular=False
    )

    assert result.status == "RESULT_CONFIRMED"
    assert len(adapter.calls) == 1
    assert refreshed.open_positions == ()
    assert refreshed.selected_position is None


def test_public_material_redacts_account_target_and_management_values(tmp_path):
    fixture = _fixture(tmp_path)
    proposal = _proposal(fixture, "PARTIAL_CLOSE", {"close_fraction": Decimal("0.5")})
    authorization = _authorize(fixture, proposal, "PARTIAL_CLOSE")
    request = MT5ControlledManagementRequest.from_mandate_authorization(
        proposal, authorization, current_time=NOW
    )

    rendered = json.dumps(request.as_redacted_dict())
    assert ACCOUNT not in rendered
    assert TARGET not in rendered
    assert "0.5" not in rendered
    assert authorization.to_public_dict()["execution_authority"] is False


def test_standing_mandate_ui_exposes_all_canonical_management_intents():
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    for intent in (
        "CANCEL_PENDING_ORDER",
        "MODIFY_POSITION_PROTECTION",
        "PARTIAL_CLOSE",
        "CLOSE_POSITION",
    ):
        assert f'"{intent}"' in source


def _fixture(tmp_path, *, state="POSITION_OPEN", permitted_management_actions=None):
    prepared = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(prepared["candidate"], operating_mode="autonomous_live")
    authority = TradingAuthorityService(
        TradingAuthorityStore(tmp_path / "authority.jsonl")
    )
    authority.set_mode(
        "autonomous_live",
        account_fingerprint=ACCOUNT,
        account_is_demo=True,
        operator_grant=True,
        nonce="autonomous-management-mode",
        now=NOW,
    )
    mandate = authority.grant_mandate(
        mandate_id="autonomous-management-mandate",
        mandate_version=1,
        account_fingerprint=ACCOUNT,
        account_is_demo=True,
        permitted_symbols=("XAUUSD",),
        permitted_broker_symbols=("XAUUSDm",),
        permitted_order_families=("MARKET", "PENDING"),
        permitted_management_actions=permitted_management_actions
        or (
            "CANCEL_PENDING_ORDER",
            "MODIFY_POSITION_PROTECTION",
            "PARTIAL_CLOSE",
            "CLOSE_POSITION",
        ),
        maximum_volume="2",
        maximum_risk_per_trade="2",
        maximum_concurrent_positions=5,
        maximum_trades_per_day=10,
        maximum_loss_per_day="10",
        active_from=(NOW - timedelta(minutes=1)).isoformat(),
        active_until=(NOW + timedelta(hours=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        nonce="autonomous-management-mandate-nonce",
        idempotency_key="autonomous-management-mandate-key",
        kill_switch_engaged=False,
        operator_grant=True,
        now=NOW,
    )
    opening = authority.authorize_candidate(
        candidate,
        mandate_id=mandate.mandate_id,
        account_fingerprint=ACCOUNT,
        account_is_demo=True,
        evaluated_risk_per_trade="0.5",
        concurrent_positions=0,
        trades_today=0,
        loss_today="0",
        current_kill_switch_engaged=False,
        lifecycle_healthy=True,
        reconciliation_healthy=True,
        authorization_nonce="opening-authorization",
        now=NOW,
    )
    observation = _observation(state)
    target = PositionReadItem(
        protected_reference=TARGET,
        canonical_symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        direction="BUY",
        volume=Decimal("1"),
        state=state,
        occurred_at=NOW.isoformat(),
        stop_loss=Decimal("90"),
        take_profit=Decimal("120"),
        provenance=PositionProvenance(
            strategy_reference=STRATEGY,
            candidate_reference=candidate.candidate_reference,
            authorization_reference=opening.authorization_id,
            execution_reference=EXECUTION,
            lifecycle_reference=observation.observation_id,
        ),
    )
    model = PositionReadModel(
        schema_version="position-read-model/v1",
        query_type="PENDING" if state == "ORDER_ACTIVE" else "CURRENT",
        status="AVAILABLE",
        snapshot_reference="snapshot-reference",
        snapshot_timestamp=NOW.isoformat(),
        account_context_match=True,
        open_positions=(target,) if state != "ORDER_ACTIVE" else (),
        pending_orders=(target,) if state == "ORDER_ACTIVE" else (),
        selected_position=target,
        account_context_fingerprint=ACCOUNT,
    )
    return SimpleNamespace(
        authority=authority,
        mandate=mandate,
        candidate=candidate,
        opening=opening,
        observation=observation,
        target=target,
        model=model,
    )


def _observation(state):
    stable = {
        "protected_execution_reference": EXECUTION,
        "lifecycle_state": state,
        "account_fingerprint_hash": hashlib.sha256(ACCOUNT.encode()).hexdigest(),
        "evidence_classification": "UNIQUE_MANAGEMENT_TARGET",
        "protected_broker_references": {
            "orders": [TARGET] if state == "ORDER_ACTIVE" else [],
            "deals": [],
            "positions": [] if state == "ORDER_ACTIVE" else [TARGET],
        },
        "discrepancy_reason": "",
        "source_snapshot_reference": "snapshot-reference",
    }
    digest = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MT5LifecycleObservation(
        observation_id="observation-" + digest[:16],
        previous_lifecycle_state="UNKNOWN",
        observation_timestamp=NOW.isoformat(),
        observation_hash=digest,
        **stable,
    )


def _proposal(fixture, intent, values):
    return build_management_proposal(
        semantic_intent=intent,
        model=fixture.model,
        target=fixture.target,
        values=values,
        observation=fixture.observation.to_protected_dict(),
        current_time=NOW,
    )


def _authorization_kwargs(fixture, intent):
    return {
        "semantic_management_intent": intent,
        "mandate_id": fixture.mandate.mandate_id,
        "strategy_reference": fixture.target.provenance.strategy_reference,
        "source_candidate_authorization_reference": fixture.opening.authorization_id,
        "evaluation_reference": "strategy-exit-evaluation",
        "policy_reference": "deterministic-management-policy",
        "account_fingerprint": ACCOUNT,
        "account_is_demo": True,
        "concurrent_positions": 1,
        "trades_today": 1,
        "loss_today": "0",
        "current_kill_switch_engaged": False,
        "lifecycle_healthy": True,
        "reconciliation_healthy": True,
        "authorization_nonce": "management-authorization",
        "now": NOW,
    }


def _authorize(fixture, proposal, intent, **changes):
    values = _authorization_kwargs(fixture, intent)
    values.update(changes)
    return fixture.authority.authorize_management(
        proposal, fixture.target, **values
    )


def _validation_kwargs():
    return {
        "account_fingerprint": ACCOUNT,
        "account_is_demo": True,
        "concurrent_positions": 1,
        "trades_today": 1,
        "loss_today": "0",
        "current_kill_switch_engaged": False,
        "lifecycle_healthy": True,
        "reconciliation_healthy": True,
    }


def _validate(fixture, authorization_id, proposal, **changes):
    values = _validation_kwargs()
    values.update(changes)
    return fixture.authority.validate_management_authorization(
        authorization_id, proposal, fixture.target, **values
    )


class _LifecycleJournal:
    def __init__(self, observation):
        self.observation = observation

    def latest_by_execution(self):
        return {EXECUTION: self.observation.to_protected_dict()}


class _PositionService:
    def __init__(self, model, observation):
        self.model = model
        self.lifecycle_journal = _LifecycleJournal(observation)

    def read(self, *, query_type, canonical_symbol, protected_reference="", singular=False):
        target = self.model.selected_position
        if protected_reference and target and protected_reference != target.protected_reference:
            return replace(self.model, status="BLOCKED", selected_position=None, blockers=("STALE_POSITION_REFERENCE",))
        return replace(self.model, query_type=query_type)

    def apply_closed_position(self):
        self.model = replace(
            self.model,
            open_positions=(),
            selected_position=None,
        )


class _Assembler:
    def build(self, **_kwargs):
        return SimpleNamespace(
            lifecycle_status=SimpleNamespace(
                supervisor_status="HEALTHY",
                bridge_available=True,
                account_context_match=True,
                discrepancy_count=0,
                lifecycle_state_counts={},
            ),
            reconciliation_result=None,
        )


class _ManagementAdapter:
    def __init__(self, status="ACCEPTED", on_call=None):
        self.status = status
        self.on_call = on_call
        self.calls = []

    def manage_prepared_request(self, request):
        self.calls.append(request)
        if self.on_call is not None:
            self.on_call()
        return MT5ControlledManagementReceipt(
            self.status,
            request.management_intent,
            "RESULT_UNKNOWN" if self.status == "UNKNOWN" else "RESULT_CONFIRMED",
            self.status == "ACCEPTED",
            self.status == "UNKNOWN",
            True,
            False,
            False,
            False,
            False,
            "BROKER_RESULT_UNKNOWN" if self.status == "UNKNOWN" else "",
        )


def _management_context(fixture):
    return {
        "mandate_id": fixture.mandate.mandate_id,
        "concurrent_positions": 1,
        "trades_today": 1,
        "loss_today": "0",
        "kill_switch_engaged": False,
        "authorization_nonce": "coordinator-management-authorization",
    }


def _coordinator(
    fixture,
    position_service,
    adapter,
    tmp_path,
    context_provider=None,
    evaluation=None,
):
    evaluation = evaluation or AutonomousManagementEvaluation(
        decision="PROPOSE",
        semantic_intent="CLOSE_POSITION",
        target_reference=fixture.target.protected_reference,
        strategy_reference=fixture.target.provenance.strategy_reference,
        evaluation_reference="coordinator-exit-evaluation",
        policy_reference="coordinator-management-policy",
    )
    return AutonomousTradingCoordinator(
        feature_service=FeatureService("2026-07-21T12:00:00+00:00"),
        input_assembler=_Assembler(),
        account_context_provider=lambda: {
            "status": "OK",
            "account_context_fingerprint": ACCOUNT,
            "account_id_hash": "c" * 64,
            "captured_at": NOW.isoformat(),
            "account_is_demo": True,
            "redacted": True,
        },
        authority_service=fixture.authority,
        position_read_service=position_service,
        management_evaluator=lambda *_args: evaluation,
        management_context_provider=context_provider
        or (lambda *_args: _management_context(fixture)),
        management_adapter=adapter,
        monitor_journal=AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl"),
        clock=lambda: NOW,
    )

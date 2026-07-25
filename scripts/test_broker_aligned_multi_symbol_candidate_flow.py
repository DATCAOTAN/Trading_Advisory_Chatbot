from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, service
from scripts.test_controlled_pending_order_dry_run import (
    FINGERPRINT,
    account_context,
    confirmation_for,
    review_for,
)
from scripts.test_controlled_pending_order_submission import (
    AUTH_TOKEN,
    FakePendingClient,
    FakePendingMT5,
    bridge_service,
    pending_request,
    resign_contract,
)
from scripts.test_structured_market_pending_order_candidate import structured_inputs
from src.config import Config
from src.services.trading.calendar.models import CalendarEvent
from src.services.trading.calendar.relevance import relevance_for_event
from src.services.trading.decision.autonomous_orchestrator import (
    autonomous_market_snapshot_provenance_hash,
)
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    OperatorCandidateInputError,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    ControlledPendingOrderDryRunMapper,
)
from src.services.trading.knowledge.router import KnowledgeRouter
from src.services.trading.market.feature_engine import _spread_state
from src.services.trading.market.market_snapshot_bundle import (
    MarketSnapshotBundle,
    MarketSnapshotBundleBuilder,
)
from src.services.trading.market.models import TickSnapshot
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider
from src.services.trading.market.timeframes import broker_symbol_for
from src.ui.operator_candidate_generation import OperatorCandidateGenerationController
from tools.mt5_bridge.execution import ProtectedBridgeExecutionRequest


def btc_inputs(*, metadata=True):
    base = structured_inputs("BUY_LIMIT")
    snapshot_values = {
        "symbol": "BTCUSD",
        "broker_symbol": "BTCUSDm",
        "point": "0.01",
        "tick_size": "0.01",
        "digits": 2,
        "minimum_distance_points": "10",
        "volume_min": "0.01",
        "volume_max": "10",
        "volume_step": "0.01",
        "tick_value": "0.01",
        "contract_size": "1",
    }
    if not metadata:
        snapshot_values["tick_value"] = None
    return replace(
        base,
        runtime_context=replace(
            base.runtime_context, symbol="BTCUSD", broker_symbol="BTCUSDm"
        ),
        method_selection=replace(base.method_selection, symbol="BTCUSD"),
        score_report=replace(
            base.score_report, symbol="BTCUSD", broker_symbol="BTCUSDm"
        ),
        risk_result=replace(
            base.risk_result, symbol="BTCUSD", broker_symbol="BTCUSDm"
        ),
        order_proposal=replace(base.order_proposal, symbol="BTCUSD"),
        order_market_snapshot=replace(base.order_market_snapshot, **snapshot_values),
    )


class RecordingProvider(MT5BridgeMarketDataProvider):
    def __init__(self):
        super().__init__(bridge_url="http://invalid.local")
        self.request_symbols = []

    def _get_json(self, path, params=None):
        if params and "symbol" in params:
            self.request_symbols.append(params["symbol"])
        if path == "/health":
            return {"status": "OK"}
        if path == "/account":
            return {"account_id_hash": "account-hash"}
        if path == "/tick":
            return {
                "bid": 100.0,
                "ask": 101.0,
                "spread": 1.0,
                "timestamp": NOW.isoformat(),
                "digits": 2,
                "point": 0.01,
                "tick_size": 0.01,
                "minimum_distance_points": 10,
                "volume_min": 0.01,
                "volume_max": 10.0,
                "volume_step": 0.01,
                "tick_value": 0.01,
                "contract_size": 1.0,
            }
        if path == "/ohlcv":
            return {"bars": [], "data_quality": "EMPTY"}
        return {}


def test_shared_resolver_aligns_bundle_and_provider_requests():
    provider = RecordingProvider()
    bundle = MarketSnapshotBundleBuilder(provider).build("BTCUSD", ["M15", "H1", "H4"], 1)
    assert broker_symbol_for("BTCUSD") == "BTCUSDm"
    assert provider.normalize_symbol("BTCUSD") == "BTCUSDm"
    assert bundle.symbol == "BTCUSD"
    assert bundle.broker_symbol == "BTCUSDm"
    assert provider.request_symbols == ["BTCUSDm"] * 4
    assert bundle.tick.tick_value == 0.01
    assert bundle.tick.contract_size == 1.0


def test_xau_mapping_and_no_symbol_controller_call_remain_compatible(tmp_path):
    assert broker_symbol_for("XAUUSD") == Config.MARKET_BROKER_SYMBOL_XAUUSD

    class LegacyAssembler:
        calls = 0
        def build(self):
            self.calls += 1
            return structured_inputs("BUY")

    assembler = LegacyAssembler()
    outcome = OperatorCandidateGenerationController(
        assembler, service(tmp_path)
    ).generate({}, "legacy-request")
    assert outcome.status == "GENERATED"
    assert assembler.calls == 1


def test_explicit_operator_symbol_is_forwarded_once(tmp_path):
    class SymbolAssembler:
        symbols = []
        def build(self, *, symbol=None):
            self.symbols.append(symbol)
            return btc_inputs()

    assembler = SymbolAssembler()
    outcome = OperatorCandidateGenerationController(
        assembler, service(tmp_path)
    ).generate({}, "btc-request", symbol="BTCUSD")
    assert outcome.status == "GENERATED"
    assert assembler.symbols == ["BTCUSD"]


def test_authoritative_assembler_prefers_explicit_symbol():
    class RecordingFeatureService:
        symbols = []
        def build_features(self, symbol, *_args):
            self.symbols.append(symbol)
            raise RuntimeError("stop after symbol capture")

    feature_service = RecordingFeatureService()
    assembler = AuthoritativeAutonomousInputAssembler(
        SimpleNamespace(calendar_provider=SimpleNamespace()),
        feature_service=feature_service,
    )
    with pytest.raises(OperatorCandidateInputError, match="MARKET_SNAPSHOT_UNAVAILABLE"):
        assembler.build(symbol="BTCUSD")
    assert feature_service.symbols == ["BTCUSD"]


def test_candidate_preserves_both_symbols_and_tampering_fails_closed(tmp_path):
    orchestrator = service(tmp_path)
    candidate = orchestrator.build_candidate(btc_inputs(), now=NOW)
    assert candidate.symbol_reference == "BTCUSD"
    assert candidate.broker_symbol_reference == "BTCUSDm"
    assert orchestrator.validate_candidate(candidate, now=NOW).valid

    tampered = replace(candidate, broker_symbol_reference="XAUUSDm")
    validation = orchestrator.validate_candidate(tampered, now=NOW)
    assert not validation.valid
    assert "BROKER_SYMBOL_REFERENCE_MISMATCH" in validation.issues


def test_broker_metadata_is_integrity_bound_and_missing_btc_metadata_blocks(tmp_path):
    complete = btc_inputs()
    missing = btc_inputs(metadata=False)
    assert autonomous_market_snapshot_provenance_hash(
        complete.order_market_snapshot
    ) != autonomous_market_snapshot_provenance_hash(missing.order_market_snapshot)
    candidate = service(tmp_path).build_candidate(missing, now=NOW)
    assert "BROKER_SYMBOL_METADATA_MISSING" in candidate.blocked_reason_codes


def btc_pending_result(tmp_path):
    orchestrator = service(tmp_path)
    inputs = btc_inputs()
    candidate = orchestrator.build_candidate(inputs, now=NOW)
    review = review_for(candidate, broker_symbol="BTCUSDm")
    confirmation = confirmation_for(candidate, review, broker_symbol="BTCUSDm")
    return ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=inputs.order_market_snapshot,
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        expiration_policy="GTC",
        deviation=10,
        magic=42,
        comment="btc-pending-test",
        audit="btc-symbol-integrity",
        now=NOW,
    )


def test_pending_contract_and_terminal_mapping_use_btcusdm(tmp_path):
    result = btc_pending_result(tmp_path)
    assert result.validation.valid
    assert result.contract.symbol == "BTCUSD"
    assert result.contract.broker_symbol == "BTCUSDm"
    assert result.request_draft.broker_symbol == "BTCUSDm"

    current = datetime.now(timezone.utc)
    contract = resign_contract(
        result.contract,
        generated_at=current.isoformat(),
        expires_at=(current + timedelta(minutes=5)).isoformat(),
    )
    request = pending_request(tmp_path, contract=contract)

    class RecordingClient(FakePendingClient):
        seen_symbols = []
        def pending_order_context(self, symbol):
            self.seen_symbols.append(symbol)
            return super().pending_order_context(symbol)

    client = RecordingClient()
    executor = bridge_service(tmp_path, client=client, mt5=FakePendingMT5())
    parsed = ProtectedBridgeExecutionRequest.from_payload(request.as_protected_dict())
    values = executor._validate_pending_integrity(parsed)
    executor._validate_mapping(values)
    mapped = executor._map_request(values)
    assert client.seen_symbols == ["BTCUSDm"]
    assert mapped["symbol"] == "BTCUSDm"


def test_broker_symbol_tampering_is_rejected_by_pending_mapper(tmp_path):
    orchestrator = service(tmp_path)
    inputs = btc_inputs()
    candidate = orchestrator.build_candidate(inputs, now=NOW)
    tampered = replace(candidate, broker_symbol_reference="XAUUSDm")
    review = review_for(tampered, broker_symbol="XAUUSDm")
    confirmation = confirmation_for(tampered, review, broker_symbol="XAUUSDm")
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=tampered,
        market_snapshot=inputs.order_market_snapshot,
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert not result.validation.valid
    assert "BROKER_SYMBOL_REFERENCE_MISMATCH" in result.validation.blockers


def test_btc_spread_and_gold_only_evidence_do_not_fall_back_to_xau():
    bundle = MarketSnapshotBundle(
        bundle_id="btc-bundle",
        created_at=NOW.isoformat(),
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        provider_name="fixture",
        tick=TickSnapshot("BTCUSD", bid=100.0, ask=101.0, spread=1.0),
    )
    assert _spread_state(bundle) == "WIDE"

    gold_event = CalendarEvent(
        event_id="gold-event",
        title="Gold inventory update",
        country="EU",
        currency="EUR",
        impact="LOW",
        event_time_utc=NOW.isoformat(),
    )
    assert relevance_for_event("BTCUSD", gold_event).relevance_score < 0.25

    gold_card = SimpleNamespace(
        macro_id="gold-only",
        affected_assets=["XAUUSD"],
        affected_currencies=["USD"],
        event_type="macro",
        title="Gold macro",
    )
    generic_usd = SimpleNamespace(
        macro_id="generic-usd",
        affected_assets=[],
        affected_currencies=["USD"],
        event_type="macro",
        title="USD macro",
    )
    selected = KnowledgeRouter()._select_macros(
        [gold_card, generic_usd],
        "BTCUSD",
        SimpleNamespace(calendar_risk_state="CLEAR"),
        SimpleNamespace(primary_regime="NEWS_RISK"),
        "autonomous_live",
    )
    assert [item.macro_id for item in selected] == ["generic-usd"]


def test_no_external_or_broker_side_effects_are_introduced():
    assert Config.TRADING_AUTONOMOUS_POLICY_GATE_ENABLED is False
    assert Config.TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION is False
    assert Config.TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND is False
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs, service
from scripts.test_autonomous_supervisor_strategy_binding import _strategy
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    OperatorCandidateInputError,
)


class _Component:
    def __init__(self, value):
        self.value = value

    def build_features(self, *_args, **_kwargs):
        return self.value

    def build(self, *_args, **_kwargs):
        return self.value

    def detect(self, *_args, **_kwargs):
        return self.value

    def route(self, *_args, **_kwargs):
        return self.value

    def select(self, *_args, **_kwargs):
        return self.value

    def score(self, *_args, **_kwargs):
        return self.value

    def decide(self, *_args, **_kwargs):
        return self.value

    def run_once(self):
        return self.value


class _ProposalProvider:
    def __init__(self):
        self.calls = 0

    def produce(self, _request):
        self.calls += 1
        return AutonomousOrderProposalResult(
            blockers=("VALID_NO_PROPOSAL",),
            reason_codes=("NO_PROPOSAL",),
            proposal_status="VALID_NO_PROPOSAL",
        )


def test_explicit_deterministic_strategy_builds_candidate_inputs_without_llm_veto(
    tmp_path,
):
    assembler, provider, method_selector = _assembler()

    result = assembler.build(
        now=NOW,
        symbol="XAUUSD",
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
    )

    assert provider.calls == 0
    assert method_selector.calls == [{"mode": "autonomous_live", "use_llm": False}]
    assert result.direction == "BUY"
    assert result.order_proposal.order_type == "BUY"
    assert result.order_proposal.stop_loss == "98"
    assert result.order_proposal.take_profit == "107"
    assert result.order_proposal.proposed_volume == "0.33"
    assert result.proposal_source == "EDITABLE_TRADE_DRAFT"
    candidate = service(tmp_path).run_once(result, now=NOW).candidate
    assert candidate.intent == "OPEN_POSITION"
    assert candidate.executable is False
    assert candidate.execution_authority is False
    assert candidate.order_send_allowed is False


def test_advisory_provider_no_proposal_remains_no_action_authority():
    assembler, provider, _method_selector = _assembler()

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(now=NOW, symbol="XAUUSD")

    assert exc_info.value.blockers == ("VALID_NO_PROPOSAL", "NO_PROPOSAL")
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("tick_change", "blocker"),
    (
        ({"tick_value": None}, "TICK_VALUE_UNAVAILABLE"),
        ({"volume_step": None}, "VOLUME_STEP_INVALID"),
        ({"minimum_distance_points": 1000}, "STOP_DISTANCE_INVALID"),
    ),
)
def test_deterministic_risk_and_broker_constraints_fail_closed(tick_change, blocker):
    assembler, provider, _method_selector = _assembler(tick_change=tick_change)

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=_strategy(),
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert blocker in exc_info.value.blockers
    assert provider.calls == 0


def test_incomplete_strategy_blocks_before_provider():
    assembler, provider, _method_selector = _assembler()
    strategy = replace(
        _strategy(),
        semantic_unresolved_fields=("indicators.RSI.parameters.period",),
    )

    with pytest.raises(OperatorCandidateInputError):
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=strategy,
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert provider.calls == 0


def test_unknown_runtime_account_environment_fails_closed():
    assembler, provider, _method_selector = _assembler(account_environment="UNKNOWN")

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=_strategy(),
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert "DEMO_ACCOUNT_SCOPE_REQUIRED" in exc_info.value.blockers
    assert provider.calls == 0


def _assembler(*, tick_change=None, account_environment="DEMO"):
    inputs = make_inputs()
    inputs.runtime_context.symbol = "XAUUSD"
    inputs.runtime_context.broker_symbol = "XAUUSDm"
    inputs.method_selection.symbol = "XAUUSD"
    inputs.score_report.symbol = "XAUUSD"
    inputs.score_report.broker_symbol = "XAUUSDm"
    inputs.risk_result.symbol = "XAUUSD"
    inputs.risk_result.broker_symbol = "XAUUSDm"
    strategy = _strategy()
    tick_values = {
        "timestamp": NOW.isoformat(),
        "bid": "100",
        "ask": "101",
        "digits": 2,
        "point": "0.01",
        "tick_size": "0.01",
        "minimum_distance_points": 0,
        "volume_min": "0.01",
        "volume_max": "100",
        "volume_step": "0.01",
        "tick_value": "1",
        "contract_size": "100",
    }
    tick_values.update(tick_change or {})
    tick = SimpleNamespace(**tick_values)
    evidence = SimpleNamespace(
        strategy_identity=strategy.identity,
        regime="RANGING",
        regime_confidence=0.8,
        setup=SimpleNamespace(scores={}, hard_blockers=()),
        features=SimpleNamespace(
            indicator_values={"rsi_14_m1": {"previous": 20.0, "current": 30.0}}
        ),
        reasons=(),
        history=(),
    )
    feature = SimpleNamespace(
        feature_snapshot_id="feature-deterministic",
        created_at=NOW.isoformat(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        source_snapshot_ids=("snapshot-deterministic",),
        blockers=(),
        timeframes=("M1",),
        reasoning_evidence_v2=evidence,
        indicator_snapshots={
            "M1": SimpleNamespace(atr="2", swing_high="110", swing_low="95")
        },
    )
    feature_result = SimpleNamespace(
        feature_snapshot=feature,
        quality_report=SimpleNamespace(status="COMPLETE", warnings=()),
        bundle=SimpleNamespace(
            bundle_id="bundle-deterministic",
            created_at=NOW.isoformat(),
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
            provider_name="mt5_bridge",
            provider_health=SimpleNamespace(status="OK"),
            errors=(),
            tick=tick,
            account_id_hash="a" * 64,
        ),
    )
    account = SimpleNamespace(
        account_id_hash="a" * 64,
        equity="10000",
        free_margin="9000",
        account_environment=account_environment,
        redacted=True,
    )
    provider = _ProposalProvider()
    method_selector = _RecordingMethodSelector(inputs.method_selection)
    assembler = AuthoritativeAutonomousInputAssembler(
        SimpleNamespace(
            provider=SimpleNamespace(get_account=lambda: account),
            calendar_provider=object(),
        ),
        feature_service=_Component(feature_result),
        calendar_builder=_Component(object()),
        regime_detector=_Component(object()),
        knowledge_router=_Component(object()),
        context_builder=_Component(inputs.runtime_context),
        method_selector=method_selector,
        scoring_engine=_Component(inputs.score_report),
        decision_engine=_Component(inputs.risk_result),
        lifecycle_supervisor=_Component(inputs.lifecycle_status),
        proposal_provider=provider,
    )
    return assembler, provider, method_selector


class _RecordingMethodSelector:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def select(self, _context, **kwargs):
        self.calls.append(kwargs)
        return self.value

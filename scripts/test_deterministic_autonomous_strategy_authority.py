from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs, service
from scripts.test_autonomous_supervisor_strategy_binding import _strategy
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalResult,
)
from src.services.trading.decision.autonomous_execution_policy import (
    AutonomousExecutionPolicyConfig,
    AutonomousExecutionPolicyGate,
    AutonomousPolicyInputs,
)
from src.services.trading.decision.models import DecisionBlocker
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    OperatorCandidateInputError,
)
from src.services.trading.proposal.editable_trade_draft import (
    TradeDraftSizingConstraints,
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


@pytest.mark.parametrize(
    ("maximum_risk", "maximum_volume", "volume"),
    (
        ("1000", "100", "0.33"),
        ("30", "100", "0.1"),
        ("1000", "0.05", "0.05"),
        ("30", "0.05", "0.05"),
    ),
)
def test_deterministic_sizing_uses_most_restrictive_mandate_cap(
    maximum_risk, maximum_volume, volume
):
    assembler, _provider, _selector = _assembler(
        maximum_risk=maximum_risk,
        maximum_volume=maximum_volume,
    )

    result = assembler.build(
        now=NOW,
        symbol="XAUUSD",
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
    )

    assert result.order_proposal.proposed_volume == volume
    actual_risk = Decimal(volume) * Decimal("300")
    assert actual_risk <= Decimal(maximum_risk)
    assert Decimal(volume) <= Decimal(maximum_volume)


def test_deterministic_sizing_floors_to_broker_step():
    assembler, _provider, _selector = _assembler(
        tick_change={"volume_step": "0.03"},
        maximum_risk="1000",
        maximum_volume="0.1",
    )

    result = assembler.build(
        now=NOW,
        symbol="XAUUSD",
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
    )

    assert result.order_proposal.proposed_volume == "0.09"


@pytest.mark.parametrize(
    ("maximum_risk", "maximum_volume", "blocker"),
    (
        ("1", "100", "MANDATE_RISK_BUDGET_BELOW_BROKER_MINIMUM"),
        ("1000", "0.005", "MANDATE_VOLUME_LIMIT_BELOW_BROKER_MINIMUM"),
    ),
)
def test_mandate_budget_below_broker_minimum_fails_without_rounding_up(
    maximum_risk, maximum_volume, blocker
):
    assembler, provider, _selector = _assembler(
        maximum_risk=maximum_risk,
        maximum_volume=maximum_volume,
    )

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=_strategy(),
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert exc_info.value.blockers == (blocker,)
    assert provider.calls == 0


def test_autonomous_deterministic_sizing_requires_authoritative_constraints():
    assembler, provider, _selector = _assembler(include_constraints=False)

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=_strategy(),
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert exc_info.value.blockers == ("MANDATE_SIZING_CONSTRAINTS_MISSING",)
    assert provider.calls == 0


@pytest.mark.parametrize("readiness_action", ("WAIT", "NO_TRADE"))
def test_valid_deterministic_draft_preserves_open_eligibility_until_policy(
    tmp_path, readiness_action
):
    assembler, provider, _method_selector = _assembler(
        risk_action=readiness_action
    )
    inputs = assembler.build(
        now=NOW,
        symbol="XAUUSD",
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
    )
    orchestrator = service(tmp_path / "candidate")

    first = orchestrator.run_once(inputs, now=NOW)
    loaded = orchestrator.journal.load_candidate(first.candidate.candidate_reference)
    duplicate = orchestrator.run_once(inputs, now=NOW)

    assert provider.calls == 0
    assert first.candidate.intent == "OPEN_POSITION"
    assert first.candidate.deterministic_eligibility_result == "ELIGIBLE_CANDIDATE"
    assert loaded is not None
    assert (loaded.intent, loaded.deterministic_eligibility_result) == (
        "OPEN_POSITION",
        "ELIGIBLE_CANDIDATE",
    )
    assert duplicate.candidate.candidate_reference == first.candidate.candidate_reference
    assert duplicate.journal_appended is False

    policy = AutonomousExecutionPolicyGate(
        config=AutonomousExecutionPolicyConfig(
            enabled=True,
            open_eligibility_enabled=True,
            hard_block=False,
            allowed_operating_modes=(first.candidate.operating_mode,),
            journal_path=str(tmp_path / "policy.jsonl"),
        )
    ).run_once(
        AutonomousPolicyInputs(
            candidate=loaded,
            risk_result=inputs.risk_result,
            account_context_reference="b" * 64,
            account_context_created_at=NOW.isoformat(),
            account_context_matches=True,
            semantic_proposal_complete=True,
        ),
        now=NOW,
    )
    assert policy.policy_result.decision == "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
    assert policy.policy_result.target_controlled_boundary == "CONTROLLED_OPEN_POSITION"


def test_deterministic_hard_risk_blocker_is_preserved_before_policy(tmp_path):
    assembler, _provider, _method_selector = _assembler(
        risk_action="BLOCKED",
        risk_blockers=(DecisionBlocker(code="RISK_LIMIT"),),
    )
    inputs = assembler.build(
        now=NOW,
        symbol="XAUUSD",
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
    )
    candidate = service(tmp_path).run_once(inputs, now=NOW).candidate

    assert candidate.intent == "NO_ACTION"
    assert candidate.deterministic_eligibility_result == "NOT_ELIGIBLE"
    assert "RISK_RESULT_BLOCKED" in candidate.blocked_reason_codes


def test_false_entry_condition_stops_before_deterministic_draft():
    assembler, provider, _method_selector = _assembler(
        feature_blockers=("ENTRY_CONDITION_FALSE",)
    )

    with pytest.raises(OperatorCandidateInputError) as exc_info:
        assembler.build(
            now=NOW,
            symbol="XAUUSD",
            strategy=_strategy(),
            strategy_direction="BUY",
            strategy_action="OPEN_POSITION",
        )

    assert exc_info.value.blockers == ("ENTRY_CONDITION_FALSE",)
    assert provider.calls == 0


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


def _assembler(
    *,
    tick_change=None,
    account_environment="DEMO",
    risk_action="REVIEW_READY",
    risk_blockers=(),
    feature_blockers=(),
    maximum_risk="1000",
    maximum_volume="100",
    include_constraints=True,
):
    inputs = make_inputs()
    inputs.runtime_context.symbol = "XAUUSD"
    inputs.runtime_context.broker_symbol = "XAUUSDm"
    inputs.method_selection.symbol = "XAUUSD"
    inputs.score_report.symbol = "XAUUSD"
    inputs.score_report.broker_symbol = "XAUUSDm"
    inputs.risk_result.symbol = "XAUUSD"
    inputs.risk_result.broker_symbol = "XAUUSDm"
    inputs.risk_result.action = risk_action
    inputs.risk_result.blockers = list(risk_blockers)
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
        blockers=tuple(feature_blockers),
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
        sizing_constraints_provider=(
            (
                lambda _strategy: TradeDraftSizingConstraints(
                    maximum_risk_amount=Decimal(maximum_risk),
                    maximum_volume=Decimal(maximum_volume),
                    authority_reference="mandate-test:v1",
                )
            )
            if include_constraints else None
        ),
    )
    return assembler, provider, method_selector


class _RecordingMethodSelector:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def select(self, _context, **kwargs):
        self.calls.append(kwargs)
        return self.value

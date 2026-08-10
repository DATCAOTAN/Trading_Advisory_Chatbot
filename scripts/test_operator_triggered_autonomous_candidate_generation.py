from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.services.trading.decision.operator_candidate_generation as generation_module

from scripts.test_autonomous_decision_orchestrator import (
    NOW,
    lifecycle_status,
    make_inputs,
    reconciliation_unknown,
    service,
)
from scripts.test_structured_market_pending_order_candidate import structured_inputs
from src.config import Config
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalResult,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    OperatorCandidateInputError,
    _validate_market_sources,
    _validate_proposal_result,
    _validate_structured_inputs,
)
from src.ui.autonomous_candidate_review import (
    AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY,
    clear_autonomous_decision_run_result,
    get_autonomous_decision_run_result,
)
from src.ui.operator_candidate_generation import (
    AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY,
    OperatorCandidateGenerationController,
)


class StaticAssembler:
    def __init__(self, inputs=None, error: str = ""):
        self.inputs = inputs or make_inputs()
        self.error = error
        self.calls = 0

    def build(self):
        self.calls += 1
        if self.error:
            raise OperatorCandidateInputError(self.error)
        return self.inputs


class CountingOrchestrator:
    def __init__(self, tmp_path, result=None):
        self.delegate = service(tmp_path)
        self.result = result
        self.calls = 0

    def run_once(self, inputs):
        self.calls += 1
        return self.result or self.delegate.run_once(inputs, now=NOW)


def controller(tmp_path, inputs=None, result=None, error=""):
    assembler = StaticAssembler(inputs, error)
    orchestrator = CountingOrchestrator(tmp_path, result)
    return OperatorCandidateGenerationController(assembler, orchestrator), assembler, orchestrator


def market_result(**changes):
    timestamp = changes.pop("timestamp", NOW.isoformat())
    quality_status = changes.pop("quality_status", "COMPLETE")
    broker_symbol = changes.pop("broker_symbol", "XAUUSDm")
    feature = SimpleNamespace(
        feature_snapshot_id="feature-fixture",
        created_at=changes.pop("feature_created_at", NOW.isoformat()),
        symbol=changes.pop("feature_symbol", Config.MARKET_DEFAULT_SYMBOL),
        broker_symbol=broker_symbol,
        source_snapshot_ids=changes.pop("source_snapshot_ids", ["snapshot-safe-ref"]),
        blockers=changes.pop("feature_blockers", []),
    )
    bundle = SimpleNamespace(
        bundle_id="market-bundle-fixture",
        created_at=NOW.isoformat(),
        symbol=Config.MARKET_DEFAULT_SYMBOL,
        provider_name="mt5_bridge",
        provider_health=SimpleNamespace(status=changes.pop("health", "OK")),
        errors=changes.pop("errors", []),
        tick=changes.pop(
            "tick", SimpleNamespace(timestamp=timestamp, bid="100", ask="101")
        ),
        account_id_hash=changes.pop("account_id_hash", "a" * 64),
        broker_symbol=changes.pop("bundle_broker_symbol", broker_symbol),
    )
    assert not changes
    return SimpleNamespace(
        bundle=bundle,
        quality_report=SimpleNamespace(status=quality_status),
        feature_snapshot=feature,
    )


def assert_market_blocker(expected, **changes):
    with pytest.raises(OperatorCandidateInputError, match=expected):
        _validate_market_sources(
            market_result(**changes),
            symbol=Config.MARKET_DEFAULT_SYMBOL,
            now=NOW,
            max_age_seconds=300,
        )


def test_explicit_generation_calls_assembler_and_orchestrator_once(tmp_path):
    value, assembler, orchestrator = controller(tmp_path)
    outcome = value.generate({}, "request-1")
    assert outcome.status == "GENERATED"
    assert assembler.calls == orchestrator.calls == 1


@pytest.mark.parametrize(
    "blocker",
    ("ENTRY_CONDITION_ARMED", "ENTRY_CONDITION_WAITING_FOR_REARM"),
)
def test_autonomous_entry_condition_blocks_before_proposal_provider(blocker):
    with pytest.raises(OperatorCandidateInputError) as exc_info:
        _validate_market_sources(
            market_result(feature_blockers=[blocker]),
            symbol=Config.MARKET_DEFAULT_SYMBOL,
            now=NOW,
            max_age_seconds=300,
        )

    assert exc_info.value.blockers == (
        "STRUCTURED_PROPOSAL_NOT_AVAILABLE",
        blocker,
    )


def test_typed_result_is_stored_through_existing_owner(tmp_path):
    value, _assembler, _orchestrator = controller(tmp_path)
    state = {}
    outcome = value.generate(state, "request-1")
    assert outcome.stored is True
    assert isinstance(get_autonomous_decision_run_result(state), AutonomousDecisionRunResult)


def test_refresh_without_generate_does_not_call_orchestrator(tmp_path):
    _value, assembler, orchestrator = controller(tmp_path)
    state = {}
    assert get_autonomous_decision_run_result(state) is None
    assert assembler.calls == orchestrator.calls == 0


def test_unrelated_rerun_only_reads_stored_result(tmp_path):
    value, assembler, orchestrator = controller(tmp_path)
    state = {}
    value.generate(state, "request-1")
    first = get_autonomous_decision_run_result(state)
    second = get_autonomous_decision_run_result(state)
    assert first is second
    assert assembler.calls == orchestrator.calls == 1


def test_duplicate_request_is_ignored(tmp_path):
    value, assembler, orchestrator = controller(tmp_path)
    state = {}
    value.generate(state, "request-1")
    duplicate = value.generate(state, "request-1")
    assert duplicate.status == "DUPLICATE_IGNORED"
    assert assembler.calls == orchestrator.calls == 1


def test_active_request_guard_prevents_callback_overlap(tmp_path):
    value, assembler, orchestrator = controller(tmp_path)
    state = {AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY: True}
    outcome = value.generate(state, "request-1")
    assert outcome.blocker == "GENERATION_ALREADY_ACTIVE"
    assert assembler.calls == orchestrator.calls == 0


def test_explicit_second_generation_replaces_result(tmp_path):
    value, assembler, orchestrator = controller(tmp_path, make_inputs(risk_action="NO_TRADE"))
    state = {}
    value.generate(state, "request-1")
    first = get_autonomous_decision_run_result(state)
    assembler.inputs = make_inputs(risk_action="WAIT")
    value.generate(state, "request-2")
    second = get_autonomous_decision_run_result(state)
    assert first is not second
    assert assembler.calls == orchestrator.calls == 2


def test_clear_removes_only_current_candidate(tmp_path):
    value, _assembler, _orchestrator = controller(tmp_path)
    state = {"unrelated": "preserved"}
    value.generate(state, "request-1")
    clear_autonomous_decision_run_result(state)
    assert AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY not in state
    assert state["unrelated"] == "preserved"


def test_missing_market_snapshot_blocks_before_orchestrator():
    with pytest.raises(OperatorCandidateInputError, match="MARKET_SNAPSHOT_MISSING"):
        _validate_market_sources(
            SimpleNamespace(bundle=None, quality_report=None, feature_snapshot=None),
            symbol=Config.MARKET_DEFAULT_SYMBOL,
            now=NOW,
            max_age_seconds=300,
        )


def test_stale_market_quality_blocks():
    assert_market_blocker("MARKET_SNAPSHOT_STALE", quality_status="STALE")


def test_stale_tick_blocks():
    assert_market_blocker("MARKET_SNAPSHOT_STALE", timestamp="2026-07-22T00:00:00+00:00")


def test_missing_symbol_metadata_blocks():
    assert_market_blocker("SYMBOL_METADATA_MISSING", broker_symbol="")


def test_symbol_mismatch_blocks():
    assert_market_blocker("SYMBOL_METADATA_MISSING", feature_symbol="EURUSD")


def test_missing_account_context_blocks():
    assert_market_blocker("ACCOUNT_CONTEXT_UNAVAILABLE", account_id_hash="")


def test_unavailable_provider_blocks():
    assert_market_blocker("MARKET_PROVIDER_UNAVAILABLE", health="UNAVAILABLE")


def test_invalid_market_quality_blocks():
    assert_market_blocker("MARKET_SNAPSHOT_INVALID", quality_status="INVALID")


def test_account_context_mismatch_blocks_structured_inputs():
    inputs = replace(make_inputs(), lifecycle_status=lifecycle_status(account_match=False))
    with pytest.raises(OperatorCandidateInputError, match="ACCOUNT_CONTEXT_MISMATCH"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_lifecycle_conflict_blocks_structured_inputs():
    unsafe = replace(lifecycle_status(), discrepancy_count=1)
    inputs = replace(make_inputs(), lifecycle_status=unsafe)
    with pytest.raises(OperatorCandidateInputError, match="LIFECYCLE_CONFLICT"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_stale_lifecycle_blocks_structured_inputs():
    stale = replace(lifecycle_status(), last_successful_cycle="2026-07-22T00:00:00+00:00")
    inputs = replace(make_inputs(), lifecycle_status=stale)
    with pytest.raises(OperatorCandidateInputError, match="LIFECYCLE_STALE"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_reconciliation_conflict_blocks_structured_inputs():
    inputs = replace(make_inputs(), reconciliation_result=reconciliation_unknown())
    with pytest.raises(OperatorCandidateInputError, match="RECONCILIATION_UNRESOLVED"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_missing_reasoning_evidence_blocks_structured_inputs():
    inputs = make_inputs()
    inputs.runtime_context.source_refs.clear()
    with pytest.raises(OperatorCandidateInputError, match="STRUCTURED_REASONING_EVIDENCE_MISSING"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_reference_mismatch_blocks_structured_inputs():
    inputs = make_inputs()
    inputs.score_report.source_context_pack_id = "different-context"
    with pytest.raises(OperatorCandidateInputError, match="STRUCTURED_RUNTIME_REFERENCE_MISMATCH"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_provider_failure_preserves_previous_candidate(tmp_path):
    initial = service(tmp_path).run_once(make_inputs(), now=NOW)
    value, assembler, orchestrator = controller(tmp_path, error="MARKET_SNAPSHOT_UNAVAILABLE")
    state = {AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY: initial}
    outcome = value.generate(state, "request-1")
    assert outcome.blocker == "MARKET_SNAPSHOT_UNAVAILABLE"
    assert get_autonomous_decision_run_result(state) is initial
    assert assembler.calls == 1 and orchestrator.calls == 0


def test_malformed_orchestrator_result_is_not_stored(tmp_path):
    value, _assembler, orchestrator = controller(tmp_path)
    orchestrator.result = object()
    state = {}
    outcome = value.generate(state, "request-1")
    assert outcome.blocker == "INVALID_ORCHESTRATOR_RESULT"
    assert get_autonomous_decision_run_result(state) is None


def test_invalid_result_preserves_previous_candidate(tmp_path):
    initial = service(tmp_path).run_once(make_inputs(), now=NOW)
    invalid = replace(initial, validation=replace(initial.validation, valid=False, issues=("INVALID",)))
    value, _assembler, _orchestrator = controller(tmp_path, result=invalid)
    state = {AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY: initial}
    outcome = value.generate(state, "request-1")
    assert outcome.blocker == "INVALID"
    assert get_autonomous_decision_run_result(state) is initial


def test_journal_failure_preserves_previous_candidate(tmp_path):
    initial = service(tmp_path).run_once(make_inputs(), now=NOW)
    unsafe = replace(initial, persistence_safe=False, journal_warning="DECISION_JOURNAL_CORRUPT")
    value, _assembler, _orchestrator = controller(tmp_path, result=unsafe)
    state = {AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY: initial}
    outcome = value.generate(state, "request-1")
    assert outcome.blocker == "DECISION_JOURNAL_CORRUPT"
    assert get_autonomous_decision_run_result(state) is initial


@pytest.mark.parametrize(
    ("inputs", "expected_intent", "expected_action"),
    [
        (make_inputs(risk_action="NO_TRADE"), "NO_ACTION", ""),
        (structured_inputs("BUY"), "OPEN_POSITION", "MARKET"),
        (structured_inputs("SELL_LIMIT"), "OPEN_POSITION", "PENDING"),
        (make_inputs(requested_intent="REQUIRE_HUMAN_REVIEW"), "REQUIRE_HUMAN_REVIEW", ""),
    ],
)
def test_valid_result_types_are_stored_without_reclassification(
    tmp_path, inputs, expected_intent, expected_action
):
    value, _assembler, _orchestrator = controller(tmp_path, inputs)
    state = {}
    outcome = value.generate(state, "request-1")
    stored = get_autonomous_decision_run_result(state)
    assert outcome.status == "GENERATED"
    assert stored.candidate.intent == expected_intent
    assert stored.candidate.action == expected_action


def test_every_stored_result_remains_non_executable(tmp_path):
    value, _assembler, _orchestrator = controller(tmp_path, structured_inputs("BUY_STOP"))
    state = {}
    value.generate(state, "request-1")
    candidate = get_autonomous_decision_run_result(state).candidate
    assert candidate.execution_authority is False
    assert candidate.execution_permission_requested is False
    assert candidate.executable is False
    assert candidate.order_send_allowed is False
    assert candidate.order_sent is False


def test_authoritative_assembler_uses_existing_pipeline_in_order():
    inputs = make_inputs()
    calls = []
    feature_result = market_result()

    class Component:
        def __init__(self, name, returned):
            self.name = name
            self.returned = returned

        def _call(self):
            calls.append(self.name)
            return self.returned

        def build_features(self, *args, **kwargs):
            return self._call()

        def build(self, *args, **kwargs):
            return self._call()

        def detect(self, *args, **kwargs):
            return self._call()

        def route(self, *args, **kwargs):
            return self._call()

        def select(self, *args, **kwargs):
            return self._call()

        def score(self, *args, **kwargs):
            return self._call()

        def decide(self, *args, **kwargs):
            return self._call()

        def produce(self, *args, **kwargs):
            return self._call()

        def run_once(self):
            return self._call()

    proposal_inputs = structured_inputs("BUY")
    proposal_result = AutonomousOrderProposalResult(
        proposal_reference="autonomous_order_proposal_fixture",
        created_at=NOW.isoformat(),
        direction="BUY",
        semantic_parameter_references=("autonomous_order_proposal_fixture",),
        order_proposal=proposal_inputs.order_proposal,
        order_market_snapshot=proposal_inputs.order_market_snapshot,
        source_bindings=(
            "feature-fixture",
            "market-bundle-fixture",
            inputs.runtime_context.context_pack_id,
            inputs.method_selection.result_id,
            inputs.score_report.score_report_id,
            inputs.risk_result.decision_id,
        ),
        provenance_hash="a" * 64,
    )
    assembler = AuthoritativeAutonomousInputAssembler(
        SimpleNamespace(provider=object(), calendar_provider=object()),
        feature_service=Component("feature", feature_result),
        calendar_builder=Component("calendar", object()),
        regime_detector=Component("regime", object()),
        knowledge_router=Component("knowledge", object()),
        context_builder=Component("context", inputs.runtime_context),
        method_selector=Component("method", inputs.method_selection),
        scoring_engine=Component("score", inputs.score_report),
        decision_engine=Component("risk", inputs.risk_result),
        lifecycle_supervisor=Component("lifecycle", inputs.lifecycle_status),
        proposal_provider=Component("proposal", proposal_result),
    )
    assembled = assembler.build(now=NOW)
    assert calls == [
        "feature", "calendar", "regime", "knowledge", "context",
        "method", "score", "risk", "lifecycle", "proposal",
    ]
    assert assembled.runtime_context is inputs.runtime_context
    assert assembled.direction == "BUY"
    assert assembled.semantic_parameter_references == (
        "autonomous_order_proposal_fixture",
    )
    assert assembled.order_proposal is proposal_inputs.order_proposal
    assert assembled.order_market_snapshot is proposal_inputs.order_market_snapshot


def test_normal_reasoning_latency_uses_current_handoff_clock(monkeypatch):
    handoff_at = NOW + timedelta(seconds=10)
    inputs = make_inputs()
    for artifact in (
        inputs.runtime_context,
        inputs.method_selection,
        inputs.score_report,
        inputs.risk_result,
    ):
        artifact.created_at = handoff_at.isoformat()
    inputs = replace(
        inputs,
        lifecycle_status=replace(
            inputs.lifecycle_status,
            last_successful_cycle=handoff_at.isoformat(),
        ),
    )
    with pytest.raises(
        OperatorCandidateInputError,
        match="STRUCTURED_RUNTIME_INPUT_STALE",
    ):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)
    feature_result = market_result(
        timestamp=NOW.isoformat(), feature_created_at=NOW.isoformat()
    )
    proposal_inputs = structured_inputs("BUY")
    proposal_result = AutonomousOrderProposalResult(
        proposal_reference="autonomous_order_proposal_fixture",
        created_at=handoff_at.isoformat(),
        direction="BUY",
        semantic_parameter_references=("autonomous_order_proposal_fixture",),
        order_proposal=proposal_inputs.order_proposal,
        order_market_snapshot=proposal_inputs.order_market_snapshot,
        source_bindings=(
            feature_result.feature_snapshot.feature_snapshot_id,
            feature_result.bundle.bundle_id,
            inputs.runtime_context.context_pack_id,
            inputs.method_selection.result_id,
            inputs.score_report.score_report_id,
            inputs.risk_result.decision_id,
        ),
        provenance_hash="a" * 64,
    )

    class Clock(datetime):
        values = iter((NOW, handoff_at))

        @classmethod
        def now(cls, tz=None):
            value = next(cls.values)
            return value if tz is None else value.astimezone(tz)

    class ProposalProvider:
        calls = 0
        request = None

        def produce(self, request):
            self.calls += 1
            self.request = request
            return proposal_result

    provider = ProposalProvider()
    monkeypatch.setattr(generation_module, "datetime", Clock)
    assembler = AuthoritativeAutonomousInputAssembler(
        SimpleNamespace(provider=object(), calendar_provider=object()),
        feature_service=SimpleNamespace(
            build_features=lambda *args, **kwargs: feature_result
        ),
        calendar_builder=SimpleNamespace(build=lambda *args, **kwargs: object()),
        regime_detector=SimpleNamespace(detect=lambda *args, **kwargs: object()),
        knowledge_router=SimpleNamespace(route=lambda *args, **kwargs: object()),
        context_builder=SimpleNamespace(
            build=lambda *args, **kwargs: inputs.runtime_context
        ),
        method_selector=SimpleNamespace(
            select=lambda *args, **kwargs: inputs.method_selection
        ),
        scoring_engine=SimpleNamespace(
            score=lambda *args, **kwargs: inputs.score_report
        ),
        decision_engine=SimpleNamespace(
            decide=lambda *args, **kwargs: inputs.risk_result
        ),
        lifecycle_supervisor=SimpleNamespace(
            run_once=lambda: inputs.lifecycle_status
        ),
        proposal_provider=provider,
    )

    assembled = assembler.build()

    assert provider.calls == 1
    assert provider.request.evaluated_at == handoff_at
    assert provider.request.feature_result is feature_result
    assert provider.request.runtime_context is inputs.runtime_context
    assert provider.request.score_report.source_feature_snapshot_id == (
        feature_result.feature_snapshot.feature_snapshot_id
    )
    assert assembled.runtime_context is inputs.runtime_context


def test_structured_freshness_uses_utc_and_blocks_genuinely_stale_input():
    inputs = make_inputs()
    stale_at = NOW - timedelta(seconds=301)
    for artifact in (
        inputs.runtime_context,
        inputs.method_selection,
        inputs.score_report,
        inputs.risk_result,
    ):
        artifact.created_at = stale_at.replace(tzinfo=None).isoformat()
    with pytest.raises(OperatorCandidateInputError, match="STRUCTURED_RUNTIME_INPUT_STALE"):
        _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


@pytest.mark.parametrize(
    "created_at",
    (NOW.isoformat(), NOW.replace(tzinfo=None).isoformat()),
)
def test_structured_freshness_treats_naive_timestamps_as_utc(created_at):
    inputs = make_inputs()
    for artifact in (
        inputs.runtime_context,
        inputs.method_selection,
        inputs.score_report,
        inputs.risk_result,
    ):
        artifact.created_at = created_at
    _validate_structured_inputs(inputs, now=NOW, max_age_seconds=300)


def test_proposal_snapshot_identity_mismatch_fails_closed():
    inputs = make_inputs()
    proposal_inputs = structured_inputs("BUY")
    result = AutonomousOrderProposalResult(
        proposal_reference="autonomous_order_proposal_fixture",
        created_at=NOW.isoformat(),
        direction="BUY",
        semantic_parameter_references=("autonomous_order_proposal_fixture",),
        order_proposal=proposal_inputs.order_proposal,
        order_market_snapshot=proposal_inputs.order_market_snapshot,
        source_bindings=(
            "different-feature",
            "market-bundle-fixture",
            inputs.runtime_context.context_pack_id,
            inputs.method_selection.result_id,
            inputs.score_report.score_report_id,
            inputs.risk_result.decision_id,
        ),
        provenance_hash="a" * 64,
    )
    with pytest.raises(
        OperatorCandidateInputError,
        match="STRUCTURED_PROPOSAL_REFERENCE_MISMATCH",
    ):
        _validate_proposal_result(result, market_result(), inputs)


def test_generation_code_has_no_export_submission_or_broker_mutation_calls():
    paths = [
        Path("src/services/trading/decision/operator_candidate_generation.py"),
        Path("src/ui/autonomous_candidate_review.py"),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for marker in (
        "controlled-submit",
        "controlled_manage",
        "reconcile(",
        ".order_send(",
        "write_pending_candidate_handoff(",
    ):
        assert marker not in source


def test_dashboard_generation_is_explicit_and_export_remains_separate():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert '"Generate Candidate"' in source
    assert source.count("controller.generate(") == 2
    assert '"Validate and Create Manual Candidate"' in source
    assert source.count("write_pending_candidate_handoff(") == 1
    assert source.index('"Generate Candidate"') < source.index(
        '"Export Protected Pending Candidate"'
    )


@pytest.mark.parametrize(
    ("proposal_result", "expected_blocker"),
    [
        (
            AutonomousOrderProposalResult(
                blockers=("STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON",)
            ),
            "STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON",
        ),
        (
            AutonomousOrderProposalResult(source_bindings=("", "", "", "", "", "")),
            "PROPOSAL_PROVENANCE_MISSING",
        ),
    ],
)
def test_provider_result_blockers_stop_before_orchestrator(
    tmp_path, proposal_result, expected_blocker
):
    class ProviderResultAssembler:
        calls = 0

        def build(self):
            self.calls += 1
            _validate_proposal_result(
                proposal_result,
                market_result(),
                make_inputs(),
            )

    assembler = ProviderResultAssembler()
    orchestrator = CountingOrchestrator(tmp_path)
    value = OperatorCandidateGenerationController(assembler, orchestrator)
    outcome = value.generate({}, "request-proposal-blocked")
    assert outcome.status == "BLOCKED"
    assert outcome.blocker == expected_blocker
    assert assembler.calls == 1
    assert orchestrator.calls == 0


def test_no_proposal_is_natural_no_action_before_orchestrator(tmp_path):
    value, assembler, orchestrator = controller(
        tmp_path, error="STRUCTURED_PROPOSAL_NOT_AVAILABLE"
    )
    outcome = value.generate({}, "request-no-proposal")
    assert outcome.status == "NO_ACTION"
    assert outcome.blocker == "STRUCTURED_PROPOSAL_NOT_AVAILABLE"
    assert outcome.stored is False
    assert assembler.calls == 1
    assert orchestrator.calls == 0

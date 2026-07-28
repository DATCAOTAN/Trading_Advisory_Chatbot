from __future__ import annotations

import json
import os
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.config import Config
from src.services.trading.decision.autonomous_orchestrator import (
    OFFLINE_FIXTURE_MODE,
    OFFLINE_FIXTURE_REFERENCE_PREFIX,
    AutonomousDecisionConfig,
    AutonomousDecisionInputs,
    AutonomousDecisionOrchestrator,
    autonomous_account_context_reference,
)
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalProvider,
    AutonomousOrderProposalRequest,
)
from src.services.trading.decision.models import TradeReadinessDecision
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
    _validate_market_sources,
    _validate_proposal_result,
    _validate_structured_inputs,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.data_quality import DataQualityReport
from src.services.trading.market.feature_models import FeatureSnapshot, IndicatorSnapshot
from src.services.trading.market.live_feature_service import LiveFeatureResult
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundle
from src.services.trading.market.models import MarketSnapshot, OHLCVBar, ProviderHealth, TickSnapshot
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport


OFFLINE_FIXTURE_SCHEMA = "offline-autonomous-candidate-fixture/v1"
DEFAULT_REFERENCE_TIME = "2026-07-21T12:00:00+00:00"

_EXECUTION_FLAGS = (
    "TRADING_AUTONOMOUS_POLICY_GATE_ENABLED",
    "TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED",
    "TRADING_AUTONOMOUS_MANAGEMENT_ELIGIBILITY_ENABLED",
    "TRADING_EXECUTION_LIVE_ENABLED",
    "TRADING_EXECUTION_AUTONOMOUS_ENABLED",
    "TRADING_EXECUTION_LIVE_ADAPTER_ENABLED",
    "TRADING_EXECUTION_MT5_LIVE_ADAPTER_ENABLED",
    "TRADING_MT5_LIVE_EXECUTION_ENABLED",
    "TRADING_MT5_ORDER_SEND_ENABLED",
    "TRADING_MT5_EXECUTION_BRIDGE_ENABLED",
    "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION",
    "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND",
    "TRADING_MT5_LIVE_ADAPTER_ENABLED",
    "TRADING_MT5_CONTROLLED_EXECUTION_ENABLED",
    "TRADING_MT5_PENDING_SUBMISSION_ENABLED",
    "TRADING_MT5_PENDING_LIMIT_ENABLED",
    "TRADING_MT5_PENDING_STOP_ENABLED",
    "TRADING_MT5_PENDING_STOP_LIMIT_ENABLED",
    "TRADING_MT5_CONTROLLED_MANAGEMENT_ENABLED",
    "TRADING_MT5_MANAGEMENT_CANCEL_ALLOWED",
    "TRADING_MT5_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED",
    "TRADING_MT5_MANAGEMENT_POSITION_CLOSE_ALLOWED",
    "MT5_BRIDGE_ORDER_SEND_ENABLED",
    "MT5_BRIDGE_LIVE_EXECUTION_ENABLED",
    "MT5_BRIDGE_CONTROLLED_EXECUTION_ENABLED",
    "MT5_BRIDGE_PENDING_SUBMISSION_ENABLED",
    "MT5_BRIDGE_PENDING_LIMIT_ENABLED",
    "MT5_BRIDGE_PENDING_STOP_ENABLED",
    "MT5_BRIDGE_PENDING_STOP_LIMIT_ENABLED",
    "MT5_BRIDGE_CONTROLLED_MANAGEMENT_ENABLED",
    "MT5_BRIDGE_MANAGEMENT_CANCEL_ALLOWED",
    "MT5_BRIDGE_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED",
    "MT5_BRIDGE_MANAGEMENT_POSITION_CLOSE_ALLOWED",
)


@dataclass(frozen=True)
class OfflineScenario:
    name: str
    risk_action: str = "REVIEW_READY"
    order_type: str = "BUY"
    proposal_status: str = "PROPOSE"
    stale_market: bool = False
    account_context_match: bool = True
    reconciliation_unresolved: bool = False
    lifecycle_discrepancy: bool = False
    source_reference_mismatch: bool = False
    invalid_price_relation: bool = False
    invalid_volume: bool = False
    malformed_proposal: bool = False
    schema_invalid_proposal: bool = False


SCENARIOS = {
    item.name: item
    for item in (
        OfflineScenario("fresh_no_action", risk_action="WAIT", proposal_status="NO_PROPOSAL"),
        OfflineScenario("fresh_human_review", risk_action="REQUIRE_HUMAN_REVIEW"),
        OfflineScenario("fresh_market"),
        OfflineScenario("fresh_pending", order_type="BUY_LIMIT"),
        OfflineScenario("invalid_price_relation", order_type="BUY_LIMIT", invalid_price_relation=True),
        OfflineScenario("invalid_volume", invalid_volume=True),
        OfflineScenario("stale_market", stale_market=True),
        OfflineScenario("source_reference_mismatch", source_reference_mismatch=True),
        OfflineScenario("account_context_mismatch", account_context_match=False),
        OfflineScenario("lifecycle_discrepancy", lifecycle_discrepancy=True),
        OfflineScenario("reconciliation_discrepancy", reconciliation_unresolved=True),
        OfflineScenario("malformed_proposal", malformed_proposal=True),
        OfflineScenario("schema_invalid_proposal", schema_invalid_proposal=True),
    )
}


class DeterministicProposalAdapter:
    def __init__(self, response: str) -> None:
        self.response = response
        self.invocation_count = 0

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        del prompt, max_tokens, temperature
        self.invocation_count += 1
        return self.response


def load_offline_scenario(scenario_or_path: str | Path) -> tuple[OfflineScenario, datetime]:
    name = str(scenario_or_path)
    if name in SCENARIOS:
        return SCENARIOS[name], _timestamp(DEFAULT_REFERENCE_TIME)
    try:
        payload = json.loads(Path(scenario_or_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("OFFLINE_FIXTURE_INVALID") from exc
    required = {
        "schema_version",
        "scenario",
        "reference_timestamp",
        "offline_provenance",
        "non_exportable",
        "non_submittable",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("OFFLINE_FIXTURE_SCHEMA_INVALID")
    if (
        payload["schema_version"] != OFFLINE_FIXTURE_SCHEMA
        or payload["offline_provenance"] != OFFLINE_FIXTURE_MODE
        or payload["non_exportable"] is not True
        or payload["non_submittable"] is not True
        or payload["scenario"] not in SCENARIOS
    ):
        raise ValueError("OFFLINE_FIXTURE_SAFETY_INVALID")
    return SCENARIOS[payload["scenario"]], _timestamp(payload["reference_timestamp"])


def run_offline_candidate_acceptance(
    scenario_or_path: str | Path, *, journal_path: str | Path | None = None
) -> dict[str, Any]:
    previous = os.environ.get("TRADING_OFFLINE_ACCEPTANCE")
    os.environ["TRADING_OFFLINE_ACCEPTANCE"] = "true"
    try:
        return _run_offline_candidate_acceptance(scenario_or_path, journal_path=journal_path)
    finally:
        if previous is None:
            os.environ.pop("TRADING_OFFLINE_ACCEPTANCE", None)
        else:
            os.environ["TRADING_OFFLINE_ACCEPTANCE"] = previous


def _run_offline_candidate_acceptance(
    scenario_or_path: str | Path, *, journal_path: str | Path | None = None
) -> dict[str, Any]:
    _require_execution_disabled()
    scenario, reference_time = load_offline_scenario(scenario_or_path)
    feature_result = _feature_result(scenario, reference_time)
    inputs = _decision_inputs(scenario, reference_time)
    adapter = DeterministicProposalAdapter(_proposal_response(scenario))
    result = _base_report(scenario, reference_time, feature_result)

    try:
        _validate_market_sources(
            feature_result,
            symbol="XAUUSD",
            now=reference_time,
            max_age_seconds=300,
        )
        result["freshness_result"] = "FRESH"
        _validate_structured_inputs(inputs, now=reference_time, max_age_seconds=300)
        proposal = AutonomousOrderProposalProvider(adapter).produce(
            AutonomousOrderProposalRequest(
                feature_result=feature_result,
                runtime_context=inputs.runtime_context,
                method_selection=inputs.method_selection,
                score_report=inputs.score_report,
                risk_decision=inputs.risk_result,
                evaluated_at=reference_time,
                maximum_age_seconds=300,
            )
        )
        _validate_proposal_result(proposal, feature_result, inputs)
        inputs = replace(
            inputs,
            direction=proposal.direction,
            semantic_parameter_references=proposal.semantic_parameter_references,
            order_proposal=proposal.order_proposal,
            order_market_snapshot=proposal.order_market_snapshot,
        )
        context = (
            nullcontext("")
            if journal_path is not None
            else tempfile.TemporaryDirectory(prefix="offline-candidate-")
        )
        with context as temporary:
            selected_journal_path = (
                Path(journal_path)
                if journal_path is not None
                else Path(temporary) / "offline-decisions.jsonl"
            )
            orchestrator = AutonomousDecisionOrchestrator(
                AutonomousDecisionConfig(
                    ttl_seconds=300,
                    input_max_age_seconds=300,
                    journal_path=str(selected_journal_path),
                )
            )
            run = orchestrator.run_once(inputs, now=reference_time)
            candidate = run.candidate
            records = orchestrator.journal.records()
            duplicate_appended = orchestrator.journal.append_idempotent(candidate)
            records_after_duplicate = orchestrator.journal.records()
        persisted = (
            run.journal_appended
            and len(records) == 1
            and records[0]["candidate_reference"] == candidate.candidate_reference
            and records[0]["provenance_hash"] == candidate.provenance_hash
        )
        if (
            not run.validation.valid
            or not run.persistence_safe
            or not persisted
            or duplicate_appended
            or len(records_after_duplicate) != 1
            or candidate.operating_mode != OFFLINE_FIXTURE_MODE
            or not candidate.market_snapshot_reference.startswith(
                OFFLINE_FIXTURE_REFERENCE_PREFIX
            )
            or any(
                (
                    candidate.execution_authority,
                    candidate.human_confirmation_present,
                    candidate.execution_permission_requested,
                    candidate.live_submission_allowed,
                    candidate.live_execution_allowed,
                    candidate.order_send_allowed,
                    candidate.execution_allowed,
                    candidate.executable,
                    candidate.order_sent,
                )
            )
        ):
            raise RuntimeError("OFFLINE_PROVENANCE_INVARIANT_FAILED")
        result.update(
            generation_count=1,
            candidate_admission_count=1,
            candidate_persistence_count=1,
            candidate_integrity_result="VALID",
            candidate_provenance_result="VALID",
            duplicate_admission_result="REJECTED_IDEMPOTENTLY",
            candidate_reference=candidate.candidate_reference,
            natural_intent=(
                candidate.action if candidate.intent == "OPEN_POSITION" else candidate.intent
            ),
            candidate_intent=candidate.intent,
            eligibility=candidate.deterministic_eligibility_result,
            validation_result=run.validation.valid,
            validation_issues=list(run.validation.issues),
            ordered_reason_codes=list(candidate.blocked_reason_codes),
            ordered_blockers=list(candidate.blocked_reason_codes),
            generated_timestamp=candidate.generated_at,
            expiry_timestamp=candidate.expires_at,
        )
    except OperatorCandidateInputError as exc:
        blockers = list(exc.blockers)
        if blockers == ["STRUCTURED_PROPOSAL_NOT_AVAILABLE"]:
            result.update(
                natural_intent="NO_PROPOSAL",
                eligibility="NOT_ELIGIBLE",
                validation_result=True,
                ordered_reason_codes=blockers,
                ordered_blockers=[],
            )
            result["deterministic_proposal_adapter_invocation_count"] = adapter.invocation_count
            return result
        result.update(
            natural_intent="BLOCKED",
            validation_result=False,
            ordered_reason_codes=blockers,
            ordered_blockers=blockers,
        )
        if any("STALE" in item for item in blockers):
            result["freshness_result"] = "STALE"

    result["deterministic_proposal_adapter_invocation_count"] = adapter.invocation_count
    if adapter.invocation_count > 1 or result["generation_count"] > 1:
        raise RuntimeError("OFFLINE_INVOCATION_LIMIT_EXCEEDED")
    return result


def _base_report(
    scenario: OfflineScenario,
    reference_time: datetime,
    feature_result: LiveFeatureResult,
) -> dict[str, Any]:
    return {
        "status": "COMPLETED",
        "scenario_name": scenario.name,
        "offline_provenance": OFFLINE_FIXTURE_MODE,
        "reference_timestamp": reference_time.isoformat(),
        "resolved_symbol": feature_result.bundle.broker_symbol,
        "market_snapshot_timestamps": {
            "bundle": feature_result.bundle.created_at,
            "tick": feature_result.bundle.tick.timestamp if feature_result.bundle.tick else "",
        },
        "freshness_result": "BLOCKED",
        "external_proposal_provider_invocation_count": 0,
        "deterministic_proposal_adapter_invocation_count": 0,
        "generation_count": 0,
        "candidate_admission_count": 0,
        "candidate_persistence_count": 0,
        "candidate_integrity_result": "NOT_CREATED",
        "candidate_provenance_result": "NOT_CREATED",
        "duplicate_admission_result": "NOT_APPLICABLE",
        "candidate_reference": "",
        "natural_intent": "BLOCKED",
        "candidate_intent": "",
        "eligibility": "NOT_ELIGIBLE",
        "readiness": scenario.risk_action,
        "validation_result": False,
        "validation_issues": [],
        "ordered_reason_codes": [],
        "ordered_blockers": [],
        "generated_timestamp": "",
        "expiry_timestamp": "",
        "lifecycle_result": "HEALTHY",
        "reconciliation_result": (
            "RESULT_UNKNOWN" if scenario.reconciliation_unresolved else "NOT_PRESENT"
        ),
        "account_context_result": "MATCH" if scenario.account_context_match else "MISMATCH",
        "export_eligibility": False,
        "submission_eligibility": False,
        "protected_export_count": 0,
        "submission_count": 0,
        "broker_mutation_count": 0,
        "metadata_redacted": True,
    }

def _decision_inputs(
    scenario: OfflineScenario,
    reference_time: datetime,
) -> AutonomousDecisionInputs:
    created_at = reference_time.isoformat()
    source_ref = OFFLINE_FIXTURE_REFERENCE_PREFIX + "source"
    context = RuntimeContextPack(
        context_pack_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "context",
        created_at=created_at,
        mode=OFFLINE_FIXTURE_MODE,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={"data_quality_status": "COMPLETE"},
        calendar_context_summary={"calendar_risk_state": "CLEAR"},
        market_regime_summary={"primary_regime": "TREND"},
        selected_method_cards=[{"method_id": "offline_method"}],
        source_refs=[source_ref],
    )
    method = MethodSelectionResult(
        result_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "reasoning",
        created_at=created_at,
        mode=context.mode,
        symbol=context.symbol,
        primary_method_id="offline_method",
        selected_playbook_ids=["offline_playbook"],
        overall_context_fit=0.82,
        confidence=0.82,
        candidate_assessments=[
            MethodCandidateAssessment(
                method_id="offline_method",
                role="PRIMARY_CANDIDATE",
                compatibility_score=0.82,
                source_refs=[source_ref],
            )
        ],
        source_context_pack_id=context.context_pack_id,
        source_refs=[source_ref],
    )
    score = SignalScoreReport(
        score_report_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "score",
        created_at=created_at,
        mode=context.mode,
        symbol=context.symbol,
        broker_symbol=context.broker_symbol,
        primary_method_id=method.primary_method_id,
        selected_playbook_ids=["offline_playbook"],
        final_context_score=0.82,
        grade="GOOD",
        source_feature_snapshot_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "feature",
        source_calendar_context_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "calendar",
        source_regime_snapshot_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "regime",
        source_context_pack_id=context.context_pack_id,
        source_method_selection_id=method.result_id,
        source_refs=[source_ref],
    )
    if scenario.source_reference_mismatch:
        score = replace(
            score,
            source_method_selection_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "wrong-method",
        )
    risk = TradeReadinessDecision(
        decision_id=OFFLINE_FIXTURE_REFERENCE_PREFIX + "risk",
        created_at=created_at,
        mode=context.mode,
        symbol=context.symbol,
        broker_symbol=context.broker_symbol,
        action=scenario.risk_action,
        readiness_score=0.82,
        confidence=0.82,
        grade="GOOD",
        primary_method_id=method.primary_method_id,
        source_score_report_id=score.score_report_id,
        source_feature_snapshot_id=score.source_feature_snapshot_id,
        source_calendar_context_id=score.source_calendar_context_id,
        source_regime_snapshot_id=score.source_regime_snapshot_id,
        source_context_pack_id=context.context_pack_id,
        source_method_selection_id=method.result_id,
        source_refs=[source_ref],
    )
    lifecycle = MT5RuntimeSupervisorStatus(
        supervisor_status="HEALTHY",
        last_successful_cycle=created_at,
        lifecycle_state_counts={},
        discrepancy_count=1 if scenario.lifecycle_discrepancy else 0,
        bridge_available=True,
        account_context_match=scenario.account_context_match,
        records_inspected=0,
        health_reason="OFFLINE_FIXTURE",
    )
    reconciliation = (
        MT5ReconciliationReceipt(
            status="BLOCKED",
            reconciliation_reference=OFFLINE_FIXTURE_REFERENCE_PREFIX + "reconciliation",
            evidence_classification="RESULT_UNKNOWN",
            original_execution_state="RESULT_UNKNOWN",
            resulting_execution_state="RESULT_UNKNOWN",
            retry_decision="RETRY_PROHIBITED",
            order_reference_present=False,
            deal_reference_present=False,
            position_reference_present=False,
        )
        if scenario.reconciliation_unresolved
        else None
    )
    return AutonomousDecisionInputs(
        runtime_context=context,
        method_selection=method,
        score_report=score,
        risk_result=risk,
        lifecycle_status=lifecycle,
        reconciliation_result=reconciliation,
        requested_intent="OPEN_POSITION",
        exposure_effect="NONE",
        timeframe_profile=("M15", "H1", "H4"),
        account_context_reference=autonomous_account_context_reference("c" * 64),
    )


def _feature_result(
    scenario: OfflineScenario,
    reference_time: datetime,
) -> LiveFeatureResult:
    observed_at = reference_time - timedelta(seconds=301) if scenario.stale_market else reference_time
    created_at = reference_time.isoformat()
    prefix = OFFLINE_FIXTURE_REFERENCE_PREFIX
    bars = [
        OHLCVBar(
            timestamp=(reference_time - timedelta(minutes=15)).isoformat(),
            open=100.0,
            high=102.0,
            low=99.0,
            close=100.5,
            volume=1.0,
            timeframe="M15",
            symbol="XAUUSD",
            source=OFFLINE_FIXTURE_MODE,
        )
    ]
    bundle = MarketSnapshotBundle(
        bundle_id=prefix + "market-bundle",
        created_at=created_at,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        provider_name=OFFLINE_FIXTURE_MODE,
        timeframes={
            timeframe: MarketSnapshot(
                symbol="XAUUSD",
                timeframe=timeframe,
                bars=bars,
                source=OFFLINE_FIXTURE_MODE,
                fetched_at=created_at,
                provider_name=OFFLINE_FIXTURE_MODE,
                data_quality="COMPLETE",
            )
            for timeframe in ("M15", "H1", "H4")
        },
        tick=TickSnapshot(
            symbol="XAUUSD",
            bid=100.0,
            ask=101.0,
            spread=1.0,
            timestamp=observed_at.isoformat(),
            provider_name=OFFLINE_FIXTURE_MODE,
            digits=2,
            point=0.01,
            tick_size=0.01,
            minimum_distance_points=10.0,
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
            tick_value=1.0,
            contract_size=100.0,
        ),
        account_id_hash="c" * 64,
        source=OFFLINE_FIXTURE_MODE,
        data_quality_summary="COMPLETE",
        provider_health=ProviderHealth(
            provider_name=OFFLINE_FIXTURE_MODE,
            status="OK",
            checked_at=created_at,
            details_redacted={"offline_fixture": True},
        ),
    )
    indicator = IndicatorSnapshot(
        symbol="XAUUSD",
        timeframe="M15",
        computed_at=created_at,
        atr=1.2,
        latest_close=100.5,
        swing_high=103.0,
        swing_low=98.0,
        support_zones=[99.0],
        resistance_zones=[102.0],
        data_quality="COMPLETE",
    )
    feature = FeatureSnapshot(
        feature_snapshot_id=prefix + "feature",
        created_at=created_at,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        provider_name=OFFLINE_FIXTURE_MODE,
        timeframes=["M15", "H1", "H4"],
        primary_timeframe="M15",
        indicator_snapshots={"M15": indicator},
        trend_direction="UP",
        trend_strength=0.8,
        volatility_state="NORMAL",
        momentum_state="POSITIVE",
        pullback_detected=True,
        multi_timeframe_alignment="ALIGNED",
        data_quality_status="COMPLETE",
        source_snapshot_ids=[prefix + "market-snapshot"],
    )
    quality = DataQualityReport(
        status="COMPLETE",
        per_timeframe_quality={item: "COMPLETE" for item in ("M15", "H1", "H4")},
        latest_timestamp_by_timeframe={
            item: bars[0].timestamp for item in ("M15", "H1", "H4")
        },
        provider_name=OFFLINE_FIXTURE_MODE,
        checked_at=created_at,
    )
    return LiveFeatureResult(bundle, quality, feature, 0.0, 0.0)


def _proposal_response(scenario: OfflineScenario) -> str:
    if scenario.malformed_proposal:
        return '{"status":"PROPOSE","order_type":'
    if scenario.proposal_status == "NO_PROPOSAL":
        return json.dumps(
            {
                "status": "NO_PROPOSAL",
                "order_type": None,
                "entry_price": None,
                "trigger_price": None,
                "limit_price": None,
                "stop_loss": None,
                "take_profit": None,
                "proposed_volume": None,
                "reason_codes": ["NO_PROPOSAL"],
                "blockers": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    payload: dict[str, Any] = {
        "status": "PROPOSE",
        "order_type": scenario.order_type,
        "entry_price": None,
        "trigger_price": None,
        "limit_price": None,
        "stop_loss": "99",
        "take_profit": "102",
        "proposed_volume": "0" if scenario.invalid_volume else "0.01",
        "reason_codes": ["OFFLINE_METHOD_ALIGNED"],
        "blockers": [],
    }
    if scenario.order_type == "BUY_LIMIT":
        payload.update(
            entry_price="102" if scenario.invalid_price_relation else "99",
            stop_loss="98",
            take_profit="103",
        )
    if scenario.schema_invalid_proposal:
        payload["unexpected"] = True
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _require_execution_disabled() -> None:
    enabled = [name for name in _EXECUTION_FLAGS if bool(getattr(Config, name, False))]
    if enabled:
        raise RuntimeError("OFFLINE_HARNESS_EXECUTION_FLAGS_ENABLED:" + ",".join(enabled))


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("OFFLINE_FIXTURE_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("OFFLINE_FIXTURE_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)

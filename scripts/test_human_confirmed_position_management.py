from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.ui import tab_chatbot

from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import resolve_structured_semantics
from src.services.semantic.structured_semantics import StructuredSemanticResult
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementReceipt,
    management_confirmation_phrase,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
)
from src.services.trading.human_confirmed_management import (
    HumanConfirmedManagementService,
    ManagementProposalPatch,
)
from src.services.trading.position_read_model import (
    PositionProvenance,
    PositionReadItem,
    PositionReadModel,
)


ACCOUNT = "a" * 64
EXECUTION = "execution-reference"
POSITION = "b" * 64
ORDER = "c" * 64


class _LifecycleJournal:
    def __init__(self, observation):
        self.observation = observation

    def latest_by_execution(self):
        return {EXECUTION: self.observation.to_protected_dict()}


class _PositionService:
    def __init__(self, model, observation):
        self.model = model
        self.lifecycle_journal = _LifecycleJournal(observation)
        self.read_calls = 0

    def read_from_query_plan(self, _query_plan):
        return self.model

    def read(self, **_kwargs):
        self.read_calls += 1
        return self.model


class _Adapter:
    def __init__(self, status="ACCEPTED"):
        self.status = status
        self.calls = []

    def manage_prepared_request(self, request, *, typed_confirmation):
        self.calls.append((request, typed_confirmation))
        return MT5ControlledManagementReceipt(
            self.status,
            request.management_intent,
            "CHECK_REGISTERED",
            self.status == "ACCEPTED",
            self.status == "UNKNOWN",
            True,
            self.status == "ACCEPTED",
            False,
            False,
            False,
            "",
        )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _observation(state, *, order=False, position=True, fingerprint=ACCOUNT):
    stable = {
        "protected_execution_reference": EXECUTION,
        "lifecycle_state": state,
        "account_fingerprint_hash": _sha(fingerprint),
        "evidence_classification": "UNIQUE_MANAGEMENT_TARGET",
        "protected_broker_references": {
            "orders": [ORDER] if order else [],
            "deals": [],
            "positions": [POSITION] if position else [],
        },
        "discrepancy_reason": "",
        "source_snapshot_reference": "snapshot-reference",
    }
    digest = _sha(json.dumps(stable, sort_keys=True, separators=(",", ":")))
    return MT5LifecycleObservation(
        observation_id="observation-" + digest[:16],
        previous_lifecycle_state="UNKNOWN",
        observation_timestamp=datetime.now(timezone.utc).isoformat(),
        observation_hash=digest,
        **stable,
    )


def _item(*, state="POSITION_OPEN", reference=POSITION, volume=1.0, stop=90.0, take=120.0):
    observation = _observation(state, order=state == "ORDER_ACTIVE", position=state != "ORDER_ACTIVE")
    return PositionReadItem(
        protected_reference=reference,
        canonical_symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        direction="BUY",
        volume=volume,
        state=state,
        occurred_at=observation.observation_timestamp,
        stop_loss=stop,
        take_profit=take,
        provenance=PositionProvenance(
            execution_reference=EXECUTION,
            lifecycle_reference=observation.observation_id,
        ),
    ), observation


def _model(item, *, blockers=(), fingerprint=ACCOUNT):
    return PositionReadModel(
        schema_version="position-read-model/v1",
        query_type="PENDING" if item and item.state == "ORDER_ACTIVE" else "CURRENT",
        status="BLOCKED" if blockers else "AVAILABLE",
        snapshot_reference="snapshot-reference",
        snapshot_timestamp=datetime.now(timezone.utc).isoformat(),
        account_context_match=not blockers,
        open_positions=(item,) if item and item.state != "ORDER_ACTIVE" else (),
        pending_orders=(item,) if item and item.state == "ORDER_ACTIVE" else (),
        selected_position=None if blockers else item,
        blockers=tuple(blockers),
        account_context_fingerprint=fingerprint,
    )


def _plan(intent, conditions=(), *, action="MANAGE_POSITION"):
    conditions = list(conditions)
    return SimpleNamespace(
        primary_intent="position_management",
        constraints={"requested_mode": "human_confirmed_live"},
        semantic_context={
            "input": {
                "action": action,
                "subtype": intent,
                "conditions": conditions,
                "explicit_fields": [f"conditions[{index}]" for index in range(len(conditions))],
                "account_scope": "DEMO",
            }
        },
    )


def _condition(subject, value):
    return {"subject": subject, "operator": "EQUAL", "value": value}


def _service(item, observation, *, adapter=None, model=None):
    position_service = _PositionService(model or _model(item), observation)
    return HumanConfirmedManagementService(
        position_read_service=position_service,
        adapter=adapter or _Adapter(),
    ), position_service


def test_cancel_pending_order_requires_exact_human_confirmation():
    item, observation = _item(state="ORDER_ACTIVE", reference=ORDER)
    service, _ = _service(item, observation)
    outcome = service.create_from_query_plan(_plan("CANCEL_PENDING_ORDER"))
    assert outcome.proposal is not None
    assert outcome.proposal.status == "NON_EXECUTABLE"
    assert outcome.proposal.confirmation_required is True
    assert outcome.proposal.backend_proposal.management_intent == "CANCEL_PENDING_ORDER"


@pytest.mark.parametrize(
    "blocker",
    ["POSITION_NOT_FOUND", "AMBIGUOUS_POSITION_REFERENCE", "STALE_POSITION_REFERENCE"],
)
def test_target_resolution_blockers_never_create_a_proposal(blocker):
    item, observation = _item()
    service, _ = _service(item, observation, model=_model(item, blockers=(blocker,)))
    outcome = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION"))
    assert outcome.proposal is None
    assert outcome.blockers == (blocker,)


@pytest.mark.parametrize(
    ("conditions", "expected_stop", "expected_take"),
    [
        ((_condition("requested_stop_loss", 95),), "95", "120"),
        ((_condition("requested_take_profit", 130),), "90", "130"),
        ((_condition("requested_stop_loss", 95), _condition("requested_take_profit", 130)), "95", "130"),
    ],
)
def test_modify_protection_preserves_the_unchanged_side(conditions, expected_stop, expected_take):
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(_plan("MODIFY_POSITION_PROTECTION", conditions)).proposal
    assert proposal is not None
    assert proposal.backend_proposal.requested_stop_loss == expected_stop
    assert proposal.backend_proposal.requested_take_profit == expected_take


def test_modify_protection_no_change_is_blocked():
    item, observation = _item()
    service, _ = _service(item, observation)
    outcome = service.create_from_query_plan(
        _plan("MODIFY_POSITION_PROTECTION", (_condition("requested_stop_loss", 90),))
    )
    assert outcome.proposal is None
    assert outcome.blockers == ("MANAGEMENT_NO_CHANGE",)


def test_llm_suggested_management_number_without_user_explicit_provenance_is_blocked():
    item, observation = _item()
    service, _ = _service(item, observation)
    plan = _plan("MODIFY_POSITION_PROTECTION", (_condition("requested_stop_loss", 95),))
    plan.semantic_context["input"]["explicit_fields"] = []
    outcome = service.create_from_query_plan(plan)
    assert outcome.proposal is None
    assert outcome.blockers == ("MANAGEMENT_VALUE_NOT_USER_EXPLICIT",)


def test_invalid_protection_is_blocked_before_controlled_management():
    item, observation = _item()
    adapter = _Adapter()
    service, _ = _service(item, observation, adapter=adapter)
    outcome = service.create_from_query_plan(
        _plan("MODIFY_POSITION_PROTECTION", (_condition("requested_stop_loss", 0),))
    )
    assert outcome.proposal is None
    assert outcome.blockers == ("PROTECTION_VALUES_INVALID",)
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.5, "0.5"), (0.25, "0.75")],
)
def test_partial_close_calculates_resulting_volume_deterministically(fraction, expected):
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(
        _plan("PARTIAL_CLOSE", (_condition("close_fraction", fraction),))
    ).proposal
    assert proposal is not None
    assert proposal.backend_proposal.management_intent == "CLOSE_POSITION"
    assert proposal.backend_proposal.requested_resulting_volume == expected


@pytest.mark.parametrize(
    ("subject", "value", "expected"),
    [("close_amount", 0.2, "0.8"), ("resulting_volume", 0.4, "0.4")],
)
def test_partial_close_accepts_each_existing_typed_volume_representation(subject, value, expected):
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(
        _plan("PARTIAL_CLOSE", (_condition(subject, value),))
    ).proposal
    assert proposal is not None
    assert proposal.backend_proposal.requested_resulting_volume == expected


@pytest.mark.parametrize("fraction", [0, 1, 1.1])
def test_invalid_partial_close_fraction_is_blocked(fraction):
    item, observation = _item()
    service, _ = _service(item, observation)
    outcome = service.create_from_query_plan(
        _plan("PARTIAL_CLOSE", (_condition("close_fraction", fraction),))
    )
    assert outcome.proposal is None
    assert outcome.blockers == ("CLOSE_FRACTION_INVALID",)


def test_full_close_sets_resulting_volume_to_zero():
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    assert proposal is not None
    assert proposal.backend_proposal.requested_resulting_volume == "0"


def test_already_closed_position_is_ineligible():
    item, observation = _item(state="POSITION_CLOSED")
    service, _ = _service(item, observation)
    outcome = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION"))
    assert outcome.proposal is None
    assert outcome.blockers == ("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE",)


def test_proposal_revision_invalidates_old_confirmation_material():
    item, observation = _item()
    service, _ = _service(item, observation)
    original = service.create_from_query_plan(
        _plan("MODIFY_POSITION_PROTECTION", (_condition("requested_stop_loss", 95),))
    ).proposal
    assert original is not None
    revised = service.revise(
        original,
        ManagementProposalPatch(requested_stop_loss=Decimal("96"), requested_take_profit=Decimal("120")),
    ).proposal
    assert revised is not None
    assert revised.revision == 2
    assert revised.backend_proposal.mutation_hash != original.backend_proposal.mutation_hash
    assert revised.backend_proposal.idempotency_key != original.backend_proposal.idempotency_key


def test_wrong_confirmation_stops_before_adapter():
    item, observation = _item()
    adapter = _Adapter()
    service, _ = _service(item, observation, adapter=adapter)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    receipt = service.confirm_and_manage(proposal, typed_confirmation="wrong")
    assert receipt.status == "BLOCKED"
    assert receipt.reason == "MANAGEMENT_CONFIRMATION_INVALID"
    assert adapter.calls == []


def test_target_change_after_proposal_stops_before_adapter():
    item, observation = _item()
    adapter = _Adapter()
    service, position_service = _service(item, observation, adapter=adapter)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    position_service.model = _model(replace(item, volume=0.5))
    receipt = service.confirm_and_manage(
        proposal,
        typed_confirmation=management_confirmation_phrase("CLOSE_POSITION"),
    )
    assert receipt.reason == "POSITION_VOLUME_CHANGED"
    assert adapter.calls == []


def test_account_fingerprint_change_stops_before_adapter():
    item, observation = _item()
    adapter = _Adapter()
    service, position_service = _service(item, observation, adapter=adapter)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    position_service.model = _model(item, fingerprint="d" * 64)
    receipt = service.confirm_and_manage(
        proposal,
        typed_confirmation=management_confirmation_phrase("CLOSE_POSITION"),
    )
    assert receipt.reason == "ACCOUNT_CONTEXT_CHANGED"
    assert adapter.calls == []


def test_confirmed_request_reuses_existing_controlled_management_boundary():
    item, observation = _item()
    adapter = _Adapter()
    service, _ = _service(item, observation, adapter=adapter)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    phrase = management_confirmation_phrase("CLOSE_POSITION")
    first = service.confirm_and_manage(proposal, typed_confirmation=phrase)
    second = service.confirm_and_manage(proposal, typed_confirmation=phrase)
    assert first.status == second.status == "ACCEPTED"
    assert len(adapter.calls) == 2
    assert adapter.calls[0][0].idempotency_key == adapter.calls[1][0].idempotency_key


def test_unknown_result_is_returned_without_service_retry():
    item, observation = _item()
    adapter = _Adapter(status="UNKNOWN")
    service, _ = _service(item, observation, adapter=adapter)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    receipt = service.confirm_and_manage(
        proposal,
        typed_confirmation=management_confirmation_phrase("CLOSE_POSITION"),
    )
    assert receipt.status == "UNKNOWN"
    assert receipt.reconciliation_required is True
    assert len(adapter.calls) == 1


def test_management_routes_through_query_plan_and_position_read_capability():
    semantic = StructuredSemanticResult.from_payload(
        {
            "schema_version": "structured-semantic/v1",
            "primary_intent": "POSITION_MANAGEMENT",
            "secondary_intents": [],
            "action": "MANAGE_POSITION",
            "direction": "",
            "subtype": "PARTIAL_CLOSE",
            "domain": "trading",
            "symbols": ["BTCUSD"],
            "indicators": [],
            "requested_data": [],
            "conditions": [{"subject": "close_fraction", "operator": "EQUAL", "value": 0.5}],
            "context_references": [POSITION],
            "requested_mode": "",
            "account_scope": "DEMO",
            "explicit_fields": ["action", "subtype", "symbols[0]", "conditions[0]"],
            "unresolved_fields": [],
            "negated": False,
            "hypothetical": False,
        }
    )
    plan = QueryPlanAssembler().assemble("close half", structured_semantics=semantic)
    requirements = ContextRequirementPlanner().plan(plan)
    assert plan.primary_intent == "position_management"
    assert plan.constraints["requested_mode"] == "human_confirmed_live"
    assert [need.capability for need in requirements.needs] == ["position_read"]
    assert plan.requires_execution is False


def test_previous_position_reference_inherits_only_an_authoritative_protected_reference():
    base = StructuredSemanticResult.from_payload(
        {
            "schema_version": "structured-semantic/v1",
            "primary_intent": "POSITION_MANAGEMENT",
            "secondary_intents": [],
            "action": "NONE",
            "direction": "",
            "subtype": "DETAIL",
            "domain": "trading",
            "symbols": ["BTCUSD"],
            "indicators": [],
            "requested_data": ["position"],
            "conditions": [],
            "context_references": [POSITION],
            "requested_mode": "",
            "account_scope": "DEMO",
            "explicit_fields": ["symbols[0]"],
            "unresolved_fields": [],
            "negated": False,
            "hypothetical": False,
        }
    )
    previous = resolve_structured_semantics(base)
    follow_up = replace(
        base,
        action="CLOSE_POSITION",
        subtype="CLOSE_POSITION",
        symbols=(),
        requested_data=(),
        context_references=("previous_position",),
    )
    resolved = resolve_structured_semantics(follow_up, previous)
    assert resolved.semantic.context_references == (POSITION,)
    assert "context_references.previous_position" not in resolved.unresolved_fields


def test_previous_position_without_authoritative_reference_stays_unresolved():
    semantic = StructuredSemanticResult.from_payload(
        {
            "schema_version": "structured-semantic/v1",
            "primary_intent": "POSITION_MANAGEMENT",
            "secondary_intents": [],
            "action": "CLOSE_POSITION",
            "direction": "",
            "subtype": "CLOSE_POSITION",
            "domain": "trading",
            "symbols": [],
            "indicators": [],
            "requested_data": [],
            "conditions": [],
            "context_references": ["previous_position"],
            "requested_mode": "",
            "account_scope": "DEMO",
            "explicit_fields": ["action"],
            "unresolved_fields": [],
            "negated": False,
            "hypothetical": False,
        }
    )
    resolved = resolve_structured_semantics(semantic)
    assert resolved.semantic.context_references == ()
    assert "context_references.previous_position" in resolved.unresolved_fields


def test_public_proposal_redacts_account_and_exact_target_reference():
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    payload = proposal.to_public_dict()
    rendered = json.dumps(payload)
    assert ACCOUNT not in rendered
    assert POSITION not in rendered
    assert payload["status"] == "NON_EXECUTABLE"
    assert payload["executable"] is False
    assert payload["execution_authority"] is False


class _UIContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _UIColumn:
    def __init__(self, events):
        self.events = events

    def metric(self, label, value):
        self.events.append(("metric", label, value))

    def form_submit_button(self, label, **_kwargs):
        self.events.append(("button", label))
        return False


class _Streamlit:
    def __init__(self):
        self.events = []
        self.session_state = {"messages": []}

    def markdown(self, value):
        self.events.append(("markdown", value))

    def warning(self, value):
        self.events.append(("warning", value))

    def info(self, value):
        self.events.append(("info", value))

    def success(self, value):
        self.events.append(("success", value))

    def caption(self, value):
        self.events.append(("caption", value))

    def columns(self, count):
        return [_UIColumn(self.events) for _ in range(count)]

    def form(self, _key):
        return _UIContext()

    def text_input(self, label, **_kwargs):
        self.events.append(("text_input", label))
        return ""

    def number_input(self, label, **kwargs):
        self.events.append(("number_input", label))
        return kwargs.get("value")

    def form_submit_button(self, label, **_kwargs):
        self.events.append(("button", label))
        return False

    def rerun(self):
        raise AssertionError("render-only test must not rerun")


def test_streamlit_management_card_is_non_executable_and_requires_explicit_confirmation(monkeypatch):
    item, observation = _item()
    service, _ = _service(item, observation)
    proposal = service.create_from_query_plan(_plan("CLOSE_POSITION", action="CLOSE_POSITION")).proposal
    fake = _Streamlit()
    monkeypatch.setattr(tab_chatbot, "st", fake)
    artifacts = {
        "management_proposal": proposal.to_public_dict(),
        "management_proposal_protected": proposal,
    }
    tab_chatbot._capture_management_proposal(artifacts)
    tab_chatbot._render_management_proposal_card(artifacts["management_proposal"])
    assert "management_proposal_protected" not in artifacts
    assert any(event[0] == "caption" and "NON_EXECUTABLE" in event[1] for event in fake.events)
    assert ("button", "Confirm Management") in fake.events
    assert ("button", "Cancel") in fake.events


def test_streamlit_blocker_has_no_confirmation_control(monkeypatch):
    fake = _Streamlit()
    monkeypatch.setattr(tab_chatbot, "st", fake)
    tab_chatbot._render_management_proposal_card(
        {
            "schema_version": "human-confirmed-management-proposal/v1",
            "status": "BLOCKED",
            "blockers": ["AMBIGUOUS_POSITION_REFERENCE"],
        }
    )
    assert ("warning", "Management blocked: AMBIGUOUS_POSITION_REFERENCE") in fake.events
    assert not any(event[0] == "button" for event in fake.events)

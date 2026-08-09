from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementReceipt,
    MT5ControlledManagementRequest,
    MT5ManagementIntent,
    MT5ManagementProposal,
    management_confirmation_phrase,
)
from src.services.trading.position_read_model import (
    PositionReadItem,
    PositionReadModel,
    PositionReadModelService,
)


MANAGEMENT_FAMILIES = frozenset(
    {
        "CANCEL_PENDING_ORDER",
        "MODIFY_POSITION_PROTECTION",
        "PARTIAL_CLOSE",
        "CLOSE_POSITION",
    }
)
MANAGEMENT_VALUE_SUBJECTS = frozenset(
    {
        "requested_stop_loss",
        "requested_take_profit",
        "close_fraction",
        "close_amount",
        "resulting_volume",
    }
)


@dataclass(frozen=True)
class ManagementProposalPatch:
    requested_stop_loss: Decimal | None = None
    requested_take_profit: Decimal | None = None
    close_fraction: Decimal | None = None
    close_amount: Decimal | None = None
    resulting_volume: Decimal | None = None


@dataclass(frozen=True)
class HumanConfirmedManagementProposal:
    proposal_id: str
    revision: int
    semantic_intent: str
    backend_proposal: MT5ManagementProposal
    canonical_symbol: str
    broker_symbol: str
    target_reference: str
    current_stop_loss: Decimal | None
    current_take_profit: Decimal | None
    close_fraction: Decimal | None = None
    close_amount: Decimal | None = None
    status: str = "NON_EXECUTABLE"
    mode: str = "human_confirmed_live"
    confirmation_required: bool = True
    warnings: tuple[str, ...] = ()

    @property
    def confirmation_phrase(self) -> str:
        return management_confirmation_phrase(self.backend_proposal.management_intent)

    def to_public_dict(self) -> dict[str, Any]:
        backend = self.backend_proposal
        return {
            "schema_version": "human-confirmed-management-proposal/v1",
            "proposal_id": self.proposal_id,
            "revision": self.revision,
            "semantic_intent": self.semantic_intent,
            "management_intent": backend.management_intent,
            "canonical_symbol": self.canonical_symbol,
            "broker_symbol": self.broker_symbol,
            "target_reference": f"{self.target_reference[:12]}...",
            "lifecycle_state": backend.lifecycle_state,
            "current_volume": backend.current_observed_volume,
            "current_stop_loss": _decimal_output(self.current_stop_loss),
            "current_take_profit": _decimal_output(self.current_take_profit),
            "requested_stop_loss": backend.requested_stop_loss,
            "requested_take_profit": backend.requested_take_profit,
            "requested_resulting_volume": backend.requested_resulting_volume,
            "close_fraction": _decimal_output(self.close_fraction),
            "close_amount": _decimal_output(self.close_amount),
            "mode": self.mode,
            "confirmation_required": self.confirmation_required,
            "status": self.status,
            "warnings": list(self.warnings),
            "blockers": [],
            "executable": False,
            "execution_authority": False,
            "metadata_redacted": True,
        }


@dataclass(frozen=True)
class HumanConfirmedManagementOutcome:
    status: str
    proposal: HumanConfirmedManagementProposal | None = None
    blockers: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        if self.proposal is not None:
            return self.proposal.to_public_dict()
        return {
            "schema_version": "human-confirmed-management-proposal/v1",
            "status": self.status,
            "blockers": list(self.blockers),
            "confirmation_required": False,
            "executable": False,
            "execution_authority": False,
            "metadata_redacted": True,
        }


class HumanConfirmedManagementService:
    """Thin human-review layer over PositionReadModel and controlled management."""

    def __init__(
        self,
        *,
        position_read_service: PositionReadModelService | None = None,
        adapter: MT5LiveAdapterDisabled | None = None,
    ) -> None:
        self.position_read_service = position_read_service or PositionReadModelService()
        self.adapter = adapter or MT5LiveAdapterDisabled()

    def create_from_query_plan(
        self,
        query_plan: Any,
        *,
        model: PositionReadModel | None = None,
    ) -> HumanConfirmedManagementOutcome:
        semantic = dict(getattr(query_plan, "semantic_context", {}) or {}).get("input", {})
        if not isinstance(semantic, Mapping):
            return _blocked("MANAGEMENT_SEMANTICS_UNAVAILABLE")
        intent = str(semantic.get("subtype") or "").strip().upper()
        action = str(semantic.get("action") or "").strip().upper()
        if not intent and action == "CLOSE_POSITION":
            intent = "CLOSE_POSITION"
        if intent not in MANAGEMENT_FAMILIES:
            return _blocked("MANAGEMENT_INTENT_UNRESOLVED")
        if str(getattr(query_plan, "constraints", {}).get("requested_mode", "")) != "human_confirmed_live":
            return _blocked("HUMAN_CONFIRMED_MODE_REQUIRED")
        unresolved_references = tuple(
            value
            for value in (getattr(query_plan, "ambiguity", ()) or ())
            if str(value).startswith("unresolved:context_references.")
        )
        if unresolved_references:
            return _blocked("MANAGEMENT_TARGET_REFERENCE_UNRESOLVED")
        if str(semantic.get("account_scope") or "").upper() == "REAL":
            return _blocked("REAL_ACCOUNT_MANAGEMENT_FORBIDDEN")
        values, value_blocker = _management_values(
            semantic.get("conditions"),
            semantic.get("explicit_fields"),
        )
        if value_blocker:
            return _blocked(value_blocker)
        model = model or self.position_read_service.read_from_query_plan(query_plan)
        if model.status != "AVAILABLE" or model.selected_position is None:
            return _blocked(*(model.blockers or ("MANAGEMENT_TARGET_UNAVAILABLE",)))
        return self._build(intent, model, model.selected_position, values, revision=1)

    def revise(
        self,
        proposal: HumanConfirmedManagementProposal,
        patch: ManagementProposalPatch,
    ) -> HumanConfirmedManagementOutcome:
        model = self._reload(proposal)
        if model.status != "AVAILABLE" or model.selected_position is None:
            return _blocked(*(model.blockers or ("MANAGEMENT_TARGET_UNAVAILABLE",)))
        values = {
            "requested_stop_loss": patch.requested_stop_loss,
            "requested_take_profit": patch.requested_take_profit,
            "close_fraction": patch.close_fraction,
            "close_amount": patch.close_amount,
            "resulting_volume": patch.resulting_volume,
        }
        return self._build(
            proposal.semantic_intent,
            model,
            model.selected_position,
            values,
            revision=proposal.revision + 1,
        )

    def confirm_and_manage(
        self,
        proposal: HumanConfirmedManagementProposal,
        *,
        typed_confirmation: str,
    ) -> MT5ControlledManagementReceipt:
        model = self._reload(proposal)
        target = model.selected_position
        if model.status != "AVAILABLE" or target is None:
            return _blocked_receipt(proposal.backend_proposal.management_intent, (model.blockers or ("MANAGEMENT_TARGET_UNAVAILABLE",))[0])
        stale = _target_changed(proposal, target)
        if stale:
            return _blocked_receipt(proposal.backend_proposal.management_intent, stale)
        try:
            observation = self._observation(target)
            if (
                observation.get("observation_id") != proposal.backend_proposal.lifecycle_observation_reference
                or observation.get("observation_hash") != proposal.backend_proposal.lifecycle_observation_hash
            ):
                return _blocked_receipt(
                    proposal.backend_proposal.management_intent,
                    "LIFECYCLE_OBSERVATION_STALE",
                )
            MT5ManagementProposal.from_lifecycle_observation(
                observation,
                management_intent=proposal.backend_proposal.management_intent,
                expected_account_context_fingerprint=model.account_context_fingerprint,
                symbol=proposal.broker_symbol,
                current_observed_volume=target.volume,
                idempotency_key=proposal.backend_proposal.idempotency_key,
                requested_resulting_volume=proposal.backend_proposal.requested_resulting_volume,
                requested_stop_loss=proposal.backend_proposal.requested_stop_loss,
                requested_take_profit=proposal.backend_proposal.requested_take_profit,
                requested_deviation=proposal.backend_proposal.requested_deviation,
            )
            request = MT5ControlledManagementRequest.confirm(
                proposal.backend_proposal,
                typed_confirmation=typed_confirmation,
            )
        except ValueError as exc:
            return _blocked_receipt(proposal.backend_proposal.management_intent, str(exc))
        return self.adapter.manage_prepared_request(request, typed_confirmation=typed_confirmation)

    def _reload(self, proposal: HumanConfirmedManagementProposal) -> PositionReadModel:
        query_type = "PENDING" if proposal.semantic_intent == "CANCEL_PENDING_ORDER" else "CURRENT"
        return self.position_read_service.read(
            query_type=query_type,
            canonical_symbol=proposal.canonical_symbol,
            protected_reference=proposal.target_reference,
            singular=True,
        )

    def _build(
        self,
        semantic_intent: str,
        model: PositionReadModel,
        target: PositionReadItem,
        values: Mapping[str, Decimal | None],
        *,
        revision: int,
    ) -> HumanConfirmedManagementOutcome:
        try:
            observation = self._observation(target)
            backend = build_management_proposal(
                semantic_intent=semantic_intent,
                model=model,
                target=target,
                values=values,
                observation=observation,
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            return _blocked(str(exc) or "MANAGEMENT_PROPOSAL_INVALID")
        proposal_id = "management_proposal_" + backend.mutation_hash[:24]
        return HumanConfirmedManagementOutcome(
            status="READY_FOR_HUMAN_CONFIRMATION",
            proposal=HumanConfirmedManagementProposal(
                proposal_id=proposal_id,
                revision=revision,
                semantic_intent=semantic_intent,
                backend_proposal=backend,
                canonical_symbol=target.canonical_symbol,
                broker_symbol=target.broker_symbol,
                target_reference=target.protected_reference,
                current_stop_loss=_optional_decimal(target.stop_loss),
                current_take_profit=_optional_decimal(target.take_profit),
                close_fraction=values.get("close_fraction"),
                close_amount=values.get("close_amount"),
            ),
        )

    def _observation(self, target: PositionReadItem) -> Mapping[str, Any]:
        reference = target.provenance.execution_reference
        if not reference:
            raise ValueError("PROTECTED_EXECUTION_REFERENCE_UNAVAILABLE")
        observation = self.position_read_service.lifecycle_journal.latest_by_execution().get(reference)
        if not observation:
            raise ValueError("LIFECYCLE_OBSERVATION_UNAVAILABLE")
        if target.provenance.lifecycle_reference and observation.get("observation_id") != target.provenance.lifecycle_reference:
            raise ValueError("LIFECYCLE_OBSERVATION_STALE")
        return observation


def build_management_proposal(
    *,
    semantic_intent: str,
    model: PositionReadModel,
    target: PositionReadItem,
    values: Mapping[str, Decimal | None],
    observation: Mapping[str, Any],
    current_time: datetime | None = None,
) -> MT5ManagementProposal:
    """Build the shared deterministic S6 proposal without granting authority."""
    current = _decimal(target.volume, "CURRENT_VOLUME_INVALID")
    backend_intent, resulting, stop_loss, take_profit, deviation = _proposal_values(
        semantic_intent,
        target,
        current,
        values,
    )
    idempotency = _idempotency_key(
        semantic_intent,
        target.protected_reference,
        str(observation.get("observation_id") or ""),
        resulting,
        stop_loss,
        take_profit,
    )
    return MT5ManagementProposal.from_lifecycle_observation(
        observation,
        management_intent=backend_intent,
        expected_account_context_fingerprint=model.account_context_fingerprint,
        symbol=target.broker_symbol,
        current_observed_volume=current,
        idempotency_key=idempotency,
        requested_resulting_volume=resulting,
        requested_stop_loss=stop_loss,
        requested_take_profit=take_profit,
        requested_deviation=deviation,
        current_time=current_time,
    )


def management_target_changed(
    proposal: MT5ManagementProposal, target: PositionReadItem
) -> str:
    if target.state != proposal.lifecycle_state:
        return "MANAGEMENT_LIFECYCLE_CHANGED"
    if _optional_decimal(target.volume) != _optional_decimal(proposal.current_observed_volume):
        return "POSITION_VOLUME_CHANGED"
    return ""


def _management_values(
    value: Any,
    explicit_fields: Any,
) -> tuple[dict[str, Decimal | None], str]:
    if not isinstance(value, list):
        return {}, "MANAGEMENT_VALUES_INVALID"
    explicit = set(explicit_fields) if isinstance(explicit_fields, list) else set()
    output: dict[str, Decimal | None] = {name: None for name in MANAGEMENT_VALUE_SUBJECTS}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            return output, "MANAGEMENT_VALUES_INVALID"
        subject = str(item.get("subject") or "").strip().lower()
        if subject not in MANAGEMENT_VALUE_SUBJECTS:
            continue
        if not ({f"conditions[{index}]", f"conditions[{index}].value"} & explicit):
            return output, "MANAGEMENT_VALUE_NOT_USER_EXPLICIT"
        if output[subject] is not None or str(item.get("operator") or "").strip().upper() not in {"EQUAL", "EQUALS", "="}:
            return output, "MANAGEMENT_VALUES_CONFLICT"
        try:
            output[subject] = _decimal(item.get("value"), "MANAGEMENT_VALUE_INVALID")
        except (InvalidOperation, TypeError, ValueError):
            return output, "MANAGEMENT_VALUE_INVALID"
    return output, ""


def _proposal_values(
    semantic_intent: str,
    target: PositionReadItem,
    current: Decimal,
    values: Mapping[str, Decimal | None],
) -> tuple[str, Decimal | None, Decimal | None, Decimal | None, int | None]:
    if semantic_intent == "CANCEL_PENDING_ORDER":
        if target.state != "ORDER_ACTIVE":
            raise ValueError("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE")
        return MT5ManagementIntent.CANCEL_PENDING_ORDER.value, None, None, None, None
    if target.state not in {"POSITION_OPEN", "POSITION_PARTIALLY_REDUCED"}:
        raise ValueError("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE")
    if semantic_intent == "MODIFY_POSITION_PROTECTION":
        requested_stop = values.get("requested_stop_loss")
        requested_take = values.get("requested_take_profit")
        if requested_stop is None and requested_take is None:
            raise ValueError("PROTECTION_VALUES_REQUIRED")
        if (
            requested_stop is not None and requested_stop <= 0
            or requested_take is not None and requested_take <= 0
        ):
            raise ValueError("PROTECTION_VALUES_INVALID")
        stop = requested_stop if requested_stop is not None else _optional_decimal(target.stop_loss)
        take = requested_take if requested_take is not None else _optional_decimal(target.take_profit)
        if stop == _optional_decimal(target.stop_loss) and take == _optional_decimal(target.take_profit):
            raise ValueError("MANAGEMENT_NO_CHANGE")
        return MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value, current, stop, take, None
    if semantic_intent == "CLOSE_POSITION":
        return MT5ManagementIntent.CLOSE_POSITION.value, Decimal("0"), None, None, 0
    selected = [
        (name, values.get(name))
        for name in ("close_fraction", "close_amount", "resulting_volume")
        if values.get(name) is not None
    ]
    if len(selected) != 1:
        raise ValueError("PARTIAL_CLOSE_VALUE_REQUIRED" if not selected else "PARTIAL_CLOSE_VALUES_CONFLICT")
    name, number = selected[0]
    assert number is not None
    if name == "close_fraction":
        if number <= 0 or number >= 1:
            raise ValueError("CLOSE_FRACTION_INVALID")
        resulting = current * (Decimal("1") - number)
    elif name == "close_amount":
        if number <= 0 or number >= current:
            raise ValueError("CLOSE_AMOUNT_INVALID")
        resulting = current - number
    else:
        resulting = number
    if resulting <= 0 or resulting >= current:
        raise ValueError("CLOSE_VOLUME_INVALID")
    return MT5ManagementIntent.CLOSE_POSITION.value, resulting, None, None, 0


def _target_changed(proposal: HumanConfirmedManagementProposal, target: PositionReadItem) -> str:
    backend = proposal.backend_proposal
    if target.state != backend.lifecycle_state:
        return "MANAGEMENT_LIFECYCLE_CHANGED"
    if _optional_decimal(target.volume) != _optional_decimal(backend.current_observed_volume):
        return "POSITION_VOLUME_CHANGED"
    if _optional_decimal(target.stop_loss) != proposal.current_stop_loss or _optional_decimal(target.take_profit) != proposal.current_take_profit:
        return "POSITION_PROTECTION_CHANGED"
    return ""


def _idempotency_key(
    semantic_intent: str,
    target_reference: str,
    observation_reference: str,
    resulting: Decimal | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> str:
    material = json.dumps(
        {
            "intent": semantic_intent,
            "target": target_reference,
            "observation": observation_reference,
            "resulting": _decimal_output(resulting),
            "stop_loss": _decimal_output(stop_loss),
            "take_profit": _decimal_output(take_profit),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "management_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _blocked(*blockers: str) -> HumanConfirmedManagementOutcome:
    return HumanConfirmedManagementOutcome(
        status="BLOCKED",
        blockers=tuple(str(value) for value in blockers if str(value)),
    )


def _blocked_receipt(intent: str, reason: str) -> MT5ControlledManagementReceipt:
    return MT5ControlledManagementReceipt(
        "BLOCKED", intent, "NOT_RESERVED", False, False, False,
        False, False, False, False, str(reason),
    )


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(code)
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(code)
    return number


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else _decimal(value, "MANAGEMENT_VALUE_INVALID")


def _decimal_output(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text

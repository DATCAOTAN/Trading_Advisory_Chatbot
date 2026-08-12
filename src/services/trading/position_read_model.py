from __future__ import annotations

import hmac
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleJournal,
    MT5LifecycleJournalError,
    MT5PositionSupervisorConfig,
    _validate_snapshot,
)
from src.services.trading.execution.mt5_bridge_write_skeleton.client import (
    MT5BridgeWriteSkeletonClient,
)
from src.services.trading.market.timeframes import resolve_symbol
from tools.mt5_bridge.execution import ProtectedExecutionJournal, ProtectedExecutionJournalError


@dataclass(frozen=True)
class PositionProvenance:
    trading_scope: str = field(default="", repr=False)
    strategy_reference: str = ""
    draft_reference: str = ""
    candidate_reference: str = ""
    authorization_reference: str = ""
    execution_reference: str = ""
    lifecycle_reference: str = ""
    management_reference: str = ""
    unavailable: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionReadItem:
    protected_reference: str
    canonical_symbol: str
    broker_symbol: str
    direction: str
    volume: float | None
    state: str
    occurred_at: str
    open_time: str = ""
    close_time: str = ""
    entry_price: float | None = None
    current_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    order_type: str = ""
    pnl_source: str = "UNAVAILABLE"
    provenance: PositionProvenance = field(default_factory=PositionProvenance)
    metadata_redacted: bool = True


@dataclass(frozen=True)
class PositionReadModel:
    schema_version: str
    query_type: str
    status: str
    snapshot_reference: str
    snapshot_timestamp: str
    account_context_match: bool
    open_positions: tuple[PositionReadItem, ...] = ()
    pending_orders: tuple[PositionReadItem, ...] = ()
    history: tuple[PositionReadItem, ...] = ()
    selected_position: PositionReadItem | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata_redacted: bool = True
    account_context_fingerprint: str = field(default="", repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("account_context_fingerprint", None)
        for collection in ("open_positions", "pending_orders", "history"):
            for item in payload[collection]:
                item["provenance"].pop("trading_scope", None)
        if payload.get("selected_position"):
            payload["selected_position"]["provenance"].pop("trading_scope", None)
        payload["metadata_redacted"] = True
        return payload


class PositionReadModelService:
    """Project current broker state through existing protected lifecycle owners."""

    def __init__(
        self,
        *,
        config: MT5PositionSupervisorConfig | None = None,
        bridge_client: Any | None = None,
        execution_journal: ProtectedExecutionJournal | None = None,
        lifecycle_journal: MT5LifecycleJournal | None = None,
        candidate_journal: Any | None = None,
        now: Any | None = None,
    ) -> None:
        self.config = config or MT5PositionSupervisorConfig.from_config()
        self.bridge_client = bridge_client or MT5BridgeWriteSkeletonClient(
            self.config.bridge_url, timeout_seconds=self.config.bridge_timeout_seconds
        )
        self.execution_journal = execution_journal or ProtectedExecutionJournal(
            self.config.execution_journal_path
        )
        self.lifecycle_journal = lifecycle_journal or MT5LifecycleJournal(
            self.config.lifecycle_journal_path
        )
        if candidate_journal is None:
            from src.config import Config
            from src.services.trading.decision.autonomous_orchestrator import AutonomousDecisionJournal

            candidate_journal = AutonomousDecisionJournal(Config.TRADING_AUTONOMOUS_DECISION_JOURNAL_PATH)
        self.candidate_journal = candidate_journal
        self._now = now or (lambda: datetime.now(timezone.utc))

    def read_from_query_plan(self, query_plan: Any) -> PositionReadModel:
        semantic = dict(getattr(query_plan, "semantic_context", {}) or {})
        semantic_payload = dict(semantic.get("input", {}) or {})
        requested = tuple(str(value).lower() for value in semantic_payload.get("requested_data", []) or [])
        references = tuple(str(value) for value in semantic_payload.get("context_references", []) or [])
        protected_references = tuple(
            value for value in references if re.fullmatch(r"[0-9a-fA-F]{64}", value)
        )
        symbols = list(getattr(getattr(query_plan, "entities", None), "symbols", []) or [])
        query_type = _query_type(requested, str(semantic_payload.get("subtype", "")))
        account_wide = "account_wide" in requested
        trading_scope = str(
            getattr(query_plan, "constraints", {}).get("trading_scope") or ""
        )
        management_request = getattr(query_plan, "primary_intent", "") == "position_management"
        if management_request and len(protected_references) > 1:
            return self._blocked(query_type, "AMBIGUOUS_POSITION_REFERENCE")
        return self.read(
            query_type=query_type,
            canonical_symbol=symbols[0] if len(symbols) == 1 else "",
            protected_reference=protected_references[0] if len(protected_references) == 1 else "",
            singular=(
                not account_wide
                and (
                    management_request
                    or query_type in {"DETAIL", "PNL", "PROVENANCE"}
                    or bool(references)
                )
            ),
            trading_scope=trading_scope,
            account_wide=account_wide,
        )

    def read(
        self,
        *,
        query_type: str = "CURRENT",
        canonical_symbol: str = "",
        protected_reference: str = "",
        singular: bool = False,
        trading_scope: str = "",
        account_wide: bool = False,
    ) -> PositionReadModel:
        try:
            lifecycle = self.lifecycle_journal.latest_by_execution()
            executions = self.execution_journal.execution_records()
        except (MT5LifecycleJournalError, ProtectedExecutionJournalError):
            return self._blocked(query_type, "PROTECTED_JOURNAL_UNAVAILABLE")
        tags = list(dict.fromkeys(
            str(record.get("protected_execution", {}).get("correlation_tag", ""))
            for record in executions
            if record.get("protected_execution", {}).get("correlation_tag")
        ))[:100]
        try:
            snapshot = self.bridge_client.lifecycle_snapshot(
                self.config.history_window_seconds, tags, self.config.auth_token
            )
            _validate_snapshot(snapshot)
        except Exception:
            return self._blocked(query_type, "BRIDGE_UNAVAILABLE")
        if snapshot.get("status") != "OK" or snapshot.get("terminal_connected") is not True:
            return self._blocked(query_type, str(snapshot.get("reason") or "BRIDGE_UNAVAILABLE"))
        timestamp = str(snapshot.get("snapshot_timestamp") or "")
        if not _fresh(timestamp, self.config.interval_seconds * 3, self._now()):
            return self._blocked(query_type, "POSITION_SNAPSHOT_STALE", snapshot)
        fingerprint = str(snapshot.get("account_context_fingerprint") or "")
        snapshot_tags = {
            str(tag)
            for group in ("positions", "active_orders", "recent_deals")
            for row in snapshot.get(group, [])
            for tag in row.get("matched_correlation_tags", []) or []
        }
        linked_executions = [
            record for record in executions
            if str(record.get("protected_execution", {}).get("correlation_tag", "")) in snapshot_tags
        ]
        account_match = all(
            not record.get("account_context_fingerprint")
            or hmac.compare_digest(str(record["account_context_fingerprint"]), fingerprint)
            for record in linked_executions
        )
        if not account_match:
            return self._blocked(query_type, "ACCOUNT_CONTEXT_MISMATCH", snapshot)

        execution_by_tag = {
            str(record.get("protected_execution", {}).get("correlation_tag")): record
            for record in executions
            if record.get("protected_execution", {}).get("correlation_tag")
        }
        positions = tuple(
            self._item(row, "POSITION_OPEN", execution_by_tag, lifecycle)
            for row in snapshot.get("positions", [])
        )
        orders = tuple(
            self._item(row, "ORDER_ACTIVE", execution_by_tag, lifecycle)
            for row in snapshot.get("active_orders", [])
        )
        history = tuple(
            self._closed_item(row, snapshot.get("recent_deals", []), execution_by_tag, lifecycle)
            for row in snapshot.get("recent_deals", [])
            if str(row.get("entry")) in {"OUT", "INOUT"}
        )
        all_items = positions + orders + history
        if trading_scope and not account_wide:
            positions = tuple(
                item for item in positions
                if hmac.compare_digest(item.provenance.trading_scope, trading_scope)
            )
            orders = tuple(
                item for item in orders
                if hmac.compare_digest(item.provenance.trading_scope, trading_scope)
            )
            history = tuple(
                item for item in history
                if hmac.compare_digest(item.provenance.trading_scope, trading_scope)
            )
        selectable = (
            orders
            if query_type == "PENDING"
            else positions + history
            if query_type == "PROVENANCE"
            else positions
        )
        selected, target_blocker = _select_position(
            selectable, canonical_symbol, protected_reference, singular
        )
        unsafe_states = {
            item.state for item in all_items
            if item.state in {"RECONCILIATION_REQUIRED", "INCONSISTENT"}
        }
        blockers = tuple(
            value for value in (target_blocker, *sorted(unsafe_states)) if value
        )
        warnings = tuple(
            value for value in (
                "PROVENANCE_PARTIAL" if any(item.provenance.unavailable for item in positions + orders + history) else "",
            ) if value
        )
        return PositionReadModel(
            schema_version="position-read-model/v1",
            query_type=query_type,
            status="BLOCKED" if blockers else "AVAILABLE",
            snapshot_reference=str(snapshot.get("snapshot_reference") or ""),
            snapshot_timestamp=timestamp,
            account_context_match=True,
            open_positions=positions,
            pending_orders=orders,
            history=history,
            selected_position=selected,
            blockers=blockers,
            warnings=warnings,
            account_context_fingerprint=fingerprint,
        )

    def _item(
        self,
        row: Mapping[str, Any],
        default_state: str,
        execution_by_tag: Mapping[str, Mapping[str, Any]],
        lifecycle: Mapping[str, Mapping[str, Any]],
    ) -> PositionReadItem:
        tags = [str(value) for value in row.get("matched_correlation_tags", []) or []]
        execution = next((execution_by_tag[tag] for tag in tags if tag in execution_by_tag), None)
        broker_symbol = str(row.get("symbol") or "")
        resolved = resolve_symbol(broker_symbol)
        realized = _net_realized(row) if default_state == "POSITION_CLOSED" else None
        observation: Mapping[str, Any] = {}
        if execution:
            reference = str(execution.get("protected_execution", {}).get("protected_execution_reference") or "")
            observation = lifecycle.get(reference, {})
        if not observation:
            broker_reference = str(row.get("broker_reference_hash") or "")
            observation = next(
                (
                    value for value in lifecycle.values()
                    if broker_reference
                    and broker_reference in (
                        value.get("protected_broker_references", {}).get("positions", [])
                        + value.get("protected_broker_references", {}).get("orders", [])
                        + value.get("protected_broker_references", {}).get("deals", [])
                    )
                ),
                {},
            )
        lifecycle_state = str(observation.get("lifecycle_state") or default_state)
        return PositionReadItem(
            protected_reference=str(row.get("broker_reference_hash") or ""),
            canonical_symbol=resolved.canonical_symbol or broker_symbol,
            broker_symbol=broker_symbol,
            direction=str(row.get("direction") or "UNKNOWN"),
            volume=_number(row.get("volume")),
            state=lifecycle_state,
            occurred_at=str(row.get("time") or ""),
            open_time=str(row.get("time") or "") if default_state == "POSITION_OPEN" else "",
            close_time=str(row.get("time") or "") if default_state == "POSITION_CLOSED" else "",
            entry_price=_number(row.get("open_price", row.get("entry_price", row.get("price")))),
            current_price=_number(row.get("current_price")),
            stop_loss=_number(row.get("stop_loss")),
            take_profit=_number(row.get("take_profit")),
            unrealized_pnl=_number(row.get("unrealized_pnl")),
            realized_pnl=realized,
            order_type=str(row.get("order_type") or ""),
            pnl_source=("BROKER_CURRENT" if row.get("unrealized_pnl") is not None else "BROKER_COMPONENTS" if realized is not None else "UNAVAILABLE"),
            provenance=self._provenance(execution, observation),
        )

    def _closed_item(
        self,
        row: Mapping[str, Any],
        deals: list[Mapping[str, Any]],
        execution_by_tag: Mapping[str, Mapping[str, Any]],
        lifecycle: Mapping[str, Mapping[str, Any]],
    ) -> PositionReadItem:
        item = self._item(row, "POSITION_CLOSED", execution_by_tag, lifecycle)
        position_reference = str(row.get("position_reference_hash") or "")
        opening = next(
            (
                deal for deal in deals
                if position_reference
                and hmac.compare_digest(
                    str(deal.get("position_reference_hash") or ""), position_reference
                )
                and str(deal.get("entry")) == "IN"
            ),
            None,
        )
        return replace(
            item,
            entry_price=_number(opening.get("price")) if opening else None,
            current_price=_number(row.get("price")),
            open_time=str(opening.get("time") or "") if opening else "",
            close_time=str(row.get("time") or ""),
        )

    def _provenance(
        self,
        execution: Mapping[str, Any] | None,
        observation: Mapping[str, Any],
    ) -> PositionProvenance:
        if not execution:
            return PositionProvenance(
                lifecycle_reference=str(observation.get("observation_id") or ""),
                unavailable=("CONTROLLED_EXECUTION_REFERENCE",),
            )
        protected = dict(execution.get("protected_execution", {}) or {})
        execution_ref = str(protected.get("protected_execution_reference") or "")
        candidate_ref = str(protected.get("source_artifact_reference") or "")
        strategy_ref = ""
        draft_ref = ""
        trading_scope = ""
        authorization_ref = str(protected.get("authorization_reference") or protected.get("human_confirmation_reference") or "")
        if self.candidate_journal and candidate_ref:
            try:
                candidate = self.candidate_journal.load_candidate(candidate_ref)
            except (RuntimeError, ValueError):
                candidate = None
            if candidate is not None:
                strategy_ref = str(getattr(candidate, "strategy_id", "") or "")
                draft_ref = str(getattr(candidate, "proposal_source_reference", "") or "")
                trading_scope = str(getattr(candidate, "trading_scope", "") or "")
        missing = tuple(
            name for name, value in (
                ("STRATEGY_REFERENCE", strategy_ref),
                ("DRAFT_REFERENCE", draft_ref),
                ("CANDIDATE_REFERENCE", candidate_ref),
                ("AUTHORIZATION_REFERENCE", authorization_ref),
                ("LIFECYCLE_REFERENCE", observation.get("observation_id")),
                ("MANAGEMENT_REFERENCE", ""),
            ) if not value
        )
        return PositionProvenance(
            trading_scope=trading_scope,
            strategy_reference=strategy_ref,
            draft_reference=draft_ref,
            candidate_reference=candidate_ref,
            authorization_reference=authorization_ref,
            execution_reference=execution_ref,
            lifecycle_reference=str(observation.get("observation_id") or ""),
            unavailable=missing,
        )

    @staticmethod
    def _blocked(query_type: str, blocker: str, snapshot: Mapping[str, Any] | None = None) -> PositionReadModel:
        snapshot = snapshot or {}
        return PositionReadModel(
            schema_version="position-read-model/v1",
            query_type=query_type,
            status="UNAVAILABLE",
            snapshot_reference=str(snapshot.get("snapshot_reference") or ""),
            snapshot_timestamp=str(snapshot.get("snapshot_timestamp") or ""),
            account_context_match=False,
            blockers=(blocker,),
        )


def render_position_read_model(model: PositionReadModel) -> str:
    if model.blockers:
        return "Position state unavailable: " + ", ".join(model.blockers)
    if model.query_type == "PENDING":
        return _summary("Pending orders", model.pending_orders)
    if model.query_type == "HISTORY":
        return _summary("Recent closed trades", model.history)
    if model.selected_position is not None:
        if model.query_type == "PROVENANCE":
            return _provenance_summary(model.selected_position)
        return _item_summary(model.selected_position)
    return _summary("Open positions", model.open_positions)


def _summary(title: str, items: tuple[PositionReadItem, ...]) -> str:
    if not items:
        return f"{title}: none (authoritative broker snapshot)."
    return title + ":\n" + "\n".join(f"- {_item_summary(item)}" for item in items)


def _item_summary(item: PositionReadItem) -> str:
    pnl = item.unrealized_pnl if item.unrealized_pnl is not None else item.realized_pnl
    return (
        f"{item.canonical_symbol} {item.direction}; state={item.state}; volume={item.volume}; "
        f"entry={item.entry_price}; current={item.current_price}; P/L={pnl}; "
        f"SL={item.stop_loss}; TP={item.take_profit}; reference={item.protected_reference[:12]}..."
    )


def _provenance_summary(item: PositionReadItem) -> str:
    provenance = item.provenance
    chain = (
        f"strategy={_safe_reference(provenance.strategy_reference)} -> "
        f"Draft={_safe_reference(provenance.draft_reference)} -> "
        f"Candidate={_safe_reference(provenance.candidate_reference)} -> "
        f"authorization={_safe_reference(provenance.authorization_reference)} -> "
        f"execution={_safe_reference(provenance.execution_reference)} -> "
        f"lifecycle={_safe_reference(provenance.lifecycle_reference)} -> "
        f"management={_safe_reference(provenance.management_reference)}"
    )
    unavailable = ", ".join(provenance.unavailable) or "none"
    return f"{_item_summary(item)}\nStored provenance: {chain}. Unavailable: {unavailable}."


def _safe_reference(value: str) -> str:
    return f"{value[:12]}..." if value else "UNAVAILABLE"


def _select_position(
    positions: tuple[PositionReadItem, ...], symbol: str, reference: str, singular: bool
) -> tuple[PositionReadItem | None, str]:
    if reference:
        matches = [item for item in positions if hmac.compare_digest(item.protected_reference, reference)]
        return (matches[0], "") if len(matches) == 1 else (None, "STALE_POSITION_REFERENCE")
    matches = [item for item in positions if not symbol or item.canonical_symbol == symbol]
    if not singular:
        return None, ""
    if len(matches) == 1:
        return matches[0], ""
    return (None, "POSITION_NOT_FOUND") if not matches else (None, "AMBIGUOUS_POSITION_REFERENCE")


def _query_type(requested: tuple[str, ...], subtype: str) -> str:
    text = " ".join((*requested, str(subtype or "").lower()))
    if any(value in text for value in ("pending", "order")):
        return "PENDING"
    if any(value in text for value in ("history", "closed", "realized")):
        return "HISTORY"
    if "provenance" in text or "why" in text or "reason" in text:
        return "PROVENANCE"
    if "pnl" in text or "profit" in text or "loss" in text:
        return "PNL"
    if any(value in text for value in ("detail", "stop_loss", "take_profit", "volume")):
        return "DETAIL"
    return "CURRENT"


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _net_realized(row: Mapping[str, Any]) -> float | None:
    values = [row.get(name) for name in ("profit", "commission", "swap", "fee")]
    if all(value is None for value in values):
        return None
    try:
        return float(sum(Decimal(str(value or 0)) for value in values))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _fresh(timestamp: str, max_age_seconds: float, now: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
        return -5 <= age <= max(1.0, max_age_seconds)
    except (TypeError, ValueError):
        return False

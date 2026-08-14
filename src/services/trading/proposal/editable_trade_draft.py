from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Generic, Mapping, TypeVar

from src.config import Config
from src.services.trading.market.timeframes import resolve_symbols_from_text


T = TypeVar("T")
FIELD_STATUSES = {
    "VALID", "MISSING_REQUIRED", "INVALID", "CONFLICTING",
    "CALCULATED_PENDING", "NOT_APPLICABLE",
}
FIELD_SOURCES = {
    "USER_EXPLICIT", "USER_EDITED", "CONVERSATION_INHERITED",
    "USER_SELECTED_METHOD", "LLM_METHOD_SUGGESTION", "STRATEGY_POLICY",
    "DEMO_DEFAULT", "MARKET_CALCULATED", "SYSTEM_CALCULATED",
}
STOP_METHODS = {"USER_EXPLICIT", "ATR_MULTIPLE", "RECENT_STRUCTURE"}
TARGET_METHODS = {"USER_EXPLICIT", "REWARD_RISK_RATIO", "RECENT_STRUCTURE"}
SIZING_METHODS = {"USER_EXPLICIT_VOLUME", "ACCOUNT_RISK_FRACTION"}
SEMANTIC_UNRESOLVED_PREFIX = "SEMANTIC_UNRESOLVED:"


class TradeDraftError(RuntimeError):
    pass


def semantic_prerequisite_blockers(request: Any) -> tuple[str, ...]:
    """Return typed semantic prerequisites that must precede live evidence."""
    strategy = getattr(request, "strategy", None)
    fields = tuple(getattr(strategy, "semantic_unresolved_fields", ()) or ())
    request_blockers = tuple(getattr(request, "blockers", ()) or ())
    return tuple(
        dict.fromkeys(
            (
                *(f"{SEMANTIC_UNRESOLVED_PREFIX}{field}" for field in fields if str(field).strip()),
                *(str(blocker) for blocker in request_blockers if str(blocker).startswith(SEMANTIC_UNRESOLVED_PREFIX)),
            )
        )
    )


@dataclass(frozen=True)
class TradeFieldValue(Generic[T]):
    value: T | None
    status: str
    source: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in FIELD_STATUSES or self.source not in FIELD_SOURCES:
            raise ValueError("TRADE_FIELD_VALUE_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": _json_value(self.value),
            "status": self.status,
            "source": self.source,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class TradeDraftMarketEvidence:
    reference: str
    observed_at: str
    canonical_symbol: str
    broker_symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    atr: Decimal | None = None
    swing_high: Decimal | None = None
    swing_low: Decimal | None = None
    point: Decimal | None = None
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    minimum_distance_points: Decimal | None = None
    volume_min: Decimal | None = None
    volume_max: Decimal | None = None
    volume_step: Decimal | None = None
    contract_size: Decimal | None = None
    account_equity: Decimal | None = None
    free_margin: Decimal | None = None
    account_reference: str = ""
    account_environment: str = "UNKNOWN"
    freshness: str = "UNKNOWN"
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditableTradeDraft:
    draft_id: str
    conversation_id: str
    source_request_id: str
    revision: int
    created_at: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    symbol: TradeFieldValue[Mapping[str, Any]]
    direction: TradeFieldValue[str]
    action: TradeFieldValue[str]
    entry: TradeFieldValue[Mapping[str, Any]]
    stop: TradeFieldValue[Mapping[str, Any]]
    target: TradeFieldValue[Mapping[str, Any]]
    risk: TradeFieldValue[Mapping[str, Any]]
    sizing: TradeFieldValue[Mapping[str, Any]]
    exit_rule: TradeFieldValue[Mapping[str, Any]]
    mode: TradeFieldValue[str]
    confirmation_policy: TradeFieldValue[str]
    account_scope: TradeFieldValue[str]
    market_evidence_reference: str = ""
    market_evidence_timestamp: str = ""
    account_context_bound: bool = False
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    executable: bool = False
    execution_authority: bool = False
    candidate_reference: str = ""
    confirmation_reference: str = ""

    def __post_init__(self) -> None:
        if self.revision < 1 or self.executable or self.execution_authority:
            raise ValueError("EDITABLE_TRADE_DRAFT_INVALID")

    def to_protected_dict(self) -> dict[str, Any]:
        return {
            "schema": "editable-trade-draft/v1",
            "draft_id": self.draft_id,
            "conversation_id": self.conversation_id,
            "source_request_id": self.source_request_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_hash": self.strategy_hash,
            **{
                name: getattr(self, name).as_dict()
                for name in (
                    "symbol", "direction", "action", "entry", "stop", "target",
                    "risk", "sizing", "exit_rule", "mode", "confirmation_policy",
                    "account_scope",
                )
            },
            "market_evidence_reference": self.market_evidence_reference,
            "market_evidence_timestamp": self.market_evidence_timestamp,
            "account_context_bound": self.account_context_bound,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "executable": False,
            "execution_authority": False,
            "candidate_reference": self.candidate_reference,
            "confirmation_reference": self.confirmation_reference,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema": "editable-trade-draft-public/v1",
            "draft_id": self.draft_id,
            "revision": self.revision,
            "symbol": (self.symbol.value or {}).get("canonical_symbol", ""),
            "broker_symbol": (self.symbol.value or {}).get("broker_symbol", ""),
            "direction": self.direction.value or "",
            "action": self.action.value or "",
            "field_statuses": {
                name: {"status": getattr(self, name).status, "source": getattr(self, name).source}
                for name in ("entry", "stop", "target", "risk", "sizing")
            },
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "account_context_bound": self.account_context_bound,
            "market_evidence_present": bool(self.market_evidence_reference),
            "execution_authority": False,
            "executable": False,
            "metadata_redacted": True,
        }

    @classmethod
    def from_protected_dict(cls, payload: Mapping[str, Any]) -> "EditableTradeDraft":
        if (
            payload.get("schema") != "editable-trade-draft/v1"
            or payload.get("executable") is not False
            or payload.get("execution_authority") is not False
        ):
            raise ValueError("EDITABLE_TRADE_DRAFT_INVALID")
        fields = {
            name: _field_from_dict(name, payload.get(name) or {})
            for name in (
                "symbol", "direction", "action", "entry", "stop", "target", "risk",
                "sizing", "exit_rule", "mode", "confirmation_policy", "account_scope",
            )
        }
        return cls(
            draft_id=str(payload.get("draft_id") or ""),
            conversation_id=str(payload.get("conversation_id") or ""),
            source_request_id=str(payload.get("source_request_id") or ""),
            revision=int(payload.get("revision") or 0),
            created_at=str(payload.get("created_at") or ""),
            strategy_id=str(payload.get("strategy_id") or ""),
            strategy_version=str(payload.get("strategy_version") or ""),
            strategy_hash=str(payload.get("strategy_hash") or ""),
            **fields,
            market_evidence_reference=str(payload.get("market_evidence_reference") or ""),
            market_evidence_timestamp=str(payload.get("market_evidence_timestamp") or ""),
            account_context_bound=payload.get("account_context_bound") is True,
            blockers=tuple(str(item) for item in payload.get("blockers") or ()),
            warnings=tuple(str(item) for item in payload.get("warnings") or ()),
            executable=False,
            execution_authority=False,
            candidate_reference=str(payload.get("candidate_reference") or ""),
            confirmation_reference=str(payload.get("confirmation_reference") or ""),
        )


@dataclass(frozen=True)
class TradeParameterPatch:
    expected_revision: int
    stop_loss: Decimal | None = None
    stop_method: str | None = None
    atr_multiplier: Decimal | None = None
    take_profit: Decimal | None = None
    target_method: str | None = None
    reward_risk_ratio: Decimal | None = None
    risk_fraction: Decimal | None = None
    requested_volume: Decimal | None = None
    direction: str | None = None


@dataclass(frozen=True)
class TradeDraftPolicy:
    policy_version: str = "editable-trade-risk/v1"
    default_atr_multiplier: Decimal = Decimal("1.5")
    default_reward_risk_ratio: Decimal = Decimal("2")
    default_demo_risk_fraction: Decimal = Decimal("0.01")
    maximum_risk_fraction: Decimal = Decimal("0.02")
    maximum_stop_fraction: Decimal = Decimal("0.20")
    minimum_reward_risk_ratio: Decimal = Decimal("0.5")
    maximum_reward_risk_ratio: Decimal = Decimal("10")


@dataclass(frozen=True)
class TradeDraftSizingConstraints:
    maximum_risk_amount: Decimal
    maximum_volume: Decimal
    authority_reference: str

    def __post_init__(self) -> None:
        if (
            not self.maximum_risk_amount.is_finite()
            or self.maximum_risk_amount <= 0
            or not self.maximum_volume.is_finite()
            or self.maximum_volume <= 0
            or not str(self.authority_reference).strip()
        ):
            raise ValueError("TRADE_DRAFT_SIZING_CONSTRAINTS_INVALID")


class EditableTradeDraftStore:
    _lock = threading.Lock()

    def __init__(self, path: str | Path | None = None) -> None:
        value = Path(path or "data/trading/execution_journal/editable_trade_drafts.jsonl")
        self.path = value if value.is_absolute() else Config.BASE_DIR / value

    def append(self, draft: EditableTradeDraft) -> EditableTradeDraft:
        with self._lock:
            rows = self._read_rows()
            for row in rows:
                if row["draft"]["draft_id"] == draft.draft_id and int(row["draft"]["revision"]) == draft.revision:
                    existing = EditableTradeDraft.from_protected_dict(row["draft"])
                    if existing == draft:
                        return existing
                    raise TradeDraftError("DRAFT_REVISION_CONFLICT")
            previous_hash = rows[-1]["record_hash"] if rows else ""
            row = {
                "draft": draft.to_protected_dict(),
                "previous_record_hash": previous_hash,
                "record_hash": "",
            }
            row["record_hash"] = _hash(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
            return draft

    def latest_for_conversation(self, conversation_id: str) -> EditableTradeDraft | None:
        drafts = [
            EditableTradeDraft.from_protected_dict(row["draft"])
            for row in self._read_rows()
            if row["draft"].get("conversation_id") == conversation_id
        ]
        return max(drafts, key=lambda item: item.revision) if drafts else None

    def load(self, draft_id: str, revision: int | None = None) -> EditableTradeDraft | None:
        drafts = [
            EditableTradeDraft.from_protected_dict(row["draft"])
            for row in self._read_rows()
            if row["draft"].get("draft_id") == draft_id
            and (revision is None or int(row["draft"].get("revision") or 0) == revision)
        ]
        return max(drafts, key=lambda item: item.revision) if drafts else None

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        previous_hash = ""
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    actual = str(row.get("record_hash") or "")
                    material = dict(row)
                    material["record_hash"] = ""
                    if (
                        not actual
                        or actual != _hash(material)
                        or str(row.get("previous_record_hash") or "") != previous_hash
                    ):
                        raise TradeDraftError("DRAFT_JOURNAL_INTEGRITY_INVALID")
                    EditableTradeDraft.from_protected_dict(row.get("draft") or {})
                    rows.append(row)
                    previous_hash = actual
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TradeDraftError("DRAFT_JOURNAL_INTEGRITY_INVALID") from exc
        return rows


class EditableTradeDraftService:
    def __init__(
        self,
        store: EditableTradeDraftStore | None = None,
        policy: TradeDraftPolicy | None = None,
        sizing_constraints: TradeDraftSizingConstraints | None = None,
    ) -> None:
        self.store = store or EditableTradeDraftStore()
        self.policy = policy or TradeDraftPolicy()
        self.sizing_constraints = sizing_constraints

    def build_or_load(
        self,
        request: Any,
        *,
        conversation_id: str,
        evidence: TradeDraftMarketEvidence | None,
    ) -> EditableTradeDraft:
        if semantic_prerequisite_blockers(request):
            raise TradeDraftError("STRATEGY_COMPLETION_REQUIRED")
        previous = self.store.latest_for_conversation(conversation_id)
        if previous is not None and previous.source_request_id == request.request_id:
            return previous
        draft = self._build(request, conversation_id, evidence, previous)
        return self.store.append(draft)

    def apply_patch(
        self,
        draft_id: str,
        patch: TradeParameterPatch,
        *,
        evidence: TradeDraftMarketEvidence | None = None,
    ) -> EditableTradeDraft:
        current = self.store.load(draft_id)
        if current is None:
            raise TradeDraftError("DRAFT_NOT_FOUND")
        if current.revision != patch.expected_revision:
            raise TradeDraftError("DRAFT_REVISION_CONFLICT")
        values = _draft_values(current)
        changed: set[str] = set()
        for name in (
            "stop_loss", "stop_method", "atr_multiplier", "take_profit",
            "target_method", "reward_risk_ratio", "risk_fraction",
            "requested_volume", "direction",
        ):
            value = getattr(patch, name)
            if value is not None:
                values[name] = str(value).upper() if name in {"stop_method", "target_method", "direction"} else _decimal(value)
                changed.add(name)
        if "stop_loss" in changed:
            values["stop_method"] = "USER_EXPLICIT"
        elif "atr_multiplier" in changed:
            values["stop_method"] = "ATR_MULTIPLE"
            values["stop_loss"] = None
        elif "stop_method" in changed and values["stop_method"] != "USER_EXPLICIT":
            values["stop_loss"] = None
        if "take_profit" in changed:
            values["target_method"] = "USER_EXPLICIT"
        elif "reward_risk_ratio" in changed:
            values["target_method"] = "REWARD_RISK_RATIO"
            values["take_profit"] = None
        elif "target_method" in changed and values["target_method"] != "USER_EXPLICIT":
            values["take_profit"] = None
        if "requested_volume" in changed:
            values["sizing_method"] = "USER_EXPLICIT_VOLUME"
        if "direction" in changed and current.entry.source == "MARKET_CALCULATED":
            values["entry_price"] = None
        _validate_patch(values, changed, self.policy)
        next_draft = _calculate_draft(
            current,
            values,
            evidence or _evidence_from_draft(current),
            self.policy,
            changed,
            self.sizing_constraints,
        )
        next_draft = replace(
            next_draft,
            revision=current.revision + 1,
            created_at=_now(),
            candidate_reference="",
            confirmation_reference="",
        )
        return self.store.append(next_draft)

    def _build(
        self,
        request: Any,
        conversation_id: str,
        evidence: TradeDraftMarketEvidence | None,
        previous: EditableTradeDraft | None,
    ) -> EditableTradeDraft:
        text = str(
            getattr(getattr(request, "strategy", None), "strategy_description", "")
            or getattr(request, "trade_instruction_text", "")
            or ""
        )
        extracted = extract_trade_fields(text)
        values = _draft_values(previous) if previous else {}
        values.update({key: value for key, value in extracted.items() if value not in (None, "")})
        values["direction"] = str(getattr(request, "trade_direction", "") or values.get("direction") or "")
        values["action"] = str(getattr(request, "trade_action", "") or values.get("action") or "")
        strategy = getattr(request, "strategy", None)
        symbol_explicit = bool(resolve_symbols_from_text(text))
        symbol_source = "USER_EXPLICIT" if symbol_explicit else "CONVERSATION_INHERITED"
        timeframe_explicit = bool(re.search(r"\b(?:M1|M5|M15|H1|H4|D1)\b", text, re.I))
        timeframe_source = "USER_EXPLICIT" if timeframe_explicit else "CONVERSATION_INHERITED"
        values.update(
            {
                "canonical_symbol": str(getattr(request, "canonical_symbol", "") or ""),
                "broker_symbol": str(getattr(request, "broker_symbol", "") or ""),
                "timeframes": tuple(getattr(request, "timeframe_profile", ()) or ()),
                "symbol_source": symbol_source,
                "timeframe_source": timeframe_source,
                "entry_rule": tuple(rule.as_dict() for rule in getattr(strategy, "entry_rules", ()) or ()),
                "entry_rule_source": "USER_EXPLICIT",
                "mode": str(getattr(request, "requested_mode", "") or ""),
                "confirmation_policy": str(getattr(request, "confirmation_policy", "") or ""),
                "account_scope": str(getattr(request, "account_scope", "") or ""),
            }
        )
        identity = getattr(strategy, "identity", None)
        semantic_blockers = semantic_prerequisite_blockers(request)
        base = EditableTradeDraft(
            draft_id=(previous.draft_id if previous else "editable_trade_draft_" + hashlib.sha256(conversation_id.encode()).hexdigest()[:24]),
            conversation_id=conversation_id,
            source_request_id=str(request.request_id),
            revision=(previous.revision + 1 if previous else 1),
            created_at=_now(),
            strategy_id=str(getattr(identity, "strategy_id", "") or ""),
            strategy_version=str(getattr(identity, "strategy_version", "") or ""),
            strategy_hash=str(getattr(identity, "normalized_strategy_hash", "") or ""),
            symbol=_field(None, "MISSING_REQUIRED", symbol_source),
            direction=_field(None, "MISSING_REQUIRED", "USER_EXPLICIT"),
            action=_field(None, "MISSING_REQUIRED", "USER_EXPLICIT"),
            entry=_field(None, "MISSING_REQUIRED", "USER_EXPLICIT"),
            stop=_field(None, "MISSING_REQUIRED", "STRATEGY_POLICY"),
            target=_field(None, "MISSING_REQUIRED", "STRATEGY_POLICY"),
            risk=_field(None, "MISSING_REQUIRED", "DEMO_DEFAULT"),
            sizing=_field(None, "MISSING_REQUIRED", "STRATEGY_POLICY"),
            exit_rule=_field(None, "NOT_APPLICABLE", "STRATEGY_POLICY"),
            mode=_field(values["mode"] or None, "VALID" if values["mode"] else "MISSING_REQUIRED", "CONVERSATION_INHERITED"),
            confirmation_policy=_field(values["confirmation_policy"] or None, "VALID" if values["confirmation_policy"] else "MISSING_REQUIRED", "CONVERSATION_INHERITED"),
            account_scope=_field(values["account_scope"] or None, "VALID" if values["account_scope"] else "MISSING_REQUIRED", "CONVERSATION_INHERITED"),
            blockers=semantic_blockers,
        )
        return _calculate_draft(
            base, values, evidence, self.policy, set(), self.sizing_constraints
        )


def build_deterministic_strategy_draft(
    strategy: Any,
    *,
    direction: str,
    action: str,
    broker_symbol: str,
    evidence: TradeDraftMarketEvidence,
    policy: TradeDraftPolicy | None = None,
    sizing_constraints: TradeDraftSizingConstraints | None = None,
) -> EditableTradeDraft:
    """Calculate one non-persistent proposal from an authoritative typed strategy."""
    request = _DeterministicStrategyDraftRequest(
        request_id=str(strategy.request_id),
        requested_mode=str(strategy.requested_mode),
        confirmation_policy=str(strategy.confirmation_policy),
        canonical_symbol=str(strategy.canonical_symbol),
        broker_symbol=str(broker_symbol),
        timeframe_profile=tuple(strategy.timeframes),
        strategy_description=str(strategy.strategy_description),
        account_scope=str(strategy.account_scope),
        trade_action=str(action).upper(),
        trade_direction=str(direction).upper(),
        trade_instruction_text=str(strategy.strategy_description),
        strategy=strategy,
    )
    blockers = semantic_prerequisite_blockers(request)
    if blockers:
        raise TradeDraftError("STRATEGY_COMPLETION_REQUIRED")
    conversation_id = f"{strategy.identity.strategy_id}:{evidence.reference}"
    return EditableTradeDraftService(
        policy=policy, sizing_constraints=sizing_constraints
    )._build(
        request, conversation_id, evidence, None
    )


@dataclass(frozen=True)
class _DeterministicStrategyDraftRequest:
    request_id: str
    requested_mode: str
    confirmation_policy: str
    canonical_symbol: str
    broker_symbol: str
    timeframe_profile: tuple[str, ...]
    strategy_description: str
    account_scope: str
    trade_action: str
    trade_direction: str
    trade_instruction_text: str
    strategy: Any
    blockers: tuple[str, ...] = ()


def extract_trade_fields(text: str) -> dict[str, Any]:
    normalized = _normalized(text)
    result: dict[str, Any] = {}
    patterns = {
        "stop_loss": r"\b(?:sl|stop[- ]?loss|dung lo)\s*(?:=|:|tai|at)?\s*(-?\d+(?:[.,]\d+)?)",
        "take_profit": r"\b(?:tp|take[- ]?profit|chot loi)\s*(?:=|:|tai|at)?\s*(-?\d+(?:[.,]\d+)?)",
        "requested_volume": r"\b(?:volume|lot|khoi luong)\s*(?:=|:)?\s*(\d+(?:[.,]\d+)?)",
        "reward_risk_ratio": r"\b(?:rr|r:r|reward[- ]?risk)\s*(?:=|:)?\s*(\d+(?:[.,]\d+)?)",
        "entry_price": r"\b(?:entry|gia vao)\s*(?:=|:|tai|at)?\s*(\d+(?:[.,]\d+)?)",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, normalized)
        if match:
            result[name] = _decimal(match.group(1).replace(",", "."))
    risk = re.search(r"\b(?:risk|rui ro)\s*(?:=|:)?\s*(\d+(?:[.,]\d+)?)\s*%", normalized)
    if risk:
        result["risk_fraction"] = _decimal(risk.group(1).replace(",", ".")) / Decimal("100")
    atr_multiplier = re.search(r"\bATR(?:\s*\d+)?\s*(?:x|\*)\s*(\d+(?:[.,]\d+)?)", normalized, re.I)
    if atr_multiplier:
        result["atr_multiplier"] = _decimal(atr_multiplier.group(1).replace(",", "."))
        result["stop_method"] = "ATR_MULTIPLE"
    if "stop_loss" in result:
        result["stop_method"] = "USER_EXPLICIT"
    if "take_profit" in result:
        result["target_method"] = "USER_EXPLICIT"
    elif "reward_risk_ratio" in result:
        result["target_method"] = "REWARD_RISK_RATIO"
    if "requested_volume" in result:
        result["sizing_method"] = "USER_EXPLICIT_VOLUME"
    return result


def market_evidence_from_live_result(
    result: Any,
    account: Any,
    *,
    primary_timeframe: str,
    account_environment: str = "UNKNOWN",
) -> TradeDraftMarketEvidence:
    bundle = result.bundle
    tick = bundle.tick
    indicator = result.feature_snapshot.indicator_snapshots.get(primary_timeframe)
    return TradeDraftMarketEvidence(
        reference=str(bundle.bundle_id),
        observed_at=str(tick.timestamp if tick else bundle.created_at),
        canonical_symbol=str(bundle.symbol),
        broker_symbol=str(bundle.broker_symbol),
        bid=_optional_decimal(getattr(tick, "bid", None)),
        ask=_optional_decimal(getattr(tick, "ask", None)),
        atr=_optional_decimal(getattr(indicator, "atr", None)),
        swing_high=_optional_decimal(getattr(indicator, "swing_high", None)),
        swing_low=_optional_decimal(getattr(indicator, "swing_low", None)),
        point=_optional_decimal(getattr(tick, "point", None)),
        tick_size=_optional_decimal(getattr(tick, "tick_size", None)),
        tick_value=_optional_decimal(getattr(tick, "tick_value", None)),
        minimum_distance_points=_optional_decimal(getattr(tick, "minimum_distance_points", None)),
        volume_min=_optional_decimal(getattr(tick, "volume_min", None)),
        volume_max=_optional_decimal(getattr(tick, "volume_max", None)),
        volume_step=_optional_decimal(getattr(tick, "volume_step", None)),
        contract_size=_optional_decimal(getattr(tick, "contract_size", None)),
        account_equity=_optional_decimal(getattr(account, "equity", None)),
        free_margin=_optional_decimal(getattr(account, "free_margin", None)),
        account_reference=str(getattr(account, "account_id_hash", "") or ""),
        account_environment=str(account_environment or "UNKNOWN").upper(),
        freshness=str(getattr(result.quality_report, "status", "UNKNOWN") or "UNKNOWN"),
        blockers=tuple(
            str(item)
            for item in getattr(result.feature_snapshot, "blockers", ()) or ()
        ),
        warnings=tuple(str(item) for item in getattr(result.quality_report, "warnings", ()) or ()),
    )


def _calculate_draft(
    base: EditableTradeDraft,
    values: dict[str, Any],
    evidence: TradeDraftMarketEvidence | None,
    policy: TradeDraftPolicy,
    changed: set[str],
    sizing_constraints: TradeDraftSizingConstraints | None = None,
) -> EditableTradeDraft:
    blockers = [
        blocker
        for blocker in base.blockers
        if blocker.startswith(SEMANTIC_UNRESOLVED_PREFIX)
    ]
    warnings: list[str] = []
    evidence_not_attempted = any(
        blocker.startswith(SEMANTIC_UNRESOLVED_PREFIX) for blocker in blockers
    )
    if evidence_not_attempted:
        warnings.append("EVIDENCE_NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED")
    symbol = str(values.get("canonical_symbol") or "")
    broker = str(values.get("broker_symbol") or "")
    timeframes = tuple(values.get("timeframes") or ())
    if not symbol:
        blockers.append("SYMBOL_REQUIRED")
    if not timeframes:
        blockers.append("TIMEFRAME_REQUIRED")
    symbol_field = _field(
        {"canonical_symbol": symbol, "broker_symbol": broker, "timeframes": timeframes}
        if symbol or broker or timeframes else None,
        "VALID" if symbol and broker and timeframes else "MISSING_REQUIRED",
        str(values.get("symbol_source") or "CONVERSATION_INHERITED"),
    )
    direction = str(values.get("direction") or "").upper()
    action = str(values.get("action") or "")
    if direction not in {"BUY", "SELL"}:
        blockers.append("STRATEGY_DIRECTION_MISSING")
    if action not in {"OPEN_POSITION", "GENERIC_TRADE"}:
        blockers.append("ENTRY_ACTION_MISSING")
    rule = tuple(values.get("entry_rule") or ())
    if not rule:
        blockers.append("ENTRY_RULE_MISSING")

    evidence_valid = bool(
        evidence
        and evidence.canonical_symbol == symbol
        and evidence.broker_symbol == broker
        and evidence.freshness in {"COMPLETE", "PARTIAL"}
        and not evidence.blockers
    )
    if symbol and not evidence_valid and not evidence_not_attempted:
        blockers.append("MARKET_DATA_STALE" if evidence and evidence.freshness == "STALE" else "MARKET_EVIDENCE_UNAVAILABLE")
    entry = _optional_decimal(values.get("entry_price"))
    if entry is None and evidence_valid and direction:
        entry = evidence.ask if direction == "BUY" else evidence.bid
    entry_source = "USER_EDITED" if "entry_price" in changed else str(values.get("entry_source") or ("USER_EXPLICIT" if values.get("entry_price") else "MARKET_CALCULATED"))
    entry_field = _field(
        {"rules": rule, "reference_price": entry, "order_type": "MARKET"},
        "VALID" if rule and entry is not None else "CALCULATED_PENDING" if rule else "MISSING_REQUIRED",
        entry_source,
        (evidence.reference,) if evidence_valid and evidence else (),
    )

    stop_method = str(values.get("stop_method") or "")
    stop = _optional_decimal(values.get("stop_loss"))
    atr_multiplier = _optional_decimal(values.get("atr_multiplier"))
    if stop is not None and stop_method in {"", "USER_EXPLICIT"}:
        stop_method = "USER_EXPLICIT"
    elif not stop_method:
        stop_method = "ATR_MULTIPLE" if evidence_valid and evidence and evidence.atr else "RECENT_STRUCTURE"
    if stop_method == "ATR_MULTIPLE":
        atr_multiplier = atr_multiplier or policy.default_atr_multiplier
        if entry is not None and evidence_valid and evidence and evidence.atr:
            stop = entry - evidence.atr * atr_multiplier if direction == "BUY" else entry + evidence.atr * atr_multiplier
        elif not evidence_not_attempted:
            blockers.append("ATR_EVIDENCE_UNAVAILABLE")
    elif stop_method == "RECENT_STRUCTURE":
        structure = (
            evidence.swing_low
            if evidence_valid and evidence and direction == "BUY"
            else evidence.swing_high
            if evidence_valid and evidence
            else None
        )
        if structure is not None:
            buffer = (evidence.atr or Decimal("0")) * Decimal("0.1")
            stop = structure - buffer if direction == "BUY" else structure + buffer
        elif not evidence_not_attempted:
            blockers.append("STRUCTURE_EVIDENCE_UNAVAILABLE")
    elif stop_method not in STOP_METHODS:
        blockers.append("STOP_POLICY_MISSING")
    if stop is not None and evidence and evidence.tick_size:
        stop = _round_tick(stop, evidence.tick_size)
    stop_status = "VALID" if stop is not None else "CALCULATED_PENDING"
    if stop is not None and entry is not None and direction:
        minimum = (evidence.minimum_distance_points or Decimal("0")) * (evidence.point or Decimal("0")) if evidence else Decimal("0")
        distance = abs(entry - stop)
        if (direction == "BUY" and stop >= entry) or (direction == "SELL" and stop <= entry) or distance < minimum or distance > abs(entry) * policy.maximum_stop_fraction:
            blockers.append("STOP_DISTANCE_INVALID")
            stop_status = "INVALID"
    else:
        distance = None
    stop_source = "USER_EDITED" if {"stop_loss", "stop_method", "atr_multiplier"} & changed else str(values.get("stop_source") or ("USER_EXPLICIT" if values.get("stop_loss") else "STRATEGY_POLICY"))
    stop_field = _field(
        {"method": stop_method, "price": stop, "atr_multiplier": atr_multiplier},
        stop_status,
        stop_source,
        (evidence.reference,) if stop is not None and evidence_valid and evidence else (),
    )

    target_method = str(values.get("target_method") or "")
    target = _optional_decimal(values.get("take_profit"))
    rr = _optional_decimal(values.get("reward_risk_ratio"))
    if target is not None and target_method in {"", "USER_EXPLICIT"}:
        target_method = "USER_EXPLICIT"
    elif not target_method:
        target_method = "REWARD_RISK_RATIO"
    if target_method == "REWARD_RISK_RATIO":
        rr = rr or policy.default_reward_risk_ratio
        if not policy.minimum_reward_risk_ratio <= rr <= policy.maximum_reward_risk_ratio:
            blockers.append("TARGET_POLICY_INVALID")
        elif entry is not None and distance is not None:
            target = entry + distance * rr if direction == "BUY" else entry - distance * rr
        elif not evidence_not_attempted:
            blockers.append("TARGET_CALCULATION_DEPENDENCY_MISSING")
    elif target_method == "RECENT_STRUCTURE":
        target = (
            evidence.swing_high if evidence_valid and evidence and direction == "BUY"
            else evidence.swing_low if evidence_valid and evidence else None
        )
        if target is None and not evidence_not_attempted:
            blockers.append("STRUCTURE_EVIDENCE_UNAVAILABLE")
    elif target_method not in TARGET_METHODS:
        blockers.append("TARGET_POLICY_MISSING")
    if target is not None and rr is not None and entry is not None and distance is not None:
        implied = abs(target - entry) / distance
        if abs(implied - rr) > Decimal("0.01"):
            blockers.append("TARGET_POLICY_CONFLICT")
    if target is not None and evidence and evidence.tick_size:
        target = _round_tick(target, evidence.tick_size)
    target_status = "VALID" if target is not None else "CALCULATED_PENDING"
    if target is not None and entry is not None and direction and ((direction == "BUY" and target <= entry) or (direction == "SELL" and target >= entry)):
        blockers.append("TARGET_DISTANCE_INVALID")
        target_status = "INVALID"
    target_source = "USER_EDITED" if {"take_profit", "target_method", "reward_risk_ratio"} & changed else str(values.get("target_source") or ("USER_EXPLICIT" if values.get("take_profit") else "STRATEGY_POLICY"))
    target_field = _field(
        {"method": target_method, "price": target, "reward_risk_ratio": rr},
        target_status,
        target_source,
        (evidence.reference,) if target is not None and evidence_valid and evidence else (),
    )

    risk_fraction = _optional_decimal(values.get("risk_fraction")) or policy.default_demo_risk_fraction
    if risk_fraction <= 0 or risk_fraction > policy.maximum_risk_fraction:
        blockers.append("RISK_LIMIT_EXCEEDED")
    equity = evidence.account_equity if evidence_valid and evidence else None
    risk_amount = equity * risk_fraction if equity is not None else None
    authorized_risk_budget = (
        min(risk_amount, sizing_constraints.maximum_risk_amount)
        if risk_amount is not None and sizing_constraints is not None
        else risk_amount
    )
    if equity is None and not evidence_not_attempted:
        blockers.append("ACCOUNT_RISK_BASIS_UNAVAILABLE")
    risk_source = "USER_EDITED" if "risk_fraction" in changed else str(values.get("risk_source") or ("USER_EXPLICIT" if values.get("risk_fraction") else "DEMO_DEFAULT"))

    requested_volume = _optional_decimal(values.get("requested_volume"))
    sizing_method = str(values.get("sizing_method") or ("USER_EXPLICIT_VOLUME" if requested_volume is not None else "ACCOUNT_RISK_FRACTION"))
    proposed_volume = requested_volume
    required_metadata = bool(evidence and evidence.tick_size and evidence.tick_value and evidence.volume_step and evidence.volume_min and evidence.volume_max)
    volume_by_risk = None
    authorized_volume_cap = None
    if sizing_method == "ACCOUNT_RISK_FRACTION":
        if authorized_risk_budget is not None and distance and required_metadata:
            risk_per_lot = (distance / evidence.tick_size) * evidence.tick_value
            volume_by_risk = authorized_risk_budget / risk_per_lot
            if sizing_constraints is None:
                proposed_volume = _floor_volume(
                    volume_by_risk,
                    evidence.volume_step,
                    evidence.volume_min,
                    evidence.volume_max,
                )
            else:
                authorized_volume_cap = min(
                    sizing_constraints.maximum_volume, evidence.volume_max
                )
                proposed_volume = _floor_volume_to_cap(
                    min(volume_by_risk, authorized_volume_cap),
                    evidence.volume_step,
                    authorized_volume_cap,
                )
                if proposed_volume < evidence.volume_min:
                    blockers.append(
                        "MANDATE_VOLUME_LIMIT_BELOW_BROKER_MINIMUM"
                        if authorized_volume_cap < evidence.volume_min
                        else "MANDATE_RISK_BUDGET_BELOW_BROKER_MINIMUM"
                    )
                    proposed_volume = None
        elif not required_metadata and not evidence_not_attempted:
            blockers.append("TICK_VALUE_UNAVAILABLE" if not evidence or not evidence.tick_value else "VOLUME_STEP_INVALID")
    elif sizing_method != "USER_EXPLICIT_VOLUME":
        blockers.append("POSITION_SIZING_POLICY_MISSING")
    actual_risk = None
    actual_fraction = None
    if proposed_volume is not None and distance and evidence and evidence.tick_size and evidence.tick_value:
        actual_risk = distance / evidence.tick_size * evidence.tick_value * proposed_volume
        actual_fraction = actual_risk / equity if equity else None
        if actual_fraction is not None and actual_fraction > policy.maximum_risk_fraction:
            blockers.append("RISK_LIMIT_EXCEEDED")
        if sizing_constraints is not None:
            if actual_risk > sizing_constraints.maximum_risk_amount:
                blockers.append("MANDATE_RISK_LIMIT_EXCEEDED")
            if proposed_volume > sizing_constraints.maximum_volume:
                blockers.append("MANDATE_VOLUME_LIMIT_EXCEEDED")
            if proposed_volume > evidence.volume_max:
                blockers.append("BROKER_VOLUME_MAXIMUM_EXCEEDED")
    sizing_source = "USER_EDITED" if "requested_volume" in changed else str(values.get("sizing_source") or ("USER_EXPLICIT" if requested_volume is not None else "SYSTEM_CALCULATED"))
    sizing_status = "VALID" if proposed_volume is not None else "CALCULATED_PENDING"
    sizing_field = _field(
        {
            "method": sizing_method,
            "requested_volume": requested_volume,
            "proposed_volume": proposed_volume,
            "actual_risk_amount": actual_risk,
            "actual_risk_fraction": actual_fraction,
            "volume_by_risk": volume_by_risk,
            "authorized_volume_cap": authorized_volume_cap,
            "mandate_maximum_volume": (
                sizing_constraints.maximum_volume if sizing_constraints else None
            ),
            "broker_minimum_volume": evidence.volume_min if evidence else None,
            "broker_maximum_volume": evidence.volume_max if evidence else None,
            "broker_volume_step": evidence.volume_step if evidence else None,
            "sizing_authority_reference": (
                sizing_constraints.authority_reference if sizing_constraints else ""
            ),
        },
        sizing_status,
        sizing_source,
        (evidence.reference,) if proposed_volume is not None and evidence_valid and evidence else (),
    )
    risk_field = _field(
        {
            "fraction": risk_fraction,
            "amount": risk_amount,
            "policy_risk_amount": risk_amount,
            "mandate_maximum_risk": (
                sizing_constraints.maximum_risk_amount if sizing_constraints else None
            ),
            "authorized_risk_budget": authorized_risk_budget,
            "policy_version": policy.policy_version,
        },
        "VALID" if risk_amount is not None and "RISK_LIMIT_EXCEEDED" not in blockers else "CALCULATED_PENDING" if risk_amount is None else "INVALID",
        risk_source,
        (evidence.account_reference,) if evidence and evidence.account_reference else (),
    )
    account_scope = str(values.get("account_scope") or "")
    account_scope_source = "CONVERSATION_INHERITED"
    if account_scope == "UNKNOWN" and evidence and evidence.account_environment == "DEMO":
        account_scope = "DEMO"
        account_scope_source = "DEMO_DEFAULT"
    if account_scope != "DEMO" and not evidence_not_attempted:
        blockers.append("DEMO_ACCOUNT_SCOPE_REQUIRED")
    if evidence:
        blockers.extend(evidence.blockers)
        warnings.extend(evidence.warnings)
    return replace(
        base,
        symbol=symbol_field,
        direction=_field(direction or None, "VALID" if direction in {"BUY", "SELL"} else "MISSING_REQUIRED", "USER_EDITED" if "direction" in changed else "USER_EXPLICIT"),
        action=_field(action or None, "VALID" if action in {"OPEN_POSITION", "GENERIC_TRADE"} else "MISSING_REQUIRED", "USER_EXPLICIT"),
        entry=entry_field,
        stop=stop_field,
        target=target_field,
        risk=risk_field,
        sizing=sizing_field,
        exit_rule=_field({"rules": ()}, "NOT_APPLICABLE", "STRATEGY_POLICY"),
        account_scope=_field(
            account_scope or None,
            "VALID" if account_scope == "DEMO" else "MISSING_REQUIRED",
            account_scope_source,
        ),
        market_evidence_reference=evidence.reference if evidence_valid and evidence else "",
        market_evidence_timestamp=evidence.observed_at if evidence_valid and evidence else "",
        account_context_bound=bool(evidence_valid and evidence and evidence.account_reference),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
        executable=False,
        execution_authority=False,
    )


def _draft_values(draft: EditableTradeDraft | None) -> dict[str, Any]:
    if draft is None:
        return {}
    symbol = dict(draft.symbol.value or {})
    entry = dict(draft.entry.value or {})
    stop = dict(draft.stop.value or {})
    target = dict(draft.target.value or {})
    risk = dict(draft.risk.value or {})
    sizing = dict(draft.sizing.value or {})
    return {
        "canonical_symbol": symbol.get("canonical_symbol", ""),
        "broker_symbol": symbol.get("broker_symbol", ""),
        "timeframes": tuple(symbol.get("timeframes") or ()),
        "symbol_source": draft.symbol.source,
        "direction": draft.direction.value or "",
        "action": draft.action.value or "",
        "entry_rule": tuple(entry.get("rules") or ()),
        "entry_price": entry.get("reference_price"),
        "entry_source": draft.entry.source,
        "stop_method": stop.get("method"),
        "stop_loss": stop.get("price"),
        "atr_multiplier": stop.get("atr_multiplier"),
        "stop_source": draft.stop.source,
        "target_method": target.get("method"),
        "take_profit": target.get("price"),
        "reward_risk_ratio": target.get("reward_risk_ratio"),
        "target_source": draft.target.source,
        "risk_fraction": risk.get("fraction"),
        "risk_source": draft.risk.source,
        "sizing_method": sizing.get("method"),
        "requested_volume": sizing.get("requested_volume"),
        "sizing_source": draft.sizing.source,
        "mode": draft.mode.value or "",
        "confirmation_policy": draft.confirmation_policy.value or "",
        "account_scope": draft.account_scope.value or "",
    }


def _evidence_from_draft(draft: EditableTradeDraft) -> TradeDraftMarketEvidence | None:
    if not draft.market_evidence_reference:
        return None
    symbol = dict(draft.symbol.value or {})
    entry = _optional_decimal((draft.entry.value or {}).get("reference_price"))
    return TradeDraftMarketEvidence(
        reference=draft.market_evidence_reference,
        observed_at=draft.market_evidence_timestamp,
        canonical_symbol=str(symbol.get("canonical_symbol") or ""),
        broker_symbol=str(symbol.get("broker_symbol") or ""),
        bid=entry,
        ask=entry,
        freshness="COMPLETE",
    )


def _validate_patch(values: Mapping[str, Any], changed: set[str], policy: TradeDraftPolicy) -> None:
    if "stop_method" in changed and values["stop_method"] not in STOP_METHODS:
        raise TradeDraftError("STOP_POLICY_INVALID")
    if "target_method" in changed and values["target_method"] not in TARGET_METHODS:
        raise TradeDraftError("TARGET_POLICY_INVALID")
    if "direction" in changed and values["direction"] not in {"BUY", "SELL"}:
        raise TradeDraftError("STRATEGY_DIRECTION_INVALID")
    for name in changed - {"stop_method", "target_method", "direction"}:
        value = _optional_decimal(values.get(name))
        if value is None or value <= 0:
            raise TradeDraftError(f"{name.upper()}_INVALID")
    if "risk_fraction" in changed and _decimal(values["risk_fraction"]) > policy.maximum_risk_fraction:
        raise TradeDraftError("RISK_LIMIT_EXCEEDED")


def _field(value: Any, status: str, source: str, evidence: tuple[str, ...] = ()) -> TradeFieldValue[Any]:
    return TradeFieldValue(value, status, source, tuple(item for item in evidence if item))


def _field_from_dict(name: str, payload: Mapping[str, Any]) -> TradeFieldValue[Any]:
    value = payload.get("value")
    if isinstance(value, Mapping):
        value = dict(value)
        if name == "symbol":
            value["timeframes"] = tuple(value.get("timeframes") or ())
        if name in {"entry", "exit_rule"}:
            value["rules"] = tuple(value.get("rules") or ())
        decimal_keys = {
            "entry": ("reference_price",),
            "stop": ("price", "atr_multiplier"),
            "target": ("price", "reward_risk_ratio"),
            "risk": (
                "fraction", "amount", "policy_risk_amount",
                "mandate_maximum_risk", "authorized_risk_budget",
            ),
            "sizing": (
                "requested_volume", "proposed_volume", "actual_risk_amount",
                "actual_risk_fraction", "volume_by_risk",
                "authorized_volume_cap", "mandate_maximum_volume",
                "broker_minimum_volume", "broker_maximum_volume",
                "broker_volume_step",
            ),
        }.get(name, ())
        for key in decimal_keys:
            if value.get(key) not in (None, ""):
                value[key] = _decimal(value[key])
    return TradeFieldValue(
        value,
        str(payload.get("status") or "INVALID"),
        str(payload.get("source") or "STRATEGY_POLICY"),
        tuple(str(item) for item in payload.get("evidence") or ()),
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TradeDraftError("DECIMAL_VALUE_INVALID") from exc
    if not result.is_finite():
        raise TradeDraftError("DECIMAL_VALUE_INVALID")
    return result


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return _decimal(value)
    except TradeDraftError:
        return None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _round_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    return (value / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size


def _floor_volume(value: Decimal, step: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    bounded = max(minimum, min(maximum, value))
    return max(minimum, (bounded / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step)


def _floor_volume_to_cap(value: Decimal, step: Decimal, maximum: Decimal) -> Decimal:
    bounded = min(maximum, value)
    return (bounded / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.lower().replace("đ", "d").split())

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


OPERATING_MODES = {"advisory_only", "human_confirmed_live", "autonomous_live"}
AUTHORIZATION_SOURCES = {"HUMAN_CONFIRMATION", "STANDING_MANDATE"}
AUTHORITY_SCHEMA_VERSION = "trading-authority/v1"


class TradingAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class OperatingModeAuthority:
    mode_record_id: str
    created_at: str
    operating_mode: str
    account_fingerprint_hash: str
    account_is_demo: bool
    operator_grant: bool
    nonce: str
    artifact_hash: str = ""

    def protected_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_hash"] = ""
        return payload

    def integrity_valid(self) -> bool:
        return _valid_hash(self.artifact_hash) and hmac.compare_digest(
            self.artifact_hash, _hash(self.protected_payload())
        )


@dataclass(frozen=True)
class StandingTradingMandate:
    mandate_id: str
    mandate_version: int
    created_at: str
    active_from: str
    active_until: str
    expires_at: str
    operating_mode: str
    account_fingerprint_hash: str
    account_is_demo: bool
    permitted_symbols: tuple[str, ...]
    permitted_broker_symbols: tuple[str, ...]
    permitted_order_families: tuple[str, ...]
    permitted_management_actions: tuple[str, ...]
    maximum_volume: str
    maximum_risk_per_trade: str
    maximum_concurrent_positions: int
    maximum_trades_per_day: int
    maximum_loss_per_day: str
    nonce: str
    idempotency_key: str
    kill_switch_engaged: bool
    operator_grant: bool
    revoked: bool = False
    revoked_at: str = ""
    revocation_nonce: str = ""
    artifact_hash: str = ""

    def protected_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["permitted_symbols"] = list(self.permitted_symbols)
        payload["permitted_broker_symbols"] = list(self.permitted_broker_symbols)
        payload["permitted_order_families"] = list(self.permitted_order_families)
        payload["permitted_management_actions"] = list(
            self.permitted_management_actions
        )
        payload["artifact_hash"] = ""
        return payload

    def integrity_valid(self) -> bool:
        return _valid_hash(self.artifact_hash) and hmac.compare_digest(
            self.artifact_hash, _hash(self.protected_payload())
        )


@dataclass(frozen=True)
class MandateCandidateAuthorization:
    authorization_id: str
    authorization_source: str
    created_at: str
    expires_at: str
    candidate_reference: str
    candidate_provenance_hash: str
    structured_order_hash: str
    proposal_source_reference: str
    source_refs: tuple[str, ...]
    account_fingerprint_hash: str
    symbol: str
    broker_symbol: str
    order_family: str
    protected_order_parameters: Mapping[str, Any] = field(repr=False)
    evaluated_risk_per_trade: str = ""
    concurrent_positions: int = 0
    trades_today: int = 0
    loss_today: str = "0"
    mandate_id: str = ""
    mandate_version: int = 0
    authorization_nonce: str = ""
    deterministic_idempotency_key: str = field(default="", repr=False)
    kill_switch_engaged: bool = True
    mandate_revoked: bool = False
    artifact_hash: str = ""

    def protected_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_refs"] = list(self.source_refs)
        payload["protected_order_parameters"] = dict(
            self.protected_order_parameters
        )
        payload["artifact_hash"] = ""
        return payload

    def integrity_valid(self) -> bool:
        return (
            self.authorization_source == "STANDING_MANDATE"
            and _valid_hash(self.artifact_hash)
            and hmac.compare_digest(
                self.artifact_hash, _hash(self.protected_payload())
            )
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "authorization_source": self.authorization_source,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "candidate_reference": self.candidate_reference,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "order_family": self.order_family,
            "mandate_id": self.mandate_id,
            "mandate_version": self.mandate_version,
            "parameters_redacted": True,
            "execution_authority": False,
            "executable": False,
            "order_send_allowed": False,
        }


class TradingAuthorityStore:
    _process_lock = threading.Lock()

    def __init__(
        self,
        path: str | Path = "data/trading/execution_journal/trading_authority.jsonl",
    ):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(self, event_type: str, artifact: Any) -> tuple[dict[str, Any], bool]:
        payload = artifact.protected_payload()
        payload["artifact_hash"] = artifact.artifact_hash
        event_id = _event_id(artifact)
        with self._exclusive_lock():
            rows = self.read_strict()
            existing = next((row for row in rows if row["event_id"] == event_id), None)
            if existing is not None:
                if not hmac.compare_digest(
                    str(existing["payload"].get("artifact_hash", "")),
                    str(payload.get("artifact_hash", "")),
                ):
                    raise TradingAuthorityError("AUTHORITY_IDEMPOTENCY_CONFLICT")
                return existing, False
            previous_hash = rows[-1]["record_hash"] if rows else ""
            row = {
                "schema_version": AUTHORITY_SCHEMA_VERSION,
                "event_id": event_id,
                "event_type": event_type,
                "created_at": artifact.created_at,
                "payload": payload,
                "previous_record_hash": previous_hash,
                "metadata_redacted": True,
                "record_hash": "",
            }
            row["record_hash"] = _hash(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return row, True

    def read_strict(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise TradingAuthorityError("AUTHORITY_STORE_UNAVAILABLE") from exc
        rows: list[dict[str, Any]] = []
        previous_hash = ""
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TradingAuthorityError("AUTHORITY_STORE_CORRUPT") from exc
            if not isinstance(row, dict) or row.get("schema_version") != AUTHORITY_SCHEMA_VERSION:
                raise TradingAuthorityError("AUTHORITY_STORE_CORRUPT")
            actual_hash = str(row.get("record_hash", ""))
            material = dict(row)
            material["record_hash"] = ""
            if (
                row.get("metadata_redacted") is not True
                or row.get("previous_record_hash") != previous_hash
                or not _valid_hash(actual_hash)
                or not hmac.compare_digest(actual_hash, _hash(material))
            ):
                raise TradingAuthorityError("AUTHORITY_STORE_CORRUPT")
            rows.append(row)
            previous_hash = actual_hash
        return rows

    def latest_mode(self) -> OperatingModeAuthority | None:
        rows = [row for row in self.read_strict() if row["event_type"] == "MODE_SET"]
        return _mode_from_payload(rows[-1]["payload"]) if rows else None

    def latest_mandate(self, mandate_id: str) -> StandingTradingMandate | None:
        rows = [
            row
            for row in self.read_strict()
            if row["event_type"] in {"MANDATE_GRANTED", "MANDATE_REVOKED"}
            and row["payload"].get("mandate_id") == mandate_id
        ]
        return _mandate_from_payload(rows[-1]["payload"]) if rows else None

    def load_authorization(self, authorization_id: str) -> MandateCandidateAuthorization:
        rows = [
            row
            for row in self.read_strict()
            if row["event_type"] == "CANDIDATE_AUTHORIZED"
            and row["payload"].get("authorization_id") == authorization_id
        ]
        if not rows:
            raise TradingAuthorityError("MANDATE_AUTHORIZATION_NOT_FOUND")
        return _authorization_from_payload(rows[-1]["payload"])

    def _exclusive_lock(self):
        store = self

        class LockContext:
            def __enter__(self):
                store._process_lock.acquire()
                store.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.fd = os.open(
                        store.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                except (FileExistsError, OSError) as exc:
                    store._process_lock.release()
                    raise TradingAuthorityError("AUTHORITY_STORE_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    store.lock_path.unlink()
                finally:
                    store._process_lock.release()

        return LockContext()


class TradingAuthorityService:
    def __init__(self, store: TradingAuthorityStore):
        self.store = store

    def set_mode(
        self,
        operating_mode: str,
        *,
        account_fingerprint: str,
        account_is_demo: bool,
        operator_grant: bool,
        nonce: str,
        now: datetime | None = None,
    ) -> OperatingModeAuthority:
        created_at = _utc(now).isoformat()
        fingerprint_hash = _fingerprint_hash(account_fingerprint)
        if (
            operating_mode not in OPERATING_MODES
            or not account_is_demo
            or operator_grant is not True
            or not _identifier(nonce)
        ):
            raise TradingAuthorityError("MODE_AUTHORITY_INVALID")
        material = {
            "created_at": created_at,
            "operating_mode": operating_mode,
            "account_fingerprint_hash": fingerprint_hash,
            "account_is_demo": True,
            "operator_grant": True,
            "nonce": nonce,
        }
        record = OperatingModeAuthority(
            mode_record_id="mode_authority_" + _hash(material)[:24],
            artifact_hash="",
            **material,
        )
        record = replace(record, artifact_hash=_hash(record.protected_payload()))
        self.store.append("MODE_SET", record)
        return record

    def grant_mandate(
        self,
        *,
        mandate_id: str,
        mandate_version: int,
        account_fingerprint: str,
        account_is_demo: bool,
        permitted_symbols: tuple[str, ...],
        permitted_broker_symbols: tuple[str, ...],
        permitted_order_families: tuple[str, ...],
        permitted_management_actions: tuple[str, ...],
        maximum_volume: str,
        maximum_risk_per_trade: str,
        maximum_concurrent_positions: int,
        maximum_trades_per_day: int,
        maximum_loss_per_day: str,
        active_from: str,
        active_until: str,
        expires_at: str,
        nonce: str,
        idempotency_key: str,
        kill_switch_engaged: bool,
        operator_grant: bool,
        now: datetime | None = None,
    ) -> StandingTradingMandate:
        created_at = _utc(now).isoformat()
        current_mode = self.store.latest_mode()
        previous = self.store.latest_mandate(mandate_id)
        if (
            not _identifier(mandate_id)
            or mandate_version < 1
            or (previous is not None and mandate_version <= previous.mandate_version)
            or current_mode is None
            or current_mode.operating_mode != "autonomous_live"
            or not account_is_demo
            or operator_grant is not True
            or not _identifier(nonce)
            or not _identifier(idempotency_key)
        ):
            raise TradingAuthorityError("MANDATE_GRANT_INVALID")
        fingerprint_hash = _fingerprint_hash(account_fingerprint)
        if not hmac.compare_digest(
            current_mode.account_fingerprint_hash, fingerprint_hash
        ):
            raise TradingAuthorityError("MANDATE_ACCOUNT_MISMATCH")
        symbols = _identifiers(permitted_symbols)
        broker_symbols = _identifiers(permitted_broker_symbols)
        order_families = _allowed_values(
            permitted_order_families, {"MARKET", "PENDING"}
        )
        management_actions = _allowed_values(
            permitted_management_actions,
            {"OBSERVE", "NO_ACTION", "CANCEL_PENDING", "MODIFY_PROTECTION", "CLOSE_POSITION"},
            allow_empty=True,
        )
        _positive_decimal(maximum_volume, "MANDATE_MAXIMUM_VOLUME_INVALID")
        _positive_decimal(maximum_risk_per_trade, "MANDATE_MAXIMUM_RISK_INVALID")
        _positive_decimal(maximum_loss_per_day, "MANDATE_MAXIMUM_LOSS_INVALID")
        if (
            maximum_concurrent_positions < 1
            or maximum_trades_per_day < 1
            or not _ordered_times(active_from, active_until, expires_at, _utc(now))
        ):
            raise TradingAuthorityError("MANDATE_LIMITS_INVALID")
        mandate = StandingTradingMandate(
            mandate_id=mandate_id,
            mandate_version=mandate_version,
            created_at=created_at,
            active_from=active_from,
            active_until=active_until,
            expires_at=expires_at,
            operating_mode="autonomous_live",
            account_fingerprint_hash=fingerprint_hash,
            account_is_demo=True,
            permitted_symbols=symbols,
            permitted_broker_symbols=broker_symbols,
            permitted_order_families=order_families,
            permitted_management_actions=management_actions,
            maximum_volume=str(maximum_volume),
            maximum_risk_per_trade=str(maximum_risk_per_trade),
            maximum_concurrent_positions=maximum_concurrent_positions,
            maximum_trades_per_day=maximum_trades_per_day,
            maximum_loss_per_day=str(maximum_loss_per_day),
            nonce=nonce,
            idempotency_key=idempotency_key,
            kill_switch_engaged=bool(kill_switch_engaged),
            operator_grant=True,
        )
        mandate = replace(mandate, artifact_hash=_hash(mandate.protected_payload()))
        self.store.append("MANDATE_GRANTED", mandate)
        return mandate

    def revoke_mandate(
        self,
        mandate_id: str,
        *,
        operator_grant: bool,
        revocation_nonce: str,
        now: datetime | None = None,
    ) -> StandingTradingMandate:
        mandate = self.store.latest_mandate(mandate_id)
        if (
            mandate is None
            or not mandate.integrity_valid()
            or mandate.revoked
            or operator_grant is not True
            or not _identifier(revocation_nonce)
        ):
            raise TradingAuthorityError("MANDATE_REVOCATION_INVALID")
        revoked = replace(
            mandate,
            created_at=_utc(now).isoformat(),
            revoked=True,
            revoked_at=_utc(now).isoformat(),
            revocation_nonce=revocation_nonce,
            artifact_hash="",
        )
        revoked = replace(revoked, artifact_hash=_hash(revoked.protected_payload()))
        self.store.append("MANDATE_REVOKED", revoked)
        return revoked

    def authorize_candidate(
        self,
        candidate: Any,
        *,
        mandate_id: str,
        account_fingerprint: str,
        account_is_demo: bool,
        evaluated_risk_per_trade: str,
        concurrent_positions: int,
        trades_today: int,
        loss_today: str,
        current_kill_switch_engaged: bool,
        lifecycle_healthy: bool,
        reconciliation_healthy: bool,
        authorization_nonce: str,
        now: datetime | None = None,
    ) -> MandateCandidateAuthorization:
        evaluated_at = _utc(now)
        mode = self.store.latest_mode()
        mandate = self.store.latest_mandate(mandate_id)
        blockers = self._candidate_blockers(
            candidate,
            mode,
            mandate,
            account_fingerprint,
            account_is_demo,
            evaluated_risk_per_trade,
            concurrent_positions,
            trades_today,
            loss_today,
            current_kill_switch_engaged,
            lifecycle_healthy,
            reconciliation_healthy,
            evaluated_at,
        )
        if blockers or not _identifier(authorization_nonce):
            raise TradingAuthorityError(blockers[0] if blockers else "AUTHORIZATION_NONCE_INVALID")
        assert mandate is not None
        protected_parameters = {
            name: getattr(candidate, name, "")
            for name in (
                "side",
                "order_type",
                "action",
                "entry_price",
                "trigger_price",
                "limit_price",
                "stop_loss",
                "take_profit",
                "proposed_volume",
            )
        }
        source_refs = _candidate_source_refs(candidate)
        expires_at = min(
            _time(str(candidate.expires_at)),
            _time(mandate.active_until),
            _time(mandate.expires_at),
        ).isoformat()
        key_material = {
            "candidate_reference": candidate.candidate_reference,
            "candidate_provenance_hash": candidate.provenance_hash,
            "structured_order_hash": candidate.structured_order_hash,
            "mandate_id": mandate.mandate_id,
            "mandate_version": mandate.mandate_version,
            "authorization_nonce": authorization_nonce,
            "account_fingerprint_hash": mandate.account_fingerprint_hash,
            "protected_order_parameters": protected_parameters,
            "evaluated_risk_per_trade": str(evaluated_risk_per_trade),
        }
        idempotency_key = _hash(key_material)
        authorization = MandateCandidateAuthorization(
            authorization_id="mandate_authorization_" + idempotency_key[:24],
            authorization_source="STANDING_MANDATE",
            created_at=evaluated_at.isoformat(),
            expires_at=expires_at,
            candidate_reference=candidate.candidate_reference,
            candidate_provenance_hash=candidate.provenance_hash,
            structured_order_hash=candidate.structured_order_hash,
            proposal_source_reference=candidate.proposal_source_reference,
            source_refs=source_refs,
            account_fingerprint_hash=mandate.account_fingerprint_hash,
            symbol=candidate.symbol_reference,
            broker_symbol=candidate.broker_symbol_reference,
            order_family=candidate.action,
            protected_order_parameters=protected_parameters,
            evaluated_risk_per_trade=str(evaluated_risk_per_trade),
            concurrent_positions=concurrent_positions,
            trades_today=trades_today,
            loss_today=str(loss_today),
            mandate_id=mandate.mandate_id,
            mandate_version=mandate.mandate_version,
            authorization_nonce=authorization_nonce,
            deterministic_idempotency_key=idempotency_key,
            kill_switch_engaged=False,
            mandate_revoked=False,
        )
        authorization = replace(
            authorization, artifact_hash=_hash(authorization.protected_payload())
        )
        self.store.append("CANDIDATE_AUTHORIZED", authorization)
        return authorization

    def validate_candidate_authorization(
        self,
        authorization_id: str,
        candidate: Any,
        *,
        account_fingerprint: str,
        account_is_demo: bool,
        current_kill_switch_engaged: bool,
        evaluated_risk_per_trade: str | None = None,
        concurrent_positions: int | None = None,
        trades_today: int | None = None,
        loss_today: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        try:
            authorization = self.store.load_authorization(authorization_id)
            mandate = self.store.latest_mandate(authorization.mandate_id)
            mode = self.store.latest_mode()
        except TradingAuthorityError as exc:
            return (str(exc),)
        blockers: list[str] = []
        if not authorization.integrity_valid():
            blockers.append("MANDATE_AUTHORIZATION_INTEGRITY_INVALID")
        if authorization.authorization_source != "STANDING_MANDATE":
            blockers.append("AUTHORIZATION_SOURCE_INVALID")
        if mandate is None or not mandate.integrity_valid():
            blockers.append("MANDATE_INTEGRITY_INVALID")
        elif (
            mandate.revoked
            or mandate.mandate_version != authorization.mandate_version
            or not hmac.compare_digest(mandate.artifact_hash, _latest_mandate_hash(mandate))
        ):
            blockers.append("MANDATE_REVOKED_OR_VERSION_CHANGED")
        if mode is None or not mode.integrity_valid() or mode.operating_mode != "autonomous_live":
            blockers.append("AUTONOMOUS_MODE_NOT_AUTHORITATIVE")
        fingerprint_hash = _fingerprint_hash(account_fingerprint)
        expected = (
            authorization.candidate_reference,
            authorization.candidate_provenance_hash,
            authorization.structured_order_hash,
            authorization.proposal_source_reference,
            authorization.symbol,
            authorization.broker_symbol,
            authorization.order_family,
            authorization.source_refs,
            dict(authorization.protected_order_parameters),
        )
        actual = (
            candidate.candidate_reference,
            candidate.provenance_hash,
            candidate.structured_order_hash,
            candidate.proposal_source_reference,
            candidate.symbol_reference,
            candidate.broker_symbol_reference,
            candidate.action,
            _candidate_source_refs(candidate),
            {
                name: getattr(candidate, name, "")
                for name in (
                    "side",
                    "order_type",
                    "action",
                    "entry_price",
                    "trigger_price",
                    "limit_price",
                    "stop_loss",
                    "take_profit",
                    "proposed_volume",
                )
            },
        )
        if not hmac.compare_digest(_hash(expected), _hash(actual)):
            blockers.append("MANDATE_CANDIDATE_BINDING_MISMATCH")
        if (
            not account_is_demo
            or not hmac.compare_digest(authorization.account_fingerprint_hash, fingerprint_hash)
        ):
            blockers.append("MANDATE_ACCOUNT_MISMATCH")
        if current_kill_switch_engaged:
            blockers.append("KILL_SWITCH_ENGAGED")
        if None in {
            evaluated_risk_per_trade,
            concurrent_positions,
            trades_today,
            loss_today,
        }:
            blockers.append("MANDATE_LIMIT_EVIDENCE_MISSING")
        elif mandate is not None:
            try:
                if Decimal(str(evaluated_risk_per_trade)) > Decimal(
                    mandate.maximum_risk_per_trade
                ):
                    blockers.append("MANDATE_RISK_LIMIT_EXCEEDED")
                if Decimal(str(loss_today)) >= Decimal(mandate.maximum_loss_per_day):
                    blockers.append("MANDATE_DAILY_LOSS_LIMIT_EXHAUSTED")
            except InvalidOperation:
                blockers.append("MANDATE_NUMERIC_INPUT_INVALID")
            if int(concurrent_positions) >= mandate.maximum_concurrent_positions:
                blockers.append("MANDATE_POSITION_LIMIT_EXHAUSTED")
            if int(trades_today) >= mandate.maximum_trades_per_day:
                blockers.append("MANDATE_TRADE_LIMIT_EXHAUSTED")
        if _time(authorization.expires_at) <= _utc(now):
            blockers.append("MANDATE_AUTHORIZATION_EXPIRED")
        return tuple(dict.fromkeys(blockers))

    @staticmethod
    def _candidate_blockers(
        candidate,
        mode,
        mandate,
        account_fingerprint,
        account_is_demo,
        evaluated_risk_per_trade,
        concurrent_positions,
        trades_today,
        loss_today,
        current_kill_switch_engaged,
        lifecycle_healthy,
        reconciliation_healthy,
        now,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if mode is None or not mode.integrity_valid() or mode.operating_mode != "autonomous_live":
            blockers.append("AUTONOMOUS_MODE_NOT_AUTHORITATIVE")
        if mandate is None or not mandate.integrity_valid():
            blockers.append("MANDATE_INTEGRITY_INVALID")
            return tuple(blockers)
        fingerprint_hash = _fingerprint_hash(account_fingerprint)
        if (
            not account_is_demo
            or not mandate.account_is_demo
            or not hmac.compare_digest(mandate.account_fingerprint_hash, fingerprint_hash)
            or (mode is not None and not hmac.compare_digest(mode.account_fingerprint_hash, fingerprint_hash))
        ):
            blockers.append("MANDATE_ACCOUNT_MISMATCH")
        if mandate.revoked:
            blockers.append("MANDATE_REVOKED")
        if mandate.kill_switch_engaged or current_kill_switch_engaged:
            blockers.append("KILL_SWITCH_ENGAGED")
        if not (_time(mandate.active_from) <= now < min(_time(mandate.active_until), _time(mandate.expires_at))):
            blockers.append("MANDATE_EXPIRED_OR_INACTIVE")
        if candidate.operating_mode != "autonomous_live":
            blockers.append("CANDIDATE_MODE_MISMATCH")
        required_references = (
            candidate.candidate_reference,
            candidate.provenance_hash,
            candidate.structured_order_hash,
            candidate.proposal_source_reference,
            candidate.account_context_reference,
            candidate.risk_result_reference,
            candidate.lifecycle_observation_reference,
        )
        if any(not _identifier(str(value or "")) for value in required_references):
            blockers.append("CANDIDATE_AUTHORITY_REFERENCES_INVALID")
        if _time(candidate.expires_at) <= now:
            blockers.append("CANDIDATE_EXPIRED")
        if candidate.symbol_reference not in mandate.permitted_symbols or candidate.broker_symbol_reference not in mandate.permitted_broker_symbols:
            blockers.append("MANDATE_SYMBOL_NOT_ALLOWED")
        if candidate.action not in mandate.permitted_order_families:
            blockers.append("MANDATE_ORDER_FAMILY_NOT_ALLOWED")
        if candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE" or candidate.blocked_reason_codes:
            blockers.append("CANDIDATE_NOT_ELIGIBLE")
        try:
            if Decimal(str(candidate.proposed_volume)) > Decimal(mandate.maximum_volume):
                blockers.append("MANDATE_VOLUME_LIMIT_EXCEEDED")
            if Decimal(str(evaluated_risk_per_trade)) > Decimal(mandate.maximum_risk_per_trade):
                blockers.append("MANDATE_RISK_LIMIT_EXCEEDED")
            if Decimal(str(loss_today)) >= Decimal(mandate.maximum_loss_per_day):
                blockers.append("MANDATE_DAILY_LOSS_LIMIT_EXHAUSTED")
        except InvalidOperation:
            blockers.append("MANDATE_NUMERIC_INPUT_INVALID")
        if concurrent_positions >= mandate.maximum_concurrent_positions:
            blockers.append("MANDATE_POSITION_LIMIT_EXHAUSTED")
        if trades_today >= mandate.maximum_trades_per_day:
            blockers.append("MANDATE_TRADE_LIMIT_EXHAUSTED")
        if not lifecycle_healthy:
            blockers.append("LIFECYCLE_NOT_HEALTHY")
        if not reconciliation_healthy:
            blockers.append("RECONCILIATION_NOT_HEALTHY")
        return tuple(dict.fromkeys(blockers))


def _mode_from_payload(payload: Mapping[str, Any]) -> OperatingModeAuthority:
    record = OperatingModeAuthority(**dict(payload))
    if not record.integrity_valid():
        raise TradingAuthorityError("MODE_AUTHORITY_CORRUPT")
    return record


def _mandate_from_payload(payload: Mapping[str, Any]) -> StandingTradingMandate:
    values = dict(payload)
    for name in (
        "permitted_symbols",
        "permitted_broker_symbols",
        "permitted_order_families",
        "permitted_management_actions",
    ):
        values[name] = tuple(values.get(name, ()))
    record = StandingTradingMandate(**values)
    if not record.integrity_valid():
        raise TradingAuthorityError("MANDATE_INTEGRITY_INVALID")
    return record


def _authorization_from_payload(payload: Mapping[str, Any]) -> MandateCandidateAuthorization:
    values = dict(payload)
    if values.get("authorization_source") != "STANDING_MANDATE":
        raise TradingAuthorityError("AUTHORIZATION_SOURCE_INVALID")
    values["source_refs"] = tuple(values.get("source_refs", ()))
    values["protected_order_parameters"] = dict(
        values.get("protected_order_parameters", {})
    )
    record = MandateCandidateAuthorization(**values)
    if not record.integrity_valid():
        raise TradingAuthorityError("MANDATE_AUTHORIZATION_INTEGRITY_INVALID")
    return record


def _event_id(artifact: Any) -> str:
    return str(
        getattr(artifact, "authorization_id", "")
        or getattr(artifact, "mode_record_id", "")
        or (
            f"{artifact.mandate_id}:v{artifact.mandate_version}:"
            f"{'revoked' if artifact.revoked else 'granted'}"
        )
    )


def _candidate_source_refs(candidate: Any) -> tuple[str, ...]:
    return tuple(
        value
        for value in dict.fromkeys(
            (
                candidate.candidate_reference,
                candidate.provenance_hash,
                candidate.structured_order_hash,
                candidate.proposal_source_reference,
                candidate.market_context_reference,
                candidate.market_snapshot_reference,
                candidate.market_snapshot_provenance_hash,
                candidate.account_context_reference,
                candidate.risk_result_reference,
                candidate.lifecycle_observation_reference,
                candidate.reconciliation_reference,
                *candidate.knowledge_evidence_references,
                *candidate.proposed_semantic_parameter_references,
            )
        )
        if value
    )


def _fingerprint_hash(fingerprint: str) -> str:
    value = str(fingerprint or "").strip().lower()
    if not _valid_hash(value):
        raise TradingAuthorityError("ACCOUNT_FINGERPRINT_INVALID")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identifiers(values: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(str(value).strip() for value in values))
    if not result or any(not _identifier(value) for value in result):
        raise TradingAuthorityError("MANDATE_SCOPE_INVALID")
    return result


def _allowed_values(
    values: tuple[str, ...], allowed: set[str], *, allow_empty: bool = False
) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(str(value).strip().upper() for value in values))
    if (not result and not allow_empty) or any(value not in allowed for value in result):
        raise TradingAuthorityError("MANDATE_SCOPE_INVALID")
    return result


def _identifier(value: str) -> bool:
    return bool(value and value.strip() == value and not any(ch.isspace() for ch in value))


def _positive_decimal(value: str, error: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise TradingAuthorityError(error) from exc
    if not result.is_finite() or result <= 0:
        raise TradingAuthorityError(error)
    return result


def _ordered_times(active_from: str, active_until: str, expires_at: str, now: datetime) -> bool:
    try:
        start, end, expiry = map(_time, (active_from, active_until, expires_at))
    except (TypeError, ValueError):
        return False
    return start <= now < end <= expiry


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _valid_hash(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=list).encode("utf-8")
    ).hexdigest()


def _latest_mandate_hash(mandate: StandingTradingMandate) -> str:
    return _hash(mandate.protected_payload())

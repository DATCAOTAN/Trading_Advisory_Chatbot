from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List

from tools.mt5_bridge.redaction import hash_identifier, redact_server

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover - depends on host installation
    mt5 = None


TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
    "D": "TIMEFRAME_D1",
}

MT5_OPERATION_TIMEOUT_SECONDS = float(os.getenv("MT5_OPERATION_TIMEOUT_SECONDS", "2"))


class MT5Client:
    def __init__(self):
        self._initialized = False

    def ensure_initialized(self) -> tuple[bool, str]:
        if mt5 is None:
            return False, "MetaTrader5 Python package is not available on host"
        if self._initialized:
            return True, "initialized"
        try:
            initialized = _call_mt5(mt5.initialize)
        except TimeoutError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"MT5 initialize failed: {type(exc).__name__}"
        if not initialized:
            try:
                code, message = _call_mt5(mt5.last_error, timeout_seconds=1)
            except Exception:
                code, message = "unknown", "MT5 last_error unavailable"
            return False, f"MT5 initialize failed: {code} {message}"
        self._initialized = True
        return True, "initialized"

    def health(self) -> Dict[str, Any]:
        package_available = mt5 is not None
        initialized, message = self.ensure_initialized()
        account = self.account_info() if initialized else {}
        return {
            "status": "OK" if initialized and account.get("account_id_hash") else ("DEGRADED" if initialized else "UNAVAILABLE"),
            "message": message,
            "mt5_package_available": package_available,
            "terminal_connected": initialized,
            "account_info_available": bool(account.get("account_id_hash")),
            "account": {"account_id_hash": account.get("account_id_hash", ""), "server_redacted": account.get("server_redacted", "")},
        }

    def account_info(self) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message}
        try:
            info = _call_mt5(mt5.account_info)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc)}
        if info is None:
            return {"status": "UNAVAILABLE", "message": "MT5 account info unavailable"}
        data = info._asdict()
        account_context_fingerprint = _account_context_fingerprint(data)
        return {
            "status": "OK",
            "account_id_hash": hash_identifier(data.get("login")),
            "server_redacted": redact_server(data.get("server")),
            "currency": data.get("currency"),
            "balance": data.get("balance"),
            "equity": data.get("equity"),
            "margin": data.get("margin"),
            "free_margin": data.get("margin_free"),
            "leverage": data.get("leverage"),
            "trade_mode": data.get("trade_mode"),
            "trade_allowed": bool(data.get("trade_allowed", False)),
            "account_context_fingerprint": account_context_fingerprint,
            "redacted": True,
        }

    def execution_context(self) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message, "redacted": True}
        try:
            account = _call_mt5(mt5.account_info)
            terminal = _call_mt5(mt5.terminal_info)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc), "redacted": True}
        if account is None or terminal is None:
            return {"status": "UNAVAILABLE", "message": "MT5 execution context unavailable", "redacted": True}
        account_data = account._asdict()
        terminal_data = terminal._asdict()
        return {
            "status": "OK",
            "terminal_connected": bool(terminal_data.get("connected", False)),
            "terminal_trade_allowed": bool(terminal_data.get("trade_allowed", False)),
            "account_trade_allowed": bool(account_data.get("trade_allowed", False)),
            "account_context_fingerprint": _account_context_fingerprint(account_data),
            "account_id_hash": hash_identifier(account_data.get("login")),
            "server_redacted": redact_server(account_data.get("server")),
            "currency": account_data.get("currency"),
            "trade_mode": account_data.get("trade_mode"),
            "redacted": True,
        }

    def pending_order_context(self, symbol: str) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message, "metadata_redacted": True}
        try:
            selected = _call_mt5(mt5.symbol_select, symbol, True)
            info = _call_mt5(mt5.symbol_info, symbol)
            tick = _call_mt5(mt5.symbol_info_tick, symbol)
        except Exception as exc:
            return {
                "status": "UNAVAILABLE",
                "message": type(exc).__name__,
                "metadata_redacted": True,
            }
        if not selected or info is None or tick is None:
            return {
                "status": "UNAVAILABLE",
                "message": "PENDING_SYMBOL_CONTEXT_UNAVAILABLE",
                "metadata_redacted": True,
            }
        info_data = info._asdict()
        tick_data = tick._asdict()
        order_mode = int(info_data.get("order_mode") or 0)
        supported: list[str] = []
        capabilities = (
            ("LIMIT", ("BUY_LIMIT", "SELL_LIMIT"), "SYMBOL_ORDER_LIMIT"),
            ("STOP", ("BUY_STOP", "SELL_STOP"), "SYMBOL_ORDER_STOP"),
            (
                "STOP_LIMIT",
                ("BUY_STOP_LIMIT", "SELL_STOP_LIMIT"),
                "SYMBOL_ORDER_STOP_LIMIT",
            ),
        )
        for _, order_types, flag_name in capabilities:
            flag = getattr(mt5, flag_name, None)
            if isinstance(flag, int) and order_mode & flag == flag:
                supported.extend(
                    order_type
                    for order_type in order_types
                    if hasattr(mt5, "ORDER_TYPE_" + order_type)
                )
        disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", object())
        return {
            "status": "OK",
            "symbol": symbol,
            "symbol_available": True,
            "symbol_trade_allowed": info_data.get("trade_mode") != disabled_mode,
            "bid": tick_data.get("bid"),
            "ask": tick_data.get("ask"),
            "digits": info_data.get("digits"),
            "point": info_data.get("point"),
            "tick_size": info_data.get("trade_tick_size"),
            "trade_stops_level": info_data.get("trade_stops_level"),
            "volume_min": info_data.get("volume_min"),
            "volume_max": info_data.get("volume_max"),
            "volume_step": info_data.get("volume_step"),
            "expiration_mode": info_data.get("expiration_mode"),
            "supported_pending_order_types": supported,
            "metadata_redacted": True,
        }
    def symbols(self) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message, "symbols": []}
        try:
            symbols = _call_mt5(mt5.symbols_get)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc), "symbols": []}
        names = [item.name for item in symbols or [] if getattr(item, "visible", False) or getattr(item, "select", False)]
        return {"status": "OK", "symbols": sorted(names)[:1000]}

    def tick(self, symbol: str) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message}
        try:
            _call_mt5(mt5.symbol_select, symbol, True)
            tick = _call_mt5(mt5.symbol_info_tick, symbol)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc)}
        if tick is None:
            return {"status": "UNAVAILABLE", "message": f"tick unavailable for {symbol}"}
        data = tick._asdict()
        bid = _safe_float(data.get("bid"))
        ask = _safe_float(data.get("ask"))
        return {
            "status": "OK",
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": (ask - bid) if bid is not None and ask is not None else None,
            "timestamp": _timestamp(data.get("time_msc") or data.get("time")),
            "source": "mt5_terminal",
        }

    def ohlcv(self, symbol: str, timeframe: str, count: int) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message, "bars": [], "data_quality": "EMPTY"}
        try:
            _call_mt5(mt5.symbol_select, symbol, True)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc), "bars": [], "data_quality": "EMPTY"}
        tf_name = TIMEFRAME_MAP.get(str(timeframe).upper(), "TIMEFRAME_M15")
        tf = getattr(mt5, tf_name)
        try:
            rates = _call_mt5(mt5.copy_rates_from_pos, symbol, tf, 0, max(1, int(count or 1)))
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc), "bars": [], "data_quality": "EMPTY"}
        if rates is None or len(rates) == 0:
            return {"status": "OK", "symbol": symbol, "timeframe": timeframe, "bars": [], "data_quality": "EMPTY", "source": "mt5_terminal"}
        bars: List[Dict[str, Any]] = []
        for row in rates:
            bars.append(
                {
                    "timestamp": _timestamp(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["tick_volume"]),
                    "timeframe": timeframe,
                    "symbol": symbol,
                    "source": "mt5_terminal",
                }
            )
        tick = self.tick(symbol)
        return {
            "status": "OK",
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "latest_bid": tick.get("bid"),
            "latest_ask": tick.get("ask"),
            "spread": tick.get("spread"),
            "source": "mt5_terminal",
            "data_quality": "COMPLETE" if len(bars) >= min(count, 2) else "PARTIAL",
        }

    def positions(self, symbol: str | None = None) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "message": message, "positions": []}
        try:
            rows = _call_mt5(mt5.positions_get, symbol=symbol) if symbol else _call_mt5(mt5.positions_get)
        except TimeoutError as exc:
            return {"status": "UNAVAILABLE", "message": str(exc), "positions": []}
        positions = []
        for item in rows or []:
            data = item._asdict()
            positions.append(
                {
                    "position_id_hash": hash_identifier(data.get("ticket")),
                    "symbol": data.get("symbol"),
                    "side": "LONG" if data.get("type") == 0 else "SHORT",
                    "volume": data.get("volume"),
                    "open_time": _timestamp(data.get("time")),
                    "open_price": data.get("price_open"),
                    "current_price": data.get("price_current"),
                    "pnl": data.get("profit"),
                    "source": "mt5_terminal",
                    "redacted": True,
                }
            )
        return {"status": "OK", "positions": positions}

    def reconciliation_evidence(self, start: datetime, end: datetime) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "QUERY_FAILED", "message": message, "orders": [], "deals": [], "positions": []}
        try:
            active_orders = _call_mt5(mt5.orders_get)
            historical_orders = _call_mt5(mt5.history_orders_get, start, end)
            deals = _call_mt5(mt5.history_deals_get, start, end)
            positions = _call_mt5(mt5.positions_get)
            if (
                active_orders is None
                or historical_orders is None
                or deals is None
                or positions is None
            ):
                return {
                    "status": "QUERY_FAILED",
                    "message": "MT5_QUERY_RETURNED_NONE",
                    "orders": [],
                    "deals": [],
                    "positions": [],
                }
        except Exception as exc:
            return {
                "status": "QUERY_FAILED",
                "message": type(exc).__name__,
                "orders": [],
                "deals": [],
                "positions": [],
            }
        return {
            "status": "OK",
            "orders": [
                _normalize_reconciliation_row(item, "order")
                for item in [*(active_orders or []), *(historical_orders or [])]
            ],
            "deals": [_normalize_reconciliation_row(item, "deal") for item in deals or []],
            "positions": [_normalize_reconciliation_row(item, "position") for item in positions or []],
        }

    def lifecycle_snapshot(
        self, start: datetime, end: datetime, correlation_tags: List[str] | None = None
    ) -> Dict[str, Any]:
        context = self.execution_context()
        if context.get("status") != "OK" or context.get("terminal_connected") is not True:
            return _unavailable_lifecycle_snapshot("MT5_CONTEXT_UNAVAILABLE")
        try:
            active_orders = _call_mt5(mt5.orders_get)
            recent_orders = _call_mt5(mt5.history_orders_get, start, end)
            recent_deals = _call_mt5(mt5.history_deals_get, start, end)
            positions = _call_mt5(mt5.positions_get)
            if any(rows is None for rows in (active_orders, recent_orders, recent_deals, positions)):
                return _unavailable_lifecycle_snapshot("MT5_QUERY_RETURNED_NONE")
        except Exception as exc:
            return _unavailable_lifecycle_snapshot(type(exc).__name__)
        tags = tuple(dict.fromkeys(str(tag) for tag in correlation_tags or [] if tag))
        snapshot = {
            "status": "OK",
            "terminal_connected": True,
            "terminal_trade_allowed": context.get("terminal_trade_allowed") is True,
            "account_trade_allowed": context.get("account_trade_allowed") is True,
            "account_context_fingerprint": context.get("account_context_fingerprint", ""),
            "active_orders": [_normalize_lifecycle_row(item, "order", tags) for item in active_orders or []],
            "recent_orders": [_normalize_lifecycle_row(item, "order", tags) for item in recent_orders or []],
            "recent_deals": [_normalize_lifecycle_row(item, "deal", tags) for item in recent_deals or []],
            "positions": [_normalize_lifecycle_row(item, "position", tags) for item in positions or []],
            "metadata_redacted": True,
        }
        stable = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        snapshot["snapshot_reference"] = "mt5_lifecycle_snapshot_" + hash_identifier(stable)[:24]
        return snapshot

    def resolve_management_target(
        self, target_kind: str, protected_reference: str, symbol: str
    ) -> Dict[str, Any]:
        ok, message = self.ensure_initialized()
        if not ok:
            return {"status": "UNAVAILABLE", "reason": message, "match_count": 0}
        if target_kind not in {"order", "position"}:
            return {"status": "INVALID", "reason": "TARGET_KIND_INVALID", "match_count": 0}
        try:
            rows = _call_mt5(mt5.orders_get) if target_kind == "order" else _call_mt5(mt5.positions_get)
            if rows is None:
                return {"status": "UNAVAILABLE", "reason": "MT5_QUERY_RETURNED_NONE", "match_count": 0}
            matches = [
                item
                for item in rows
                if str(item._asdict().get("symbol", "")) == symbol
                and hash_identifier(item._asdict().get("ticket")) == protected_reference
            ]
            if len(matches) != 1:
                return {"status": "NOT_UNIQUE", "match_count": len(matches)}
            data = matches[0]._asdict()
            type_names = (
                ("ORDER_TYPE_BUY", "ORDER_TYPE_SELL")
                if target_kind == "order"
                else ("POSITION_TYPE_BUY", "POSITION_TYPE_SELL")
            )
            if data.get("type") == getattr(mt5, type_names[0], object()):
                direction = "BUY"
            elif data.get("type") == getattr(mt5, type_names[1], object()):
                direction = "SELL"
            else:
                direction = "UNKNOWN"
            tick = _call_mt5(mt5.symbol_info_tick, symbol) if target_kind == "position" else None
            info = _call_mt5(mt5.symbol_info, symbol) if target_kind == "position" else None
            tick_data = tick._asdict() if tick is not None else {}
            info_data = info._asdict() if info is not None else {}
            point = Decimal(str(info_data.get("point") or "0"))
            stops = Decimal(str(info_data.get("trade_stops_level") or "0"))
            volume = data.get("volume_initial") if target_kind == "order" else data.get("volume")
            return {
                "status": "OK",
                "match_count": 1,
                "target_kind": target_kind,
                "ticket": data.get("ticket"),
                "broker_reference_hash": hash_identifier(data.get("ticket")),
                "symbol": symbol,
                "direction": direction,
                "volume": volume,
                "stop_loss": data.get("sl") or 0,
                "take_profit": data.get("tp") or 0,
                "bid": tick_data.get("bid"),
                "ask": tick_data.get("ask"),
                "minimum_stop_distance": str(point * stops),
                "volume_min": info_data.get("volume_min") or 0,
                "volume_step": info_data.get("volume_step") or 0,
            }
        except Exception as exc:
            return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "match_count": 0}

    def close(self) -> None:
        if mt5 is not None and self._initialized:
            try:
                _call_mt5(mt5.shutdown, timeout_seconds=1)
            except Exception:
                pass
        self._initialized = False


def _call_mt5(operation: Callable[..., Any], *args: Any, timeout_seconds: float | None = None, **kwargs: Any) -> Any:
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, operation(*args, **kwargs)))
        except Exception as exc:  # pragma: no cover - depends on host terminal state
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds if timeout_seconds is not None else MT5_OPERATION_TIMEOUT_SECONDS)
    if thread.is_alive():
        name = getattr(operation, "__name__", "operation")
        raise TimeoutError(f"MT5 {name} timed out")
    ok, value = result_queue.get_nowait()
    if ok:
        return value
    raise value


def _timestamp(value: Any) -> str:
    try:
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_reconciliation_row(item: Any, kind: str) -> Dict[str, Any]:
    data = item._asdict()
    type_value = data.get("type")
    buy_names = {
        "order": (
            "ORDER_TYPE_BUY", "ORDER_TYPE_BUY_LIMIT", "ORDER_TYPE_BUY_STOP",
            "ORDER_TYPE_BUY_STOP_LIMIT",
        ),
        "deal": ("DEAL_TYPE_BUY",),
        "position": ("POSITION_TYPE_BUY",),
    }
    sell_names = {
        "order": (
            "ORDER_TYPE_SELL", "ORDER_TYPE_SELL_LIMIT", "ORDER_TYPE_SELL_STOP",
            "ORDER_TYPE_SELL_STOP_LIMIT",
        ),
        "deal": ("DEAL_TYPE_SELL",),
        "position": ("POSITION_TYPE_SELL",),
    }
    buy_values = {getattr(mt5, name, object()) for name in buy_names[kind]}
    sell_values = {getattr(mt5, name, object()) for name in sell_names[kind]}
    if type_value in buy_values:
        direction = "BUY"
    elif type_value in sell_values:
        direction = "SELL"
    else:
        direction = "UNKNOWN"
    volume = (
        data.get("volume_initial")
        if kind == "order"
        else data.get("volume")
    )
    return {
        "ticket": data.get("ticket"),
        "order": data.get("order"),
        "position_id": data.get("position_id") or data.get("position"),
        "symbol": data.get("symbol"),
        "direction": direction,
        "volume": volume,
        "time": _timestamp(data.get("time_msc") or data.get("time_setup_msc") or data.get("time")),
        "comment": str(data.get("comment", ""))[:64],
        "order_status": _order_status(data.get("state")) if kind == "order" else "",
    }


def _order_status(value: Any) -> str:
    mappings = {
        "ACTIVE": (
            "ORDER_STATE_STARTED", "ORDER_STATE_PLACED", "ORDER_STATE_PARTIAL",
            "ORDER_STATE_REQUEST_ADD", "ORDER_STATE_REQUEST_MODIFY",
        ),
        "FILLED": ("ORDER_STATE_FILLED",),
        "CANCELLED": ("ORDER_STATE_CANCELED",),
        "REJECTED": ("ORDER_STATE_REJECTED",),
        "EXPIRED": ("ORDER_STATE_EXPIRED",),
    }
    for status, names in mappings.items():
        if value in {getattr(mt5, name, object()) for name in names}:
            return status
    return "UNKNOWN"

def _normalize_lifecycle_row(item: Any, kind: str, correlation_tags: tuple[str, ...]) -> Dict[str, Any]:
    row = _normalize_reconciliation_row(item, kind)
    comment = str(row.pop("comment", ""))
    ticket = row.pop("ticket", None)
    order = row.pop("order", None)
    position = row.pop("position_id", None)
    data = item._asdict()
    entry_value = data.get("entry")
    entry = "UNKNOWN"
    if kind == "deal":
        if entry_value == getattr(mt5, "DEAL_ENTRY_IN", object()):
            entry = "IN"
        elif entry_value in {
            getattr(mt5, "DEAL_ENTRY_OUT", object()),
            getattr(mt5, "DEAL_ENTRY_OUT_BY", object()),
        }:
            entry = "OUT"
        elif entry_value == getattr(mt5, "DEAL_ENTRY_INOUT", object()):
            entry = "INOUT"
    normalized = {
        **row,
        "broker_reference_hash": hash_identifier(ticket) if ticket is not None else "",
        "order_reference_hash": hash_identifier(order) if order is not None else "",
        "position_reference_hash": hash_identifier(position) if position is not None else "",
        "entry": entry,
        "matched_correlation_tags": [tag for tag in correlation_tags if tag in comment],
        "metadata_redacted": True,
    }
    if kind == "position":
        normalized["protection_reference_hash"] = protection_reference_hash(
            str(data.get("symbol", "")), data.get("sl") or 0, data.get("tp") or 0
        )
    return normalized


def protection_reference_hash(symbol: str, stop_loss: Any, take_profit: Any) -> str:
    payload = {
        "symbol": str(symbol),
        "stop_loss": _normalized_number(stop_loss),
        "take_profit": _normalized_number(take_profit),
    }
    return hash_identifier(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _normalized_number(value: Any) -> str:
    number = Decimal(str(value))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _unavailable_lifecycle_snapshot(reason: str) -> Dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "reason": reason,
        "terminal_connected": False,
        "terminal_trade_allowed": False,
        "account_trade_allowed": False,
        "account_context_fingerprint": "",
        "active_orders": [],
        "recent_orders": [],
        "recent_deals": [],
        "positions": [],
        "snapshot_reference": "",
        "metadata_redacted": True,
    }

def _account_context_fingerprint(account_data: Dict[str, Any]) -> str:
    stable_context = {
        "login": account_data.get("login"),
        "server": account_data.get("server"),
        "currency": account_data.get("currency"),
        "trade_mode": account_data.get("trade_mode"),
    }
    return hash_identifier(json.dumps(stable_context, ensure_ascii=True, sort_keys=True, separators=(",", ":")))

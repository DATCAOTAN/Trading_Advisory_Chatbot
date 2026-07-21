from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
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


def _account_context_fingerprint(account_data: Dict[str, Any]) -> str:
    stable_context = {
        "login": account_data.get("login"),
        "server": account_data.get("server"),
        "currency": account_data.get("currency"),
        "trade_mode": account_data.get("trade_mode"),
    }
    return hash_identifier(json.dumps(stable_context, ensure_ascii=True, sort_keys=True, separators=(",", ":")))

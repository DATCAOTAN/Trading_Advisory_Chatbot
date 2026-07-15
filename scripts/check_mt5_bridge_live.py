from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.config import Config


_configured_bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or os.getenv("MT5_BRIDGE_URL", "http://127.0.0.1:8765")
if "host.docker.internal" in _configured_bridge_url:
    _configured_bridge_url = "http://127.0.0.1:8765"
BRIDGE_URL = _configured_bridge_url.rstrip("/")
TIMEOUT = float(os.getenv("MT5_BRIDGE_TIMEOUT_SECONDS", "3"))
LOGICAL_SYMBOL = os.getenv("MT5_CHECK_SYMBOL", "XAUUSD").upper()
BROKER_SYMBOL = os.getenv(
    f"MT5_SYMBOL_MAP_{LOGICAL_SYMBOL}",
    str(getattr(Config, f"MT5_SYMBOL_MAP_{LOGICAL_SYMBOL}", LOGICAL_SYMBOL) or LOGICAL_SYMBOL),
)


def get_json(path: str, params: dict | None = None):
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    req = urllib.request.Request(f"{BRIDGE_URL}{path}{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def main() -> int:
    try:
        health = get_json("/health")
    except Exception as exc:
        print(f"MT5 bridge unavailable at {BRIDGE_URL}: {type(exc).__name__}")
        return 2

    print(f"health={health.get('status')} message={health.get('message', '')}")
    account = get_json("/account")
    print(
        "account="
        f"hash={str(account.get('account_id_hash') or '')[:12]} "
        f"server={account.get('server_redacted') or 'n/a'} "
        f"currency={account.get('currency') or 'n/a'} "
        f"balance_available={account.get('balance') is not None}"
    )
    tick = get_json("/tick", {"symbol": BROKER_SYMBOL})
    print(
        "tick="
        f"logical_symbol={LOGICAL_SYMBOL} broker_symbol={BROKER_SYMBOL} "
        f"symbol={tick.get('symbol')} bid={tick.get('bid')} ask={tick.get('ask')} "
        f"spread={tick.get('spread')} timestamp={tick.get('timestamp')}"
    )
    ohlcv = get_json("/ohlcv", {"symbol": BROKER_SYMBOL, "timeframe": "M15", "count": "10"})
    bars = ohlcv.get("bars") or []
    latest = bars[-1].get("timestamp") if bars else "n/a"
    print(
        "ohlcv="
        f"symbol={ohlcv.get('symbol')} timeframe={ohlcv.get('timeframe')} "
        f"bars={len(bars)} latest={latest} quality={ohlcv.get('data_quality')}"
    )
    if health.get("status") not in {"OK", "DEGRADED"} or not bars:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

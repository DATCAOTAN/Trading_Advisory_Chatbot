"""Read-only MT5 history export. Never imports the execution service."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.research.historical_dataset import (
    BAR_FIELDS, TICK_FIELDS, HistoricalDataRequest, merge_chunks, persist_dataset, utc,
)
from tools.mt5_bridge.mt5_client import MT5Client, _call_mt5, mt5


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOT = PROJECT_ROOT / "data/research/mt5"
CONTRACT_FIELDS = (
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size",
    "volume_min", "volume_max", "volume_step", "currency_profit", "currency_margin",
    "trade_stops_level", "trade_mode",
)


def _native_rows(values: Any, fields: tuple[str, ...]) -> list[dict]:
    rows = []
    for item in values:
        row = {}
        for key in fields:
            value = item[key]
            row[key] = value.item() if hasattr(value, "item") else value
        rows.append(row)
    return rows


def export_history(request: HistoricalDataRequest, *, root: Path = RESEARCH_ROOT) -> tuple[Path, dict]:
    if mt5 is None:
        raise ValueError("MT5_HOST_PACKAGE_UNAVAILABLE")
    if broker_symbol_for(request.canonical_symbol) != request.broker_symbol:
        raise ValueError("BROKER_SYMBOL_MAPPING_MISMATCH")
    if utc(request.end) > datetime.now(timezone.utc):
        raise ValueError("REQUEST_INCLUDES_UNCOMPLETED_HISTORY")
    client = MT5Client()
    initialized, _ = client.ensure_initialized()
    if not initialized:
        raise ValueError("MT5_INITIALIZATION_UNAVAILABLE")
    account = client.account_info()
    terminal = _call_mt5(mt5.terminal_info)
    if terminal is None or not terminal.connected:
        raise ValueError("MT5_TERMINAL_DISCONNECTED")
    if account.get("status") != "OK" or account.get("account_environment") != "DEMO":
        raise ValueError("DEMO_ACCOUNT_REQUIRED")
    info = _call_mt5(mt5.symbol_info, request.broker_symbol)
    if info is None or info.name != request.broker_symbol:
        raise ValueError("BROKER_SYMBOL_UNAVAILABLE")
    contract = {key: getattr(info, key, None) for key in CONTRACT_FIELDS}
    for key in ("point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min", "volume_max", "volume_step"):
        if not isinstance(contract[key], (int, float)) or not 0 < float(contract[key]) < float("inf"):
            raise ValueError("BROKER_CONTRACT_METADATA_UNAVAILABLE")
    if contract["volume_min"] > contract["volume_max"]:
        raise ValueError("BROKER_VOLUME_RANGE_INVALID")
    chunks = []
    failures = []
    cursor, end = utc(request.start), utc(request.end)
    fields = BAR_FIELDS if request.kind == "bars" else TICK_FIELDS
    while cursor < end:
        stop = min(end, cursor + timedelta(days=7))
        if request.kind == "bars":
            timeframe = getattr(mt5, "TIMEFRAME_" + request.timeframe)
            values = _call_mt5(
                mt5.copy_rates_range, request.broker_symbol, timeframe, cursor, stop,
                timeout_seconds=30,
            )
        else:
            values = _call_mt5(
                mt5.copy_ticks_range, request.broker_symbol, cursor, stop, mt5.COPY_TICKS_ALL,
                timeout_seconds=30,
            )
        if values is None:
            failures.append({"start": cursor.isoformat(), "end": stop.isoformat(), "reason": "MT5_HISTORY_READ_UNAVAILABLE"})
            chunks.append([])
        else:
            if len(values) > 1_000_000:
                raise ValueError("HISTORICAL_CHUNK_TOO_LARGE")
            chunks.append(_native_rows(values, fields))
        cursor = stop
    merged, overlap_rows = merge_chunks(chunks, request.kind)
    timestamp_key = "time" if request.kind == "bars" else "time_msc"
    scale = 1 if request.kind == "bars" else 1000
    merged = [r for r in merged if utc(request.start).timestamp() * scale <= r[timestamp_key] < end.timestamp() * scale]
    current = client.account_info()
    if (
        current.get("account_environment") != "DEMO"
        or not account.get("account_context_fingerprint")
        or current.get("account_context_fingerprint") != account["account_context_fingerprint"]
    ):
        raise ValueError("ACCOUNT_CHANGED_DURING_EXPORT")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    source = Path(__file__).read_bytes() + (
        PROJECT_ROOT / "src/services/trading/research/historical_dataset.py"
    ).read_bytes()
    return persist_dataset(
        root, request, merged, contract=contract,
        acquired_at=datetime.now(timezone.utc).isoformat(), overlap_rows=overlap_rows,
        source_revision=revision, exporter_source_checksum=hashlib.sha256(source).hexdigest(),
        acquisition_failures=failures,
        terminal_history_bar_limit=getattr(terminal, "maxbars", None),
        mt5_package_version=str(getattr(mt5, "__version__", "UNKNOWN")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--broker-symbol", required=True)
    parser.add_argument("--start", required=True, help="Inclusive timezone-aware UTC boundary")
    parser.add_argument("--end", required=True, help="Exclusive timezone-aware UTC boundary")
    parser.add_argument("--timeframe", choices=("M1", "M15", "H1", "H4"), default="M1")
    parser.add_argument("--kind", choices=("bars", "ticks"), default="bars")
    parser.add_argument("--warmup-records", type=int, default=35)
    parser.add_argument("--session-policy", choices=("UTC_WEEKDAYS_CONSERVATIVE_V1", "CONTINUOUS_UTC_V1"), default="UTC_WEEKDAYS_CONSERVATIVE_V1")
    args = parser.parse_args(argv)
    try:
        request = HistoricalDataRequest(
            args.symbol, args.broker_symbol, args.timeframe, args.start, args.end,
            args.kind, args.warmup_records, args.session_policy,
        )
        folder, manifest = export_history(request)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"status": "EXPORT_BLOCKED", "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}))
        return 2
    print(json.dumps({
        "dataset_id": manifest["dataset_id"], "path": str(folder),
        "status": manifest["quality"]["status"], "records": manifest["record_count"],
        "first": manifest["quality"]["first_timestamp"], "last": manifest["quality"]["last_timestamp"],
        "missing_bars": manifest["quality"]["missing_expected_bars"],
        "chunk_overlap_rows_removed": manifest["chunk_overlap_rows_removed"],
    }))
    return 0 if manifest["quality"]["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

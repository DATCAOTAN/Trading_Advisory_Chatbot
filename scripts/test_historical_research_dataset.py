from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.trading.market.indicators import IndicatorEngine
from src.services.trading.research.historical_dataset import (
    BAR_FIELDS, HistoricalDataRequest, as_market_snapshot, assess_quality,
    canonical_bytes, checksum, load_dataset, merge_chunks, persist_dataset, utc,
)
from tools.mt5_bridge import export_research_history as exporter


# Synthetic fixtures test software contracts only, never historical performance.
START = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
REQUEST = HistoricalDataRequest("XAUUSD", "XAUUSDm", "M1", START.isoformat(), (START + timedelta(hours=1)).isoformat())
ACQUIRED = (START + timedelta(days=1)).isoformat()
CONTRACT = {
    "digits": 3, "point": 0.001, "trade_tick_size": 0.001, "trade_tick_value": 0.1,
    "trade_contract_size": 100.0, "volume_min": 0.01, "volume_max": 200.0,
    "volume_step": 0.01, "currency_profit": "USD", "currency_margin": "USD",
    "trade_stops_level": 0, "trade_mode": 4,
}


def bars(count=60, start=START):
    return [{
        "time": int((start + timedelta(minutes=i)).timestamp()),
        "open": 4000.1234567890123, "high": 4002.0, "low": 3999.0,
        "close": 4001.0, "tick_volume": 25, "spread": 110, "real_volume": 0,
    } for i in range(count)]


def save(tmp_path, rows=None, request=REQUEST, **kwargs):
    return persist_dataset(tmp_path, request, bars() if rows is None else rows, contract=CONTRACT, acquired_at=ACQUIRED, **kwargs)


@pytest.mark.parametrize("value", ("2026-11-02", "2026-11-02T10:00:00", datetime(2026, 11, 2), None))
def test_request_rejects_naive_or_missing_utc(value):
    with pytest.raises((ValueError, TypeError)):
        utc(value)


def test_offset_is_normalized_without_changing_instant():
    assert utc("2026-11-02T17:00:00+07:00") == START
    assert replace(REQUEST, start="2026-11-02T17:00:00+07:00").start == REQUEST.start


@pytest.mark.parametrize("changes", (
    {"timeframe": "M2"}, {"kind": "made-up"}, {"canonical_symbol": " "},
    {"warmup_records": 0}, {"warmup_records": True}, {"end": REQUEST.start},
    {"start": (START + timedelta(seconds=1)).isoformat()},
    {"kind": "ticks", "end": (START + timedelta(days=1)).isoformat()},
))
def test_unsupported_requests_fail_closed(changes):
    with pytest.raises(ValueError):
        replace(REQUEST, **changes)


@pytest.mark.parametrize("mutation,reason", (
    ("duplicate", "DUPLICATE_OR_NON_MONOTONIC_TIMESTAMP"),
    ("reverse", "DUPLICATE_OR_NON_MONOTONIC_TIMESTAMP"),
    ("high", "OHLC_RANGE_INVALID"), ("zero", "INVALID_PRICE"),
    ("nan", "INVALID_PRICE"), ("spread", "INVALID_SPREAD_OR_VOLUME"),
    ("time", "MALFORMED_TIMESTAMP"), ("outside", "TIMESTAMP_OUTSIDE_REQUEST"),
    ("missing", "FIELD_SCHEMA_MISMATCH"),
))
def test_malformed_data_is_invalid_not_primary(mutation, reason):
    rows = bars()
    if mutation == "duplicate": rows[1] = dict(rows[0])
    elif mutation == "reverse": rows.reverse()
    elif mutation == "high": rows[0]["high"] = 3990
    elif mutation == "zero": rows[0]["open"] = 0
    elif mutation == "nan": rows[0]["close"] = float("nan")
    elif mutation == "spread": rows[0]["spread"] = -1
    elif mutation == "time": rows[0]["time"] = "not-a-time"
    elif mutation == "outside": rows[0]["time"] -= 60
    else: rows[0].pop("real_volume")
    result = assess_quality(rows, REQUEST)
    assert result["status"] == "INVALID" and reason in result["issues"]


def test_chunk_overlap_is_explicit_deduplicated_and_conflicts_rejected():
    rows = bars()
    merged, overlap = merge_chunks([rows[:31], rows[30:]], "bars")
    assert merged == rows and overlap == 1
    with pytest.raises(ValueError, match="CONFLICTING_CHUNK_OVERLAP"):
        merge_chunks([rows[:31], [dict(rows[30], spread=999), *rows[31:]]], "bars")
    with pytest.raises(ValueError, match="DUPLICATE_TIMESTAMP_WITHIN_CHUNK"):
        merge_chunks([[rows[0], rows[0]]], "bars")
    with pytest.raises(ValueError, match="NON_MONOTONIC_CHUNK"):
        merge_chunks([rows[::-1]], "bars")


@pytest.mark.parametrize("rows,status", (([], "INSUFFICIENT_HISTORY"), (bars(34), "INSUFFICIENT_HISTORY"), (bars()[1:], "PARTIAL")))
def test_missing_truncated_or_warmup_history_cannot_enter_primary(tmp_path, rows, status):
    folder, manifest = save(tmp_path, rows)
    assert manifest["quality"]["status"] == status
    assert load_dataset(folder, require_verified=False)[1] == rows
    with pytest.raises(ValueError, match="REQUIRES_VERIFIED"):
        load_dataset(folder)


def test_weekend_closure_is_separate_from_weekday_gaps():
    friday = datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc)
    monday = datetime(2026, 11, 2, tzinfo=timezone.utc)
    request = replace(REQUEST, start=friday.isoformat(), end=(monday + timedelta(minutes=1)).isoformat(), warmup_records=2)
    rows = [bars(1, friday)[0], bars(1, monday)[0]]
    quality = assess_quality(rows, request)
    assert quality["status"] == "VERIFIED"
    assert quality["declared_closed_bar_slots"] == 2880
    assert quality["missing_expected_bars"] == 0
    assert assess_quality(rows, replace(request, session_policy="CONTINUOUS_UTC_V1"))["status"] == "PARTIAL"
    gap = assess_quality(bars()[:30] + bars()[31:], REQUEST)
    assert gap["status"] == "PARTIAL" and gap["missing_expected_bars"] == 1


def test_manifest_precision_checksum_reuse_and_indicator_adapter(tmp_path):
    folder, manifest = save(tmp_path)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    same, reused = save(tmp_path)
    assert same == folder and reused == manifest
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
    loaded, rows = load_dataset(folder)
    assert rows[0]["open"] == bars()[0]["open"]
    assert checksum((folder / "data.jsonl").read_bytes()) == loaded["data_checksum"]
    snapshot = as_market_snapshot(folder)
    assert IndicatorEngine().compute(snapshot).atr is not None
    assert "UNKNOWN_CURRENT_SNAPSHOT_ONLY" == loaded["contract_metadata_historical_validity"]
    assert loaded["execution_authority"] is False
    assert not any(k in str(loaded) for k in ("account_fingerprint", "account_login", "password", "ticket", "deal_id"))


def test_tampered_dataset_or_manifest_is_rejected(tmp_path):
    folder, _ = save(tmp_path)
    (folder / "data.jsonl").write_bytes((folder / "data.jsonl").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        load_dataset(folder)
    folder, _ = save(tmp_path / "other")
    manifest = json.loads((folder / "manifest.json").read_bytes())
    manifest["record_count"] = 999
    (folder / "manifest.json").write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError, match="MANIFEST_INTEGRITY_INVALID"):
        load_dataset(folder)


@pytest.mark.parametrize("bid,ask,expected", ((10, 11, "PARTIAL"), (12, 11, "INVALID"), (0, 11, "INVALID")))
def test_ticks_validate_bid_ask_without_claiming_complete_history(bid, ask, expected):
    request = replace(REQUEST, kind="ticks", warmup_records=1)
    row = {"time": int(START.timestamp()), "time_msc": int(START.timestamp()*1000), "bid": bid, "ask": ask, "last": 0, "flags": 2}
    assert assess_quality([row], request)["status"] == expected


def fake_host(monkeypatch, *, environment="DEMO", source=None):
    calls = []
    info = SimpleNamespace(name="XAUUSDm", **CONTRACT)
    native = SimpleNamespace(
        TIMEFRAME_M1=1, COPY_TICKS_ALL=0, __version__="fixture",
        terminal_info=lambda: SimpleNamespace(connected=True, maxbars=100000),
        symbol_info=lambda symbol: info,
    )
    def copy_rates_range(symbol, timeframe, start, end):
        calls.append((symbol, timeframe, start, end))
        assert start.tzinfo is not None and end.tzinfo is not None
        return bars() if source is None else source
    native.copy_rates_range = copy_rates_range
    client = SimpleNamespace(
        ensure_initialized=lambda: (True, "fixture"),
        account_info=lambda: {"status": "OK", "account_environment": environment, "account_context_fingerprint": "a" * 64},
    )
    monkeypatch.setattr(exporter, "mt5", native)
    monkeypatch.setattr(exporter, "MT5Client", lambda: client)
    monkeypatch.setattr(exporter, "_call_mt5", lambda op, *a, timeout_seconds=None, **k: op(*a, **k))
    return calls, native, client


def test_host_export_parses_native_history_without_broker_mutation(tmp_path, monkeypatch):
    calls, native, _ = fake_host(monkeypatch)
    folder, manifest = exporter.export_history(REQUEST, root=tmp_path)
    assert len(calls) == 1 and calls[0][0] == "XAUUSDm"
    assert load_dataset(folder)[0] == manifest
    assert manifest["quality"]["field_coverage"] == {k:60 for k in BAR_FIELDS}
    assert manifest["terminal_history_bar_limit"] == 100000
    assert len(manifest["source_revision"]) == 40
    assert set(vars(native)) == {"TIMEFRAME_M1", "COPY_TICKS_ALL", "__version__", "terminal_info", "symbol_info", "copy_rates_range"}


@pytest.mark.parametrize("environment", ("REAL", "UNKNOWN"))
def test_non_demo_export_stops_before_history(tmp_path, monkeypatch, environment):
    calls, _, _ = fake_host(monkeypatch, environment=environment)
    with pytest.raises(ValueError, match="DEMO_ACCOUNT_REQUIRED"):
        exporter.export_history(REQUEST, root=tmp_path)
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_failed_history_is_persisted_as_insufficient_not_fabricated(tmp_path, monkeypatch):
    calls, native, _ = fake_host(monkeypatch)
    native.copy_rates_range = lambda *a: None
    folder, manifest = exporter.export_history(REQUEST, root=tmp_path)
    assert manifest["record_count"] == 0
    assert manifest["quality"]["status"] == "INSUFFICIENT_HISTORY"
    assert manifest["acquisition_failures"][0]["reason"] == "MT5_HISTORY_READ_UNAVAILABLE"
    with pytest.raises(ValueError, match="REQUIRES_VERIFIED"):
        load_dataset(folder)


def test_changed_account_discards_export_before_persistence(tmp_path, monkeypatch):
    _, _, client = fake_host(monkeypatch)
    responses = iter([
        {"status":"OK", "account_environment":"DEMO", "account_context_fingerprint":"a" * 64},
        {"status":"OK", "account_environment":"DEMO", "account_context_fingerprint":"b" * 64},
    ])
    client.account_info = lambda: next(responses)
    with pytest.raises(ValueError, match="ACCOUNT_CHANGED_DURING_EXPORT"):
        exporter.export_history(REQUEST, root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_research_boundary_has_no_authority_execution_or_llm_imports():
    paths = [Path(exporter.__file__), *Path("src/services/trading/research").glob("*.py")]
    for path in paths:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(part in (node.module or "") for part in ("execution", "authority", "candidate", "llm"))
                if str(path).startswith("src"):
                    assert node.module != "MetaTrader5"
            if isinstance(node, ast.Import):
                assert all(alias.name != "MetaTrader5" for alias in node.names)
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"order_send", "order_check", "symbol_select", "login"}


def test_research_exports_are_excluded_from_git_and_docker():
    for path in (".gitignore", ".dockerignore"):
        assert "data/research/" in Path(path).read_text(encoding="utf-8").splitlines()


def test_numpy_native_rows_keep_source_precision_and_integer_timestamps():
    import numpy as np

    native = np.array(
        [tuple(bars(1)[0][k] for k in BAR_FIELDS)],
        dtype=[(k, "i8" if k in {"time", "tick_volume", "spread", "real_volume"} else "f8") for k in BAR_FIELDS],
    )
    parsed = exporter._native_rows(native, BAR_FIELDS)
    assert parsed == bars(1)
    assert type(parsed[0]["time"]) is int
    assert parsed[0]["open"] == bars(1)[0]["open"]


def test_incomplete_existing_export_is_not_overwritten(tmp_path):
    folder, _ = save(tmp_path)
    (folder / "manifest.json").rename(folder / "interrupted-manifest.json")
    original = (folder / "data.jsonl").read_bytes()
    with pytest.raises(FileNotFoundError):
        save(tmp_path)
    assert (folder / "data.jsonl").read_bytes() == original
    assert not (folder / "manifest.json").exists()


def test_contract_private_fields_and_uncompleted_requests_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="UNSAFE_CONTRACT_METADATA_FIELDS"):
        persist_dataset(tmp_path, REQUEST, bars(), contract={**CONTRACT, "login": "private"}, acquired_at=ACQUIRED)
    with pytest.raises(ValueError, match="UNCOMPLETED_HISTORY"):
        persist_dataset(tmp_path, REQUEST, bars(), contract=CONTRACT, acquired_at=REQUEST.start)
    assert list(tmp_path.iterdir()) == []

"""Offline contract tests; all native-looking rows here are software fixtures."""
import copy
from decimal import Decimal

import pytest

from scripts.test_goal_research_workflow import app
from scripts.test_historical_signals import evaluate, ready, signal_page
from src.config import Config
from src.services.trading.research.historical_dataset import canonical_bytes, checksum, utc
from src.services.trading.research.input_package import _publish
from src.services.trading.research.native_backtest import inspect_native_backtest


RAW_FIXTURE = b"Fixture only; not a native report."


@pytest.fixture
def research(app, tmp_path, monkeypatch):
    subject, db, _ = ready(app, tmp_path, monkeypatch)
    signals = evaluate(subject, approved=True)
    proposal = subject.inspect_goal_research("A")["proposal"]
    root = Config.DATA_DIR / "research"
    result = {
        "schema_version": "r1-native-tester-result/v1", "kind": "MT5_TESTER_SIMULATION",
        "execution_allowed": False, "signal_sha256": signals["result_sha256"],
        "strategy_sha256": "a" * 64, "native_report_sha256": checksum(RAW_FIXTURE), "tester_binary_sha256": "c" * 64,
        "fill_model": "EVERY_TICK_REAL_TICKS", "equity_sampling": "NATIVE_TICK", "optimization": False,
        "tester_build": 5000, "currency": "USD", "partitions": {},
    }
    signal = signals["result"]
    start, split, end = (int(utc(signal["evaluation_window"][key]).timestamp()) for key in ("start", "split", "end"))
    for part, first, last, gross, net in (("IS", start, split, "12", "10"), ("OOS", split, end, "-6", "-8")):
        rows = [{key: row[key] for key in ("signal_time", "rule", "action", "triggered")} for row in signal["partitions"][part]]
        at = rows[0]["signal_time"]
        leg = {"price": "4000", "volume": "0.01", "spread_points": "5", "slippage_points": "0"}
        trade = {"position": "P1", "side": "BUY", "entry_rule": rows[0]["rule"], "entry_signal_time": at,
                 "exit_rule": None, "exit_signal_time": None, "exit_reason": "TP" if part == "IS" else "SL",
                 "entry": {**leg, "time_ms": at * 1000 + 1, "order": "O1", "deal": "D1"},
                 "exit": {**leg, "price": "4010" if part == "IS" else "3990", "time_ms": at * 1000 + 10, "order": "O2", "deal": "D2"},
                 "stop_loss": "3990", "take_profit": "4010", "initial_risk": "10", "gross_profit": gross,
                 "commission": "-1", "swap": "-0.75", "fee": "-0.25", "net_profit": net}
        result["partitions"][part] = {"signals": rows, "trades": [trade], "flat_at_start": True, "flat_at_end": True,
            "equity": [{"time_ms": first * 1000, "equity": "1000"}, {"time_ms": at * 1000 + 2, "equity": "981"},
                       {"time_ms": at * 1000 + 2, "equity": "980"},
                       {"time_ms": last * 1000, "equity": str(Decimal("1000") + Decimal(net))}]}
    return subject, db, root, proposal, signals, result


def publish(root, result, **overrides):
    (root / "results" / f"native_tester_raw_{checksum(RAW_FIXTURE)}.bin").write_bytes(RAW_FIXTURE)
    _publish(root / "results", canonical_bytes(result), prefix="native_tester_result")
    receipt = {"schema_version": "r1-native-tester-receipt/v1", "result_sha256": checksum(canonical_bytes(result)),
               "isolation": "VERIFIED", "numeric_parity": "VERIFIED", "strategy_mapping": "VERIFIED",
               "run_approval": "EXPLICIT", "execution_allowed": False,
               "isolation_evidence_sha256": "d" * 64, "numeric_parity_evidence_sha256": "e" * 64,
               "run_approval_sha256": "f" * 64,
               **{key: result[key] for key in ("signal_sha256", "strategy_sha256", "native_report_sha256", "tester_binary_sha256")},
               **overrides}
    _publish(root / "results", canonical_bytes(receipt), prefix="native_tester_receipt")
    return checksum(canonical_bytes(receipt))


def test_no_trusted_receipt_reports_real_gates_without_reading_files(research, monkeypatch):
    _, _, root, proposal, signals, _ = research
    monkeypatch.setattr("src.services.trading.research.native_backtest._object", lambda *args: pytest.fail("untrusted read"))
    report = inspect_native_backtest(root, proposal, signals)
    assert report["status"] == "BLOCKED" and report["performance"] is None
    assert {"NATIVE_STRATEGY_MAPPING_UNSUPPORTED_BY_PARITY_EA", "NATIVE_NUMERIC_PARITY_NOT_VERIFIED",
            "WHOLE_ENVIRONMENT_ISOLATION_NOT_PROVEN", "NATIVE_TESTER_RUN_APPROVAL_REQUIRED"} <= set(report["blockers"])


def test_read_only_report_and_exact_partition_metrics(research):
    _, _, root, proposal, signals, result = research
    pin = publish(root, result)
    before = {path: path.read_bytes() for path in (root / "results").glob("*.json")}
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=pin)
    assert report["status"] == "VERIFIED_NATIVE_REPORT" and report["research_verdict"] == "INCONCLUSIVE"
    assert report["kind"] == "MT5_TESTER_SIMULATION" and report["execution_allowed"] is False
    first, second = report["performance"]["IS"], report["performance"]["OOS"]
    assert (first["trade_count"], Decimal(first["net_pnl"]), first["win_rate"], first["profit_factor"]) == (1, 10, "1", None)
    assert (Decimal(second["expectancy"]), second["win_rate"], second["profit_factor"], second["max_drawdown"]) == (-8, "0", "0", "20")
    assert "deal" not in first["trades"][0]["entry"] and "order" not in first["trades"][0]["entry"]
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert report["provenance"]["signal_sha256"] == signals["result_sha256"]


@pytest.mark.parametrize("mutation,reason", [
    ("signal", "BACKTEST_NATIVE_SIGNAL_PARITY_FAILED"),
    ("missing_signal", "BACKTEST_NATIVE_SIGNAL_PARITY_FAILED"),
    ("duplicate_signal", "BACKTEST_SIGNAL_DUPLICATE"),
    ("before_close", "BACKTEST_NATIVE_TRADE_TIMING_OR_SIGNAL_INVALID"),
    ("unknown_cost", "BACKTEST_NATIVE_NUMBER_UNAVAILABLE_OR_INVALID"),
    ("same_deal", "BACKTEST_NATIVE_LIFECYCLE_INVALID"),
    ("protection", "BACKTEST_NATIVE_PROTECTION_INVALID"),
    ("equity", "BACKTEST_NATIVE_EQUITY_PNL_MISMATCH"),
    ("net", "BACKTEST_NATIVE_NET_PNL_MISMATCH"),
    ("carry_position", "BACKTEST_PARTITION_NOT_FLAT"),
])
def test_mismatches_never_publish_performance(research, mutation, reason):
    _, _, root, proposal, signals, result = research
    first = result["partitions"]["IS"]
    trade = first["trades"][0]
    if mutation == "signal":
        first["signals"][0]["triggered"] = False
    elif mutation == "missing_signal":
        first["signals"].pop()
    elif mutation == "duplicate_signal":
        first["signals"].append(first["signals"][0])
    elif mutation == "before_close":
        trade["entry"]["time_ms"] = trade["entry_signal_time"] * 1000
    elif mutation == "unknown_cost":
        trade["entry"]["slippage_points"] = None
    elif mutation == "same_deal":
        trade["exit"]["deal"] = trade["entry"]["deal"]
    elif mutation == "protection":
        trade["stop_loss"] = "4010"
    elif mutation == "equity":
        first["equity"][-1]["equity"] = "999"
    elif mutation == "net":
        trade["net_profit"] = "99"
    else:
        first["flat_at_end"] = False
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=publish(root, result))
    assert report["status"] == "BLOCKED" and report["performance"] is None and reason in report["blockers"]


@pytest.mark.parametrize("overrides,reason", [
    ({"numeric_parity": "FAIL"}, "BACKTEST_TRUSTED_RECEIPT_INVALID"),
    ({"isolation": "INCONCLUSIVE"}, "BACKTEST_TRUSTED_RECEIPT_INVALID"),
    ({"run_approval": "MATH_ONLY"}, "BACKTEST_TRUSTED_RECEIPT_INVALID"),
    ({"numeric_parity_evidence_sha256": None}, "BACKTEST_TRUSTED_RECEIPT_INVALID"),
    ({"signal_sha256": "0" * 64}, "BACKTEST_RECEIPT_SCOPE_MISMATCH"),
])
def test_receipt_cannot_transfer_approval_or_scope(research, overrides, reason):
    _, _, root, proposal, signals, result = research
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=publish(root, result, **overrides))
    assert report["blockers"] == [reason] and report["performance"] is None


def test_result_bytes_are_checked_before_parsing(research):
    _, _, root, proposal, signals, result = research
    pin = publish(root, result)
    (root / "results" / f"native_tester_result_{checksum(canonical_bytes(result))}.json").write_bytes(b"{}")
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=pin)
    assert report["blockers"] == ["BACKTEST_ARTIFACT_INTEGRITY_FAILED"]


def test_native_raw_report_bytes_are_required_and_pinned(research):
    _, _, root, proposal, signals, result = research
    pin = publish(root, result)
    (root / "results" / f"native_tester_raw_{checksum(RAW_FIXTURE)}.bin").write_bytes(b"other bytes")
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=pin)
    assert report["blockers"] == ["BACKTEST_ARTIFACT_INTEGRITY_FAILED"] and report["performance"] is None


def test_unknown_signal_coverage_blocks_even_a_pinned_receipt(research):
    _, _, root, proposal, signals, result = research
    signals = copy.deepcopy(signals)
    signals["result"]["status"] = "PARTIAL"
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=publish(root, result))
    assert report["blockers"] == ["BACKTEST_SIGNAL_COVERAGE_INCOMPLETE"]


def test_changed_signal_bytes_cannot_use_the_old_attestation(research):
    _, _, root, proposal, signals, result = research
    signals = copy.deepcopy(signals)
    signals["result"]["feature_sha256"] = "0" * 64
    report = inspect_native_backtest(root, proposal, signals, trusted_receipt_sha256=publish(root, result))
    assert report["blockers"] == ["BACKTEST_SIGNAL_BINDING_MISMATCH"] and report["performance"] is None


def test_streamlit_read_only_blocked_and_review_views(research, monkeypatch):
    subject, db, root, _, _, result = research
    monkeypatch.delenv("RESEARCH_NATIVE_TESTER_RECEIPT_SHA256", raising=False)
    page = signal_page(subject, db)
    assert not page.exception and any(w.value == "NATIVE_TESTER_RUN_APPROVAL_REQUIRED" for w in page.warning)
    assert not any("Run native" in b.label for b in page.button)
    monkeypatch.setenv("RESEARCH_NATIVE_TESTER_RECEIPT_SHA256", publish(root, result))
    page.run()
    assert not page.exception and any("VERIFIED_NATIVE_REPORT" in item.value for item in page.text)
    assert len(page.dataframe) == 7

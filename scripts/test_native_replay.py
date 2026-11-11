"""Synthetic transport/contract fixtures only; no native invocation or receipts."""
import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest

from scripts.test_goal_research_workflow import app
from scripts.test_historical_features import configured, compute
from scripts.test_historical_signals import evaluate, rule
from src.config import Config
from src.services.trading.research import native_replay as replay
from src.services.trading.research.data_integration import cost_readiness
from src.services.trading.research.historical_dataset import canonical_bytes, checksum
from src.services.trading.research.native_backtest import inspect_native_backtest


@pytest.fixture
def research(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch, signal_rules=[rule()], confirmed=True,
                               specification_updates={"reentry": []})
    compute(subject, approved=True)
    signals = evaluate(subject, approved=True)
    proposal = subject.inspect_goal_research("A")["proposal"]
    record = subject._goal_research_context("A")[6]
    root = Config.DATA_DIR / "research"
    policy = {"profile": replay.PROFILE, "signal_sha256": signals["result_sha256"], "side": "BUY", "volume": "0.01",
              "stop_loss": "3990", "take_profit": "4010", "risk_cap": "10", "currency": "USD",
              "server_utc_offset_seconds": 7200, "max_signal_delay_ms": 100, "tick_dataset_sha256": "1" * 64,
              "cost_assumptions_sha256": checksum(canonical_bytes(cost_readiness(proposal)["assumptions"])),
              "deviation_points": 0, "risk_fraction": "0.01"}
    return root, proposal, record, policy, signals


def prepare(research, policy=None, approval=None):
    root, proposal, record, original, _ = research
    policy = original if policy is None else policy
    return replay.prepare_replay(root, proposal, record, policy, now=datetime.now(timezone.utc),
                                 reviewed_policy_sha256=approval if approval is not None else checksum(canonical_bytes(policy)))


def capture(package, part):
    window = package["partitions"][part]
    signals = window["signals"]
    start, end = window["start"] * 1000, window["end"] * 1000
    entry = signals[0]["signal_time"] * 1000 + 1
    rows = [["META", package["strategy_sha256"], part, 5000, "USD", "0.01"], ["EQUITY", start, "1000"]]
    for index, item in enumerate(signals):
        stamp = item["signal_time"]
        rows.append(["SIGNAL", index, stamp, item["action"], int(item["triggered"]), stamp * 1000 + 1])
        if not index:
            rows.append(["ACTION", index, "1", "2", "4000", "10"])
        if stamp * 1000 + 1 < end:
            rows.append(["EQUITY", stamp * 1000 + 1, "999"])
    rows.extend([["EQUITY", end - 1, "1008"], ["EQUITY", end, "1008"], ["DEAL", "1", "2", "3", entry, "IN", "BUY", "RULE",
        "4000", "0.01", "3999.95", "4000", "0", "-1", "0", "0"],
        ["DEAL", "4", "5", "3", end - 1, "OUT", "SELL", "TP", "4010", "0.01", "4010", "4010.05", "10", "-1", "0", "0"],
        ["COMPLETE"]])
    return replay._csv(rows).encode("ascii")


def normalize(package, captures, *, evidence_changes=None):
    policy = package["strategy"]["policy"]
    evidence = {"strategy_sha256": package["strategy_sha256"], "tester_binary_sha256": "2" * 64,
        "capture_sha256": {part: checksum(data) for part, data in captures.items()},
        "schedule_sha256": {part: value["schedule_sha256"] for part, value in package["partitions"].items()},
        "tick_dataset_sha256": policy["tick_dataset_sha256"], "cost_assumptions_sha256": policy["cost_assumptions_sha256"],
        "fill_model": "EVERY_TICK_REAL_TICKS", "execution_delay_ms": 0, "optimization": False, **(evidence_changes or {})}
    return replay.normalize_replay(package, captures, run_evidence=evidence,
                                   trusted_run_evidence_sha256=checksum(canonical_bytes(evidence)))


def test_repeatable_export_and_result_normalization_without_receipt(research):
    root, proposal, _, _, signals = research
    package = prepare(research)
    assert package == prepare(research)
    assert package["strategy"]["broker_symbol"] == "XAUUSDm"
    assert package["strategy"]["signal_request"]["revision_id"] == proposal.head.revision_id
    path = replay.publish_replay_package(root, package)
    assert replay.publish_replay_package(root, package) == path
    captures = {part: capture(package, part) for part in ("IS", "OOS")}
    result, raw = normalize(package, captures)
    assert normalize(package, captures) == (result, raw)
    assert result["partitions"]["IS"]["trades"][0]["net_profit"] == "8"
    assert Decimal(result["partitions"]["IS"]["trades"][0]["entry"]["spread_points"]) == 5
    assert result["evaluation_mode"] == replay.MODE
    path = replay.publish_replay_result(root, result, raw)
    assert replay.publish_replay_result(root, result, raw) == path
    assert not list((root / "results").glob("native_tester_receipt*"))
    assert inspect_native_backtest(root, proposal, signals)["performance"] is None


@pytest.mark.parametrize("mutation", ["extra", "wrong_signal", "risk", "clock", "bracket", "approval", "costs"])
def test_rejects_unreviewed_or_unsupported_policy(research, mutation):
    policy = dict(research[3])
    changes = {"extra": {"management": "TRAIL"}, "wrong_signal": {"signal_sha256": "9" * 64}, "risk": {"risk_cap": "0"},
               "clock": {"server_utc_offset_seconds": False}, "bracket": {"stop_loss": "4100"},
               "costs": {"cost_assumptions_sha256": "0" * 64}}
    policy.update(changes.get(mutation, {}))
    with pytest.raises(ValueError, match="POLICY|BRACKET"):
        prepare(research, policy, approval="0" * 64 if mutation == "approval" else None)


@pytest.mark.parametrize("mutation", ["incomplete", "signal", "deal", "scope", "schedule", "model", "checksum", "tick_source", "missing_equity"])
def test_rejects_unbound_or_incomplete_native_capture(research, mutation):
    package = copy.deepcopy(prepare(research))
    captures = {part: capture(package, part) for part in ("IS", "OOS")}
    changes = {}
    if mutation == "incomplete":
        captures["IS"] = captures["IS"].replace(b"COMPLETE", b"FAILED")
    elif mutation == "signal":
        captures["IS"] = captures["IS"].replace(b",ENTRY,1,", b",ENTRY,0,", 1)
    elif mutation == "deal":
        captures["IS"] = captures["IS"].replace(b",OUT,SELL,TP,", b",OUT,BUY,TP,")
    elif mutation == "scope":
        captures["IS"] = captures["OOS"]
    elif mutation == "schedule":
        package["partitions"]["IS"]["signals"][0]["action"] = "EXIT"
    elif mutation == "model":
        changes["fill_model"] = "OPEN_ONLY"
    elif mutation == "checksum":
        changes["capture_sha256"] = {part: "0" * 64 for part in captures}
    elif mutation == "missing_equity":
        lines = captures["IS"].splitlines(keepends=True)
        index = next(i for i, row in enumerate(lines) if row.endswith(b",999\n"))
        captures["IS"] = b"".join(lines[:index] + lines[index + 1:])
    else:
        changes["tick_dataset_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="BACKTEST_REPLAY_"):
        normalize(package, captures, evidence_changes=changes)


def test_archived_real_16_half_tick_regression_math_not_native_execution():
    atr = 3.1750000000000194
    entry = Decimal("4032.546")
    raw = entry - Decimal(str(atr)) * Decimal("1.5")
    assert raw == Decimal("4027.78349999999997090")
    assert raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) == Decimal("4027.783")
    assert Decimal(str(float(entry) - atr * 1.5)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) == Decimal("4027.784")


def test_short_rule_exit_uses_native_references_and_both_deal_costs():
    signals = [{"signal_time": 11, "rule": "short", "action": "ENTRY", "triggered": True},
               {"signal_time": 12, "rule": "close", "action": "EXIT", "triggered": True}]
    rows = [["META", "a" * 64, "IS", 5000, "USD", "0.01"], ["EQUITY", 10000, "1000"],
            ["SIGNAL", 0, 11, "ENTRY", 1, 11001], ["ACTION", 0, 1, 2, "4000", "10"], ["EQUITY", 11001, "999"],
            ["SIGNAL", 1, 12, "EXIT", 1, 12001], ["ACTION", 1, 4, 5, "3995", "0"], ["EQUITY", 12001, "1003"],
            ["EQUITY", 13000, "1003"], ["DEAL", 1, 2, 3, 11001, "IN", "SELL", "RULE",
            "4000", "0.01", "4000", "4000.05", "0", "-1", "0", "0"],
            ["DEAL", 4, 5, 3, 12001, "OUT", "BUY", "RULE",
            "3995", "0.01", "3994.95", "3995", "5", "-1", "0", "0"], ["COMPLETE"]]
    _, result = replay._partition(replay._csv(rows), "IS", "a" * 64, {"start": 10, "end": 13, "signals": signals},
        {"currency": "USD", "side": "SELL", "volume": "0.01", "stop_loss": "4010", "take_profit": "3990",
         "risk_cap": "10", "max_signal_delay_ms": 100})
    trade = result["trades"][0]
    assert trade["exit_rule"] == "close" and trade["exit_signal_time"] == 12
    assert trade["gross_profit"] == "5" and trade["net_profit"] == "3" and trade["commission"] == "-2"


def test_static_expert_refuses_live_optimization_and_unapproved_runs():
    expert = replay.EXPERT.read_text()
    assert "input bool ApprovedResearchReplay=false;" in expert
    assert "!MQLInfoInteger(MQL_OPTIMIZATION)" in expert and "!MQLInfoInteger(MQL_FORWARD)" in expert
    assert "!TesterOnly() || !ApprovedResearchReplay" in expert and "!TesterOnly() || !OrderSend" in expert
    assert "DEAL_FEE" in expert and "DEAL_TIME_MSC" in expert

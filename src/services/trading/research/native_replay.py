"""Prepare and normalize one bounded Tester replay. Never start or attest a run."""
import csv
from bisect import bisect_left
from decimal import Decimal, localcontext
import io
from pathlib import Path
import re

from ..market.timeframes import timeframe_duration_seconds
from .data_integration import cost_readiness, historical_requests
from .historical_dataset import canonical_bytes, checksum, utc
from .historical_signals import inspect_signal_request, load_signal_result
from .input_package import _local, _publish
from .native_backtest import _number, _performance, _pin, readiness


MODE = "VERIFIED_SIGNAL_REPLAY_BACKTEST"
PROFILE = "FIXED_VOLUME_ABSOLUTE_BRACKET_FLAT_ONLY_V1"
EXPERT = Path(__file__).resolve().parents[4] / "tools/mt5_bridge/research/SignalReplay.mq5"


def _csv(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue()


def prepare_replay(root, proposal, record, policy, *, reviewed_policy_sha256, now):
    """Project only the current approved signal artifact and an explicitly reviewed policy."""
    descriptor, _ = inspect_signal_request(root, proposal, record, now=now)
    run = record.get("signal_run", {})
    if run.get("status") != "PASS" or run.get("request_sha256") != descriptor["request_sha256"]:
        raise ValueError("BACKTEST_APPROVED_SIGNALS_REQUIRED")
    pin = run["result_sha256"]
    result = load_signal_result(root, descriptor, pin)
    if readiness(proposal, {"status": "PASS", "result": result})["blockers"]:
        raise ValueError("BACKTEST_SIGNALS_WINDOW_OR_COSTS_NOT_READY")
    specification = proposal.head.content.development.specification
    if specification.management or specification.reentry or specification.conflicts or proposal.head.content.strategy:
        raise ValueError("BACKTEST_REPLAY_MANAGEMENT_OR_REENTRY_UNSUPPORTED")
    if not _pin(reviewed_policy_sha256) or checksum(canonical_bytes(policy)) != reviewed_policy_sha256:
        raise ValueError("BACKTEST_REPLAY_POLICY_NOT_REVIEWED")
    fields = {"profile", "signal_sha256", "side", "volume", "stop_loss", "take_profit", "risk_cap",
              "currency", "server_utc_offset_seconds", "max_signal_delay_ms", "tick_dataset_sha256",
              "cost_assumptions_sha256", "deviation_points", "risk_fraction"}
    if (set(policy) != fields or policy["profile"] != PROFILE or policy["signal_sha256"] != pin
            or policy["side"] not in {"BUY", "SELL"} or not _pin(policy["tick_dataset_sha256"])
            or not isinstance(policy["currency"], str) or not re.fullmatch("[A-Z]{3}", policy["currency"])
            or type(policy["server_utc_offset_seconds"]) is not int or abs(policy["server_utc_offset_seconds"]) >= 86400
            or type(policy["max_signal_delay_ms"]) is not int or not 0 < policy["max_signal_delay_ms"] <= 86400000
            or type(policy["deviation_points"]) is not int or policy["deviation_points"] != 0
            or any(_number(policy[k]) <= 0 for k in ("volume", "stop_loss", "take_profit", "risk_cap"))
            or not 0 < _number(policy["risk_fraction"]) <= 1
            or policy["cost_assumptions_sha256"] != checksum(canonical_bytes(cost_readiness(proposal)["assumptions"]))):
        raise ValueError("BACKTEST_REPLAY_POLICY_UNSUPPORTED")
    goal_risk = proposal.brief.goal.max_risk_per_trade_pct
    if goal_risk is not None and _number(policy["risk_fraction"]) * 100 > Decimal(str(goal_risk)):
        raise ValueError("BACKTEST_REPLAY_POLICY_RISK_EXCEEDS_GOAL")
    if (policy["side"] == "BUY") != (_number(policy["stop_loss"]) < _number(policy["take_profit"])):
        raise ValueError("BACKTEST_REPLAY_BRACKET_INVALID")
    requests, blockers = historical_requests(proposal)
    if blockers or len(requests) != 1:
        raise ValueError("BACKTEST_REPLAY_SINGLE_MARKET_TIMEFRAME_REQUIRED")
    export = requests[0].export
    if not re.fullmatch(r"[A-Za-z0-9_.#-]+", export.broker_symbol):
        raise ValueError("BACKTEST_REPLAY_SYMBOL_UNSUPPORTED")
    window = descriptor["evaluation_window"]
    start, split, end = (int(utc(window[key]).timestamp()) for key in ("start", "split", "end"))
    partitions = {}
    for part, first, last in (("IS", start, split), ("OOS", split, end)):
        rows = [{k: row[k] for k in ("signal_time", "rule", "action", "triggered")} for row in result["partitions"][part]]
        triggers = [row["signal_time"] for row in rows if row["triggered"] is True]
        if not rows or len(triggers) != len(set(triggers)):
            raise ValueError("BACKTEST_REPLAY_AMBIGUOUS_OR_EMPTY_SCHEDULE")
        partitions[part] = {"start": first, "end": last, "signals": rows}
    strategy = {"schema_version": "r1-native-replay-strategy/v1", "mode": MODE, "policy": policy,
                "policy_sha256": reviewed_policy_sha256, "signal_request": descriptor, "signal_sha256": pin,
                "expert_sha256": checksum(EXPERT.read_bytes()), "broker_symbol": export.broker_symbol,
                "timeframe": export.timeframe, "execution_allowed": False,
                "partition_sha256": {part: checksum(canonical_bytes(value)) for part, value in partitions.items()}}
    strategy_pin = checksum(canonical_bytes(strategy))
    for part, partition in partitions.items():
        rows = partition["signals"]
        header = ["SIGNAL_REPLAY_V1", strategy_pin, part, export.broker_symbol,
                  timeframe_duration_seconds(export.timeframe), partition["start"], partition["end"], policy["server_utc_offset_seconds"],
                  policy["side"], *[policy[k] for k in ("volume", "stop_loss", "take_profit", "risk_cap",
                  "max_signal_delay_ms", "currency", "deviation_points", "risk_fraction")], len(rows)]
        schedule = _csv([header, *[(row["signal_time"], index, row["action"], int(row["triggered"]))
                                   for index, row in enumerate(rows)], ["END"]])
        partition.update(schedule_csv=schedule, schedule_sha256=checksum(schedule.encode("ascii")))
    return {"strategy": strategy, "strategy_sha256": strategy_pin, "partitions": partitions}


def publish_replay_package(root, package):
    """Publish the package and its two immutable Tester inputs without invoking the terminal."""
    directory = _local(root / "results")
    directory.mkdir(exist_ok=True)
    for partition in package["partitions"].values():
        _publish(directory, partition["schedule_csv"].encode("ascii"), prefix="replay_schedule", suffix="csv")
    return _publish(directory, canonical_bytes(package), prefix="native_replay_package")


def _partition(text, part, strategy_pin, expected, policy):
    rows = list(csv.reader(io.StringIO(text), strict=True))
    if (len(rows) < 2 or rows[-1] != ["COMPLETE"] or len(rows[0]) != 6
            or rows[0][:3] != ["META", strategy_pin, part]
            or rows[0][4] != policy["currency"] or not re.fullmatch("[1-9][0-9]{0,8}", rows[0][3])):
        raise ValueError("BACKTEST_REPLAY_CAPTURE_INCOMPLETE")
    build, point = int(rows[0][3]), _number(rows[0][5])
    if point <= 0:
        raise ValueError("BACKTEST_REPLAY_POINT_INVALID")
    seen, actions, taken, positions, equity = [], {}, set(), {}, []
    for row in rows[1:-1]:
        if not row:
            raise ValueError("BACKTEST_REPLAY_CAPTURE_SCHEMA_INVALID")
        kind = row[0]
        if kind == "SIGNAL" and len(row) == 6:
            idx, stamp, triggered, observed = map(int, (row[1], row[2], row[4], row[5]))
            if (idx != len(seen) or idx >= len(expected["signals"])
                    or [stamp, row[3], triggered] != [expected["signals"][idx][key] for key in ("signal_time", "action", "triggered")]
                    or observed <= expected["signals"][idx]["signal_time"] * 1000
                    or (seen and observed < seen[-1])):
                raise ValueError("BACKTEST_REPLAY_SIGNAL_SEQUENCE_INVALID")
            seen.append(observed)
        elif kind == "ACTION" and len(row) == 6:
            idx, deal, order, requested, risk = row[1:]
            idx = int(idx)
            if (deal in actions or idx in taken or idx != len(seen) - 1 or idx < 0
                    or not expected["signals"][idx]["triggered"] or _number(requested) <= 0):
                raise ValueError("BACKTEST_REPLAY_ACTION_INVALID")
            actions[deal] = (idx, order, _number(requested), _number(risk))
            taken.add(idx)
        elif kind == "EQUITY" and len(row) == 3:
            equity.append({"time_ms": int(row[1]), "equity": row[2]})
        elif kind == "DEAL" and len(row) == 16:
            positions.setdefault(row[3], []).append(row[1:])
        else:
            raise ValueError("BACKTEST_REPLAY_CAPTURE_SCHEMA_INVALID")
    if len(seen) != len(expected["signals"]):
        raise ValueError("BACKTEST_REPLAY_SIGNAL_COVERAGE_INCOMPLETE")
    trades = []
    for position, deals in positions.items():
        if (len(deals) != 2 or [deal[4] for deal in deals] != ["IN", "OUT"]
                or deals[0][5] != policy["side"] or deals[1][5] == policy["side"]):
            raise ValueError("BACKTEST_REPLAY_POSITION_UNSUPPORTED")
        legs, totals = [], [Decimal(0)] * 4
        entry_signal = exit_signal = None
        for deal, order, _, time, direction, side, reason, price, volume, bid, ask, profit, fee1, swap, fee2 in deals:
            if any(not re.fullmatch("[1-9][0-9]*", identifier) for identifier in (deal, order, position)):
                raise ValueError("BACKTEST_REPLAY_DEAL_ID_INVALID")
            action = actions.pop(deal, None)
            if reason == "RULE" and action is not None:
                index, expected_order, reference, risk = action
                signal = expected["signals"][index]
                if (expected_order != order or int(time) != seen[index]
                        or int(time) - signal["signal_time"] * 1000 > policy["max_signal_delay_ms"]):
                    raise ValueError("BACKTEST_REPLAY_DEAL_ACTION_MISMATCH")
                if direction == "IN" and signal["action"] == "ENTRY":
                    entry_signal, initial_risk = signal, risk
                elif direction == "OUT" and signal["action"] == "EXIT":
                    exit_signal = signal
                else:
                    raise ValueError("BACKTEST_REPLAY_DEAL_ACTION_MISMATCH")
            elif direction == "OUT" and action is None and reason in {"SL", "TP"}:
                reference = _number(policy["stop_loss" if reason == "SL" else "take_profit"])
            else:
                raise ValueError("BACKTEST_REPLAY_DEAL_ACTION_MISMATCH")
            if side not in {"BUY", "SELL"} or _number(bid) <= 0 or _number(ask) < _number(bid):
                raise ValueError("BACKTEST_REPLAY_DEAL_QUOTE_INVALID")
            spread = (_number(ask) - _number(bid)) / point
            slippage = (_number(price) - reference) / point * (1 if side == "BUY" else -1)
            legs.append({"deal": deal, "order": order, "time_ms": int(time), "price": price, "volume": volume,
                         "spread_points": format(spread.normalize(), "f"), "slippage_points": format(slippage.normalize(), "f")})
            totals = [a + _number(b) for a, b in zip(totals, (profit, fee1, swap, fee2))]
        if (entry_signal is None or not 0 < initial_risk <= _number(policy["risk_cap"])
                or _number(legs[0]["volume"]) != _number(policy["volume"])):
            raise ValueError("BACKTEST_REPLAY_RISK_OR_VOLUME_MISMATCH")
        trades.append({"position": position, "side": policy["side"], "entry": legs[0], "exit": legs[1],
            "entry_rule": entry_signal["rule"], "entry_signal_time": entry_signal["signal_time"],
            "exit_rule": exit_signal["rule"] if exit_signal else None, "exit_signal_time": exit_signal["signal_time"] if exit_signal else None,
            "exit_reason": deals[1][6], "stop_loss": policy["stop_loss"], "take_profit": policy["take_profit"],
            "initial_risk": str(initial_risk), "gross_profit": str(totals[0]), "commission": str(totals[1]),
            "swap": str(totals[2]), "fee": str(totals[3]), "net_profit": str(sum(totals))})
    if actions:
        raise ValueError("BACKTEST_REPLAY_ACTION_DEAL_MISSING")
    trades.sort(key=lambda trade: trade["entry"]["time_ms"])
    entries = [trade["entry"]["time_ms"] for trade in trades]
    curve_times = {point["time_ms"] for point in equity}
    end = expected["end"] * 1000
    if (any(observed not in curve_times for observed in seen if observed < end)
            or any(trade[leg]["time_ms"] not in curve_times for trade in trades for leg in ("entry", "exit"))):
        raise ValueError("BACKTEST_REPLAY_EQUITY_COVERAGE_INCOMPLETE")
    last_trigger = None
    for idx, (signal, observed) in enumerate(zip(expected["signals"], seen, strict=True)):
        stamp = signal["signal_time"] * 1000
        if not signal["triggered"] or stamp == end:
            if idx in taken:
                raise ValueError("BACKTEST_REPLAY_BOUNDARY_ACTION_INVALID")
            continue
        if observed >= end or observed - stamp > policy["max_signal_delay_ms"] or observed == last_trigger:
            raise ValueError("BACKTEST_REPLAY_TRIGGER_TIMING_UNSUPPORTED")
        last_trigger = observed
        prior = bisect_left(entries, observed) - 1
        open_at_signal = prior >= 0 and (trades[prior]["exit"]["time_ms"] > observed or
            trades[prior]["exit"]["time_ms"] == observed and trades[prior]["exit_reason"] == "RULE")
        if (idx in taken) != (open_at_signal == (signal["action"] == "EXIT")):
            raise ValueError("BACKTEST_REPLAY_ACTION_COVERAGE_MISMATCH")
    native = {"signals": expected["signals"], "trades": trades, "equity": equity, "flat_at_start": True, "flat_at_end": True}
    _performance(native, expected["signals"], expected["start"], expected["end"])
    return build, native


def normalize_replay(package, captures, *, run_evidence, trusted_run_evidence_sha256):
    """Normalize externally pinned raw Tester captures; no receipt or approval is issued."""
    strategy = package["strategy"]
    pin = package["strategy_sha256"]
    capture_sha256 = run_evidence.get("capture_sha256", {})
    tester_binary_sha256 = run_evidence.get("tester_binary_sha256")
    if (strategy["mode"] != MODE or strategy["execution_allowed"] is not False
            or checksum(canonical_bytes(strategy)) != pin or not _pin(tester_binary_sha256)
            or set(captures) != {"IS", "OOS"} or set(capture_sha256) != set(captures)
            or checksum(canonical_bytes(run_evidence)) != trusted_run_evidence_sha256
            or run_evidence.get("strategy_sha256") != pin
            or run_evidence.get("tick_dataset_sha256") != strategy["policy"]["tick_dataset_sha256"]
            or run_evidence.get("cost_assumptions_sha256") != strategy["policy"]["cost_assumptions_sha256"]
            or run_evidence.get("fill_model") != "EVERY_TICK_REAL_TICKS"
            or type(run_evidence.get("execution_delay_ms")) is not int or run_evidence["execution_delay_ms"] != 0
            or run_evidence.get("optimization") is not False):
        raise ValueError("BACKTEST_REPLAY_BINDING_INVALID")
    raw = {}
    for part in ("IS", "OOS"):
        partition = package["partitions"][part]
        if (checksum(canonical_bytes({key: partition[key] for key in ("start", "end", "signals")})) != strategy["partition_sha256"][part]
                or checksum(partition["schedule_csv"].encode("ascii")) != partition["schedule_sha256"]
                or run_evidence.get("schedule_sha256", {}).get(part) != partition["schedule_sha256"]):
            raise ValueError("BACKTEST_REPLAY_SCHEDULE_MISMATCH")
        data = captures[part]
        if not isinstance(data, bytes) or len(data) > 12 * 1024 * 1024 or checksum(data) != capture_sha256[part]:
            raise ValueError("BACKTEST_REPLAY_CAPTURE_CHECKSUM_MISMATCH")
        raw[part] = data.decode("ascii")
    with localcontext() as context:
        context.prec = 64
        reports = {part: _partition(raw[part], part, pin, package["partitions"][part], strategy["policy"]) for part in raw}
    if reports["IS"][0] != reports["OOS"][0]:
        raise ValueError("BACKTEST_REPLAY_BUILD_MISMATCH")
    payload = canonical_bytes(raw)
    result = {"schema_version": "r1-native-tester-result/v1", "kind": "MT5_TESTER_SIMULATION",
        "evaluation_mode": MODE, "execution_allowed": False, "signal_sha256": strategy["signal_sha256"],
        "run_evidence_sha256": trusted_run_evidence_sha256,
        "strategy_sha256": pin, "tester_binary_sha256": tester_binary_sha256, "native_report_sha256": checksum(payload),
        "tester_build": reports["IS"][0], "currency": strategy["policy"]["currency"], "fill_model": "EVERY_TICK_REAL_TICKS",
        "equity_sampling": "NATIVE_TICK", "optimization": False,
        "partitions": {part: report for part, (_, report) in reports.items()}}
    return result, payload


def publish_replay_result(root, result, raw):
    """Stage unadmitted bytes only. The separately reviewed host receipt is mandatory for UI display."""
    directory = _local(root / "results")
    if checksum(raw) != result["native_report_sha256"] or result.get("evaluation_mode") != MODE:
        raise ValueError("BACKTEST_REPLAY_CAPTURE_CHECKSUM_MISMATCH")
    directory.mkdir(exist_ok=True)
    _publish(directory, raw, prefix="native_tester_raw", suffix="bin")
    return _publish(directory, canonical_bytes(result), prefix="native_tester_result")

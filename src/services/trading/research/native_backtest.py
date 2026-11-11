"""Read-only admission and reporting for externally qualified MT5 Tester evidence."""
from decimal import Decimal, localcontext
import json
import re

from .data_integration import cost_readiness
from .historical_dataset import canonical_bytes, checksum, utc
from .input_package import _local


def readiness(proposal, signals):
    development = proposal.head.content.development
    window = development.historical_window if development else None
    costs = cost_readiness(proposal)
    blockers = []
    if not window or not all((window.start, window.split, window.end, window.session_policy)):
        blockers.append("BACKTEST_UTC_IS_OOS_REQUIRED")
    if costs["missing"]:
        blockers.append("BACKTEST_USER_CONFIRMED_COSTS_REQUIRED")
    if signals.get("status") != "PASS":
        blockers.append(signals.get("reason") or "BACKTEST_APPROVED_SIGNALS_REQUIRED")
    elif signals["result"]["status"] != "EVALUATED":
        blockers.append("BACKTEST_SIGNAL_COVERAGE_INCOMPLETE")
    return {"blockers": list(dict.fromkeys(blockers)), "costs_missing": costs["missing"]}


def _pin(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)


def _artifact(root, prefix, pin, suffix):
    if not _pin(pin):
        raise ValueError("BACKTEST_TRUSTED_PIN_INVALID")
    path = _local(root / "results" / f"{prefix}_{pin}.{suffix}")
    with path.open("rb") as stream:
        payload = stream.read(32 * 1024 * 1024 + 1)
    if len(payload) > 32 * 1024 * 1024 or checksum(payload) != pin:
        raise ValueError("BACKTEST_ARTIFACT_INTEGRITY_FAILED")
    return payload


def _object(root, prefix, pin):
    payload = _artifact(root, prefix, pin, "json")
    value = json.loads(payload)
    if not isinstance(value, dict) or canonical_bytes(value) != payload:
        raise ValueError("BACKTEST_ARTIFACT_SCHEMA_INVALID")
    return value


def _number(value):
    if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]{1,18}(?:\.[0-9]{1,12})?", value):
        raise ValueError("BACKTEST_NATIVE_NUMBER_UNAVAILABLE_OR_INVALID")
    return Decimal(value)


def _signal_ledger(rows):
    ledger = {}
    for row in rows:
        if type(row["signal_time"]) is not int or type(row["triggered"]) is not bool:
            raise ValueError("BACKTEST_SIGNAL_COVERAGE_INCOMPLETE")
        key = row["signal_time"], row["rule"], row["action"]
        if key in ledger:
            raise ValueError("BACKTEST_SIGNAL_DUPLICATE")
        ledger[key] = row["triggered"]
    return ledger


def _performance(native, signals, start, end):
    expected = _signal_ledger(signals)
    if not expected or _signal_ledger(native["signals"]) != expected:
        raise ValueError("BACKTEST_NATIVE_SIGNAL_PARITY_FAILED")
    rows, curve = native["trades"], native["equity"]
    if native["flat_at_start"] is not True or native["flat_at_end"] is not True:
        raise ValueError("BACKTEST_PARTITION_NOT_FLAT")
    points = [(point["time_ms"], _number(point["equity"])) for point in curve]
    times = [time for time, _ in points]
    if (not times or any(type(time) is not int for time in times) or times != sorted(times)
            or times[0] != start * 1000 or times[-1] != end * 1000 or points[0][1] <= 0
            or any(equity < 0 for _, equity in points)):
        raise ValueError("BACKTEST_NATIVE_EQUITY_INCOMPLETE")
    peak = points[0][1]
    drawdown = drawdown_fraction = Decimal(0)
    for _, equity in points:
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        drawdown_fraction = max(drawdown_fraction, (peak - equity) / peak)

    trades, pnl = [], []
    deal_ids, order_ids, position_ids = set(), set(), set()
    gross = commission = swap = fees_total = Decimal(0)
    last_exit = start * 1000
    for row in rows:
        entry, exit = row["entry"], row["exit"]
        signal_time = row["entry_signal_time"]
        entry_time, exit_time = entry["time_ms"], exit["time_ms"]
        if (any(type(t) is not int for t in (signal_time, entry_time, exit_time))
                or not start * 1000 <= signal_time * 1000 < entry_time <= exit_time < end * 1000 or entry_time < last_exit
                or expected.get((signal_time, row["entry_rule"], "ENTRY")) is not True
                or row["side"] not in {"BUY", "SELL"}):
            raise ValueError("BACKTEST_NATIVE_TRADE_TIMING_OR_SIGNAL_INVALID")
        reason = row["exit_reason"]
        if reason == "RULE":
            exit_signal = row["exit_signal_time"]
            if (type(exit_signal) is not int or not entry_time <= exit_signal * 1000 < exit_time
                    or expected.get((exit_signal, row["exit_rule"], "EXIT")) is not True):
                raise ValueError("BACKTEST_NATIVE_TRADE_TIMING_OR_SIGNAL_INVALID")
        elif reason not in {"SL", "TP"} or row["exit_signal_time"] is not None or row["exit_rule"] is not None:
            raise ValueError("BACKTEST_NATIVE_EXIT_UNSUPPORTED")
        if (not isinstance(row["position"], str) or not row["position"] or row["position"] in position_ids
                or any(not isinstance(leg[key], str) or not leg[key] for leg in (entry, exit) for key in ("deal", "order"))
                or entry["deal"] == exit["deal"] or entry["order"] == exit["order"]
                or {entry["deal"], exit["deal"]} & deal_ids or {entry["order"], exit["order"]} & order_ids):
            raise ValueError("BACKTEST_NATIVE_LIFECYCLE_INVALID")
        risk = _number(row["initial_risk"])
        if risk <= 0 or _number(entry["volume"]) <= 0 or _number(entry["volume"]) != _number(exit["volume"]):
            raise ValueError("BACKTEST_NATIVE_RISK_OR_VOLUME_INVALID")
        stop, target, entry_price = _number(row["stop_loss"]), _number(row["take_profit"]), _number(entry["price"])
        if min(stop, target) <= 0 or not (stop < entry_price < target if row["side"] == "BUY" else target < entry_price < stop):
            raise ValueError("BACKTEST_NATIVE_PROTECTION_INVALID")
        for leg in (entry, exit):
            if _number(leg["price"]) <= 0 or _number(leg["spread_points"]) < 0:
                raise ValueError("BACKTEST_NATIVE_PRICE_OR_SPREAD_INVALID")
            _number(leg["slippage_points"])
        profit, commission_value, carry, fees = (_number(row[key]) for key in ("gross_profit", "commission", "swap", "fee"))
        net = _number(row["net_profit"])
        if net != profit + commission_value + carry + fees:
            raise ValueError("BACKTEST_NATIVE_NET_PNL_MISMATCH")
        gross, commission, swap, fees_total = gross + profit, commission + commission_value, swap + carry, fees_total + fees
        pnl.append(net)
        trades.append({"side": row["side"], "entry": {k: entry[k] for k in ("time_ms", "price", "volume", "spread_points", "slippage_points")},
                       "exit": {k: exit[k] for k in ("time_ms", "price", "volume", "spread_points", "slippage_points")},
                       "exit_reason": reason, "initial_risk": str(risk), "net_profit": str(net),
                       "stop_loss": str(stop), "take_profit": str(target), "entry_signal_time": signal_time,
                       "gross_profit": str(profit), "commission": str(commission_value), "swap": str(carry), "fee": str(fees)})
        deal_ids.update((entry["deal"], exit["deal"]))
        order_ids.update((entry["order"], exit["order"]))
        position_ids.add(row["position"])
        last_exit = exit_time
    net = sum(pnl, Decimal(0))
    if points[-1][1] - points[0][1] != net:
        raise ValueError("BACKTEST_NATIVE_EQUITY_PNL_MISMATCH")
    wins = sum(value > 0 for value in pnl)
    gain = sum(value for value in pnl if value > 0)
    loss = -sum(value for value in pnl if value < 0)
    return {"trade_count": len(pnl), "gross_pnl": str(gross), "net_pnl": str(net),
            "commission": str(commission), "swap": str(swap), "fees": str(fees_total), "max_drawdown": str(drawdown),
            "max_drawdown_fraction": str(drawdown_fraction), "win_rate": str(Decimal(wins) / len(pnl)) if pnl else None,
            "profit_factor": str(Decimal(gain) / loss) if loss else None,
            "expectancy": str(net / len(pnl)) if pnl else None, "trades": trades,
            "equity_curve": [{"time_ms": time, "equity": str(equity)} for time, equity in points]}


def inspect_native_backtest(root, proposal, signals, *, trusted_receipt_sha256=""):
    """Only a host-pinned, independently reviewed receipt can admit a result, never UI input."""
    report = {"status": "BLOCKED", "research_verdict": "INCONCLUSIVE", "performance": None,
              "native_launch": "UNAVAILABLE", "execution_allowed": False, **readiness(proposal, signals)}
    if not trusted_receipt_sha256:
        report["blockers"] += ["NATIVE_STRATEGY_MAPPING_UNSUPPORTED_BY_PARITY_EA",
                               "NATIVE_NUMERIC_PARITY_NOT_VERIFIED", "WHOLE_ENVIRONMENT_ISOLATION_NOT_PROVEN",
                               "NATIVE_TESTER_RUN_APPROVAL_REQUIRED", "NATIVE_TESTER_RESULT_NOT_ATTESTED"]
    if report["blockers"]:
        return report
    try:
        signal = signals["result"]
        if (signal.get("proposal_id") != proposal.proposal_id or signal.get("revision_id") != proposal.head.revision_id
                or signal.get("proposal_sha256") != checksum(proposal.to_json().encode())
                or signal.get("scope") != proposal.scope.model_dump(mode="json")
                or checksum(canonical_bytes(signal)) != signals["result_sha256"]):
            raise ValueError("BACKTEST_SIGNAL_BINDING_MISMATCH")
        receipt = _object(root, "native_tester_receipt", trusted_receipt_sha256)
        if receipt.get("schema_version") != "r1-native-tester-receipt/v1":
            raise ValueError("BACKTEST_TRUSTED_RECEIPT_INVALID")
        if receipt.get("signal_sha256") != signals["result_sha256"]:
            raise ValueError("BACKTEST_RECEIPT_SCOPE_MISMATCH")
        proof_keys = ("strategy_sha256", "tester_binary_sha256", "native_report_sha256",
                      "isolation_evidence_sha256", "numeric_parity_evidence_sha256", "run_approval_sha256")
        if (receipt.get("isolation") != "VERIFIED" or receipt.get("numeric_parity") != "VERIFIED"
                or receipt.get("strategy_mapping") != "VERIFIED" or receipt.get("run_approval") != "EXPLICIT"
                or any(not _pin(receipt.get(key)) for key in proof_keys)
                or receipt.get("execution_allowed") is not False):
            raise ValueError("BACKTEST_TRUSTED_RECEIPT_INVALID")
        result = _object(root, "native_tester_result", receipt["result_sha256"])
        if (result.get("schema_version") != "r1-native-tester-result/v1" or result.get("kind") != "MT5_TESTER_SIMULATION"
                or result.get("execution_allowed") is not False or result.get("signal_sha256") != signals["result_sha256"]
                or result.get("strategy_sha256") != receipt["strategy_sha256"]
                or result.get("native_report_sha256") != receipt["native_report_sha256"]
                or result.get("tester_binary_sha256") != receipt["tester_binary_sha256"]
                or result.get("fill_model") != "EVERY_TICK_REAL_TICKS"
                or result.get("equity_sampling") != "NATIVE_TICK"
                or result.get("optimization") is not False
                or type(result.get("tester_build")) is not int or result["tester_build"] <= 0
                or not isinstance(result.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", result["currency"])
                or set(result["partitions"]) != {"IS", "OOS"}):
            raise ValueError("BACKTEST_RESULT_BINDING_MISMATCH")
        if not _artifact(root, "native_tester_raw", receipt["native_report_sha256"], "bin"):
            raise ValueError("BACKTEST_NATIVE_REPORT_EMPTY")
        start, split, end = (int(utc(signal["evaluation_window"][name]).timestamp()) for name in ("start", "split", "end"))
        with localcontext() as context:
            context.prec = 64
            performance = {part: _performance(result["partitions"][part], signal["partitions"][part], first, last)
                           for part, first, last in (("IS", start, split), ("OOS", split, end))}
        return {**report, "status": "VERIFIED_NATIVE_REPORT", "signal_parity": "MATCH",
                "performance": performance, "currency": result["currency"], "tester_build": result["tester_build"],
                "kind": "MT5_TESTER_SIMULATION", "fill_model": result["fill_model"],
                "confirmed_cost_assumptions": cost_readiness(proposal)["assumptions"],
                "provenance": {"receipt_sha256": trusted_receipt_sha256, "result_sha256": receipt["result_sha256"],
                               **{key: receipt[key] for key in proof_keys}, "revision_id": signal["revision_id"],
                               "feature_sha256": signal["feature_sha256"], "signal_sha256": signals["result_sha256"],
                               "feature_calculation_sha256": signal["feature_calculation_sha256"],
                               "rules_sha256": signal["rule_contract"]["rules_sha256"],
                               "inputs": signal["inputs"], "evaluation_window": signal["evaluation_window"]}}
    except (OSError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
        code = str(exc)
        report["blockers"].append(code if re.fullmatch(r"BACKTEST_[A-Z0-9_]+", code) else "BACKTEST_NATIVE_EVIDENCE_UNAVAILABLE_OR_INVALID")
        return report

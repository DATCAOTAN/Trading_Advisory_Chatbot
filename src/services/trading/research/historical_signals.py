"""Historical feature-to-StrategyRule adapter: signals only, never position simulation."""
from bisect import bisect_right
import json
import math
from pathlib import Path
import re

from ..market import timeframes
from ..reasoning import strategy_evidence as core
from .descriptive_computation import DescriptiveComputationApproval
from .historical_dataset import canonical_bytes, checksum
from .historical_features import bound_feature_inputs, feature_plan, inspect_feature_request, load_feature_result
from .input_package import _local, _publish


ALGORITHM = "HISTORICAL_SIGNALS_V1"
SCHEMA = "r1-research-signals/v1"
MAX_CONDITION_OBSERVATIONS = 100_000


def rule_contract(proposal):
    development = proposal.head.content.development
    rules = development.signal_rules if development else ()
    plan = feature_plan(proposal)
    available = {item["id"]: item for item in plan["supported"]}
    supported, unresolved = [], []
    for rule in rules:
        reasons = []
        if rule.timing is None:
            reasons.append("SIGNAL_TIMING_REQUIRED")
        elif rule.timing != "COMPLETED_BAR_CLOSE":
            reasons.append("SIGNAL_TIMING_UNSUPPORTED")
        if rule.evaluation_timeframe not in {item["timeframe"] for item in available.values()}:
            reasons.append("SIGNAL_EVALUATION_CLOCK_UNAVAILABLE")
        if rule.combination is None or not rule.conditions:
            reasons.append("SIGNAL_CONDITIONS_AND_COMBINATION_REQUIRED")
        for condition in rule.conditions:
            if condition.left not in available or (condition.right is not None and condition.right not in available):
                reasons.append("SIGNAL_VERIFIED_FEATURE_REFERENCE_REQUIRED")
            if condition.operator not in core.RULE_OPERATORS:
                reasons.append("SIGNAL_OPERATOR_UNSUPPORTED_OR_MISSING")
            elif condition.operator in core.EDGE_RULE_OPERATORS and condition.right is None:
                reasons.append("SIGNAL_CROSS_RIGHT_OPERAND_REQUIRED")
            elif condition.right is not None and condition.operator not in {"GREATER_THAN", "LESS_THAN", *core.EDGE_RULE_OPERATORS}:
                reasons.append("SIGNAL_OPERATOR_OPERANDS_UNSUPPORTED")
            expected = 0 if condition.right is not None or condition.operator in {"RISING", "FALLING"} else 2 if condition.operator == "BETWEEN" else 1
            if len(condition.constants) != expected or (condition.operator == "BETWEEN" and
                    len(condition.constants) == 2 and condition.constants[0] > condition.constants[1]):
                reasons.append("SIGNAL_CONSTANTS_INVALID_OR_MISSING")
        entry = {**rule.model_dump(mode="json"), "status": "UNRESOLVED" if reasons else "SUPPORTED",
                 "blockers": list(dict.fromkeys(reasons))}
        (unresolved if reasons else supported).append(entry)
    return {"supported": supported, "unresolved": unresolved,
            "rules_sha256": checksum(canonical_bytes([rule.model_dump(mode="json") for rule in rules])),
            "schema_version": "r1-signal-rules/v1"}


def inspect_signal_request(root, proposal, record, *, now):
    contract = rule_contract(proposal)
    if not contract["supported"]:
        raise ValueError("RESEARCH_SIGNAL_RULES_UNRESOLVED")
    receipt = record.get("signal_rules_review", {})
    reviewed = next((revision for revision in proposal.revisions if revision.revision_id == receipt.get("revision_id")), None)
    if (receipt.get("purpose") != "HISTORICAL_SIGNALS_ONLY" or receipt.get("rules_sha256") != contract["rules_sha256"]
            or reviewed is None or reviewed.content.hypothesis_fingerprint() != proposal.head.content.hypothesis_fingerprint()):
        raise ValueError("RESEARCH_SIGNAL_USER_REVIEW_REQUIRED")
    inputs = bound_feature_inputs(root, proposal, record)
    feature_request, _ = inspect_feature_request(root, proposal, inputs, now=now)
    run = record.get("feature_run", {})
    if run.get("status") != "PASS" or run.get("request_sha256") != feature_request["request_sha256"]:
        raise ValueError("RESEARCH_VERIFIED_FEATURE_RESULT_REQUIRED")
    result = load_feature_result(root, feature_request, run["result_sha256"])
    descriptor = {"algorithm": ALGORITHM, "proposal_id": proposal.proposal_id, "revision_id": proposal.head.revision_id,
        "proposal_sha256": checksum(proposal.to_json().encode()), "scope": proposal.scope.model_dump(mode="json"),
        "specification_id": feature_request["specification_id"], "inputs": feature_request["inputs"],
        "evaluation_window": proposal.head.content.development.historical_window.model_dump(mode="json"),
        "feature_sha256": run["result_sha256"], "feature_request_sha256": feature_request["request_sha256"],
        "feature_calculation_sha256": feature_request["calculation_sha256"], "rule_contract": contract,
        "rule_review": receipt, "calculation_sha256": checksum(canonical_bytes({
            "adapter": checksum(Path(__file__).read_bytes()), "core": checksum(Path(core.__file__).read_bytes()),
            "clock": checksum(Path(timeframes.__file__).read_bytes())}))}
    return {**descriptor, "request_sha256": checksum(canonical_bytes(descriptor))}, result


def evaluate_historical_signals(features, contract):
    """Sample explicit clocks; previous values use the previous clock, including across IS/OOS."""
    series = {item["id"]: item for item in features["series"]}
    clocks = {name: [row["completed_at"] for row in item["rows"]] for name, item in series.items()}
    schedules = {}
    for item in series.values():
        clock = schedules.setdefault(item["timeframe"], {})
        clock.update((row["completed_at"], row["partition"]) for row in item["rows"])

    def observation(name, at):
        index = bisect_right(clocks[name], at) - 1
        row = series[name]["rows"][index] if index >= 0 else None
        if row is not None and at - row["completed_at"] >= timeframes.timeframe_duration_seconds(series[name]["timeframe"]):
            return {"value": None, "source_completed_at": row["completed_at"], "status": "SOURCE_BAR_GAP"}
        valid = row is not None and row["status"] == "COMPUTED" and type(row["value"]) in {int, float} and math.isfinite(row["value"])
        return {"value": row["value"] if valid else None, "source_completed_at": row["completed_at"] if row else None,
                "status": row["status"] if row else "NO_COMPLETED_VALUE"}

    partitions = {"IS": [], "OOS": []}
    scored = {timeframe: sorted((point, part) for point, part in clock.items() if part in partitions)
              for timeframe, clock in schedules.items()}
    if sum(len(scored[rule["evaluation_timeframe"]]) * len(rule["conditions"])
           for rule in contract["supported"]) > MAX_CONDITION_OBSERVATIONS:
        raise ValueError("RESEARCH_SIGNAL_OBSERVATION_BUDGET_EXCEEDED")
    for rule in contract["supported"]:
        timeframe = rule["evaluation_timeframe"]
        step = timeframes.timeframe_duration_seconds(timeframe)
        for point, partition in scored[timeframe]:
            prior_point = point - step
            evaluations = []
            for condition in rule["conditions"]:
                values, sources = {}, {}
                for name in {condition["left"], condition["right"]} - {None}:
                    current = observation(name, point)
                    previous = (observation(name, prior_point) if prior_point in schedules[timeframe] else
                                {"value": None, "source_completed_at": None, "status": "PREVIOUS_CLOCK_BAR_UNAVAILABLE"})
                    values[name] = {"current": current["value"], "previous": previous["value"]}
                    sources[name] = {"current": current, "previous": previous}
                typed = core.StrategyRule(condition["operator"], condition["left"], condition["right"] or "", tuple(condition["constants"]))
                evaluation = core.evaluate_strategy_rule(typed, values)
                unknown = evaluation["current_condition"] is None or (
                    evaluation["trigger_mode"] == "EDGE" and evaluation["previous_condition"] is None)
                evaluations.append({**condition, **evaluation, "status": "UNKNOWN" if unknown else "EVALUATED", "sources": sources})
            unknown = any(item["status"] == "UNKNOWN" for item in evaluations)
            triggered = None if unknown else (all(item["triggered"] for item in evaluations) if rule["combination"] == "ALL"
                                               else any(item["triggered"] for item in evaluations))
            partitions[partition].append({"rule": rule["name"], "action": rule["action"], "signal_time": point,
                "evaluation_timeframe": rule["evaluation_timeframe"], "timing": rule["timing"],
                "combination": rule["combination"], "triggered": triggered, "status": "UNKNOWN" if unknown else "EVALUATED",
                "conditions": evaluations})
    for rows in partitions.values():
        rows.sort(key=lambda row: (row["signal_time"], row["rule"]))
    summary = {part: {"observations": len(rows), "unknown": sum(row["triggered"] is None for row in rows),
        "entry_signals": sum(row["action"] == "ENTRY" and row["triggered"] is True for row in rows),
        "exit_signals": sum(row["action"] == "EXIT" and row["triggered"] is True for row in rows)} for part, rows in partitions.items()}
    return {"partitions": partitions, "summary": summary, "unresolved_rules": contract["unresolved"],
        "status": "PARTIAL" if contract["unresolved"] or any(item["unknown"] for item in summary.values()) else "EVALUATED",
        "timing_semantics": "CONDITION_AT_COMPLETED_CLOCK_CLOSE_NOT_A_FILL; PREVIOUS_CLOCK_CONTINUES_ACROSS_IS_OOS",
        "missing_value_policy": "UNKNOWN_REQUIRED_OPERAND_BLOCKS_GROUP; NEVER_CARRY_ACROSS_MISSING_SOURCE_BARS"}


def run_historical_signals(root, proposal, record, *, approval=None, now):
    if not isinstance(approval, DescriptiveComputationApproval):
        raise ValueError("RESEARCH_COMPUTATION_OPERATOR_APPROVAL_REQUIRED")
    descriptor, features = inspect_signal_request(root, proposal, record, now=now)
    output = _local(root.absolute() / "results")
    if (approval.algorithm != ALGORITHM or approval.input_sha256 != descriptor["request_sha256"]
            or approval.proposal_id != proposal.proposal_id or approval.revision_id != proposal.head.revision_id
            or approval.scope != proposal.scope or approval.output_directory != str(output)):
        raise ValueError("RESEARCH_COMPUTATION_APPROVAL_MISMATCH")
    calculated = evaluate_historical_signals(features, descriptor["rule_contract"])
    current, _ = inspect_signal_request(root, proposal, record, now=now)
    if descriptor != current:
        raise ValueError("RESEARCH_SIGNAL_SOURCE_CHANGED")
    return _publish(output, canonical_bytes({"schema_version": SCHEMA, **descriptor, **calculated,
        "approval": approval.model_dump(mode="json", exclude={"output_directory"}),
        "execution_allowed": False, "generated_code_allowed": False, "strategy_evaluated": False,
        "fills_simulated": False}), prefix="research_signals")


def load_signal_result(root, descriptor, pin):
    if not isinstance(pin, str) or not re.fullmatch(r"[a-f0-9]{64}", pin):
        raise ValueError("RESEARCH_SIGNAL_RESULT_PIN_INVALID")
    payload = _local(root / "results" / f"research_signals_{pin}.json").read_bytes()
    if checksum(payload) != pin:
        raise ValueError("RESEARCH_SIGNAL_RESULT_CHECKSUM_MISMATCH")
    result = json.loads(payload)
    if (result.get("schema_version") != SCHEMA or any(result.get(key) != value for key, value in descriptor.items())
            or any(result.get(key) is not False for key in ("execution_allowed", "generated_code_allowed", "strategy_evaluated", "fills_simulated"))):
        raise ValueError("RESEARCH_SIGNAL_RESULT_BINDING_MISMATCH")
    return result

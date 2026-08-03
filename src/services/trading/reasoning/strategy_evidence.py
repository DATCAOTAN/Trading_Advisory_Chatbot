from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from src.services.trading.market.indicators import atr, ema_series, rsi, sma


RULE_OPERATORS = {
    "GREATER_THAN",
    "LESS_THAN",
    "CROSSES_ABOVE",
    "CROSSES_BELOW",
    "BETWEEN",
    "RISING",
    "FALLING",
}
SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}


@dataclass(frozen=True)
class ReasoningV2Policy:
    maximum_bars_per_timeframe: int = 1000
    baseline_lookback: int = 100
    safety_margin_bars: int = 10
    spread_atr_maximum: float = 0.2
    trend_efficiency_minimum: float = 0.25
    compression_ratio_maximum: float = 0.6
    expansion_ratio_minimum: float = 1.8


DEFAULT_REASONING_V2_POLICY = ReasoningV2Policy()


@dataclass(frozen=True)
class IndicatorDefinition:
    indicator_id: str
    aliases: tuple[str, ...]
    parameters: tuple[str, ...]
    required_fields: tuple[str, ...]
    output_fields: tuple[str, ...]
    formula_version: str
    minimum_bars: int
    parameter_defaults: tuple[tuple[str, float], ...]
    parameter_ranges: tuple[tuple[str, float, float, bool], ...]
    missing_value_policy: str = "BLOCK"
    supported_timeframes: tuple[str, ...] = tuple(sorted(SUPPORTED_TIMEFRAMES))

    def warmup(self, values: Mapping[str, float | int]) -> int:
        windows = [int(value) for key, value in values.items() if "period" in key]
        return max(self.minimum_bars, max(windows or (self.minimum_bars,)) * 3)


INDICATOR_REGISTRY: dict[str, IndicatorDefinition] = {
    "EMA": IndicatorDefinition("EMA", ("ema", "exponential moving average"), ("period",), ("close",), ("value",), "ema/v1", 2, (), (("period", 2, 500, True),)),
    "SMA": IndicatorDefinition("SMA", ("sma", "simple moving average"), ("period",), ("close",), ("value",), "sma/v1", 2, (), (("period", 2, 500, True),)),
    "RSI": IndicatorDefinition("RSI", ("rsi", "relative strength index"), ("period",), ("close",), ("value",), "rsi/v1", 3, (), (("period", 2, 500, True),)),
    "ATR": IndicatorDefinition("ATR", ("atr", "average true range"), ("period",), ("high", "low", "close"), ("value",), "atr/v1", 3, (), (("period", 2, 500, True),)),
    "MACD": IndicatorDefinition("MACD", ("macd",), ("fast_period", "slow_period", "signal_period"), ("close",), ("line", "signal", "histogram"), "macd/v1", 27, (("fast_period", 12), ("slow_period", 26), ("signal_period", 9)), (("fast_period", 2, 500, True), ("slow_period", 2, 500, True), ("signal_period", 2, 500, True))),
    "BOLLINGER_BANDS": IndicatorDefinition("BOLLINGER_BANDS", ("bollinger", "bollinger bands", "bbands"), ("period", "deviation"), ("close",), ("middle", "upper", "lower"), "bollinger/v1", 3, (("period", 20), ("deviation", 2)), (("period", 2, 500, True), ("deviation", 0.1, 10, False))),
}


@dataclass(frozen=True)
class IndicatorSpec:
    indicator_id: str
    timeframe: str
    parameters: tuple[tuple[str, float], ...]
    output_alias: str

    def parameter_map(self) -> dict[str, float]:
        return dict(self.parameters)

    def as_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "timeframe": self.timeframe,
            "parameters": dict(self.parameters),
            "output_alias": self.output_alias,
        }


@dataclass(frozen=True)
class StrategyRule:
    operator: str
    left: str
    right: str = ""
    constants: tuple[float, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "left": self.left,
            "right": self.right,
            "constants": list(self.constants),
        }


@dataclass(frozen=True)
class StrategyIdentity:
    strategy_id: str
    strategy_version: str
    normalized_strategy_hash: str

    def as_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ConversationalStrategyRequest:
    canonical_symbol: str
    requested_mode: str
    confirmation_policy: str
    account_scope: str
    indicators: tuple[IndicatorSpec, ...]
    entry_rules: tuple[StrategyRule, ...]
    exit_rules: tuple[StrategyRule, ...]
    strategy_description: str
    risk_policy_reference: str
    request_id: str
    identity: StrategyIdentity

    @property
    def timeframes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.timeframe for item in self.indicators))

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_symbol": self.canonical_symbol,
            "requested_mode": self.requested_mode,
            "confirmation_policy": self.confirmation_policy,
            "account_scope": self.account_scope,
            "indicators": [item.as_dict() for item in self.indicators],
            "entry_rules": [item.as_dict() for item in self.entry_rules],
            "exit_rules": [item.as_dict() for item in self.exit_rules],
            "strategy_description": self.strategy_description,
            "risk_policy_reference": self.risk_policy_reference,
            "request_id": self.request_id,
            "identity": self.identity.as_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationalStrategyRequest":
        indicators = tuple(
            IndicatorSpec(
                indicator_id=str(item["indicator_id"]),
                timeframe=str(item["timeframe"]),
                parameters=tuple(sorted((str(key), float(value)) for key, value in dict(item["parameters"]).items())),
                output_alias=str(item["output_alias"]),
            )
            for item in payload.get("indicators", ())
        )
        rules = lambda name: tuple(
            StrategyRule(
                operator=str(item["operator"]),
                left=str(item["left"]),
                right=str(item.get("right") or ""),
                constants=tuple(float(value) for value in item.get("constants", ())),
            )
            for item in payload.get(name, ())
        )
        identity_payload = dict(payload.get("identity") or {})
        value = cls(
            canonical_symbol=str(payload.get("canonical_symbol") or ""),
            requested_mode=str(payload.get("requested_mode") or ""),
            confirmation_policy=str(payload.get("confirmation_policy") or ""),
            account_scope=str(payload.get("account_scope") or ""),
            indicators=indicators,
            entry_rules=rules("entry_rules"),
            exit_rules=rules("exit_rules"),
            strategy_description=str(payload.get("strategy_description") or ""),
            risk_policy_reference=str(payload.get("risk_policy_reference") or ""),
            request_id=str(payload.get("request_id") or ""),
            identity=StrategyIdentity(
                strategy_id=str(identity_payload.get("strategy_id") or ""),
                strategy_version=str(identity_payload.get("strategy_version") or ""),
                normalized_strategy_hash=str(identity_payload.get("normalized_strategy_hash") or ""),
            ),
        )
        issues = validate_strategy(value)
        if issues or value.identity != strategy_identity(value):
            raise ValueError(",".join(issues or ("STRATEGY_IDENTITY_INVALID",)))
        return value


@dataclass(frozen=True)
class TimeframeDataRequirement:
    timeframe: str
    requested_bars: int
    indicator_aliases: tuple[str, ...]


@dataclass(frozen=True)
class StrategyDataPlan:
    requirements: tuple[TimeframeDataRequirement, ...]
    maximum_bars_per_timeframe: int = 1000

    def candle_counts(self) -> dict[str, int]:
        return {item.timeframe: item.requested_bars for item in self.requirements}


@dataclass(frozen=True)
class HistoryAvailability:
    timeframe: str
    requested_bars: int
    received_bars: int
    completed_bars: int
    oldest_bar_time: str
    newest_completed_bar_time: str
    freshness: str
    gaps: int
    blocking_items: tuple[str, ...] = ()
    terminal_maximum: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ReasonEvidence:
    code: str
    severity: str
    summary: str
    actual: Any = None
    required: Any = None
    timeframe: str = ""
    feature: str = ""
    source_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "actual": self.actual,
            "required": self.required,
            "timeframe": self.timeframe,
            "feature": self.feature,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class MarketFeatureBundleV2:
    trend: Mapping[str, Any]
    volatility: Mapping[str, Any]
    structure: Mapping[str, Any]
    momentum: Mapping[str, Any]
    timeframe_alignment: Mapping[str, Any]
    execution: Mapping[str, Any]
    data_quality: Mapping[str, Any]
    indicator_values: Mapping[str, Mapping[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "trend": dict(self.trend),
            "volatility": dict(self.volatility),
            "structure": dict(self.structure),
            "momentum": dict(self.momentum),
            "timeframe_alignment": dict(self.timeframe_alignment),
            "execution": dict(self.execution),
            "data_quality": dict(self.data_quality),
            "indicator_values": {key: dict(value) for key, value in self.indicator_values.items()},
        }


@dataclass(frozen=True)
class SetupAssessmentV2:
    direction: str
    scores: Mapping[str, float]
    aggregate_score: float
    hard_blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "scores": dict(self.scores),
            "aggregate_score": self.aggregate_score,
            "hard_blockers": list(self.hard_blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ReasoningEvidenceV2:
    schema_version: str
    strategy_identity: StrategyIdentity
    history: tuple[HistoryAvailability, ...]
    features: MarketFeatureBundleV2
    regime: str
    regime_confidence: float
    setup: SetupAssessmentV2
    reasons: tuple[ReasonEvidence, ...]
    context_size_chars: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_identity": self.strategy_identity.as_dict(),
            "history": [item.as_dict() for item in self.history],
            "features": self.features.as_dict(),
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "setup": self.setup.as_dict(),
            "reasons": [item.as_dict() for item in self.reasons],
            "context_size_chars": self.context_size_chars,
        }

    def compact_context(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "strategy": self.strategy_identity.as_dict(),
            "history": [
                {
                    "timeframe": item.timeframe,
                    "requested": item.requested_bars,
                    "completed": item.completed_bars,
                    "freshness": item.freshness,
                    "gaps": item.gaps,
                }
                for item in self.history
            ],
            "regime": {"state": self.regime, "confidence": self.regime_confidence},
            "features": self.features.as_dict(),
            "setup": self.setup.as_dict(),
            "reasons": [item.as_dict() for item in self.reasons[:20]],
        }


def parse_conversational_strategy(
    text: str,
    *,
    canonical_symbol: str,
    requested_mode: str,
    confirmation_policy: str,
    account_scope: str,
    request_id: str,
    default_timeframes: Sequence[str],
) -> ConversationalStrategyRequest | None:
    normalized = " ".join(str(text or "").upper().replace("/", " / ").split())
    if not (
        any(
            alias.upper() in normalized
            for definition in INDICATOR_REGISTRY.values()
            for alias in definition.aliases
        )
        or re.search(r"\b(ADX|CCI|STOCH(?:ASTIC)?|VWAP|ICHIMOKU)\b", normalized)
    ):
        return None
    default_timeframe = next(iter(default_timeframes), "H1")
    indicators: list[IndicatorSpec] = []
    for match in re.finditer(r"\b(EMA|SMA|RSI|ATR)\s*(\d{1,3})(?:\s*/\s*(\d{1,3}))?", normalized):
        indicator_id, first, second = match.group(1), int(match.group(2)), match.group(3)
        timeframe = _nearby_timeframe(normalized, match.end(), default_timeframe)
        for period in (first, int(second) if second else None):
            if period is None:
                continue
            indicators.append(_indicator(indicator_id, timeframe, {"period": period}))
    for match in re.finditer(r"\bMACD(?:\s*(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3}))?", normalized):
        values = tuple(int(value) for value in match.groups()) if all(match.groups()) else tuple(dict(INDICATOR_REGISTRY["MACD"].parameter_defaults).values())
        indicators.append(_indicator("MACD", _nearby_timeframe(normalized, match.end(), default_timeframe), dict(zip(("fast_period", "slow_period", "signal_period"), values))))
    for match in re.finditer(r"\b(?:BOLLINGER(?:\s+BANDS)?|BBANDS)(?:\s*(\d{1,3})(?:\s*[,/]\s*(\d+(?:\.\d+)?))?)?", normalized):
        defaults = dict(INDICATOR_REGISTRY["BOLLINGER_BANDS"].parameter_defaults)
        indicators.append(_indicator("BOLLINGER_BANDS", _nearby_timeframe(normalized, match.end(), default_timeframe), {"period": int(match.group(1) or defaults["period"]), "deviation": float(match.group(2) or defaults["deviation"])}))
    for match in re.finditer(r"\b(ADX|CCI|STOCH(?:ASTIC)?|VWAP|ICHIMOKU)\s*(\d{1,3})?", normalized):
        indicators.append(
            _indicator(
                match.group(1),
                _nearby_timeframe(normalized, match.end(), default_timeframe),
                {"period": int(match.group(2) or 14)},
            )
        )
    indicators = list({item.output_alias: item for item in indicators}.values())
    rules = _parse_rules(normalized, indicators)
    provisional = ConversationalStrategyRequest(
        canonical_symbol=canonical_symbol,
        requested_mode=requested_mode,
        confirmation_policy=confirmation_policy,
        account_scope=account_scope,
        indicators=tuple(sorted(indicators, key=lambda item: item.output_alias)),
        entry_rules=tuple(rules),
        exit_rules=(),
        strategy_description=str(text or "").strip()[:500],
        risk_policy_reference="CONFIGURED_RISK_POLICY",
        request_id=request_id,
        identity=StrategyIdentity("", "reasoning-strategy/v2", ""),
    )
    identity = strategy_identity(provisional)
    return ConversationalStrategyRequest(**{**provisional.__dict__, "identity": identity})


def validate_strategy(strategy: ConversationalStrategyRequest) -> tuple[str, ...]:
    issues: list[str] = []
    if not strategy.indicators:
        issues.append("STRATEGY_INDICATORS_MISSING")
    aliases: set[str] = set()
    for spec in strategy.indicators:
        definition = INDICATOR_REGISTRY.get(spec.indicator_id)
        if definition is None:
            issues.append("UNSUPPORTED_INDICATOR")
            continue
        if spec.timeframe not in definition.supported_timeframes:
            issues.append("UNSUPPORTED_TIMEFRAME")
        if spec.output_alias in aliases:
            issues.append("DUPLICATE_OUTPUT_ALIAS")
        aliases.add(spec.output_alias)
        values = spec.parameter_map()
        if set(values) != set(definition.parameters):
            issues.append("INDICATOR_PARAMETER_INVALID")
            continue
        parameter_ranges = {name: (minimum, maximum, integer) for name, minimum, maximum, integer in definition.parameter_ranges}
        for name, value in values.items():
            if not math.isfinite(float(value)):
                issues.append("INDICATOR_PARAMETER_INVALID")
                continue
            minimum, maximum, integer = parameter_ranges[name]
            if not minimum <= float(value) <= maximum or integer and int(value) != value:
                issues.append("INDICATOR_PARAMETER_OUT_OF_RANGE")
        if spec.indicator_id == "MACD" and values.get("fast_period", 0) >= values.get("slow_period", 0):
            issues.append("INDICATOR_PARAMETER_RELATION_INVALID")
    for rule in (*strategy.entry_rules, *strategy.exit_rules):
        if rule.operator not in RULE_OPERATORS:
            issues.append("UNSUPPORTED_RULE_OPERATOR")
        if rule.left not in aliases or (rule.right and rule.right not in aliases):
            issues.append("RULE_OUTPUT_UNKNOWN")
        expected = 2 if rule.operator == "BETWEEN" else 0 if rule.right else 1
        if len(rule.constants) != expected:
            issues.append("RULE_OPERAND_INVALID")
    return tuple(dict.fromkeys(issues))


def strategy_identity(strategy: ConversationalStrategyRequest) -> StrategyIdentity:
    material = {
        "symbol": strategy.canonical_symbol,
        "mode": strategy.requested_mode,
        "confirmation": strategy.confirmation_policy,
        "account_scope": strategy.account_scope,
        "indicators": [item.as_dict() for item in sorted(strategy.indicators, key=lambda item: item.output_alias)],
        "entry_rules": [item.as_dict() for item in strategy.entry_rules],
        "exit_rules": [item.as_dict() for item in strategy.exit_rules],
        "risk_policy_reference": strategy.risk_policy_reference,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return StrategyIdentity("strategy_" + digest[:24], "reasoning-strategy/v2", digest)


def plan_strategy_data(
    strategy: ConversationalStrategyRequest,
    policy: ReasoningV2Policy = DEFAULT_REASONING_V2_POLICY,
) -> StrategyDataPlan:
    issues = validate_strategy(strategy)
    if issues:
        raise ValueError(",".join(issues))
    requirements: list[TimeframeDataRequirement] = []
    for timeframe in strategy.timeframes:
        specs = [item for item in strategy.indicators if item.timeframe == timeframe]
        warmup = max(INDICATOR_REGISTRY[item.indicator_id].warmup(item.parameter_map()) for item in specs)
        rule_lookback = 2 if any(rule.operator.startswith("CROSSES_") for rule in strategy.entry_rules) else 1
        requested = min(
            policy.maximum_bars_per_timeframe,
            max(warmup, policy.baseline_lookback)
            + rule_lookback
            + policy.safety_margin_bars,
        )
        requirements.append(TimeframeDataRequirement(timeframe, requested, tuple(item.output_alias for item in specs)))
    return StrategyDataPlan(tuple(requirements), policy.maximum_bars_per_timeframe)


def build_reasoning_evidence(
    strategy: ConversationalStrategyRequest,
    bundle: Any,
    quality_report: Any,
    plan: StrategyDataPlan,
    policy: ReasoningV2Policy = DEFAULT_REASONING_V2_POLICY,
) -> ReasoningEvidenceV2:
    indicator_values: dict[str, dict[str, Any]] = {}
    history: list[HistoryAvailability] = []
    reasons: list[ReasonEvidence] = []
    per_tf_features: dict[str, dict[str, Any]] = {}
    requirement_map = {item.timeframe: item for item in plan.requirements}
    for timeframe, requirement in requirement_map.items():
        snapshot = bundle.timeframes.get(timeframe)
        bars = list(getattr(snapshot, "bars", ()) or ())
        quality = str(quality_report.per_timeframe_quality.get(timeframe) or "EMPTY")
        blocking = []
        if len(bars) < requirement.requested_bars:
            blocking.append("INSUFFICIENT_COMPLETED_BARS")
            reasons.append(ReasonEvidence("INSUFFICIENT_COMPLETED_BARS", "ERROR", "Completed history is below the strategy plan.", len(bars), requirement.requested_bars, timeframe, ",".join(requirement.indicator_aliases)))
        if quality == "STALE":
            blocking.append("DATA_STALE")
            reasons.append(ReasonEvidence("DATA_STALE", "ERROR", "Newest completed bar is stale.", quality, "COMPLETE", timeframe))
        gap_count = _gap_count(bars)
        history.append(HistoryAvailability(timeframe, requirement.requested_bars, len(bars), len(bars), bars[0].timestamp if bars else "", bars[-1].timestamp if bars else "", quality, gap_count, tuple(blocking)))
        if not bars:
            continue
        for spec in (item for item in strategy.indicators if item.timeframe == timeframe):
            indicator_values[spec.output_alias] = _compute_indicator(spec, bars)
        per_tf_features[timeframe] = _timeframe_features(bars, indicator_values, timeframe)

    rule_results = [_evaluate_rule(rule, indicator_values) for rule in strategy.entry_rules]
    failed_rules = [rule for rule, passed in zip(strategy.entry_rules, rule_results) if not passed]
    if failed_rules:
        reasons.append(ReasonEvidence("STRUCTURE_CONFIRMATION_MISSING", "WARN", "One or more configured entry rules are not confirmed.", len(failed_rules), 0, feature="entry_rules"))
    directions = [item.get("direction") for item in per_tf_features.values() if item.get("direction") in {"UP", "DOWN"}]
    alignment_score = abs(directions.count("UP") - directions.count("DOWN")) / max(1, len(per_tf_features))
    conflict = bool("UP" in directions and "DOWN" in directions)
    if conflict:
        reasons.append(ReasonEvidence("HIGHER_TIMEFRAME_CONFLICT", "WARN", "Configured timeframes disagree on trend direction.", directions, "aligned", feature="timeframe_alignment"))
    primary_tf = strategy.timeframes[0] if strategy.timeframes else ""
    primary = per_tf_features.get(primary_tf, {})
    atr_value = float(primary.get("atr") or 0)
    spread = float(getattr(bundle.tick, "spread", 0) or 0)
    spread_atr = spread / atr_value if atr_value > 0 else None
    if spread_atr is not None and spread_atr > policy.spread_atr_maximum:
        reasons.append(ReasonEvidence("SPREAD_TOO_WIDE", "ERROR", "Spread is too large relative to ATR.", round(spread_atr, 6), policy.spread_atr_maximum, primary_tf, "spread_atr"))
    regime, regime_confidence = _regime(primary, conflict, history, policy)
    hard_blockers = tuple(dict.fromkeys(item.code for item in reasons if item.severity == "ERROR"))
    scores = {
        "regime": 0.8 if regime in {"TREND_UP", "TREND_DOWN"} else 0.55 if regime in {"RANGE", "TRANSITION"} else 0.35,
        "trend": _clamp(float(primary.get("trend_efficiency") or 0)),
        "structure": 1.0 if not failed_rules else 0.35,
        "momentum": 0.8 if primary.get("momentum") in {"BULLISH", "BEARISH"} else 0.5,
        "volatility": 0.8 if regime not in {"UNSTABLE", "INSUFFICIENT_EVIDENCE"} else 0.2,
        "timeframe_alignment": _clamp(alignment_score),
        "execution_quality": 1.0 if spread_atr is not None and spread_atr <= policy.spread_atr_maximum else 0.2,
        "risk_compatibility": 0.8 if any(item.indicator_id == "ATR" for item in strategy.indicators) else 0.5,
    }
    aggregate = 0.0 if hard_blockers else round(mean(scores.values()), 8)
    direction = "BUY" if directions.count("UP") > directions.count("DOWN") else "SELL" if directions.count("DOWN") > directions.count("UP") else "NONE"
    features = MarketFeatureBundleV2(
        trend={tf: {key: value for key, value in item.items() if key in {"normalized_slope", "trend_efficiency", "direction"}} for tf, item in per_tf_features.items()},
        volatility={tf: {key: value for key, value in item.items() if key in {"atr", "atr_percentile", "volatility_ratio"}} for tf, item in per_tf_features.items()},
        structure={tf: {key: value for key, value in item.items() if key in {"swing_state", "structure_distance_atr"}} for tf, item in per_tf_features.items()},
        momentum={tf: item.get("momentum", "UNKNOWN") for tf, item in per_tf_features.items()},
        timeframe_alignment={"score": round(alignment_score, 8), "conflict": conflict, "directions": directions},
        execution={"spread_atr": round(spread_atr, 8) if spread_atr is not None else None},
        data_quality={"status": quality_report.status, "rule_results": rule_results},
        indicator_values=indicator_values,
    )
    evidence = ReasoningEvidenceV2("reasoning-evidence/v2", strategy.identity, tuple(history), features, regime, regime_confidence, SetupAssessmentV2(direction, scores, aggregate, hard_blockers, tuple(item.code for item in reasons if item.severity == "WARN")), tuple(reasons))
    compact_size = len(json.dumps(evidence.compact_context(), sort_keys=True, separators=(",", ":")))
    return ReasoningEvidenceV2(**{**evidence.__dict__, "context_size_chars": compact_size})


def _indicator(indicator_id: str, timeframe: str, parameters: Mapping[str, float]) -> IndicatorSpec:
    suffix = "_".join(str(int(value)) if float(value).is_integer() else str(value) for value in parameters.values())
    return IndicatorSpec(indicator_id, timeframe, tuple(sorted((key, float(value)) for key, value in parameters.items())), f"{indicator_id.lower()}_{suffix}_{timeframe.lower()}")


def _nearby_timeframe(text: str, end: int, default: str) -> str:
    match = re.search(r"\b(?:ON|AT|TRÊN|TREN)\s+(M1|M5|M15|H1|H4|D1)\b", text[end:end + 40])
    return match.group(1) if match else default


def _parse_rules(text: str, indicators: Sequence[IndicatorSpec]) -> list[StrategyRule]:
    rules: list[StrategyRule] = []
    aliases = {item.output_alias: item for item in indicators}
    ema_aliases = sorted((item.output_alias for item in indicators if item.indicator_id == "EMA"), key=lambda value: int(value.split("_")[1]))
    if len(ema_aliases) >= 2:
        if re.search(r"CROSS(?:ES)?\s+ABOVE|CẮT\s+LÊN|CAT\s+LEN", text):
            rules.append(StrategyRule("CROSSES_ABOVE", ema_aliases[0], ema_aliases[1]))
        if re.search(r"CROSS(?:ES)?\s+BELOW|CẮT\s+XUỐNG|CAT\s+XUONG", text):
            rules.append(StrategyRule("CROSSES_BELOW", ema_aliases[0], ema_aliases[1]))
    for match in re.finditer(r"RSI(?:\s*\d+)?\s+(?:IS\s+)?(ABOVE|BELOW|GREATER THAN|LESS THAN|TRÊN|TREN|DƯỚI|DUOI)\s+(\d+(?:\.\d+)?)", text):
        rsi_alias = next((name for name, spec in aliases.items() if spec.indicator_id == "RSI"), "")
        if rsi_alias:
            operator = "GREATER_THAN" if match.group(1) in {"ABOVE", "GREATER THAN", "TRÊN", "TREN"} else "LESS_THAN"
            rules.append(StrategyRule(operator, rsi_alias, constants=(float(match.group(2)),)))
    return rules


def _compute_indicator(spec: IndicatorSpec, bars: Sequence[Any]) -> dict[str, Any]:
    values = spec.parameter_map()
    closes = [float(item.close) for item in bars]
    if spec.indicator_id == "EMA":
        series = ema_series(closes, int(values["period"]))
        return {"current": _last(series), "previous": _last(series[:-1]), "formula": "ema/v1"}
    if spec.indicator_id == "SMA":
        period = int(values["period"])
        return {"current": sma(closes, period), "previous": sma(closes[:-1], period), "formula": "sma/v1"}
    if spec.indicator_id == "RSI":
        period = int(values["period"])
        return {"current": rsi(closes, period), "previous": rsi(closes[:-1], period), "formula": "rsi/v1"}
    if spec.indicator_id == "ATR":
        period = int(values["period"])
        return {"current": atr(list(bars), period), "previous": atr(list(bars[:-1]), period), "formula": "atr/v1"}
    if spec.indicator_id == "MACD":
        fast, slow, signal = (int(values[name]) for name in ("fast_period", "slow_period", "signal_period"))
        fast_values, slow_values = ema_series(closes, fast), ema_series(closes, slow)
        line = [(a - b) if a is not None and b is not None else None for a, b in zip(fast_values, slow_values)]
        compact = [value for value in line if value is not None]
        signal_values = ema_series(compact, signal)
        line_value, signal_value = _last(line), _last(signal_values)
        return {"line": line_value, "signal": signal_value, "histogram": line_value - signal_value if line_value is not None and signal_value is not None else None, "current": line_value, "previous": _last(line[:-1]), "formula": "macd/v1"}
    period, deviation = int(values["period"]), float(values["deviation"])
    window = closes[-period:]
    middle = mean(window) if len(window) == period else None
    stddev = math.sqrt(mean((value - middle) ** 2 for value in window)) if middle is not None else None
    return {"middle": middle, "upper": middle + deviation * stddev if stddev is not None else None, "lower": middle - deviation * stddev if stddev is not None else None, "current": middle, "previous": sma(closes[:-1], period), "formula": "bollinger/v1"}


def _timeframe_features(bars: Sequence[Any], indicator_values: Mapping[str, Mapping[str, Any]], timeframe: str) -> dict[str, Any]:
    closes = [float(item.close) for item in bars]
    atr_value = next((float(value["current"]) for alias, value in indicator_values.items() if alias.endswith("_" + timeframe.lower()) and alias.startswith("atr_") and value.get("current") is not None), None)
    atr_value = atr_value or atr(list(bars), min(14, max(2, len(bars) - 1))) or 0.0
    lookback = min(20, len(closes))
    net = closes[-1] - closes[-lookback]
    path = sum(abs(current - previous) for previous, current in zip(closes[-lookback:-1], closes[-lookback + 1:]))
    slope = net / max(1, lookback - 1) / atr_value if atr_value else 0.0
    efficiency = abs(net) / path if path else 0.0
    tr_values = []
    for previous, current in zip(bars[:-1], bars[1:]):
        tr_values.append(max(float(current.high) - float(current.low), abs(float(current.high) - float(previous.close)), abs(float(current.low) - float(previous.close))))
    recent_atr = mean(tr_values[-14:]) if tr_values else 0.0
    baseline = [mean(tr_values[max(0, index - 13):index + 1]) for index in range(13, len(tr_values))]
    percentile = (
        (
            sum(value < recent_atr for value in baseline)
            + 0.5 * sum(value == recent_atr for value in baseline)
        )
        / len(baseline)
        if baseline
        else 0.0
    )
    earlier = mean(tr_values[-28:-14]) if len(tr_values) >= 28 else recent_atr
    structure_bars = bars[-21:-1] or bars[-20:]
    swing_high = max(float(item.high) for item in structure_bars)
    swing_low = min(float(item.low) for item in structure_bars)
    distance = min(abs(closes[-1] - swing_high), abs(closes[-1] - swing_low)) / atr_value if atr_value else None
    momentum = "BULLISH" if net > 0 else "BEARISH" if net < 0 else "NEUTRAL"
    return {
        "normalized_slope": round(slope, 8),
        "trend_efficiency": round(efficiency, 8),
        "direction": "UP" if slope > 0.05 else "DOWN" if slope < -0.05 else "SIDEWAYS",
        "atr": round(atr_value, 8),
        "atr_percentile": round(percentile, 8),
        "volatility_ratio": round(recent_atr / earlier, 8) if earlier else None,
        "swing_state": "BREAKOUT_UP" if closes[-1] >= swing_high else "BREAKOUT_DOWN" if closes[-1] <= swing_low else "INSIDE_STRUCTURE",
        "structure_distance_atr": round(distance, 8) if distance is not None else None,
        "momentum": momentum,
    }


def _evaluate_rule(rule: StrategyRule, values: Mapping[str, Mapping[str, Any]]) -> bool:
    left = values.get(rule.left, {})
    current, previous = left.get("current"), left.get("previous")
    if current is None:
        return False
    if rule.right:
        right = values.get(rule.right, {})
        right_current, right_previous = right.get("current"), right.get("previous")
        if right_current is None:
            return False
        if rule.operator == "CROSSES_ABOVE":
            return previous is not None and right_previous is not None and previous <= right_previous and current > right_current
        if rule.operator == "CROSSES_BELOW":
            return previous is not None and right_previous is not None and previous >= right_previous and current < right_current
        return current > right_current if rule.operator == "GREATER_THAN" else current < right_current
    if rule.operator == "GREATER_THAN":
        return current > rule.constants[0]
    if rule.operator == "LESS_THAN":
        return current < rule.constants[0]
    if rule.operator == "BETWEEN":
        return rule.constants[0] <= current <= rule.constants[1]
    if rule.operator == "RISING":
        return previous is not None and current > previous
    if rule.operator == "FALLING":
        return previous is not None and current < previous
    return False


def _regime(
    primary: Mapping[str, Any],
    conflict: bool,
    history: Sequence[HistoryAvailability],
    policy: ReasoningV2Policy,
) -> tuple[str, float]:
    if any(item.blocking_items for item in history):
        return "INSUFFICIENT_EVIDENCE", 0.0
    if conflict:
        return "TRANSITION", 0.55
    efficiency, ratio, percentile = float(primary.get("trend_efficiency") or 0), float(primary.get("volatility_ratio") or 1), float(primary.get("atr_percentile") or 0.5)
    if percentile >= 0.9 or ratio >= policy.expansion_ratio_minimum:
        return "VOLATILITY_EXPANSION", 0.8
    if percentile <= 0.1 or ratio <= policy.compression_ratio_maximum:
        return "VOLATILITY_COMPRESSION", 0.75
    if efficiency < policy.trend_efficiency_minimum:
        return "RANGE", 0.7
    if primary.get("direction") == "UP":
        return "TREND_UP", min(0.95, 0.6 + efficiency * 0.35)
    if primary.get("direction") == "DOWN":
        return "TREND_DOWN", min(0.95, 0.6 + efficiency * 0.35)
    return "UNSTABLE", 0.35


def _gap_count(bars: Sequence[Any]) -> int:
    if len(bars) < 3:
        return 0
    timestamps = []
    for bar in bars:
        try:
            timestamps.append(datetime.fromisoformat(str(bar.timestamp).replace("Z", "+00:00")).timestamp())
        except ValueError:
            return 1
    steps = [current - previous for previous, current in zip(timestamps, timestamps[1:]) if current > previous]
    expected = min(steps) if steps else 0
    return sum(step > expected * 1.5 for step in steps) if expected else 0


def _last(values: Sequence[float | None]) -> float | None:
    return next((float(value) for value in reversed(values) if value is not None and math.isfinite(float(value))), None)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))

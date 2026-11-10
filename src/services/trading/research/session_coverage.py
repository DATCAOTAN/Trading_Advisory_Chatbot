"""Read-only reassessment; never rewrite original exports or infer sessions from gaps."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .historical_dataset import HistoricalDataRequest, assess_quality, utc
from ..market.timeframes import timeframe_duration_seconds


@dataclass(frozen=True)
class SessionEvidence:
    start: str
    end: str
    state: str
    source: str
    historical: bool = False

    def __post_init__(self):
        if type(self.historical) is not bool or utc(self.start) >= utc(self.end) or not self.source.strip() or self.state not in {
            "MARKET_CLOSED", "NO_QUOTES", "QUOTING", "TRADING",
        }:
            raise ValueError("SESSION_EVIDENCE_INVALID")


def reassess_coverage(rows: Sequence[dict], request: HistoricalDataRequest,
                      evidence: Sequence[SessionEvidence] = ()) -> dict:
    """Evidence intervals are explicit instants, including supplied DST offsets, not server wall time."""
    quality = assess_quality(rows, request, tick_groups=True)
    issues = set(quality["issues"]) - {"SESSION_POLICY_MISMATCH"}
    result = {
        "quality_policy_version": "mt5-session-coverage/v2",
        "internal_consistency": "INVALID" if issues else "VALID",
        "issues": sorted(issues), "coverage": "PARTIAL", "intervals": [],
        "session_sources": sorted({e.source for e in evidence}),
        "current_snapshot_is_historical_proof": False,
    }
    if request.kind == "ticks":
        result["tick_count"] = len(rows)
        result["completeness"] = "UNPROVEN_EVEN_IF_REPEATED_QUERIES_MATCH"
        return result
    present = {r["time"] for r in rows if type(r.get("time")) is int}
    step = timeframe_duration_seconds(request.timeframe)
    intervals = result["intervals"]
    for value in range(int(utc(request.start).timestamp()), int(utc(request.end).timestamp()), step):
        start = datetime.fromtimestamp(value, timezone.utc)
        end = start + timedelta(seconds=step)
        relevant = [e for e in evidence if e.historical and utc(e.start) < end and utc(e.end) > start]
        closed = [e for e in relevant if utc(e.start) <= start and utc(e.end) >= end and e.state in {"MARKET_CLOSED", "NO_QUOTES"}]
        quoting = [e for e in relevant if e.state == "QUOTING"]
        if closed and (quoting or value in present or len({e.state for e in closed}) > 1):
            classification = "UNRESOLVED"
        elif value in present:
            continue
        elif closed:
            classification = "CONFIRMED_MARKET_CLOSED" if closed[0].state == "MARKET_CLOSED" else "CONFIRMED_NO_QUOTE_INTERVAL"
        elif quoting:
            classification = "SUSPECTED_HISTORY_GAP"
        else:
            classification = "SESSION_HISTORY_UNAVAILABLE"
        sources = sorted({e.source for e in relevant})
        if intervals and intervals[-1]["end"] == start.isoformat() and intervals[-1]["classification"] == classification and intervals[-1]["sources"] == sources:
            intervals[-1]["end"] = end.isoformat()
            intervals[-1]["slots"] += 1
        else:
            intervals.append({"start": start.isoformat(), "end": end.isoformat(), "slots": 1,
                              "classification": classification, "sources": sources})
    unresolved = any(i["classification"] not in {"CONFIRMED_MARKET_CLOSED", "CONFIRMED_NO_QUOTE_INTERVAL"} for i in intervals)
    if not issues and not unresolved and len(rows) >= request.warmup_records:
        result["coverage"] = "VERIFIED_BAR_SLOTS"
    return result

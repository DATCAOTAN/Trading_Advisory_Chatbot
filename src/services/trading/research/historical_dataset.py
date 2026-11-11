from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.services.trading.market.data_quality import _check_bar_values
from src.services.trading.market.models import MarketSnapshot, OHLCVBar
from src.services.trading.market.timeframes import timeframe_duration_seconds


SCHEMA = "mt5-research-dataset/v1"
EXPORTER_VERSION = "mt5-research-export/v2"
BAR_FIELDS = ("time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume")
BAR_FIELD_TYPES = dict(zip(BAR_FIELDS, ("UTC_SECONDS", "FLOAT64", "FLOAT64", "FLOAT64", "FLOAT64", "INT64", "INT64", "INT64")))
TICK_FIELDS = ("time", "time_msc", "bid", "ask", "last", "flags")
SESSION_POLICIES = {"UTC_WEEKDAYS_CONSERVATIVE_V1", "CONTINUOUS_UTC_V1"}


def utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("UTC_AWARE_DATETIME_REQUIRED")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class HistoricalDataRequest:
    canonical_symbol: str
    broker_symbol: str
    timeframe: str
    start: str
    end: str
    kind: str = "bars"
    warmup_records: int = 35
    session_policy: str = "UTC_WEEKDAYS_CONSERVATIVE_V1"

    def __post_init__(self) -> None:
        start, end = utc(self.start), utc(self.end)
        if (
            any(not isinstance(s, str) or not s or any(c.isspace() for c in s) for s in (self.canonical_symbol, self.broker_symbol))
            or self.kind not in {"bars", "ticks"}
            or self.timeframe not in {"M1", "M15", "H1", "H4"}
            or self.session_policy not in SESSION_POLICIES
            or type(self.warmup_records) is not int or self.warmup_records < 1
            or start >= end or end - start > timedelta(days=366)
        ):
            raise ValueError("HISTORICAL_REQUEST_INVALID")
        if self.kind == "ticks" and end - start > timedelta(hours=6):
            raise ValueError("TICK_INTERVAL_EXCEEDS_SIX_HOURS")
        step = timeframe_duration_seconds(self.timeframe)
        if self.kind == "bars" and (start.timestamp() % step or end.timestamp() % step):
            raise ValueError("BAR_INTERVAL_NOT_TIMEFRAME_ALIGNED")
        object.__setattr__(self, "start", start.isoformat())
        object.__setattr__(self, "end", end.isoformat())


def merge_chunks(chunks: Sequence[Sequence[Mapping[str, Any]]], kind: str) -> tuple[list[dict], int]:
    """Only identical rows shared by different acquisition chunks may be deduplicated."""
    if kind == "ticks":
        return _merge_tick_chunks(chunks)
    key = "time" if kind == "bars" else "time_msc"
    merged: list[dict] = []
    seen: dict[Any, dict] = {}
    overlaps = 0
    for chunk in chunks:
        local: set[Any] = set()
        previous = None
        for raw in chunk:
            row = dict(raw)
            timestamp = row.get(key)
            if type(timestamp) is not int:
                raise ValueError("MALFORMED_TIMESTAMP")
            if timestamp in local:
                raise ValueError("DUPLICATE_TIMESTAMP_WITHIN_CHUNK")
            if previous is not None and timestamp <= previous:
                raise ValueError("NON_MONOTONIC_CHUNK")
            local.add(timestamp)
            previous = timestamp
            if timestamp in seen:
                if row != seen[timestamp]:
                    raise ValueError("CONFLICTING_CHUNK_OVERLAP")
                overlaps += 1
                continue
            if merged and timestamp <= merged[-1][key]:
                raise ValueError("NON_MONOTONIC_CHUNK_SEQUENCE")
            seen[timestamp] = row
            merged.append(row)
    return merged, overlaps


def _merge_tick_chunks(chunks: Sequence[Sequence[Mapping[str, Any]]]) -> tuple[list[dict], int]:
    # A millisecond is not a tick identity; compare complete ordered groups at chunk boundaries.
    groups: dict[int, list[dict]] = {}
    overlaps = 0
    for chunk in chunks:
        local: dict[int, list[dict]] = {}
        previous = None
        for raw in chunk:
            row = dict(raw)
            timestamp = row.get("time_msc")
            if type(timestamp) is not int:
                raise ValueError("MALFORMED_TIMESTAMP")
            if previous is not None and timestamp < previous:
                raise ValueError("NON_MONOTONIC_CHUNK")
            group = local.setdefault(timestamp, [])
            if row in group:
                raise ValueError("DUPLICATE_TIMESTAMP_WITHIN_CHUNK")
            group.append(row)
            previous = timestamp
        for timestamp, group in local.items():
            if timestamp in groups:
                if group != groups[timestamp]:
                    raise ValueError("CONFLICTING_CHUNK_OVERLAP")
                overlaps += len(group)
            else:
                if groups and timestamp < next(reversed(groups)):
                    raise ValueError("NON_MONOTONIC_CHUNK_SEQUENCE")
                groups[timestamp] = group
    return [row for group in groups.values() for row in group], overlaps


def _session_open(timestamp: datetime, policy: str) -> bool:
    # Unknown weekday maintenance/holidays remain gaps, never inferred closures.
    return policy == "CONTINUOUS_UTC_V1" or timestamp.weekday() < 5


def assess_quality(rows: Sequence[Mapping[str, Any]], request: HistoricalDataRequest, *, tick_groups: bool = False) -> dict:
    fields = BAR_FIELDS if request.kind == "bars" else TICK_FIELDS
    timestamp_key = "time" if request.kind == "bars" else "time_msc"
    scale = 1 if request.kind == "bars" else 1000
    start, end = utc(request.start), utc(request.end)
    codes: set[str] = set()
    times: list[int] = []
    coverage = {f: sum(row.get(f) is not None for row in rows) for f in fields}
    previous = None
    tick_group = []
    for index, row in enumerate(rows):
        timestamp = row.get(timestamp_key)
        if type(timestamp) is not int:
            codes.add("MALFORMED_TIMESTAMP")
            continue
        try:
            observed = datetime.fromtimestamp(timestamp / scale, timezone.utc)
        except (ValueError, OSError, OverflowError):
            codes.add("MALFORMED_TIMESTAMP")
            continue
        times.append(timestamp)
        if previous is not None and (timestamp < previous or (timestamp == previous and not (request.kind == "ticks" and tick_groups))):
            codes.add("DUPLICATE_OR_NON_MONOTONIC_TIMESTAMP")
        if request.kind == "ticks" and tick_groups:
            if timestamp != previous:
                tick_group = []
            if row in tick_group:
                codes.add("DUPLICATE_TICK_RECORD")
            tick_group.append(row)
        previous = timestamp
        if not start <= observed < end:
            codes.add("TIMESTAMP_OUTSIDE_REQUEST")
        if set(row) != set(fields):
            codes.add("FIELD_SCHEMA_MISMATCH")
        try:
            if request.kind == "bars":
                values = [float(row[k]) for k in ("open", "high", "low", "close")]
                if any(not math.isfinite(v) or v <= 0 for v in values):
                    codes.add("INVALID_PRICE")
                issues = []
                _check_bar_values(
                    OHLCVBar(observed.isoformat(), *values, float(row["tick_volume"])),
                    request.timeframe, index, issues,
                )
                codes.update(issue.code for issue in issues)
                if timestamp % timeframe_duration_seconds(request.timeframe):
                    codes.add("BAR_TIMESTAMP_NOT_ALIGNED")
                for field in ("spread", "tick_volume", "real_volume"):
                    if type(row[field]) is not int or row[field] < 0:
                        codes.add("INVALID_SPREAD_OR_VOLUME")
            else:
                bid, ask = float(row["bid"]), float(row["ask"])
                if not all(math.isfinite(v) and v > 0 for v in (bid, ask)) or ask < bid:
                    codes.add("INVALID_BID_ASK")
                if not math.isfinite(float(row["last"])) or float(row["last"]) < 0:
                    codes.add("INVALID_LAST_PRICE")
                if type(row["flags"]) is not int or row["flags"] < 0 or row["time"] != timestamp // 1000:
                    codes.add("INVALID_TICK_FIELDS")
        except (KeyError, TypeError, ValueError, OverflowError):
            codes.add("MALFORMED_RECORD")
    gaps = []
    missing = closures = 0
    if request.kind == "bars":
        present = set(times)
        step = timeframe_duration_seconds(request.timeframe)
        for value in range(int(start.timestamp()), int(end.timestamp()), step):
            when = datetime.fromtimestamp(value, timezone.utc)
            if not _session_open(when, request.session_policy):
                closures += 1
                continue
            if value not in present:
                missing += 1
                if gaps and gaps[-1]["end"] == when.isoformat():
                    gaps[-1]["end"] = (when + timedelta(seconds=step)).isoformat()
                elif len(gaps) < 100:
                    gaps.append({"start": when.isoformat(), "end": (when + timedelta(seconds=step)).isoformat()})
        if any(not _session_open(datetime.fromtimestamp(t, timezone.utc), request.session_policy) for t in times):
            codes.add("SESSION_POLICY_MISMATCH")
    invalid = codes - {"SESSION_POLICY_MISMATCH"}
    status = (
        "INVALID" if invalid else "INSUFFICIENT_HISTORY" if len(rows) < request.warmup_records
        else "PARTIAL" if missing or codes or request.kind == "ticks" else "VERIFIED"
    )
    return {
        "status": status, "issues": sorted(codes), "field_coverage": coverage,
        "required_warmup_records": request.warmup_records,
        "missing_expected_bars": missing, "declared_closed_bar_slots": closures,
        "gap_intervals_first_100": gaps,
        "first_timestamp": datetime.fromtimestamp(times[0] / scale, timezone.utc).isoformat() if times else None,
        "last_timestamp": datetime.fromtimestamp(times[-1] / scale, timezone.utc).isoformat() if times else None,
        "limitations": [
            "Weekday holidays/maintenance are not automatically excluded.",
            "Session policy is a declared research assumption, not broker schedule evidence.",
            *(["Tick-history completeness is unverified; " + ("distinct simultaneous ticks retained." if tick_groups else "simultaneous timestamps are not resolved.")] if request.kind == "ticks" else []),
        ],
    }


def persist_dataset(
    root: Path, request: HistoricalDataRequest, rows: Sequence[Mapping[str, Any]],
    *, contract: Mapping[str, Any], acquired_at: str, overlap_rows: int = 0,
    source_revision: str = "UNKNOWN", exporter_source_checksum: str = "UNKNOWN",
    acquisition_failures: Sequence[Mapping[str, str]] = (),
    terminal_history_bar_limit: int | None = None, mt5_package_version: str = "UNKNOWN",
) -> tuple[Path, dict]:
    acquired = utc(acquired_at)
    if utc(request.end) > acquired:
        raise ValueError("REQUEST_INCLUDES_UNCOMPLETED_HISTORY")
    quality = assess_quality(rows, request, tick_groups=True)
    if acquisition_failures:
        quality["issues"] = sorted({*quality["issues"], "ACQUISITION_FAILURE"})
        if quality["status"] == "VERIFIED":
            quality["status"] = "PARTIAL"
    if quality["status"] == "INVALID":
        raise ValueError("INVALID_DATASET:" + ",".join(quality["issues"]))
    payload = b"".join(canonical_bytes(dict(row)) + b"\n" for row in rows)
    contract_fields = {
        "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size",
        "volume_min", "volume_max", "volume_step", "currency_profit", "currency_margin",
        "trade_stops_level", "trade_mode",
    }
    if set(contract) - contract_fields:
        raise ValueError("UNSAFE_CONTRACT_METADATA_FIELDS")
    identity = {
        "request": asdict(request), "data_checksum": checksum(payload), "contract": dict(contract),
        "exporter_version": EXPORTER_VERSION, "exporter_source_checksum": exporter_source_checksum,
        "acquisition_failures": list(acquisition_failures),
    }
    dataset_id = "research_dataset_" + checksum(canonical_bytes(identity))[:24]
    folder = root / dataset_id
    manifest = {
        "schema_version": SCHEMA, "dataset_id": dataset_id,
        **identity, "source": "MT5_AUTHENTICATED_LOCAL_TERMINAL", "account_environment": "DEMO",
        "exporter_version": EXPORTER_VERSION, "acquired_at": acquired.isoformat(),
        "source_revision": source_revision, "artifact_type": "RESEARCH_DATASET",
        "execution_authority": False,
        "terminal_history_bar_limit": terminal_history_bar_limit,
        "mt5_package_version": mt5_package_version,
        "record_count": len(rows), "chunk_overlap_rows_removed": overlap_rows,
        "contract_metadata_observed_at": acquired.isoformat(),
        "contract_metadata_historical_validity": "UNKNOWN_CURRENT_SNAPSHOT_ONLY",
        "price_encoding": "unrounded_source_float64_JSON_roundtrip",
        "quality": quality,
    }
    manifest["manifest_checksum"] = checksum(canonical_bytes(manifest))
    if folder.exists():
        existing, _ = load_dataset(folder, require_verified=False)
        if existing["data_checksum"] != manifest["data_checksum"]:
            raise ValueError("EXISTING_DATASET_CONFLICT")
        return folder, existing
    folder.mkdir(parents=True)
    with (folder / "data.jsonl").open("xb") as stream:
        stream.write(payload)
    with (folder / "manifest.json").open("xb") as stream:
        stream.write(canonical_bytes(manifest) + b"\n")
    return folder, manifest


def load_dataset(
    folder: Path, *, require_verified: bool = True, expected_manifest_checksum: str | None = None,
) -> tuple[dict, list[dict]]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    protected = dict(manifest)
    recorded = protected.pop("manifest_checksum")
    if manifest.get("schema_version") != SCHEMA or manifest.get("exporter_version") not in {"mt5-research-export/v1", EXPORTER_VERSION} or checksum(canonical_bytes(protected)) != recorded:
        raise ValueError("DATASET_MANIFEST_INTEGRITY_INVALID")
    if expected_manifest_checksum is not None and recorded != expected_manifest_checksum:
        raise ValueError("RESEARCH_SOURCE_PIN_MISMATCH")
    payload = (folder / "data.jsonl").read_bytes()
    if checksum(payload) != manifest["data_checksum"]:
        raise ValueError("DATASET_CHECKSUM_MISMATCH")
    rows = [json.loads(line) for line in payload.splitlines()]
    request = HistoricalDataRequest(**manifest["request"])
    identity = {k: manifest[k] for k in (
        "request", "data_checksum", "contract", "exporter_version",
        "exporter_source_checksum", "acquisition_failures",
    )}
    if manifest["dataset_id"] != "research_dataset_" + checksum(canonical_bytes(identity))[:24] or folder.name != manifest["dataset_id"]:
        raise ValueError("DATASET_IDENTITY_MISMATCH")
    quality = assess_quality(rows, request, tick_groups=manifest["exporter_version"] == "mt5-research-export/v2")
    if manifest.get("acquisition_failures"):
        quality["issues"] = sorted({*quality["issues"], "ACQUISITION_FAILURE"})
        if quality["status"] == "VERIFIED":
            quality["status"] = "PARTIAL"
    if quality != manifest["quality"] or len(rows) != manifest["record_count"]:
        raise ValueError("DATASET_QUALITY_MISMATCH")
    if require_verified and quality["status"] != "VERIFIED":
        raise ValueError("PRIMARY_RESEARCH_REQUIRES_VERIFIED_DATA")
    return manifest, rows


def as_market_snapshot(folder: Path) -> MarketSnapshot:
    manifest, rows = load_dataset(folder)
    request = HistoricalDataRequest(**manifest["request"])
    if request.kind != "bars":
        raise ValueError("OHLCV_DATASET_REQUIRED")
    return MarketSnapshot(
        symbol=request.canonical_symbol, timeframe=request.timeframe,
        bars=[OHLCVBar(
            datetime.fromtimestamp(r["time"], timezone.utc).isoformat(),
            r["open"], r["high"], r["low"], r["close"], r["tick_volume"],
            request.timeframe, request.broker_symbol, "mt5_historical_research",
        ) for r in rows],
        source="mt5_historical_research", fetched_at=manifest["acquired_at"],
        provider_name="offline_research", data_quality="COMPLETE",
    )

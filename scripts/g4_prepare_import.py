"""Prepare inert, pinned G4 custom-symbol import media. Never invoke MT5."""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path

from src.services.trading.research.historical_dataset import HistoricalDataRequest, canonical_bytes, checksum, load_dataset
from src.services.trading.research.input_package import _publish


ALLOWLIST = {"bars.tsv", "ticks.tsv", "source_ticks.jsonl", "G4Import.mq5", "G4ImportPins.mqh", "README.txt", "g4_import_media.ps1"}
RESEARCH_SOURCE = Path(__file__).resolve().parents[1] / "tools/mt5_bridge/research/G4Import.mq5"
V8_IMPORTER_SHA256 = "39ca5be17a0ab0c3f3827f98d0e38af91c18afcbb5883243f444137f725d86a3"


def prepare(package_bytes, expected_sha256, *, prestart_folder=None, prestart_manifest_sha256=None, recovery_mode=None):
    if recovery_mode not in (None, "CONFIGURATION_ONLY", "IMPORT"):
        raise ValueError("RECOVERY_MODE_INVALID")
    if checksum(package_bytes) != expected_sha256:
        raise ValueError("CAPTURE_PACKAGE_PIN_MISMATCH")
    package = json.loads(package_bytes)
    strategy, files = package["strategy"], package["files"]
    if (strategy["purpose"] != "CAPTURE_ONLY" or strategy["execution_allowed"] is not False
            or strategy["simulate_orders"] is not False or strategy["financial_certification"] is not False
            or checksum(canonical_bytes(strategy)) != package["strategy_sha256"]
            or checksum(canonical_bytes(package["capture"])) != strategy["capture_sha256"]
            or any(checksum(value.encode()) != package["file_sha256"].get(name) for name, value in files.items())
            or checksum(files["source_ticks.jsonl"].encode()) != strategy["tick_source"]["data_sha256"]
            or checksum(files["ticks.tsv"].encode()) != strategy["ticks_tsv_sha256"]
            or checksum(files["bars.tsv"].encode()) != strategy["bars_tsv_sha256"]):
        raise ValueError("CAPTURE_BINDING_INVALID")
    symbol = "G4CAP_" + strategy["tick_source"]["data_sha256"][:12]
    if strategy["custom_symbol"] != symbol:
        raise ValueError("CUSTOM_SYMBOL_IDENTITY_INVALID")
    bars = list(csv.reader(io.StringIO(files["bars.tsv"]), delimiter="\t"))
    ticks = list(csv.reader(io.StringIO(files["ticks.tsv"]), delimiter="\t"))
    if bars.pop(0) != ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<VOL>", "<SPREAD>"]:
        raise ValueError("BAR_SCHEMA_INVALID")
    if ticks.pop(0) != ["<DATE>", "<TIME>", "<BID>", "<ASK>", "<LAST>", "<VOLUME>"]:
        raise ValueError("TICK_SCHEMA_INVALID")
    if len(bars) != strategy["bar_count"] or len(ticks) != strategy["tick_count"] or not 0 < len(ticks) <= 100000:
        raise ValueError("IMPORT_COUNT_INVALID")
    def stamp(row, milliseconds=False):
        text = row[0] + " " + row[1]
        fmt = "%Y.%m.%d %H:%M:%S.%f" if milliseconds else "%Y.%m.%d %H:%M:%S"
        value = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        return int(value.timestamp()) * 1000 + value.microsecond // 1000
    bar_times, tick_times = [], []
    for row in bars:
        if len(row) != 9 or any(not Decimal(v).is_finite() for v in row[2:]):
            raise ValueError("BAR_VALUE_INVALID")
        if any(Decimal(v) <= 0 for v in row[2:6]) or Decimal(row[3]) < max(map(Decimal, row[2:6])) or Decimal(row[4]) > min(map(Decimal, row[2:6])):
            raise ValueError("BAR_VALUE_INVALID")
        if any(not v.isdigit() for v in row[6:]):
            raise ValueError("BAR_VOLUME_INVALID")
        bar_times.append(stamp(row))
    for row in ticks:
        if len(row) != 6 or any(not Decimal(v).is_finite() for v in row[2:]) or Decimal(row[2]) <= 0 or Decimal(row[3]) < Decimal(row[2]) or row[5] != "0":
            raise ValueError("TICK_VALUE_INVALID")
        tick_times.append(stamp(row, True))
    if (any(t % 60000 for t in bar_times) or any(b-a != 60000 for a, b in zip(bar_times, bar_times[1:]))
            or any(b < a for a, b in zip(tick_times, tick_times[1:]))):
        raise ValueError("IMPORT_ORDER_OR_COVERAGE_INVALID")
    source_ticks = [json.loads(line) for line in files["source_ticks.jsonl"].splitlines()]
    if len(source_ticks) != len(ticks) or any(
            t != source["time_msc"] or source["time"] != t // 1000
            or any(Decimal(row[i]) != Decimal(str(source[key])) for i, key in ((2, "bid"), (3, "ask"), (4, "last")))
            for t, row, source in zip(tick_times, ticks, source_ticks)):
        raise ValueError("SOURCE_TICK_PROJECTION_MISMATCH")
    start = package["capture"]["start"]
    prestart_source = None
    original_bar_count = len(bars)
    if (prestart_folder is None) != (prestart_manifest_sha256 is None):
        raise ValueError("PRESTART_SOURCE_PIN_REQUIRED")
    if prestart_folder is not None:
        manifest, earlier = load_dataset(Path(prestart_folder), expected_manifest_checksum=prestart_manifest_sha256)
        request = manifest["request"]
        required_start = start - 100 * 60
        required_end = bar_times[0] // 1000
        if (manifest["source"] != "MT5_AUTHENTICATED_LOCAL_TERMINAL" or manifest["account_environment"] != "DEMO"
                or manifest["execution_authority"] is not False or manifest["artifact_type"] != "RESEARCH_DATASET"
                or request["canonical_symbol"] != strategy["signal_request"]["inputs"][0]["symbol"]
                or request["broker_symbol"] != "XAUUSDm" or request["kind"] != "bars" or request["timeframe"] != "M1"
                or datetime.fromisoformat(request["start"]).timestamp() != required_start
                or datetime.fromisoformat(request["end"]).timestamp() != required_end
                or [r["time"] for r in earlier] != list(range(required_start, required_end, 60))):
            raise ValueError("PRESTART_SCOPE_OR_COVERAGE_MISMATCH")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for row in earlier:
            stamp_value = datetime.fromtimestamp(row["time"], timezone.utc)
            writer.writerow([stamp_value.strftime("%Y.%m.%d"), stamp_value.strftime("%H:%M:%S"),
                *[row[name] for name in ("open", "high", "low", "close", "tick_volume", "real_volume", "spread")]])
        earlier_text = stream.getvalue()
        header, original_rows = files["bars.tsv"].split("\n", 1)
        files = {**files, "bars.tsv": header + "\n" + earlier_text + original_rows}
        bars = list(csv.reader(io.StringIO(earlier_text), delimiter="\t")) + bars
        bar_times = [r["time"] * 1000 for r in earlier] + bar_times
        prestart_source = {"dataset_id": manifest["dataset_id"], "manifest_sha256": manifest["manifest_checksum"],
            "data_sha256": manifest["data_checksum"], "count": len(earlier), "status": manifest["quality"]["status"],
            "usage": "TESTER_PRESTART_ONLY_NOT_STRATEGY_OPTIMIZATION", "research_scope_expanded": False,
            "approval_basis": "EXPLICIT_OPERATOR_G4_PRESTART_REQUEST"}
    before = sum(t < start * 1000 for t in bar_times)
    missing = max(0, 100 - before)
    request = None
    if missing:
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        request = {"canonical_symbol": strategy["signal_request"]["inputs"][0]["symbol"],
            "broker_symbol": "XAUUSDm", "timeframe": "M1", "kind": "bars", "start": iso(start - 100 * 60),
            "end": iso(bar_times[0] // 1000), "warmup_records": 1,
            "session_policy": "UTC_WEEKDAYS_CONSERVATIVE_V1"}
        HistoricalDataRequest(**request)
    # The custom symbol is for quote capture only. Current metadata is not historical contract evidence.
    metadata = {"digits": 3, "point": "0.001", "tick_size": "0.001", "tick_value": "0.1",
        "contract_size": "100", "volume_min": "0.01", "volume_max": "200", "volume_step": "0.01",
        "currency_base": "XAU", "currency_profit": "USD", "currency_margin": "XAU", "calculation_mode": 0,
        "evidence": "CURRENT_DEMO_SNAPSHOT_2026-11-12_NOT_HISTORICAL", "historical_swap": "UNKNOWN"}
    # shortcut: this media qualifies the existing G4 XAUUSDm snapshot only, new symbols need an evidenced snapshot.
    if strategy["signal_request"]["inputs"][0]["symbol"] != "XAUUSD" or original_bar_count != 180 or len(ticks) != 63156:
        raise ValueError("G4_PINNED_SCOPE_REQUIRED")
    payload = {name: files[name].encode() for name in ("bars.tsv", "ticks.tsv", "source_ticks.jsonl")}
    payload["G4Import.mq5"] = RESEARCH_SOURCE.read_bytes()
    source_pin = checksum(payload["G4Import.mq5"])
    # MQL day numbering is Sunday=0; include pre-start bars and the boundary tick minute.
    quote_days = sorted({(datetime.fromtimestamp(t // 1000, timezone.utc).weekday() + 1) % 7
                         for t in bar_times + tick_times})
    quote_days_mask = sum(1 << day for day in quote_days)
    preserved_symbol, guest_subdirectory = symbol, "G4Import"
    recovery = None
    if recovery_mode is not None:
        suffix = checksum(canonical_bytes({"source": source_pin, "package": expected_sha256,
            "bars": checksum(payload["bars.tsv"]), "ticks": checksum(payload["ticks.tsv"]), "mode": recovery_mode}))[:8]
        tag = ("C" if recovery_mode == "CONFIGURATION_ONLY" else "R") + suffix
        # Forex currencies derive from XXXYYY, not the arbitrary research label. Do not change calc mode.
        symbol = metadata["currency_base"] + metadata["currency_profit"] + "_G4" + tag
        guest_subdirectory = "G4Import_" + tag
        recovery = {"mode": recovery_mode, "preserved_symbol": preserved_symbol, "target_symbol": symbol,
            "guest_subdirectory": guest_subdirectory, "previous_importer_sha256": V8_IMPORTER_SHA256,
            "importer_source_sha256": source_pin, "write_authorization": "REQUIRES_EXPLICIT_TARGET_APPROVAL",
            "currency_identity": "OBSERVED_AGAINST_REQUESTED_SNAPSHOT_NO_IMPLICIT_FINANCIAL_FIDELITY",
            "configuration_readback": "DATA_REPRESENTATION_SAFETY_PROVENANCE_AND_SOURCE_QUOTE_DAYS",
            "financial_fidelity": "NOT_CERTIFIED_CURRENT_SNAPSHOT_ONLY"}
    input_folder = json.dumps(guest_subdirectory + "\\")
    payload["G4ImportPins.mqh"] = (f'#define G4_SYMBOL "{symbol}"\n#define G4_BARS {len(bars)}\n#define G4_TICKS {len(ticks)}\n'
        f'#define G4_BAR_PIN "{checksum(payload["bars.tsv"])}"\n#define G4_TICK_PIN "{checksum(payload["ticks.tsv"])}"\n'
        f'#define G4_INPUT_FOLDER {input_folder}\n#define G4_IMPORT_SOURCE_SHA256 "{source_pin}"\n'
        f'#define G4_QUOTE_DAYS_MASK {quote_days_mask}\n'
        f'#define G4_CONFIGURATION_ONLY {str(recovery_mode == "CONFIGURATION_ONLY").lower()}\n').encode()
    payload["g4_import_media.ps1"] = RESEARCH_SOURCE.parents[3].joinpath("scripts/g4_import_media.ps1").read_bytes()
    payload["README.txt"] = ("G4 import only; no Tester authorization. Follow repository native_math_isolation.md.\nRun g4_import_media.ps1 -StageGuest with the manifest pin; it only stages files, never launches binaries.\n"
        f"After separate native approval, compile MQL5/Services/{guest_subdirectory}/G4Import.mq5 with zero errors/warnings.\n"
        f"Use only Navigator > Services > {guest_subdirectory} > G4Import in the existing offline /portable terminal.\n"
        "ApproveImport defaults false. Enable it only for the exact separately approved target write.\n"
        "This is a one-shot chart-independent native helper; it returns immediately, no polling/background listener.\n"
        f"Existing custom symbol is verification-only, never overwritten. Check MQL5/Files/{guest_subdirectory}/roundtrip.csv and Experts log.\n"
        "Flags are import BID/ASK/LAST flags, not original equality. Tick volume=0 is unavailable protocol padding.\n"
        f"{len(bars)} bars and 63156 ticks must match; native PASS remains unverified until guest run. No orders, no Tester.\n"
        "Additional earlier bars are pre-start history only, not added research/optimization data.\n").encode()
    manifest = {"schema_version": "g4-custom-import-media/v1", "capture_package_sha256": expected_sha256,
        "strategy_sha256": package["strategy_sha256"], "custom_symbol": symbol, "shift_seconds": 0,
        "files": {n: checksum(v) for n, v in payload.items()}, "bar_count": len(bars), "tick_count": len(ticks),
        "metadata": metadata, "native_execution_authorized": False, "native_status": "NOT_RUN",
        "configuration_contract": {"version": "g4-data-configuration/v2",
            "required_quote_days": quote_days, "quote_days_mask": quote_days_mask,
            "quote_sessions": "SOURCE_DAYS_00_24_RESEARCH_AVAILABILITY_NOT_BROKER_SESSIONS",
            "data_gate": ["DIGITS", "CHART_MODE", "TRADE_MODE_DISABLED", "POINT", "TICK_SIZE", "DESCRIPTION", "SOURCE_QUOTE_DAYS"],
            "financial_snapshot": "OBSERVE_MISMATCHES_WITHOUT_CHANGING_REQUESTED_METADATA",
            "financial_certification": False, "tester_execution_authorized": False},
        "prestart": {"required_m1_bars": 100, "available_before_capture": before, "missing": missing,
            "earliest_100_bar_time": bar_times[0] // 1000 + 6000,
            "request": request, "acquisition_authorized": False},
        "tester_dates": {"from": "2026.11.04", "to": "2026.11.05", "exact_interval_owner": "PINNED_REPLAY_SCHEDULE"}}
    if prestart_source is not None:
        manifest["prestart"]["source"] = prestart_source
        manifest["prestart"]["acquisition_authorized"] = True
        manifest["original_bars_tsv_sha256"] = strategy["bars_tsv_sha256"]
        manifest["original_research_bar_count"] = original_bar_count
    if recovery is not None:
        manifest["recovery"] = recovery
        payload["README.txt"] += (f"Recovery mode: {recovery_mode}; target {symbol}; preserved {preserved_symbol}.\n"
            f"Stage into new MQL5/Services/{guest_subdirectory}; never replace previous helper or input folder.\n"
            "Configuration-only mode writes no bars/ticks. Neither mode grants native write authorization.\n").encode()
        payload["README.txt"] += ("Data configuration and full API roundtrip are separate from financial certification.\n"
            "Currency/snapshot mismatches remain BLOCKED for financial acceptance; no silent expected-value changes.\n"
            "Quote sessions are required only for weekdays present in pinned bars/ticks, including pre-start/boundary records.\n").encode()
        manifest["files"]["README.txt"] = checksum(payload["README.txt"])
    payload["manifest.json"] = canonical_bytes(manifest)
    return payload, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prestart-folder", type=Path)
    parser.add_argument("--prestart-manifest-sha256")
    parser.add_argument("--recovery-mode", choices=("CONFIGURATION_ONLY", "IMPORT"))
    args = parser.parse_args()
    payload, manifest = prepare(args.package.read_bytes(), args.sha256, prestart_folder=args.prestart_folder,
        prestart_manifest_sha256=args.prestart_manifest_sha256, recovery_mode=args.recovery_mode)
    args.output.mkdir(exist_ok=False)
    for name, content in payload.items():
        with (args.output / name).open("xb") as stream:
            stream.write(content)
    request = manifest["prestart"]["request"]
    request_path = None if request is None else _publish(RESEARCH_SOURCE.parents[3] / "data/research/readiness",
        canonical_bytes(request), prefix="g4_prestart_export_request")
    print(json.dumps({"status": "PREPARED_NOT_NATIVE_VERIFIED", "manifest_sha256": checksum(payload["manifest.json"]),
        "files": sorted(payload), "prestart": manifest["prestart"], "request_path": str(request_path),
        "recovery": manifest.get("recovery")}))


if __name__ == "__main__":
    main()

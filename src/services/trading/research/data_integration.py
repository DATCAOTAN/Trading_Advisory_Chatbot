"""R1 request projection and R2 source binding; no strategy or research execution."""
from base64 import b64decode
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from ..market.timeframes import broker_symbol_for, timeframe_duration_seconds
from .evidence_verification import ApprovedHistoricalSource
from .historical_dataset import BAR_FIELDS, HistoricalDataRequest, canonical_bytes, checksum, load_dataset, utc
from .input_package import _local
from .proposal import ResearchProposal, ResearchScope


@dataclass(frozen=True)
class RevisionHistoricalRequest:
    proposal_id: str
    revision_id: str
    claim_fingerprint: str
    requirement_index: int
    fields: tuple[str, ...]
    lookback: int
    warmup: int
    start: str
    end: str
    split: str | None
    export: HistoricalDataRequest

    @property
    def request_id(self):
        return checksum(canonical_bytes(asdict(self)))


def historical_requests(proposal: ResearchProposal) -> tuple[list[RevisionHistoricalRequest], list[str]]:
    development = proposal.head.content.development
    if development is None:
        return [], ["RESEARCH_SPECIFICATION_REQUIRED"]
    window = development.historical_window
    missing = []
    for name in ("start", "end", "session_policy"):
        if window is None or getattr(window, name) is None:
            missing.append("historical_window." + name)
    complete_window = not missing
    requests = []
    requirements = development.specification.data_requirements
    if not requirements:
        return [], [*missing, "specification.data_requirements"]
    for index, requirement in enumerate(requirements):
        absent = [name for name in ("dataset", "usage", "symbol", "timeframe", "fields", "lookback_bars", "warmup_bars")
                  if getattr(requirement, name) is None or getattr(requirement, name) == ()]
        if absent:
            missing.extend(f"data_requirements[{index}].{name}" for name in absent)
            continue
        if requirement.dataset != "OHLCV" or requirement.usage != "RESEARCH_ONLY":
            missing.append(f"data_requirements[{index}].OHLCV_RESEARCH_ONLY_REQUIRED")
            continue
        if not complete_window:
            continue
        step = timeframe_duration_seconds(requirement.timeframe)
        if not step or any(bound.timestamp() % step for bound in (window.start, window.end, window.split) if bound):
            missing.append(f"data_requirements[{index}].TIMEFRAME_OR_WINDOW_ALIGNMENT_INVALID")
            continue
        if requirement.lookback_bars > (window.end - window.start).total_seconds() / step:
            missing.append(f"data_requirements[{index}].LOOKBACK_EXCEEDS_DECLARED_WINDOW")
            continue
        # Exporter warmup_records is a minimum record count, not pre-window context.
        # Fetch real preceding bars explicitly; never manufacture them at session gaps.
        try:
            exported_start = window.start - timedelta(seconds=requirement.warmup_bars * step)
            export = HistoricalDataRequest(requirement.symbol, broker_symbol_for(requirement.symbol),
                requirement.timeframe, exported_start.isoformat(), window.end.isoformat(),
                "bars", max(1, requirement.lookback_bars), window.session_policy)
        except (ValueError, OverflowError):
            missing.append(f"data_requirements[{index}].HISTORICAL_REQUEST_UNSUPPORTED")
            continue
        requests.append(RevisionHistoricalRequest(proposal.proposal_id, proposal.head.revision_id,
            proposal.head.content.hypothesis_fingerprint(), index, tuple(dict.fromkeys(("time", *requirement.fields))),
            requirement.lookback_bars, requirement.warmup_bars, window.start.isoformat(), window.end.isoformat(),
            window.split.isoformat() if window.split else None, export))
    return requests, missing


def matching_history(record: dict, request: RevisionHistoricalRequest) -> tuple[str, dict | None]:
    for key, item in reversed(list(record.get("historical", {}).items())):
        stored = item.get("request", {})
        if (stored.get("proposal_id") == request.proposal_id
                and stored.get("export") == asdict(request.export)
                and stored.get("start") == request.start and stored.get("end") == request.end
                and stored.get("requirement_index") == request.requirement_index):
            return key, item
    return request.request_id, None


def cost_readiness(proposal: ResearchProposal) -> dict:
    development = proposal.head.content.development
    entries = development.transaction_costs if development else ()
    missing, declared = [], {}
    for name in ("spread", "commission", "swap", "slippage"):
        found = [item for item in entries if item.name and item.name.casefold() == name]
        if len(found) != 1 or type(found[0].value) not in {int, float} or not found[0].unit or not found[0].definition:
            missing.append(name)
        else:
            prior, author = None, None
            for revision in proposal.revisions:
                stage = revision.content.development
                current = tuple(item for item in stage.transaction_costs if item.name and item.name.casefold() == name) if stage else ()
                if current != prior:
                    author = revision.author
                prior = current
            if author != "USER_AUTHORED":
                missing.append(name + ".source_confirmation")
            declared[name] = {**found[0].model_dump(mode="json", exclude_none=True),
                              "provenance": author, "broker_verified": False}
    return {"status": "MISSING" if missing else "DECLARED_ASSUMPTIONS_NOT_BROKER_VERIFIED",
            "missing": missing, "assumptions": declared}


def dataset_folder(root: Path, dataset_id: str) -> Path:
    if not isinstance(dataset_id, str) or not re.fullmatch(r"research_dataset_[a-f0-9]{24}", dataset_id):
        raise ValueError("RESEARCH_DATASET_ID_INVALID")
    return _local(_local(root / "mt5") / dataset_id)


def receive_history_export(root: Path, response: dict, expected: HistoricalDataRequest) -> tuple[Path, dict]:
    if response.get("status") != "EXPORTED" or response.get("execution_allowed") is not False:
        raise ValueError("RESEARCH_HISTORY_ACQUISITION_BLOCKED")
    try:
        manifest_bytes = response["manifest"].encode("utf-8")
        manifest = json.loads(manifest_bytes)
        payload = b64decode(response["data_base64"], validate=True)
        if len(payload) > 32 * 1024 * 1024 or manifest["request"] != asdict(expected):
            raise ValueError("RESEARCH_EXPORT_REQUEST_MISMATCH")
        target = dataset_folder(root, manifest["dataset_id"])
        _local(root / "mt5").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=root / "mt5") as scratch:
            staged = Path(scratch) / target.name
            staged.mkdir()
            (staged / "manifest.json").write_bytes(manifest_bytes)
            (staged / "data.jsonl").write_bytes(payload)
            load_dataset(staged, require_verified=False, expected_manifest_checksum=manifest["manifest_checksum"])
            if target.exists():
                load_dataset(target, require_verified=False, expected_manifest_checksum=manifest["manifest_checksum"])
            else:
                staged.rename(target)
        return target, manifest
    except (KeyError, TypeError, UnicodeError, OSError) as exc:
        raise ValueError("RESEARCH_EXPORT_ARTIFACT_INVALID") from None


def approved_sources(root: Path, record: dict, scope: ResearchScope) -> tuple[ApprovedHistoricalSource, ...]:
    sources = {}
    for item in record.get("historical", {}).values():
        approval = item.get("source_approval")
        if approval and approval.get("scope") == scope.model_dump(mode="json"):
            if approval.get("purpose") != "READ_ONLY_HISTORICAL_RESEARCH" or not re.fullmatch(r"[a-f0-9]{64}", approval.get("manifest_sha256", "")):
                raise ValueError("RESEARCH_SOURCE_APPROVAL_INVALID")
            if any(approval.get(key) != item.get(key) for key in ("dataset_id", "manifest_sha256", "data_sha256")):
                raise ValueError("RESEARCH_SOURCE_APPROVAL_INVALID")
            source = ApprovedHistoricalSource(dataset_folder(root, approval["dataset_id"]), approval["manifest_sha256"], scope)
            sources[(source.folder.name, source.manifest_checksum)] = source
    return tuple(sources.values())


def inspect_historical_data(root: Path, proposal: ResearchProposal, request: RevisionHistoricalRequest, item: dict | None) -> dict:
    result = {"request_id": request.request_id, "request": asdict(request), "acquisition": "NOT_ACQUIRED",
              "approval": "NOT_APPROVED", "coverage": "NOT_CHECKED", "available_fields": [],
              "missing_fields": list(request.fields), "is_oos": "MISSING_SPLIT" if request.split is None else "NOT_CHECKED",
              "costs": cost_readiness(proposal), "blockers": [], "execution_allowed": False}
    if item is None:
        result["blockers"].append("RESEARCH_DATASET_NOT_ACQUIRED")
        return result
    result["acquisition"] = item["status"]
    if item["status"] != "ACQUIRED":
        result["blockers"].append(item.get("reason", "RESEARCH_HISTORY_ACQUISITION_INCOMPLETE"))
        return result
    folder = dataset_folder(root, item["dataset_id"])
    try:
        manifest, rows = load_dataset(folder, require_verified=False, expected_manifest_checksum=item["manifest_sha256"])
    except OSError:
        result["coverage"] = "SOURCE_UNAVAILABLE"
        result["blockers"].append("RESEARCH_SOURCE_UNAVAILABLE")
        return result
    except (ValueError, KeyError, TypeError):
        result["coverage"] = "INVALID"
        result["blockers"].append("RESEARCH_SOURCE_ARTIFACT_INVALID")
        return result
    if manifest["request"] != asdict(request.export):
        raise ValueError("RESEARCH_EXPORT_REQUEST_MISMATCH")
    if manifest["source"] != "MT5_AUTHENTICATED_LOCAL_TERMINAL" or manifest["account_environment"] != "DEMO" or manifest["execution_authority"] is not False:
        raise ValueError("RESEARCH_SOURCE_PROVENANCE_MISMATCH")
    if not utc(manifest["request"]["end"]) <= utc(manifest["acquired_at"]) <= datetime.now().astimezone():
        raise ValueError("RESEARCH_SOURCE_TIME_INVALID")
    available = {row["time"] for row in rows}
    step = timeframe_duration_seconds(request.export.timeframe)
    start, end = int(utc(request.start).timestamp()), int(utc(request.end).timestamp())
    research = [row for row in rows if start <= row["time"] < end]
    present_fields = [field for field in BAR_FIELDS if rows and all(row.get(field) is not None for row in rows)]
    result.update(dataset_id=manifest["dataset_id"], manifest_sha256=manifest["manifest_checksum"],
                  data_sha256=manifest["data_checksum"], coverage=manifest["quality"],
                  available_fields=present_fields, missing_fields=sorted(set(request.fields) - set(present_fields)),
                  research_bar_count=len(research), warmup_bar_count=sum(row["time"] < start for row in rows),
                  source=manifest["source"], approved_scope=item.get("source_approval"))
    result["cost_evidence"] = {
        "spread": {"available": "spread" in present_fields, "field": "spread", "unit": "BROKER_POINTS"},
        "commission": "NOT_EXPORTED", "swap": "NOT_EXPORTED", "slippage": "NOT_OBSERVABLE_FROM_OHLCV",
        "contract_metadata_historical_validity": manifest.get("contract_metadata_historical_validity", "UNKNOWN"),
    }
    if item.get("source_approval"):
        result["approval"] = "SOURCE_APPROVED_ONLY"
    if manifest["quality"]["status"] != "VERIFIED" or len(research) < request.lookback:
        result["blockers"].append("RESEARCH_COVERAGE_INSUFFICIENT")
    if result["missing_fields"]:
        result["blockers"].append("RESEARCH_INPUT_FIELDS_UNAVAILABLE")
    boundaries = [start] + ([int(utc(request.split).timestamp())] if request.split else [])
    if request.warmup > len(rows) or any(
        boundary - offset * step not in available for boundary in boundaries for offset in range(1, request.warmup + 1)
    ):
        result["blockers"].append("RESEARCH_WARMUP_INSUFFICIENT")
    if request.split:
        split = int(utc(request.split).timestamp())
        result["partition_counts"] = {"IS": sum(start <= t < split for t in available),
                                      "OOS": sum(split <= t < end for t in available)}
        result["is_oos"] = "BOUNDARIES_DEFINED" if all(result["partition_counts"].values()) else "INSUFFICIENT_COVERAGE"
    else:
        result["blockers"].append("RESEARCH_IS_OOS_SPLIT_REQUIRED")
    if result["costs"]["missing"]:
        result["blockers"].append("RESEARCH_COST_ASSUMPTIONS_REQUIRED")
    if result["approval"] == "NOT_APPROVED":
        result["blockers"].append("RESEARCH_SOURCE_NOT_APPROVED")
    return result

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (  # noqa: E402
    MT5PositionLifecycleSupervisor,
    MT5PositionSupervisorConfig,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only MT5 position lifecycle supervisor"
    )
    parser.add_argument("--once", action="store_true", help="Run one read-only cycle and stop")
    parser.add_argument("--interval-seconds", type=float)
    parser.add_argument("--history-window-seconds", type=int)
    parser.add_argument("--execution-journal")
    parser.add_argument("--lifecycle-journal")
    parser.add_argument("--bridge-url")
    return parser


def _config(args: argparse.Namespace) -> MT5PositionSupervisorConfig:
    config = MT5PositionSupervisorConfig.from_config()
    changes = {}
    if args.interval_seconds is not None:
        changes["interval_seconds"] = args.interval_seconds
    if args.history_window_seconds is not None:
        changes["history_window_seconds"] = args.history_window_seconds
    if args.execution_journal:
        changes["execution_journal_path"] = args.execution_journal
    if args.lifecycle_journal:
        changes["lifecycle_journal_path"] = args.lifecycle_journal
    if args.bridge_url:
        changes["bridge_url"] = args.bridge_url
    return replace(config, **changes)


def _safe_output(status) -> dict:
    return {
        "account_fingerprint_prefix": status.account_fingerprint_prefix,
        "records_inspected": status.records_inspected,
        "lifecycle_state_counts": status.lifecycle_state_counts,
        "discrepancy_count": status.discrepancy_count,
        "cycle_duration_ms": round(status.last_cycle_duration_ms, 3),
        "health_status": status.supervisor_status,
        "health_reason": status.health_reason,
        "bridge_available": status.bridge_available,
        "account_context_match": status.account_context_match,
        "metadata_redacted": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    supervisor = MT5PositionLifecycleSupervisor(_config(args))
    if args.once:
        status = supervisor.run_once()
        print(json.dumps(_safe_output(status), ensure_ascii=True, sort_keys=True))
        return 0 if status.supervisor_status in {"HEALTHY", "DEGRADED"} else 1
    supervisor.start()
    try:
        while True:
            time.sleep(supervisor.config.interval_seconds)
            print(json.dumps(_safe_output(supervisor.status()), ensure_ascii=True, sort_keys=True))
    except KeyboardInterrupt:
        supervisor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
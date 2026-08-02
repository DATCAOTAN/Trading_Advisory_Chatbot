from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.live_data_service import get_live_service  # noqa: E402
from src.services.trading.decision.autonomous_candidate_monitor import (  # noqa: E402
    DEFAULT_MONITOR_JOURNAL_PATH,
    AutonomousCandidateMonitor,
    AutonomousCandidateMonitorJournal,
)
from src.services.trading.decision.operator_candidate_generation import (  # noqa: E402
    AuthoritativeAutonomousInputAssembler,
)
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import (  # noqa: E402
    MarketSnapshotBundleBuilder,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Monitor completed bars for non-executable autonomous candidates."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframes", required=True, help="Comma-separated profile")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    parser.add_argument("--journal", default=DEFAULT_MONITOR_JOURNAL_PATH)
    args = parser.parse_args(argv)
    timeframes = tuple(item.strip().upper() for item in args.timeframes.split(",") if item.strip())

    live_service = get_live_service()
    monitor = AutonomousCandidateMonitor(
        feature_service=LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(live_service.provider)
        ),
        input_assembler=AuthoritativeAutonomousInputAssembler(live_service),
        journal=AutonomousCandidateMonitorJournal(args.journal),
    )
    while True:
        result = monitor.run_once(symbol=args.symbol, timeframes=timeframes)
        print(json.dumps(result.to_public_dict(), ensure_ascii=True, sort_keys=True), flush=True)
        if not args.watch:
            return 0 if result.status not in {"BLOCKED", "RESULT_UNKNOWN"} else 2
        time.sleep(max(1.0, args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())

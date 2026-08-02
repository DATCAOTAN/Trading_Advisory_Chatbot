from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.live_data_service import get_live_service  # noqa: E402
from src.services.trading.decision.autonomous_candidate_monitor import (  # noqa: E402
    DEFAULT_MONITOR_JOURNAL_PATH,
    AutonomousCandidateMonitorJournal,
)
from src.services.trading.decision.autonomous_trading_coordinator import (  # noqa: E402
    AutonomousTradingCoordinator,
)
from src.services.trading.decision.operator_candidate_generation import (  # noqa: E402
    AuthoritativeAutonomousInputAssembler,
)
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import (  # noqa: E402
    MarketSnapshotBundleBuilder,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (  # noqa: E402
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (  # noqa: E402
    TradingAuthorityService,
    TradingAuthorityStore,
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
    adapter = MT5LiveAdapterDisabled()

    def account_context():
        payload = adapter.capture_account_context()
        payload.update(
            {
                "status": "OK",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "account_is_demo": payload.get("account_environment") == "DEMO",
            }
        )
        return payload

    coordinator = AutonomousTradingCoordinator(
        feature_service=LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(live_service.provider)
        ),
        input_assembler=AuthoritativeAutonomousInputAssembler(live_service),
        account_context_provider=account_context,
        authority_service=TradingAuthorityService(TradingAuthorityStore()),
        monitor_journal=AutonomousCandidateMonitorJournal(args.journal),
    )
    try:
        while True:
            result = coordinator.run_once(symbol=args.symbol, timeframes=timeframes)
            print(json.dumps(result.to_public_dict(), ensure_ascii=True, sort_keys=True), flush=True)
            if not args.watch:
                return 0 if result.status not in {"BLOCKED", "RESULT_UNKNOWN"} else 2
            time.sleep(max(1.0, args.interval_seconds))
    except KeyboardInterrupt:
        return 130
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())

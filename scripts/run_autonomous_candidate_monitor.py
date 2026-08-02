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
from src.config import Config  # noqa: E402
from src.services.trading.decision.autonomous_candidate_monitor import (  # noqa: E402
    DEFAULT_MONITOR_JOURNAL_PATH,
    AutonomousCandidateMonitorJournal,
)
from src.services.trading.decision.autonomous_trading_coordinator import (  # noqa: E402
    AutonomousTradingCoordinator,
    production_mandate_context,
)
from src.services.trading.decision.autonomous_orchestrator import AutonomousDecisionJournal  # noqa: E402
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
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (  # noqa: E402
    ApprovalPreSubmitLifecycleService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (  # noqa: E402
    MT5PreSubmitJournalStore,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (  # noqa: E402
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.proposal.intent_store import ProposalIntentJournalStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Monitor completed bars for non-executable autonomous candidates."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframes", required=True, help="Comma-separated profile")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    parser.add_argument("--journal", default=DEFAULT_MONITOR_JOURNAL_PATH)
    parser.add_argument("--mandate-id", default="")
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

    authority_service = TradingAuthorityService(TradingAuthorityStore())
    approval_service = ApprovalPreSubmitLifecycleService(
        candidate_journal=AutonomousDecisionJournal(
            Config.TRADING_AUTONOMOUS_DECISION_JOURNAL_PATH,
            Config.TRADING_AUTONOMOUS_DECISION_MAX_READ_RECORDS,
        ),
        confirmation_store=ProposalIntentJournalStore(),
        pre_submit_store=MT5PreSubmitJournalStore(
            Config.TRADING_MT5_PRE_SUBMIT_JOURNAL_PATH,
            Config.TRADING_MT5_PRE_SUBMIT_MAX_READ_RECORDS,
        ),
        authority_service=authority_service,
    )

    def mandate_context(candidate, inputs):
        current = account_context()
        return production_mandate_context(
            candidate,
            inputs,
            authority_service=authority_service,
            mandate_id=args.mandate_id,
            account_context_fingerprint=current["account_context_fingerprint"],
            kill_switch_engaged=(
                Config.TRADING_EXECUTION_KILL_SWITCH
                or Config.TRADING_MT5_KILL_SWITCH_ENGAGED
            ),
        )

    coordinator = AutonomousTradingCoordinator(
        feature_service=LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(live_service.provider)
        ),
        input_assembler=AuthoritativeAutonomousInputAssembler(live_service),
        account_context_provider=account_context,
        authority_service=authority_service,
        approval_service=approval_service,
        mandate_context_provider=mandate_context,
        execution_adapter=adapter,
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

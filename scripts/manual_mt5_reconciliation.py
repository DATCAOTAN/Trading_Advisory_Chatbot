from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationRequest,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual read-only reconciliation of one protected MT5 execution record."
    )
    parser.add_argument(
        "--request-file",
        required=True,
        help="Protected controlled execution request JSON produced by the application",
    )
    args = parser.parse_args(argv)

    config = MT5LiveAdapterPreSubmitConfig.from_config()
    if not config.reconciliation_enabled or not config.execution_auth_token:
        print("status=BLOCKED")
        print("reason=RECONCILIATION_DISABLED")
        return 2

    payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    controlled = MT5ControlledExecutionRequest(**payload)
    reconciliation = MT5ReconciliationRequest.from_controlled_request(controlled)
    adapter = MT5LiveAdapterDisabled(config=config)
    account = adapter.capture_account_context()
    print("account_context_redacted=true")
    print(f"account_fingerprint_prefix={account['account_context_fingerprint'][:12]}")
    print(f"server_redacted={account['server_redacted']}")
    print(f"currency={account['currency']}")
    print(f"trade_mode={account['trade_mode']}")
    if account["account_context_fingerprint"] != reconciliation.expected_account_context_fingerprint:
        print("status=BLOCKED")
        print("reason=ACCOUNT_CONTEXT_CHANGED")
        return 3

    typed = input(f"Type exactly '{config.reconciliation_confirmation_phrase}' to query MT5 history: ")
    receipt = adapter.reconcile_controlled(reconciliation, typed_confirmation=typed)
    print(f"status={receipt.status}")
    print(f"evidence_classification={receipt.evidence_classification}")
    print(f"original_execution_state={receipt.original_execution_state}")
    print(f"resulting_execution_state={receipt.resulting_execution_state}")
    print(f"retry_decision={receipt.retry_decision}")
    print(f"order_reference_present={str(receipt.order_reference_present).lower()}")
    print(f"deal_reference_present={str(receipt.deal_reference_present).lower()}")
    print(f"position_reference_present={str(receipt.position_reference_present).lower()}")
    print("automatic_retry_allowed=false")
    print("metadata_redacted=true")
    return 0 if receipt.status in {"CONFIRMED", "INCONCLUSIVE", "FAILED", "NOT_REQUIRED"} else 4


if __name__ == "__main__":
    raise SystemExit(main())

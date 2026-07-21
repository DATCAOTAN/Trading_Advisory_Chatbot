from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import MT5ControlledExecutionRequest
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual, one-shot controlled MT5 execution. Never use from automated verification."
    )
    parser.add_argument("--request-file", required=True, help="Protected request JSON produced by the application")
    args = parser.parse_args(argv)

    config = MT5LiveAdapterPreSubmitConfig.from_config()
    if (
        not config.controlled_execution_enabled
        or not config.live_adapter_enabled
        or config.live_adapter_hard_block
        or not config.allow_live_submission
        or not config.allow_order_send
        or config.kill_switch_engaged
        or not config.execution_auth_token
    ):
        print("status=BLOCKED")
        print("reason=CONTROLLED_EXECUTION_DISABLED")
        return 2

    payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    request = MT5ControlledExecutionRequest(**payload)
    adapter = MT5LiveAdapterDisabled(config=config)
    account = adapter.capture_account_context()
    print("account_context_redacted=true")
    print(f"account_fingerprint_prefix={account['account_context_fingerprint'][:12]}")
    print(f"server_redacted={account['server_redacted']}")
    print(f"currency={account['currency']}")
    print(f"trade_mode={account['trade_mode']}")
    if account["account_context_fingerprint"] != request.expected_account_context_fingerprint:
        print("status=BLOCKED")
        print("reason=ACCOUNT_CONTEXT_MISMATCH")
        return 3

    typed = input(f"Type exactly '{config.execution_confirmation_phrase}' to submit once: ")
    receipt = adapter.submit_prepared_request(request, typed_confirmation=typed)
    print(f"status={receipt.status}")
    print(f"idempotency_status={receipt.idempotency_status}")
    print(f"order_sent={str(receipt.order_sent).lower()}")
    print(f"ticket_present={str(receipt.ticket_present).lower()}")
    print(f"deal_present={str(receipt.deal_present).lower()}")
    print("metadata_redacted=true")
    return 0 if receipt.status in {"ACCEPTED", "REJECTED", "UNKNOWN"} else 4


if __name__ == "__main__":
    raise SystemExit(main())

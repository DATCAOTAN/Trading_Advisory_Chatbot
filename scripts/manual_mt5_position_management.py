from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit import (
    MT5ControlledManagementRequest,
    MT5LiveAdapterDisabled,
    MT5PositionLifecycleSupervisor,
    management_confirmation_phrase,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage exactly one protected MT5 order or position after explicit confirmation."
    )
    parser.add_argument("--request-file", required=True, help="Protected management request JSON")
    args = parser.parse_args(argv)

    config = MT5LiveAdapterPreSubmitConfig.from_config()
    if _default_blocker(config):
        print("status=BLOCKED")
        print("reason=CONTROLLED_MANAGEMENT_DISABLED")
        return 2

    try:
        payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("MANAGEMENT_REQUEST_INVALID")
        request = MT5ControlledManagementRequest(**payload)
        request.validate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print("status=BLOCKED")
        print(f"reason={_safe_reason(exc)}")
        return 3

    intent_allowed = {
        "CANCEL_PENDING_ORDER": config.management_cancel_allowed,
        "MODIFY_POSITION_PROTECTION": config.management_protection_modification_allowed,
        "CLOSE_POSITION": config.management_position_close_allowed,
    }.get(request.management_intent, False)
    if not intent_allowed:
        print("status=BLOCKED")
        print("reason=MANAGEMENT_INTENT_DISABLED")
        return 2

    safe = request.as_redacted_dict()
    print(f"management_intent={safe['management_intent']}")
    print(f"symbol={safe['symbol']}")
    print(f"lifecycle_state={safe['lifecycle_state']}")
    print(f"account_fingerprint_prefix={safe['expected_account_fingerprint_prefix']}")
    print("broker_reference_redacted=true")
    phrase = management_confirmation_phrase(request.management_intent)
    typed = input(f"Type exactly '{phrase}' to manage one existing MT5 target: ")

    adapter = MT5LiveAdapterDisabled(config=config)
    receipt = adapter.manage_prepared_request(request, typed_confirmation=typed)
    print(f"status={receipt.status}")
    print(f"idempotency_status={receipt.idempotency_status}")
    print(f"management_applied={str(receipt.management_applied).lower()}")
    print(f"reconciliation_required={str(receipt.reconciliation_required).lower()}")
    print(f"order_sent={str(receipt.order_sent).lower()}")
    print(f"ticket_present={str(receipt.ticket_present).lower()}")
    print(f"deal_present={str(receipt.deal_present).lower()}")
    print(f"position_present={str(receipt.position_present).lower()}")
    print("metadata_redacted=true")

    if receipt.lifecycle_update_required:
        lifecycle = MT5PositionLifecycleSupervisor().run_once().to_safe_dict()
        print(f"lifecycle_supervisor_status={lifecycle['supervisor_status']}")
        print(f"lifecycle_discrepancy_count={lifecycle['discrepancy_count']}")
    return 0 if receipt.status in {"ACCEPTED", "REJECTED", "UNKNOWN"} else 4


def _default_blocker(config: MT5LiveAdapterPreSubmitConfig) -> bool:
    return (
        not config.controlled_management_enabled
        or config.management_hard_block
        or config.management_kill_switch_engaged
        or config.kill_switch_engaged
        or not config.live_adapter_enabled
        or config.live_adapter_hard_block
        or not config.allow_live_submission
        or not config.allow_order_send
        or not config.execution_auth_token
    )


def _safe_reason(exc: Exception) -> str:
    reason = str(exc).strip().upper()
    return reason if reason and len(reason) <= 80 else "MANAGEMENT_REQUEST_INVALID"


if __name__ == "__main__":
    raise SystemExit(main())

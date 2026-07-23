from __future__ import annotations

import argparse
import hmac

from src.services.trading.execution.mt5_live_adapter_pre_submit import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedArtifactCaptureError,
    verify_protected_artifact_bundle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    ProtectedRequestExportError,
    load_verified_protected_execution_artifacts,
)


def _safe_reason_code(value: object) -> str:
    candidate = str(value or "").strip().upper()
    if not candidate or len(candidate) > 80:
        return "UNSPECIFIED"
    if any(not (character.isalnum() or character == "_") for character in candidate):
        return "UNSPECIFIED"
    return candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual, one-shot controlled MT5 execution. Never use from automated verification."
    )
    parser.add_argument(
        "--artifact-bundle",
        required=True,
        help="Complete protected artifact bundle produced by the capture workflow",
    )
    parser.add_argument("--max-age-seconds", type=int, default=300)
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

    try:
        paths = verify_protected_artifact_bundle(args.artifact_bundle)
        verified = load_verified_protected_execution_artifacts(
            **paths,
            expected_confirmation_phrase=EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
            max_age_seconds=args.max_age_seconds,
        )
    except (ProtectedArtifactCaptureError, ProtectedRequestExportError) as exc:
        reason = str(exc).strip().upper().replace(" ", "_").replace("-", "_")
        print("status=BLOCKED")
        print(f"reason={reason or type(exc).__name__.upper()}")
        return 3

    adapter = MT5LiveAdapterDisabled(config=config)
    account = adapter.capture_account_context()
    print("account_context_redacted=true")
    print(f"account_fingerprint_prefix={account['account_context_fingerprint'][:12]}")
    print(f"server_redacted={account['server_redacted']}")
    print(f"currency={account['currency']}")
    print(f"trade_mode={account['trade_mode']}")
    if not hmac.compare_digest(
        account["account_context_fingerprint"], verified.account_fingerprint
    ):
        print("status=BLOCKED")
        print("reason=ACCOUNT_CONTEXT_MISMATCH")
        return 4

    typed = input(f"Type exactly '{config.execution_confirmation_phrase}' to submit once: ")
    receipt = adapter.submit_controlled(
        verified.approval_lock,
        verified.final_validation,
        verified.final_validation_report,
        verified.pre_submit_report,
        expected_account_context_fingerprint=verified.account_fingerprint,
        typed_confirmation=typed,
    )
    print(f"status={receipt.status}")
    print(f"idempotency_status={receipt.idempotency_status}")
    print(f"order_sent={str(receipt.order_sent).lower()}")
    print(f"ticket_present={str(receipt.ticket_present).lower()}")
    print(f"deal_present={str(receipt.deal_present).lower()}")
    print(f"reason_code={_safe_reason_code(getattr(receipt, 'reason', ''))}")
    print("metadata_redacted=true")
    return 0 if receipt.status in {"ACCEPTED", "REJECTED", "UNKNOWN"} else 4


if __name__ == "__main__":
    raise SystemExit(main())

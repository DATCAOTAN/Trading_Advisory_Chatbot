from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    ProtectedRequestExportError,
    export_protected_request,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export one protected controlled MT5 request from verified local artifacts."
    )
    parser.add_argument("--proposal-artifact", required=True)
    parser.add_argument("--approval-artifact", required=True)
    parser.add_argument("--lock-artifact", required=True)
    parser.add_argument("--final-validation-artifact", required=True)
    parser.add_argument("--final-validation-report-artifact", required=True)
    parser.add_argument("--pre-submit-artifact", required=True)
    parser.add_argument("--account-fingerprint-artifact", required=True)
    parser.add_argument("--account-fingerprint-submit-artifact", required=True)
    parser.add_argument("--human-confirmation-artifact", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-age-seconds", type=int, default=300)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = export_protected_request(
            proposal_artifact=args.proposal_artifact,
            approval_artifact=args.approval_artifact,
            lock_artifact=args.lock_artifact,
            final_validation_artifact=args.final_validation_artifact,
            final_validation_report_artifact=args.final_validation_report_artifact,
            pre_submit_artifact=args.pre_submit_artifact,
            account_fingerprint_artifact=args.account_fingerprint_artifact,
            account_fingerprint_submit_artifact=args.account_fingerprint_submit_artifact,
            human_confirmation_artifact=args.human_confirmation_artifact,
            output=args.output,
            expected_confirmation_phrase=EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
            max_age_seconds=args.max_age_seconds,
        )
    except ProtectedRequestExportError:
        print("validation_status=BLOCKED")
        return 2

    print(f"request_reference={result.request_reference_redacted}")
    print(f"semantic_hash_prefix={result.semantic_hash_prefix}")
    print(f"account_fingerprint={result.account_fingerprint_redacted}")
    print(f"output_path={result.output_path}")
    print(f"validation_status={result.validation_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

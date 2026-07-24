from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_artifact_export import (
    PendingArtifactExportError,
    export_pending_artifact_bundle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a reviewed typed pending candidate for validation only."
    )
    parser.add_argument("--candidate-artifact", required=True)
    parser.add_argument("--account-context-artifact", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--protected-root", default="data/trading/protected_requests")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    confirmation_reader: Callable[[str], str] = input,
) -> int:
    args = build_parser().parse_args(argv)
    print("validation_mode=EXPORT_ONLY")
    print("controlled_submission=NOT_CALLED")
    print(f"required_phrase={EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE}")
    try:
        phrase = confirmation_reader("Export-only confirmation: ")
        result = export_pending_artifact_bundle(
            candidate_artifact=args.candidate_artifact,
            account_context_artifact=args.account_context_artifact,
            output_dir=args.output_dir,
            confirmation_phrase=phrase,
            protected_root=args.protected_root,
        )
    except PendingArtifactExportError as exc:
        print("validation_status=BLOCKED")
        print(f"blocker={str(exc)}")
        print("executable=false")
        print("order_send_allowed=false")
        return 2

    print(f"artifact_reference={result.artifact_reference_redacted}")
    print(f"schema_version={result.schema_version}")
    print(f"pending_order_family={result.pending_order_family}")
    print(f"validation_status={result.validation_status}")
    print("blockers=none")
    print(f"freshness_status={result.freshness_status}")
    print(f"account_context_match={str(result.account_context_match).lower()}")
    print(f"export_status={result.export_status}")
    print("executable=false")
    print("order_send_allowed=false")
    print(f"artifact_path={result.artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
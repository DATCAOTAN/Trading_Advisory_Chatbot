from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (  # noqa: E402
    OperatorProtectedArtifactCaptureService,
    ProtectedArtifactCaptureError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture protected MT5 artifacts without submitting an order."
    )
    parser.add_argument("--semantic-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bridge-url")
    parser.add_argument("--mode", default="REVIEW_ONLY")
    parser.add_argument("--max-age-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None, *, confirmation_reader=None) -> int:
    args = build_parser().parse_args(argv)
    read_confirmation = confirmation_reader or input
    approval_phrase = read_confirmation("Approval confirmation: ").strip()
    export_phrase = read_confirmation("Export confirmation: ").strip()
    try:
        result = OperatorProtectedArtifactCaptureService().capture(
            semantic_input=args.semantic_input,
            output_dir=args.output_dir,
            approval_confirmation_phrase=approval_phrase,
            export_confirmation_phrase=export_phrase,
            bridge_url=args.bridge_url,
            mode=args.mode,
            max_age_seconds=args.max_age_seconds,
        )
    except ProtectedArtifactCaptureError as exc:
        reason = str(exc).strip().upper().replace(" ", "_").replace("-", "_")
        print(f"status=BLOCKED:{reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"status=BLOCKED:{type(exc).__name__}", file=sys.stderr)
        return 1

    print(f"capture_reference={result.capture_reference_redacted}")
    print(f"semantic_hash_prefix={result.semantic_hash_prefix}")
    print(f"account_fingerprint={result.account_fingerprint_redacted}")
    print(f"artifact_count={result.artifact_count}")
    print(f"bundle_path={result.bundle_path}")
    print(f"status={result.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.decision.autonomous_orchestrator import (  # noqa: E402
    AutonomousDecisionConfig,
    AutonomousDecisionOrchestrator,
    autonomous_inputs_from_mapping,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build one redacted, non-executable autonomous decision candidate."
    )
    parser.add_argument("--input", required=True, help="Structured decision input JSON path.")
    parser.add_argument("--journal", help="Optional decision journal path override.")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("input must be an object")
        inputs = autonomous_inputs_from_mapping(payload)
        config = AutonomousDecisionConfig.from_config()
        if args.journal:
            config = replace(config, journal_path=str(Path(args.journal)))
        result = AutonomousDecisionOrchestrator(config=config).run_once(inputs)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("validation_status=INVALID_INPUT")
        print("execution_authority=false")
        return 2

    candidate = result.candidate
    print(f"candidate_reference={candidate.candidate_reference}")
    print(f"intent={candidate.intent}")
    print(f"eligibility_status={candidate.deterministic_eligibility_result}")
    print("blocked_reason_codes=" + ",".join(candidate.blocked_reason_codes))
    print(f"confidence_category={candidate.confidence_category}")
    print(f"expiry={candidate.expires_at}")
    print(f"lifecycle_status={candidate.lifecycle_status}")
    print("execution_authority=false")
    print(f"validation_status={'VALID' if result.validation.valid else 'INVALID'}")
    print(f"journal_appended={str(result.journal_appended).lower()}")
    return 0 if result.validation.valid and result.persistence_safe else 2


if __name__ == "__main__":
    raise SystemExit(main())

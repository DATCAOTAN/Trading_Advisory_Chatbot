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

from src.services.trading.decision.autonomous_execution_policy import (  # noqa: E402
    AutonomousExecutionPolicyConfig,
    AutonomousExecutionPolicyGate,
    autonomous_policy_inputs_from_mapping,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate one autonomous candidate without execution authority."
    )
    parser.add_argument("--input", required=True, help="Structured policy input JSON path.")
    parser.add_argument("--journal", help="Optional policy journal path override.")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("input must be an object")
        inputs = autonomous_policy_inputs_from_mapping(payload)
        config = AutonomousExecutionPolicyConfig.from_config()
        if args.journal:
            config = replace(config, journal_path=str(Path(args.journal)))
        result = AutonomousExecutionPolicyGate(config=config).run_once(inputs)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("policy_validation_status=INVALID_INPUT")
        print("execution_authority=false")
        print("executable=false")
        return 2

    policy = result.policy_result
    print(f"policy_reference={policy.policy_decision_reference}")
    print(f"candidate_reference={policy.candidate_reference}")
    print(f"decision={policy.decision}")
    print(f"target_boundary={policy.target_controlled_boundary}")
    print("reason_codes=" + ",".join(policy.deterministic_reason_codes))
    print(f"expiry={policy.expires_at}")
    print("execution_authority=false")
    print("executable=false")
    print(f"policy_validation_status={'VALID' if result.validation.valid else 'INVALID'}")
    print(f"journal_appended={str(result.journal_appended).lower()}")
    return 0 if result.validation.valid and result.persistence_safe else 2


if __name__ == "__main__":
    raise SystemExit(main())

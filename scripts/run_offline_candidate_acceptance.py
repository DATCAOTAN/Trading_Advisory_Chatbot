from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.decision.offline_candidate_acceptance import (
    SCENARIOS,
    run_offline_candidate_acceptance,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one deterministic offline autonomous-candidate acceptance scenario."
    )
    parser.add_argument(
        "fixture",
        help="Built-in scenario name or path to a strict offline fixture JSON file.",
    )
    parser.epilog = "Built-in scenarios: " + ", ".join(SCENARIOS)
    args = parser.parse_args(argv)
    try:
        result = run_offline_candidate_acceptance(args.fixture)
    except (RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "INVARIANT_BLOCKED",
                    "offline_provenance": "offline_fixture",
                    "blockers": [str(exc)],
                    "export_eligibility": False,
                    "submission_eligibility": False,
                    "broker_mutation_count": 0,
                    "metadata_redacted": True,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
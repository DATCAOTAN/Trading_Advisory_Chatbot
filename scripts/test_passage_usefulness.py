import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.evidence.evidence_pipeline import EvidenceUsefulnessEvaluator  # noqa: E402


class PassageUsefulnessTests(unittest.TestCase):
    def test_metadata_heavy_passage_is_not_primary_useful(self):
        score, metadata_only, warnings = EvidenceUsefulnessEvaluator.evaluate(
            "Copyright 2009. ISBN 978-0-0000. Library of Congress catalog data. All rights reserved.",
            {"section": "copyright"},
            ["price action"],
        )

        self.assertTrue(metadata_only)
        self.assertLess(score, 0.5)
        self.assertIn("metadata_only", warnings)

    def test_direct_conceptual_passage_is_primary_eligible(self):
        score, metadata_only, warnings = EvidenceUsefulnessEvaluator.evaluate(
            "A trader reads price action because bars show trend, pullbacks, failed breakouts, and market behavior.",
            {"section": "trading concepts"},
            ["price action", "trend"],
        )

        self.assertFalse(metadata_only)
        self.assertGreaterEqual(score, 0.55)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()

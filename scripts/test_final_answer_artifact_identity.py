import hashlib
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.tab_chatbot import (  # noqa: E402
    _AnswerStreamLogger,
    _answer_sha256,
    _build_answer_delivery_artifact,
    _ends_with_sentence,
    _sanitize_user_facing_answer,
    check_answer_completeness,
)


class TestFinalAnswerArtifactIdentity(unittest.TestCase):
    def _runtime_artifacts(self, answer: str, source: str = "original", repair_status: str = "NOT_ATTEMPTED"):
        selected_hash = _answer_sha256(answer)
        selected = {
            "content": answer,
            "source": source,
            "repair_status": repair_status,
            "chars": len(answer),
            "sha256": selected_hash,
        }
        display_answer = _sanitize_user_facing_answer(answer)
        return {
            "final_answer_artifact": selected,
            "answer_delivery_artifact": _build_answer_delivery_artifact(answer, display_answer, selected),
            "contract_evaluation": {"status": "PASS", "repair_status": repair_status, "reason_codes": []},
        }

    def test_delivery_hash_mismatch_fails_completeness(self):
        answer = "Nguon: Test Source. Noi dung tra loi day du. Ket luan ngan: du dieu kien."
        selected_hash = hashlib.sha256(b"selected").hexdigest()
        delivered_hash = hashlib.sha256(answer.encode("utf-8")).hexdigest()

        result = check_answer_completeness(
            answer,
            "STOP",
            min_chars=1,
            intent="FINANCIAL_RAG",
            runtime_artifacts={
                "final_answer_artifact": {"sha256": selected_hash},
                "answer_delivery_artifact": {
                    "sha256": delivered_hash,
                    "matches_selected": False,
                },
            },
        )

        self.assertEqual(result["overall_status"], "FAIL")
        self.assertEqual(result["reason"], "final_artifact_inconsistency")

    def test_original_branch_identity_passes_with_canonical_delivery(self):
        answer = "Noi dung tra loi goc da hoan tat va ket thuc ro rang."
        runtime_artifacts = self._runtime_artifacts(answer, source="original", repair_status="NOT_ATTEMPTED")

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertTrue(runtime_artifacts["answer_delivery_artifact"]["matches_selected"])

    def test_repaired_branch_identity_passes(self):
        answer = "Noi dung da sua sau repair va duoc chon lam artifact cuoi cung."
        runtime_artifacts = self._runtime_artifacts(answer, source="repaired", repair_status="ATTEMPTED_IMPROVED")

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["repair_status"], "ATTEMPTED_IMPROVED")

    def test_no_improvement_fallback_keeps_original_identity(self):
        answer = "Original answer retained because repair did not improve coverage."
        runtime_artifacts = self._runtime_artifacts(answer, source="original", repair_status="ATTEMPTED_NO_IMPROVEMENT")

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["repair_status"], "ATTEMPTED_NO_IMPROVEMENT")

    def test_regressed_repair_fallback_keeps_original_identity(self):
        answer = "Original answer retained because repair regressed claim validation."
        runtime_artifacts = self._runtime_artifacts(answer, source="original", repair_status="ATTEMPTED_REGRESSED")

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["repair_status"], "ATTEMPTED_REGRESSED")

    def test_bounded_response_identity_passes(self):
        answer = "He thong khong co du bang chung bat buoc nen chi tra loi gioi han."
        runtime_artifacts = self._runtime_artifacts(answer, source="bounded")
        runtime_artifacts["is_bounded_response"] = True

        result = check_answer_completeness(answer, "OTHER", min_chars=1, intent="FINANCIAL_RAG", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["reason"], "bounded_pass")

    def test_multi_intent_aggregated_artifact_identity_passes(self):
        answer = (
            "Task 1: Noi dung thu nhat da hoan tat.\n\n"
            "Task 2: Noi dung thu hai da hoan tat.\n\n"
            "Ket luan: ca hai phan dung chung mot artifact cuoi."
        )
        runtime_artifacts = self._runtime_artifacts(answer, source="original")

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")

    def test_presentation_transform_does_not_break_canonical_identity(self):
        answer = (
            "Theo US CPI Report (Doc ID: report_us_cpi_report_2026_05_bls_v1), "
            "ket luan cua cau tra loi van duoc giu nguyen."
        )
        runtime_artifacts = self._runtime_artifacts(answer, source="original")
        delivery = runtime_artifacts["answer_delivery_artifact"]

        self.assertTrue(delivery["matches_selected"])
        self.assertTrue(delivery["presentation_transformed"])
        self.assertNotEqual(delivery["canonical_sha256"], delivery["display_sha256"])

        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)
        self.assertEqual(result["overall_status"], "PASS")

    def test_completeness_input_mismatch_guard_remains_active(self):
        selected_answer = "Selected final answer."
        delivered_answer = "Different final answer."
        runtime_artifacts = self._runtime_artifacts(selected_answer, source="original")

        result = check_answer_completeness(
            delivered_answer,
            "STOP",
            min_chars=1,
            intent="GREETING",
            runtime_artifacts=runtime_artifacts,
        )

        self.assertEqual(result["overall_status"], "FAIL")
        self.assertEqual(result["reason"], "final_artifact_inconsistency")

    def test_stream_logger_records_completeness_input_identity(self):
        answer = "Streamed answer identity is measured against the selected artifact."
        runtime_artifacts = self._runtime_artifacts(answer, source="original")
        logger = _AnswerStreamLogger("test query", request_id="identity")
        list(logger.wrap([answer]))

        result = logger.log_done(answer, min_chars=1, intent="GREETING", runtime_artifacts=runtime_artifacts)

        self.assertEqual(result["overall_status"], "PASS")
        self.assertTrue(runtime_artifacts["completeness_input_artifact"]["matches_selected"])

    def test_markdown_closing_markers_preserve_sentence_completion(self):
        complete_variants = [
            "Sentence.",
            "Sentence.*",
            "Sentence.**",
            "Sentence._",
            "Sentence.`",
            "Sentence.)",
            "Sentence.]",
            "Sentence.</em>",
            "Sentence.</strong>   ",
        ]

        for answer in complete_variants:
            with self.subTest(answer=answer):
                self.assertTrue(_ends_with_sentence(answer))

    def test_markdown_marker_without_terminal_punctuation_is_not_complete(self):
        self.assertFalse(_ends_with_sentence("The market remains uncertain*"))
        self.assertFalse(_ends_with_sentence("The market remains uncertain`"))

    def test_incomplete_connectors_and_colon_still_fail_completeness(self):
        for answer in ["The market is affected by", "The bullish scenario depends on", "Because inflation remains", "The key factors include:"]:
            with self.subTest(answer=answer):
                result = check_answer_completeness(answer, "STOP", min_chars=1, intent="UNKNOWN")
                self.assertEqual(result["overall_status"], "FAIL")
                self.assertIn(result["reason"], {"missing_sentence_ending", "ends_with_incomplete_connector"})

    def test_markdown_terminal_validation_does_not_change_artifact_hash(self):
        answer = "The final semantic sentence is complete.*"
        before_hash = _answer_sha256(answer)
        result = check_answer_completeness(answer, "STOP", min_chars=1, intent="GREETING")
        after_hash = _answer_sha256(answer)

        self.assertEqual(before_hash, after_hash)
        self.assertEqual(result["overall_status"], "PASS")
        self.assertTrue(result["ends_with_sentence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

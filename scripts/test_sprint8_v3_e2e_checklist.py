import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from scripts.v3_e2e_checklist import V3E2EChecklist
from src.config import Config


class V3E2EChecklistTests(unittest.TestCase):
    def status_by_name(self, report):
        return {item.name: item.status for item in report.items}

    def test_read_only_default_skips_optional_pdf_and_missing_deps(self):
        checklist = V3E2EChecklist(
            import_checker=lambda _name: False,
            env={},
        )

        report = checklist.run()
        statuses = self.status_by_name(report)

        self.assertEqual(statuses["config:USE_KNOWLEDGE_V3"], "PASS")
        self.assertEqual(statuses["dependency:qdrant_client"], "SKIP")
        self.assertEqual(statuses["env:COHERE_API_KEY"], "SKIP")
        self.assertEqual(statuses["pdf"], "SKIP")
        self.assertEqual(report.final_status, "SKIP")

    def test_valid_pdf_path_and_manifest_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = (
                Path(temp_dir)
                / "data"
                / "knowledge_repository"
                / "book"
                / "technical"
                / "indicators"
                / "john_murphy"
                / "sample.pdf"
            )
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4 test\n")
            pdf.with_suffix(".manifest.yaml").write_text("title: Sample\n", encoding="utf-8")
            checklist = V3E2EChecklist(
                import_checker=lambda _name: True,
                env={"COHERE_API_KEY": "fake"},
            )

            report = checklist.run(str(pdf))
            statuses = self.status_by_name(report)

            self.assertEqual(statuses["pdf:exists"], "PASS")
            self.assertEqual(statuses["pdf:path_convention"], "PASS")
            self.assertEqual(statuses["manifest"], "PASS")
            self.assertEqual(report.final_status, "PASS")

    def test_missing_manifest_fails_without_ingesting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = Path(temp_dir) / "data" / "knowledge_repository" / "book" / "technical" / "indicators" / "a" / "sample.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4 test\n")
            checklist = V3E2EChecklist(import_checker=lambda _name: True, env={"COHERE_API_KEY": "fake"})

            report = checklist.run(str(pdf))
            statuses = self.status_by_name(report)

            self.assertEqual(statuses["manifest"], "FAIL")
            self.assertEqual(report.final_status, "FAIL")

    def test_wrong_path_fails_convention_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = Path(temp_dir) / "sample.pdf"
            pdf.write_bytes(b"%PDF-1.4 test\n")
            pdf.with_suffix(".manifest.yaml").write_text("title: Sample\n", encoding="utf-8")
            checklist = V3E2EChecklist(import_checker=lambda _name: True, env={"COHERE_API_KEY": "fake"})

            report = checklist.run(str(pdf))
            statuses = self.status_by_name(report)

            self.assertEqual(statuses["pdf:path_convention"], "FAIL")
            self.assertEqual(statuses["manifest"], "PASS")
            self.assertEqual(report.final_status, "FAIL")

    def test_config_default_remains_legacy(self):
        self.assertFalse(Config.USE_KNOWLEDGE_V3)

        checklist = V3E2EChecklist(import_checker=lambda _name: False, env={})
        checklist.run()

        self.assertFalse(Config.USE_KNOWLEDGE_V3)

    def test_helper_does_not_reference_ingest_or_collection_delete(self):
        text = (PROJECT_ROOT / "scripts" / "v3_e2e_checklist.py").read_text(encoding="utf-8")

        self.assertNotIn("ingest_file", text)
        self.assertNotIn("upsert_document", text)
        self.assertNotIn("delete_collection", text)
        self.assertNotIn("xauusd_knowledge_v2", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

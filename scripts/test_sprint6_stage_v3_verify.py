import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from scripts.stage_v3_verify import StageV3Verifier
from src.config import Config


class FakeIngestor:
    def __init__(self):
        self.dry_runs = []
        self.ingests = []
        self.vector_service = None

    def dry_run(self, pdf_path):
        self.dry_runs.append(pdf_path)
        return type("Result", (), {
            "status": "READY",
            "doc_id": "fake_doc",
            "chunk_count": 1,
        })()

    def ingest_file(self, pdf_path):
        self.ingests.append(pdf_path)
        return type("Result", (), {
            "indexed": True,
            "status": "INDEXED",
            "doc_id": "fake_doc",
        })()


class IngestorFactory:
    def __init__(self):
        self.instances = []
        self.vector_services = []

    def __call__(self, vector_service):
        ingestor = FakeIngestor()
        ingestor.vector_service = vector_service
        self.instances.append(ingestor)
        self.vector_services.append(vector_service)
        return ingestor


class StageV3VerifyTests(unittest.TestCase):
    def status_by_name(self, report):
        return {check.name: check.status for check in report.checks}

    def test_fake_mode_passes_without_qdrant_or_cohere(self):
        verifier = StageV3Verifier(
            import_checker=lambda _name: False,
            env={},
        )

        report = verifier.run(fake=True, adapter_smoke=True)

        statuses = self.status_by_name(report)
        self.assertEqual(statuses["default_config"], "PASS")
        self.assertEqual(statuses["fake_knowledge_service"], "PASS")
        self.assertEqual(statuses["fake_retrieval_adapter"], "PASS")
        self.assertEqual(report.final_status, "PASS")

    def test_missing_qdrant_client_skips_indexing_without_crash(self):
        verifier = StageV3Verifier(
            import_checker=lambda name: name != "qdrant_client",
            env={"COHERE_API_KEY": "fake"},
        )

        report = verifier.run(pdf_path="fake.pdf", index=True)

        statuses = self.status_by_name(report)
        self.assertEqual(statuses["dependency:qdrant_client"], "SKIP")
        self.assertEqual(report.final_status, "SKIP")

    def test_missing_cohere_api_key_skips_indexing_without_crash(self):
        verifier = StageV3Verifier(
            import_checker=lambda _name: True,
            env={},
        )

        report = verifier.run(pdf_path="fake.pdf", index=True)

        statuses = self.status_by_name(report)
        self.assertEqual(statuses["env:COHERE_API_KEY"], "SKIP")
        self.assertEqual(report.final_status, "SKIP")

    def test_dry_run_does_not_call_vector_service_or_mutate_real_catalog(self):
        factory = IngestorFactory()
        verifier = StageV3Verifier(
            import_checker=lambda _name: True,
            env={},
            ingestor_factory=factory,
        )

        report = verifier.run(pdf_path="fake.pdf", dry_run=True)

        statuses = self.status_by_name(report)
        self.assertEqual(statuses["kp_ingest_dry_run"], "PASS")
        self.assertEqual(len(factory.instances), 1)
        self.assertEqual(factory.instances[0].dry_runs, ["fake.pdf"])
        self.assertEqual(factory.instances[0].ingests, [])
        self.assertEqual(len(factory.vector_services), 1)

    def test_index_requires_explicit_flag(self):
        factory = IngestorFactory()
        verifier = StageV3Verifier(
            import_checker=lambda _name: True,
            env={"COHERE_API_KEY": "fake"},
            ingestor_factory=factory,
        )

        report = verifier.run(pdf_path="fake.pdf")

        statuses = self.status_by_name(report)
        self.assertEqual(statuses["index"], "SKIP")
        self.assertEqual(factory.instances[0].dry_runs, ["fake.pdf"])
        self.assertEqual(factory.instances[0].ingests, [])

    def test_script_preserves_default_knowledge_v3_flag(self):
        self.assertFalse(Config.USE_KNOWLEDGE_V3)

        verifier = StageV3Verifier(import_checker=lambda _name: False, env={})
        report = verifier.run(fake=True)

        self.assertFalse(Config.USE_KNOWLEDGE_V3)
        self.assertEqual(self.status_by_name(report)["default_config"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)

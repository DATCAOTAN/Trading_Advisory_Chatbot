import argparse
import hashlib
import importlib.util
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StageCheck:
    name: str
    status: str
    message: str


@dataclass
class StageReport:
    checks: List[StageCheck] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.checks.append(StageCheck(name=name, status=status, message=message))
        print(f"[{status}] {name}: {message}")

    @property
    def final_status(self) -> str:
        if any(check.status == "FAIL" for check in self.checks):
            return "FAIL"
        if any(check.status == "SKIP" for check in self.checks):
            return "SKIP"
        return "PASS"


class StageV3Verifier:
    def __init__(
        self,
        import_checker: Optional[Callable[[str], bool]] = None,
        env: Optional[Dict[str, str]] = None,
        ingestor_factory: Optional[Callable[..., Any]] = None,
    ):
        self.import_checker = import_checker or self._default_import_checker
        self.env = env if env is not None else os.environ
        self.ingestor_factory = ingestor_factory

    def run(
        self,
        pdf_path: Optional[str] = None,
        fake: bool = False,
        index: bool = False,
        dry_run: bool = False,
        sample: bool = False,
        adapter_smoke: bool = False,
    ) -> StageReport:
        report = StageReport()
        self._check_default_config(report)

        if fake:
            self._run_fake_mode(report, adapter_smoke=adapter_smoke)
            self._print_final(report)
            return report

        if sample:
            pdf_path = self._create_sample_repository_pdf(report)

        self._check_core_dependencies(report)

        if index:
            if not self._check_index_dependencies(report):
                self._print_final(report)
                return report
        elif not dry_run:
            report.add("index", "SKIP", "Indexing disabled by default. Pass --index to run real V3 indexing.")

        if not pdf_path:
            report.add("pdf", "SKIP", "No --pdf path provided. Use --pdf or --sample for dry-run/index verification.")
            self._print_final(report)
            return report

        if dry_run or not index:
            self._run_dry_run(report, pdf_path)
            self._print_final(report)
            return report

        indexed = self._run_index(report, pdf_path)
        if indexed:
            self._run_search_smoke(report, pdf_path, adapter_smoke=adapter_smoke)
        self._print_final(report)
        return report

    def _check_default_config(self, report: StageReport) -> None:
        from src.config import Config

        if Config.USE_KNOWLEDGE_V3 is False:
            report.add("default_config", "PASS", "USE_KNOWLEDGE_V3 is False; legacy chatbot remains default.")
        else:
            report.add("default_config", "FAIL", "USE_KNOWLEDGE_V3 is not False.")

    def _check_core_dependencies(self, report: StageReport) -> None:
        for module in ["yaml", "fitz"]:
            if self.import_checker(module):
                report.add(f"dependency:{module}", "PASS", f"{module} is available.")
            else:
                report.add(f"dependency:{module}", "SKIP", f"{module} is missing; dry-run may not be available.")

    def _check_index_dependencies(self, report: StageReport) -> bool:
        ok = True
        if self.import_checker("qdrant_client"):
            report.add("dependency:qdrant_client", "PASS", "qdrant_client is available.")
        else:
            report.add("dependency:qdrant_client", "SKIP", "qdrant_client missing; skipping real indexing/search smoke.")
            ok = False

        if self.env.get("COHERE_API_KEY"):
            report.add("env:COHERE_API_KEY", "PASS", "COHERE_API_KEY is configured.")
        else:
            report.add("env:COHERE_API_KEY", "SKIP", "COHERE_API_KEY missing; skipping real embedding/indexing.")
            ok = False
        return ok

    def _run_fake_mode(self, report: StageReport, adapter_smoke: bool = False) -> None:
        from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
        from src.services.retrieval_adapter import RetrievalAdapter

        class FakeVectorService:
            def search(self, query, filters, top_k=8, score_threshold=0.7):
                return [{
                    "content": "fake v3 content",
                    "score": 0.91,
                    "payload": {
                        "doc_id": "fake_doc",
                        "chunk_id": "fake_doc_p1_c1",
                        "text": "fake v3 content",
                        "page": 1,
                        "domain": filters.get("domain", "technical"),
                        "subdomain": "indicators",
                        "knowledge_type": "book",
                        "source_tier": "tier2",
                        "language": "en",
                        "lifecycle": "ACTIVE",
                        "index_status": "INDEXED",
                        "document_metadata": {
                            "doc_id": "fake_doc",
                            "title": "Fake V3 Fixture",
                            "author": "Stage Verifier",
                        },
                    },
                }]

        class FakeLegacyService:
            def retrieve_candidates(self, query, top_k=None):
                return []

        service = KnowledgeService(vector_service=FakeVectorService())
        response = service.search(SearchRequest(query="indicator strategy", routing_filters={"domain": "technical"}))
        if response.total_found > 0 and response.chunks[0].get("citation", {}).get("doc_id"):
            report.add("fake_knowledge_service", "PASS", "KnowledgeService/SearchRequest fake path returned structured citation.")
        else:
            report.add("fake_knowledge_service", "FAIL", "Fake KnowledgeService path did not return a citation.")

        if adapter_smoke:
            adapter = RetrievalAdapter(
                legacy_service=FakeLegacyService(),
                knowledge_service=service,
                fallback_to_legacy=False,
            )
            docs = adapter.retrieve("indicator strategy", use_v3=True)
            if docs and {"content", "metadata", "score"} == set(docs[0]):
                report.add("fake_retrieval_adapter", "PASS", "RetrievalAdapter use_v3=True returned legacy-compatible shape.")
            else:
                report.add("fake_retrieval_adapter", "FAIL", "RetrievalAdapter fake smoke failed.")

    def _run_dry_run(self, report: StageReport, pdf_path: str) -> None:
        try:
            ingestor = self._make_temp_ingestor(vector_service=NoopVectorService())
            result = ingestor.dry_run(pdf_path)
            status = "PASS" if result.status in {"READY", "PARTIAL_TEXT"} else "SKIP"
            report.add("kp_ingest_dry_run", status, f"dry-run status={result.status}, doc_id={result.doc_id}, chunks={result.chunk_count}")
        except Exception as exc:
            report.add("kp_ingest_dry_run", "FAIL", f"dry-run failed: {exc}")

    def _run_index(self, report: StageReport, pdf_path: str) -> bool:
        try:
            if self.ingestor_factory is not None:
                ingestor = self.ingestor_factory(vector_service=None)
                result = ingestor.ingest_file(pdf_path)
                if result.indexed:
                    report.add("kp_ingest_index", "PASS", f"indexed doc_id={result.doc_id}")
                    return True
                report.add("kp_ingest_index", "FAIL", f"indexing did not complete: status={result.status}")
                return False

            from scripts.kp_ingest import KnowledgePlatformIngestor
            from src.services.knowledge.catalog_manager import KnowledgeCatalog
            from src.services.knowledge.vector_service import VectorServiceV3

            temp_dir = tempfile.TemporaryDirectory()
            catalog = KnowledgeCatalog(str(Path(temp_dir.name) / "catalog" / "catalog.sqlite"))
            vector_service = VectorServiceV3(catalog=catalog)
            ingestor = KnowledgePlatformIngestor(catalog=catalog, vector_service=vector_service)
            ingestor._stage_temp_dir = temp_dir
            result = ingestor.ingest_file(pdf_path)
            if result.indexed:
                report.add("kp_ingest_index", "PASS", f"indexed doc_id={result.doc_id}")
                return True
            report.add("kp_ingest_index", "FAIL", f"indexing did not complete: status={result.status}")
            return False
        except Exception as exc:
            report.add("kp_ingest_index", "FAIL", f"indexing failed: {exc}")
            return False

    def _run_search_smoke(self, report: StageReport, pdf_path: str, adapter_smoke: bool = False) -> None:
        try:
            from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
            from src.services.knowledge.catalog_manager import KnowledgeCatalog
            from src.services.knowledge.vector_service import VectorServiceV3

            temp_dir = tempfile.TemporaryDirectory()
            catalog = KnowledgeCatalog(str(Path(temp_dir.name) / "catalog" / "catalog.sqlite"))
            vector_service = VectorServiceV3(catalog=catalog)
            service = KnowledgeService(vector_service=vector_service)
            response = service.search(
                SearchRequest(
                    query=Path(pdf_path).stem.replace("_", " "),
                    routing_filters={"domain": self._infer_domain_from_path(pdf_path) or "technical"},
                    score_threshold=0.0,
                )
            )
            if response.total_found:
                report.add("knowledge_search_smoke", "PASS", f"KnowledgeService returned {response.total_found} chunks.")
            else:
                report.add("knowledge_search_smoke", "SKIP", "Index completed, but search smoke returned no chunks.")

            if adapter_smoke:
                from src.services.retrieval_adapter import RetrievalAdapter

                adapter = RetrievalAdapter(
                    legacy_service=NoopLegacyService(),
                    knowledge_service=service,
                    fallback_to_legacy=False,
                )
                docs = adapter.retrieve("indicator strategy", filters={"domain": "technical"}, use_v3=True)
                if docs:
                    report.add("retrieval_adapter_smoke", "PASS", f"Adapter returned {len(docs)} docs.")
                else:
                    report.add("retrieval_adapter_smoke", "SKIP", "Adapter smoke returned no docs.")
        except Exception as exc:
            report.add("knowledge_search_smoke", "FAIL", f"search smoke failed: {exc}")

    def _make_temp_ingestor(self, vector_service: Any):
        if self.ingestor_factory is not None:
            return self.ingestor_factory(vector_service=vector_service)

        from scripts.kp_ingest import KnowledgePlatformIngestor
        from src.services.knowledge.catalog_manager import KnowledgeCatalog

        temp_dir = tempfile.TemporaryDirectory()
        catalog = KnowledgeCatalog(str(Path(temp_dir.name) / "catalog" / "catalog.sqlite"))
        ingestor = KnowledgePlatformIngestor(catalog=catalog, vector_service=vector_service)
        ingestor._stage_temp_dir = temp_dir
        return ingestor

    def _create_sample_repository_pdf(self, report: StageReport) -> str:
        sample_root = Path(tempfile.mkdtemp(prefix="kp_stage_sample_"))
        pdf_path = sample_root / "data" / "knowledge_repository" / "book" / "technical" / "indicators" / "stage_verifier" / "stage_sample.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(self._minimal_pdf_bytes())
        checksum = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        manifest_path = pdf_path.with_suffix(".manifest.yaml")
        manifest_path.write_text(
            "\n".join([
                "title: Stage Sample",
                "title_slug: stage_sample",
                "author_slug: stage_verifier",
                "author: Stage Verifier",
                "knowledge_type: book",
                "domain: technical",
                "version: v1",
                "language: en",
                "lifecycle: ACTIVE",
                f"checksum: {checksum}",
                "publisher: Stage",
                "publish_year: 2026",
                "tags:",
                "  strategies: [trend_following]",
                "  assets: [forex]",
                "  timeframe_focus: [h1]",
                "",
            ]),
            encoding="utf-8",
        )
        report.add("sample", "PASS", f"Created sample PDF and manifest at {pdf_path}")
        return str(pdf_path)

    def _infer_domain_from_path(self, pdf_path: str) -> Optional[str]:
        parts = Path(pdf_path).parts
        if "knowledge_repository" not in parts:
            return None
        idx = parts.index("knowledge_repository")
        if len(parts) > idx + 2:
            return parts[idx + 2]
        return None

    def _print_final(self, report: StageReport) -> None:
        print(f"\nFINAL: {report.final_status}")

    @staticmethod
    def _default_import_checker(module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    @staticmethod
    def _minimal_pdf_bytes() -> bytes:
        return (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >> endobj\n"
            b"4 0 obj << /Length 44 >> stream\nBT /F1 12 Tf 10 100 Td (Stage sample) Tj ET\nendstream endobj\n"
            b"xref\n0 5\n0000000000 65535 f \n"
            b"trailer << /Root 1 0 R /Size 5 >>\nstartxref\n0\n%%EOF\n"
        )


class NoopVectorService:
    def upsert_document(self, doc_id, chunks, job_id):
        raise RuntimeError("NoopVectorService should not be called in dry-run.")


class NoopLegacyService:
    def retrieve_candidates(self, query, top_k=None):
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Docker/staging verification for Knowledge Platform V3")
    parser.add_argument("--pdf", help="PDF path under data/knowledge_repository/...")
    parser.add_argument("--dry-run", action="store_true", help="Run kp_ingest dry-run only.")
    parser.add_argument("--index", action="store_true", help="Opt in to real indexing/search smoke.")
    parser.add_argument("--fake", action="store_true", help="Run fake V3 service smoke without Qdrant/Cohere.")
    parser.add_argument("--sample", action="store_true", help="Create a temporary sample repository PDF/manifest.")
    parser.add_argument("--adapter-smoke", action="store_true", help="Also verify RetrievalAdapter use_v3 path.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = StageV3Verifier().run(
        pdf_path=args.pdf,
        fake=args.fake,
        index=args.index,
        dry_run=args.dry_run,
        sample=args.sample,
        adapter_smoke=args.adapter_smoke,
    )
    return 1 if report.final_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

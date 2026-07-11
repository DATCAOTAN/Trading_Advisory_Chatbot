import argparse
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ChecklistItem:
    name: str
    status: str
    message: str


@dataclass
class ChecklistReport:
    items: List[ChecklistItem] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.items.append(ChecklistItem(name, status, message))
        print(f"[{status}] {name}: {message}")

    @property
    def final_status(self) -> str:
        if any(item.status == "FAIL" for item in self.items):
            return "FAIL"
        if any(item.status == "SKIP" for item in self.items):
            return "SKIP"
        return "PASS"


class V3E2EChecklist:
    def __init__(
        self,
        import_checker: Optional[Callable[[str], bool]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.import_checker = import_checker or self._default_import_checker
        self.env = env if env is not None else os.environ

    def run(self, pdf_path: Optional[str] = None) -> ChecklistReport:
        report = ChecklistReport()
        self._check_config_defaults(report)
        self._check_dependencies(report)
        self._check_env(report)
        if pdf_path:
            self._check_pdf_path(report, Path(pdf_path))
        else:
            report.add("pdf", "SKIP", "No --pdf path provided; repository file checks skipped.")
        print(f"\nFINAL: {report.final_status}")
        return report

    def _check_config_defaults(self, report: ChecklistReport) -> None:
        from src.config import Config

        if Config.USE_KNOWLEDGE_V3 is False:
            report.add("config:USE_KNOWLEDGE_V3", "PASS", "Default remains False.")
        else:
            report.add("config:USE_KNOWLEDGE_V3", "FAIL", "Default is not False.")

    def _check_dependencies(self, report: ChecklistReport) -> None:
        for module in ["qdrant_client", "yaml", "pandas", "numpy"]:
            if self.import_checker(module):
                report.add(f"dependency:{module}", "PASS", f"{module} import is available.")
            else:
                report.add(f"dependency:{module}", "SKIP", f"{module} import is missing.")

    def _check_env(self, report: ChecklistReport) -> None:
        if self.env.get("COHERE_API_KEY"):
            report.add("env:COHERE_API_KEY", "PASS", "COHERE_API_KEY is set.")
        else:
            report.add("env:COHERE_API_KEY", "SKIP", "COHERE_API_KEY is missing; real indexing will be skipped.")

    def _check_pdf_path(self, report: ChecklistReport, pdf_path: Path) -> None:
        if not pdf_path.exists():
            report.add("pdf:exists", "FAIL", f"PDF does not exist: {pdf_path}")
            return
        if pdf_path.suffix.lower() != ".pdf":
            report.add("pdf:type", "FAIL", "Path is not a .pdf file.")
            return
        report.add("pdf:exists", "PASS", f"PDF exists: {pdf_path}")

        parts = pdf_path.parts
        if "knowledge_repository" not in parts:
            report.add("pdf:path_convention", "FAIL", "Path does not contain knowledge_repository.")
        else:
            idx = parts.index("knowledge_repository")
            if len(parts) >= idx + 6:
                report.add("pdf:path_convention", "PASS", "Path matches V3 repository convention shape.")
            else:
                report.add("pdf:path_convention", "FAIL", "Path is too short for V3 repository convention.")

        manifest = pdf_path.with_suffix(".manifest.yaml")
        if manifest.exists():
            report.add("manifest", "PASS", f"Manifest exists: {manifest}")
        else:
            report.add("manifest", "FAIL", f"Missing sidecar manifest: {manifest}")

    @staticmethod
    def _default_import_checker(module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only V3 Docker E2E checklist")
    parser.add_argument("--pdf", help="Optional PDF path to validate.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = V3E2EChecklist().run(pdf_path=args.pdf)
    return 1 if report.final_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

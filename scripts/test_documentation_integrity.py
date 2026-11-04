import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


REQUIRED_DOCS = [
    "README.md",
    "docs/PROJECT_CONTEXT_FOR_AI.md",
    "docs/architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md",
    "docs/architecture/00_system_overview.md",
    "docs/architecture/01_rag_evidence_core.md",
    "docs/architecture/02_agent_runtime.md",
    "docs/architecture/03_safety_compliance.md",
    "docs/architecture/04_evaluation_governance.md",
    "docs/architecture/05_dashboard_review_analytics.md",
    "docs/architecture/06_benchmark_hardening.md",
    "docs/architecture/07_data_flow.md",
    "docs/architecture/08_limitations_and_boundaries.md",
    "docs/operations/local_runbook.md",
    "docs/operations/testing_guide.md",
    "docs/operations/troubleshooting_guide.md",
    "docs/operations/docker_workflow.md",
    "docs/operations/data_storage_and_cleanup.md",
    "docs/demo/demo_script.md",
    "docs/demo/demo_scenarios.md",
    "docs/demo/interview_talking_points.md",
    "docs/demo/cv_project_summary.md",
    "docs/baselines/validated_baselines.md",
]

REQUIRED_DIAGRAMS = [
    "docs/architecture/diagrams/system_overview.mmd",
    "docs/architecture/diagrams/rag_evidence_flow.mmd",
    "docs/architecture/diagrams/agent_runtime_flow.mmd",
    "docs/architecture/diagrams/evaluation_governance_flow.mmd",
    "docs/architecture/diagrams/dashboard_review_flow.mmd",
    "docs/architecture/diagrams/benchmark_hardening_flow.mmd",
    "docs/architecture/diagrams/safety_boundary_flow.mmd",
]


def read(path):
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def all_doc_text():
    paths = REQUIRED_DOCS + REQUIRED_DIAGRAMS
    return "\n".join(read(path) for path in paths)


class DocumentationIntegrityTests(unittest.TestCase):
    def test_required_docs_and_diagrams_exist(self):
        for path in REQUIRED_DOCS:
            target = PROJECT_ROOT / path
            self.assertTrue(target.exists(), path)
            self.assertGreater(target.stat().st_size, 100, path)
        for path in REQUIRED_DIAGRAMS:
            target = PROJECT_ROOT / path
            self.assertTrue(target.exists(), path)
            self.assertGreater(target.stat().st_size, 20, path)

    def test_readme_safety_boundary(self):
        text = read("README.md").lower()

        self.assertIn("execution_allowed=false", text)
        self.assertIn("host-side mt5 bridge", text)
        for requirement in (
            "advisory_only", "human_confirmed_live", "autonomous_live",
            "standing mandate", "real accounts remain hard-blocked",
            "result_unknown", "historical results",
        ):
            self.assertIn(requirement, text)
        for obsolete_claim in (
            "this project is not a live trading bot",
            "no mt5 or broker order integration",
            "the bridge has no order endpoint",
        ):
            self.assertNotIn(obsolete_claim, text)

    def test_project_map_paths_and_local_document_links_exist(self):
        for path in ("README.md", "docs/PROJECT_CONTEXT_FOR_AI.md"):
            text = read(path)
            for reference in re.findall(r"`((?:src|scripts|tools)/[^`]+)`", text):
                self.assertTrue((PROJECT_ROOT / reference).exists(), reference)
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" not in link:
                    self.assertTrue(
                        (PROJECT_ROOT / path).parent.joinpath(link.split("#")[0]).exists(),
                        link,
                    )

    def test_docker_context_excludes_host_secrets_and_runtime_state(self):
        patterns = {
            line.strip() for line in read(".dockerignore").splitlines()
            if line.strip() and not line.startswith("#")
        }
        for protected_path in (
            ".env", ".streamlit/secrets.toml", "*.key",
            "cohere_key_api.txt", "key_api_gemini.txt", ".agents/",
            "Trading_Advisory_Chatbot.zip", "data/trading/",
            "data/cache/", "data/knowledge_catalog/", "tmp_debug_mt5_dry/",
        ):
            self.assertIn(protected_path, patterns)

    def test_safety_doc_explicit_prohibitions(self):
        text = read("docs/architecture/03_safety_compliance.md").lower()

        for phrase in [
            "buy/sell command generation",
            "entry price",
            "stop-loss",
            "take-profit",
            "lot size",
            "account-risk percent",
            "mt5 order execution",
        ]:
            self.assertIn(phrase, text)

    def test_architecture_docs_explain_evidence_and_agent_boundaries(self):
        overview = read("docs/architecture/00_system_overview.md")
        rag = read("docs/architecture/01_rag_evidence_core.md")
        agent = read("docs/architecture/02_agent_runtime.md")

        self.assertIn("EvidenceBundle", overview)
        self.assertIn("EvidenceBundle remains the grounding authority", rag)
        self.assertIn("Agent outputs are analysis context, not EvidenceItems", agent)

    def test_evaluation_governance_boundaries(self):
        text = read("docs/architecture/04_evaluation_governance.md")

        self.assertIn("BacktestEvaluation is advisory thesis evaluation, not a PnL trading backtest", text)
        self.assertIn("PaperTradingEvaluation is paper advisory follow-up evaluation, not paper bot execution", text)
        self.assertIn("HumanReview is annotation and quality review, not execution approval", text)

    def test_operations_use_project_venv_and_no_bare_test_runner(self):
        operations = "\n".join(read(path) for path in REQUIRED_DOCS if path.startswith("docs/operations/"))

        self.assertIn(r".\venv\Scripts\python.exe -m pytest", operations)
        for line in operations.splitlines():
            stripped = line.strip().lower()
            self.assertFalse(stripped.startswith("pytest "), line)
            self.assertFalse(stripped == "pytest", line)

    def test_docker_workflow_restart_without_unnecessary_rebuild(self):
        text = read("docs/operations/docker_workflow.md").lower()

        self.assertIn("docker-compose restart app", text)
        self.assertIn("rebuild only when dockerfile", text)
        self.assertIn("dependency", text)

    def test_docs_do_not_contain_secret_like_values(self):
        text = all_doc_text()
        secret_patterns = [
            r"\bsk-[A-Za-z0-9_-]{12,}",
            r"\b[A-Z0-9_]*(?:API|TOKEN|SECRET|KEY|PASSWORD|PASSWD|PWD)[A-Z0-9_]*\s*[:=]\s*['\"]?[^'\"\s]+",
            r"\b(?:mt5|broker)[_-]?(?:login|password|token|secret)\s*[:=]\s*['\"]?[^'\"\s]+",
        ]

        for pattern in secret_patterns:
            self.assertIsNone(re.search(pattern, text, re.IGNORECASE), pattern)

    def test_docs_do_not_overclaim_live_trading_or_profit(self):
        text = all_doc_text().lower()
        forbidden_claims = [
            "guaranteed profit",
            "guarantees trading performance",
            "profitable mt5 trading bot",
            "bot that trades automatically",
            "autonomous trading bot",
            "production financial advice readiness",
            "connects to mt5 and places orders",
            "mt5 order placement support",
        ]

        for claim in forbidden_claims:
            self.assertNotIn(claim, text)

    def test_docs_do_not_include_executable_trade_recommendations(self):
        text = all_doc_text().lower()
        forbidden_patterns = [
            r"\bbuy\s+(?:at|now)\b",
            r"\bsell\s+(?:at|now)\b",
            r"\brecommended\s+entry\b",
            r"\bentry\s+at\s+\d",
            r"\bstop\s+loss\s+at\s+\d",
            r"\btake\s+profit\s+at\s+\d",
            r"\blot\s+size\s*[:=]\s*\d",
            r"\baccount\s+risk\s*[:=]\s*\d",
        ]

        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, text), pattern)

    def test_cv_summary_uses_advisory_evaluation_wording(self):
        text = read("docs/demo/cv_project_summary.md").lower()

        self.assertIn("evidence-grounded financial advisory platform", text)
        self.assertIn("evaluation governance", text)
        self.assertIn("does not perform live trading", text)
        self.assertNotIn("profitable mt5 trading bot", text)


if __name__ == "__main__":
    unittest.main()

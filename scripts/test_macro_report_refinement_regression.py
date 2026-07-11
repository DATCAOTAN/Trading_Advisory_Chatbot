import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import knowledge_result, query_plan, task_view  # noqa: E402
from src.services.evidence import EvidenceSelector  # noqa: E402
from src.services.semantic.query_plan import QueryPlanAssembler  # noqa: E402


def report_plan(query="CPI report noi gi ve inflation?"):
    return query_plan(
        primary_intent="macro_report_summary",
        query=query,
        macro_events=["CPI"],
        organizations=["BLS"],
    )


def official_report_result(content, chunk_id, parent_id="", task_ids=None):
    result = knowledge_result(
        capability="official_report",
        target="CPI",
        content=content,
        title="US CPI Report",
        organization="BLS",
        event_type="CPI",
        task_ids=task_ids or ["task_1"],
    )
    result.data[0]["metadata"]["chunk_id"] = chunk_id
    if parent_id:
        result.data[0]["metadata"]["parent_chunk_id"] = parent_id
    return result


def official_report_multi_result(docs, task_ids=None):
    result = official_report_result("placeholder report content", "placeholder", task_ids=task_ids)
    result.data = []
    for index, doc in enumerate(docs, start=1):
        result.data.append(
            {
                "content": doc["content"],
                "metadata": {
                    "title": "US CPI Report",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "event_type": "CPI",
                    "section": "content",
                    "chunk_id": doc.get("chunk_id", f"doc-{index}"),
                    "parent_chunk_id": doc.get("parent_chunk_id", ""),
                },
                "score": doc.get("score", 0.9),
            }
        )
    return result


class MacroReportRefinementRegressionTests(unittest.TestCase):
    def test_report_summary_paraphrases_have_compatible_canonical_family(self):
        assembler = QueryPlanAssembler()
        queries = [
            "CPI report noi gi ve inflation?",
            "Tom tat nhung diem chinh trong bao cao CPI cua BLS.",
        ]

        plans = [assembler.assemble(query) for query in queries]

        self.assertTrue(all(plan.primary_intent == "macro_report_summary" for plan in plans))
        self.assertTrue(all("CPI" in plan.entities.macro_events for plan in plans))
        self.assertTrue(all(plan.requires_execution is False for plan in plans))

    def test_suitable_refined_component_evidence_improves_report_coverage(self):
        plan = report_plan()
        selector = EvidenceSelector()
        initial = official_report_result(
            "The report showed headline inflation increased 0.2 percent over the month "
            "and 3.0 percent over the year. It suggests inflation momentum slowed versus the prior period.",
            "initial-headline",
        )
        refined = official_report_result(
            "The report describes key components and category details across goods and services sectors. "
            "Component indexes show how separate categories contributed to the overall inflation reading.",
            "refined-components",
        )

        before = selector.select(plan, task_view(plan), [initial], "report_summary", "task_1")
        after = selector.select(plan, task_view(plan), [initial, refined], "report_summary", "task_1", phase="post_refinement")

        self.assertIn("important_components", before.coverage_result.missing_required_topics)
        self.assertEqual(before.coverage_result.coverage_ratio, 0.8)
        self.assertNotIn("important_components", after.coverage_result.missing_required_topics)
        self.assertEqual(after.coverage_result.coverage_ratio, 1.0)
        self.assertEqual(after.coverage_result.status, "COMPLETE")

    def test_refined_selected_documents_have_explicit_downstream_dispositions(self):
        plan = report_plan()
        result = official_report_multi_result(
            [
                {
                    "chunk_id": "component-a",
                    "parent_chunk_id": "parent-components",
                    "content": "The report lists key components and category details for the reported inflation measure.",
                },
                {
                    "chunk_id": "component-b",
                    "parent_chunk_id": "parent-components",
                    "content": "Component categories explain additional sector details in the same report section.",
                },
                {
                    "chunk_id": "metadata-only",
                    "content": "Copyright page. ISBN 0000. Library of Congress catalog data. Publisher address.",
                },
            ]
        )

        bundle = EvidenceSelector().select(plan, task_view(plan), [result], "report_summary", "task_1", phase="post_refinement")

        dispositions = bundle.evidence_dispositions
        self.assertEqual(len(dispositions), 3)
        self.assertTrue(all(item["status"] in {"USED", "REJECTED_WITH_REASON", "DEDUPLICATED_WITH_REASON"} for item in dispositions))
        self.assertTrue(any(item["status"] == "DEDUPLICATED_WITH_REASON" for item in dispositions))
        self.assertTrue(any(item["status"] == "REJECTED_WITH_REASON" and item["reason"] == "metadata_only" for item in dispositions))
        used_ids = {item.evidence_id for item in bundle.all_items}
        self.assertEqual(
            used_ids,
            {
                item["evidence_id"]
                for item in dispositions
                if item["status"] == "USED"
            },
        )

    def test_unsuitable_refined_evidence_remains_truthfully_degraded(self):
        plan = report_plan()
        selector = EvidenceSelector()
        initial = official_report_result(
            "The report showed headline inflation increased 0.2 percent over the month "
            "and 3.0 percent over the year. It suggests inflation momentum slowed versus the prior period.",
            "initial-headline",
        )
        unsuitable = official_report_result(
            "The report was published as an official release and repeats the headline inflation result for the period.",
            "refined-no-components",
        )

        bundle = selector.select(plan, task_view(plan), [initial, unsuitable], "report_summary", "task_1", phase="post_refinement")

        self.assertIn("important_components", bundle.coverage_result.missing_required_topics)
        self.assertEqual(bundle.coverage_result.status, "INSUFFICIENT")
        self.assertEqual(bundle.sufficiency.status, "COMPLETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)

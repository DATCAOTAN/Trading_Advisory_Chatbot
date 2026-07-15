import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents.journal_review import (  # noqa: E402
    JournalReviewAgent,
    JournalReviewInputBuilder,
    record_journal_review,
)
from src.ui.tab_chatbot import _answer_sha256, _build_answer_delivery_artifact  # noqa: E402


def answer(source=True):
    prefix = "Nguon da dung: Reading Price Charts Bar by Bar - Al Brooks.\n\n" if source else ""
    return (
        prefix +
        "- Price action duoc trinh bay nhu cach doc hanh vi gia theo boi canh.\n"
        "- Cau tra loi giu tinh dieu kien, khong dua ra lenh giao dich.\n"
        "- Rủi ro va gioi han dien giai duoc neu ro de tranh qua chac chan.\n\n"
        "Ket luan: day la ban tom tat co nguon va phu hop de luu review."
    )


def agent_result(agent_type, parent="task_1", payload=None):
    payload = payload or {}
    return {
        "task_id": f"{parent}:{agent_type}",
        "parent_task_id": parent,
        "agent_type": agent_type,
        "status": "SUCCESS",
        "structured_payload": payload,
        "failure_code": "",
    }


def market_payload(parent="task_1"):
    return {
        "task_id": f"{parent}:MarketContextAgent",
        "assessment_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "symbol": "XAUUSD",
        "market_state": {"directional_bias": "balanced"},
        "uncertainty": {"confidence": 0.6, "limitations": ["mixed context"]},
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
    }


def strategy_payload(parent="task_1"):
    return {
        "task_id": f"{parent}:StrategyAgent",
        "parent_task_id": parent,
        "thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "thesis_type": "mixed",
        "thesis_direction": "mixed",
        "confidence": {"value": 0.55},
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
    }


def risk_payload(parent="task_1"):
    return {
        "task_id": f"{parent}:RiskAgent",
        "parent_task_id": parent,
        "risk_ref": f"risk_assessment:{parent}:RiskAgent",
        "overall_risk_level": "elevated",
        "risk_posture": "conflicting_context",
        "confidence_adjustment": {"adjusted_confidence": 0.5},
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{parent}:StrategyAgent"],
    }


def consistency_payload(parent="task_1"):
    return {
        "task_id": f"{parent}:StrategyRiskConsistencyAgent",
        "parent_task_id": parent,
        "consistency_ref": f"consistency_assessment:{parent}:StrategyRiskConsistencyAgent",
        "consistency_status": "risk_weakened",
        "final_presentation_mode": "mixed_or_uncertain",
        "thesis_strength_after_risk": "weak",
        "confidence_reconciliation": {"final_confidence": 0.5},
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{parent}:StrategyAgent"],
        "risk_assessment_refs": [f"risk_assessment:{parent}:RiskAgent"],
    }


def completion(level="pass", reason="normal_stop", source=True):
    return {
        "level": level,
        "overall_status": "PASS" if level in {"pass", "warn"} else "FAIL",
        "reason": reason,
        "has_source_reference": source,
        "source_policy": "named_source_required",
    }


def runtime_artifacts(text, compliance="PASS", include_agents=True, multi=False):
    final = {"content": text, "source": "original", "repair_status": "NOT_ATTEMPTED", "chars": len(text), "sha256": _answer_sha256(text)}
    tasks = [
        {"task_id": "task_1:MarketContextAgent", "parent_task_id": "task_1", "agent_type": "MarketContextAgent", "intent_family": "macro_market_impact", "source_refs": ["market_snapshot:XAUUSD"]},
        {"task_id": "task_1:StrategyAgent", "parent_task_id": "task_1", "agent_type": "StrategyAgent", "intent_family": "macro_market_impact", "source_refs": ["market_snapshot:XAUUSD"]},
        {"task_id": "task_1:RiskAgent", "parent_task_id": "task_1", "agent_type": "RiskAgent", "intent_family": "macro_market_impact", "source_refs": ["market_snapshot:XAUUSD"]},
        {"task_id": "task_1:StrategyRiskConsistencyAgent", "parent_task_id": "task_1", "agent_type": "StrategyRiskConsistencyAgent", "intent_family": "macro_market_impact", "source_refs": ["market_snapshot:XAUUSD"]},
    ] if include_agents else []
    results = [
        agent_result("MarketContextAgent", payload=market_payload()),
        agent_result("StrategyAgent", payload=strategy_payload()),
        agent_result("RiskAgent", payload=risk_payload()),
        agent_result("StrategyRiskConsistencyAgent", payload=consistency_payload()),
    ] if include_agents else []
    evidence_bundles = [
        {
            "task_id": "task_1",
            "query_plan": {"task_id": "task_1", "primary_intent": "macro_market_impact" if include_agents else "book_concept_explanation", "requires_execution": False},
            "primary_evidence": [{"source_title": "Reading Price Charts Bar by Bar", "source_author": "Al Brooks"}],
        }
    ]
    contracts = [
        {
            "task_id": "task_1",
            "answer_type": "scenario_analysis" if include_agents else "static_explanation",
            "required_evidence_roles": ["official_report"] if include_agents else ["direct_book_passage"],
            "required_source_refs": ["US CPI Report - BLS"] if include_agents else ["Reading Price Charts Bar by Bar - Al Brooks"],
        }
    ]
    if multi:
        evidence_bundles.append({
            "task_id": "task_2",
            "query_plan": {"task_id": "task_2", "primary_intent": "book_concept_explanation", "requires_execution": False},
            "primary_evidence": [{"source_title": "Reading Price Charts Bar by Bar", "source_author": "Al Brooks"}],
        })
        contracts.append({
            "task_id": "task_2",
            "answer_type": "static_explanation",
            "required_evidence_roles": ["direct_book_passage"],
            "required_source_refs": ["Reading Price Charts Bar by Bar - Al Brooks"],
        })
    return {
        "final_answer_artifact": final,
        "answer_delivery_artifact": _build_answer_delivery_artifact(text, text, final),
        "answer_contracts": contracts,
        "evidence_bundles": evidence_bundles,
        "evidence_sufficiency": {"status": "COMPLETE", "confidence_ceiling": "high"},
        "claim_validation": {"status": "PASS"},
        "contract_evaluation": {"status": "PASS", "reason_codes": [], "repair_status": "NOT_ATTEMPTED"},
        "contract_evaluations": [{"task_id": contract["task_id"], "status": "PASS"} for contract in contracts],
        "agent_answer_compliance": {"status": compliance, "aggregate_status": compliance, "reason_codes": [], "final_answer_action": "accept"},
        "agent_runtime": {
            "execution_plan": {
                "request_id": "journal_req",
                "parent_intent": "multi_intent" if multi else ("macro_market_impact" if include_agents else "book_concept_explanation"),
                "execution_allowed": False,
                "tasks": tasks,
                "unavailable_agents": [] if include_agents else ["StaticKnowledgeAgent"],
            },
            "results": results,
            "aggregated_result": {"status": "PASS" if include_agents else "SKIPPED", "blocked_tasks": [], "warnings": []},
            "handoff": {"request_id": "journal_req", "agent_results": results, "warnings": []},
        },
    }


class JournalReviewAgentTests(unittest.TestCase):
    def test_journal_input_construction_and_record_schema(self):
        text = answer()
        artifacts = runtime_artifacts(text)

        review_input = JournalReviewInputBuilder.build(text, artifacts, completion(), "stored_with_quality_flag", "market query")
        record = JournalReviewAgent.review(review_input)

        self.assertEqual(review_input.final_answer_sha256, _answer_sha256(text))
        self.assertIn("task_1", review_input.task_ids)
        self.assertEqual(record.status, "RECORDED")
        self.assertEqual(record.quality_label, "high_quality")
        self.assertEqual(record.review_outcome, "suitable_for_memory")

    def test_compliance_warn_and_fail_quality(self):
        text = answer()
        warn_record = JournalReviewAgent.review(JournalReviewInputBuilder.build(text, runtime_artifacts(text, compliance="WARN"), completion(), "stored_with_quality_flag"))
        fail_record = JournalReviewAgent.review(JournalReviewInputBuilder.build(text, runtime_artifacts(text, compliance="FAIL"), completion(), "skip:compliance"))

        self.assertEqual(warn_record.status, "RECORDED_WITH_WARNINGS")
        self.assertEqual(warn_record.review_outcome, "suitable_for_later_review")
        self.assertEqual(fail_record.status, "DEGRADED")
        self.assertEqual(fail_record.quality_label, "unsafe_or_noncompliant")

    def test_answer_completeness_fail_and_missing_source_flag(self):
        text = answer(source=False)
        record = JournalReviewAgent.review(
            JournalReviewInputBuilder.build(text, runtime_artifacts(text, include_agents=False), completion("fail", "missing_source_reference", source=False), "skip:missing_source_reference")
        )

        self.assertEqual(record.quality_label, "incomplete")
        self.assertIn("missing_source_reference", record.task_reviews[0].review_flags)
        self.assertEqual(record.task_reviews[0].source_reference_status, "MISSING")

    def test_static_book_no_agent_path_does_not_require_market_agents(self):
        text = answer()
        record = JournalReviewAgent.review(
            JournalReviewInputBuilder.build(text, runtime_artifacts(text, include_agents=False), completion(), "stored_with_quality_flag")
        )

        self.assertEqual(record.agent_summary["agent_chain_status"], "SKIPPED")
        self.assertEqual(record.task_reviews[0].agent_status, "NOT_REQUIRED")
        self.assertFalse(record.agent_summary["market_context_present"])

    def test_multi_intent_task_reviews_are_scoped(self):
        text = answer() + "\n\nTask 2: Al Brooks price action source remains separate."
        record = JournalReviewAgent.review(
            JournalReviewInputBuilder.build(text, runtime_artifacts(text, multi=True), completion(), "stored_with_quality_flag")
        )

        self.assertEqual(len(record.task_reviews), 2)
        task_1 = next(item for item in record.task_reviews if item.task_id == "task_1")
        task_2 = next(item for item in record.task_reviews if item.task_id == "task_2")
        self.assertEqual(task_1.agent_status, "PASS")
        self.assertEqual(task_2.agent_status, "NOT_REQUIRED")
        self.assertEqual(task_2.intent_family, "static_explanation")

    def test_journal_does_not_create_evidence_or_modify_answer(self):
        text = answer()
        artifacts = runtime_artifacts(text)
        before_bundles = list(artifacts["evidence_bundles"])
        before_hash = _answer_sha256(text)

        record_journal_review(text, artifacts, completion(), "stored_with_quality_flag", "query")

        self.assertEqual(_answer_sha256(text), before_hash)
        self.assertEqual(artifacts["evidence_bundles"], before_bundles)
        self.assertIn("journal_review", artifacts)
        self.assertNotIn("EvidenceItem", str(artifacts["journal_review"]))

    def test_hash_mismatch_degrades_record(self):
        text = answer()
        artifacts = runtime_artifacts(text)
        artifacts["answer_delivery_artifact"]["canonical_sha256"] = _answer_sha256("different")

        record = JournalReviewAgent.review(JournalReviewInputBuilder.build(text, artifacts, completion(), "stored_with_quality_flag"))

        self.assertEqual(record.status, "DEGRADED")
        self.assertIn("artifact_hash_mismatch", record.limitations)

    def test_execution_allowed_and_trading_terms_create_safety_failure(self):
        text = "Nguon da dung: Reading Price Charts Bar by Bar - Al Brooks. Buy now, entry price 4100, SL 4090, use 1 lot on MT5. Ket luan: unsafe."
        artifacts = runtime_artifacts(text)
        artifacts["agent_runtime"]["execution_plan"]["execution_allowed"] = True

        record = JournalReviewAgent.review(JournalReviewInputBuilder.build(text, artifacts, completion(), "skip:safety"))

        self.assertEqual(record.safety_summary["safety_status"], "FAIL")
        self.assertTrue(record.safety_summary["execution_allowed"])
        self.assertTrue(record.safety_summary["trading_instruction_detected"])
        self.assertTrue(record.safety_summary["position_sizing_detected"])
        self.assertTrue(record.safety_summary["mt5_execution_detected"])
        self.assertEqual(record.quality_label, "unsafe_or_noncompliant")

    def test_redaction_and_no_storage_failure_with_none_artifacts(self):
        text = answer()
        artifacts = runtime_artifacts(text)
        review_input = JournalReviewInputBuilder.build(text, artifacts, completion(), "stored", "API_KEY=secret-value Al Brooks query")

        self.assertIn("[REDACTED]", review_input.user_query)
        self.assertIsNone(record_journal_review(text, None, completion(), "skip"))

    def test_runtime_artifact_records_memory_policy_and_compliance(self):
        text = answer()
        artifacts = runtime_artifacts(text)

        record = record_journal_review(text, artifacts, completion(), "stored_with_quality_flag", "query")

        self.assertIsNotNone(record)
        self.assertEqual(artifacts["journal_review"]["validation_summary"]["memory_policy_action"], "stored_with_quality_flag")
        self.assertEqual(artifacts["journal_review"]["validation_summary"]["agent_answer_compliance"], "PASS")
        self.assertFalse(artifacts["journal_review"]["safety_summary"]["execution_allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

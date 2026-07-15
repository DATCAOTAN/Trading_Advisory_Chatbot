import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents.backtest_evaluation import (  # noqa: E402
    BacktestEvaluationAgent,
    BacktestEvaluationInputBuilder,
    BacktestEvaluationRecord,
    BacktestEvaluationSafetyValidator,
    BacktestTaskEvaluation,
    HistoricalObservationWindow,
    record_backtest_evaluation,
)


def market_snapshot(direction="bullish_bias", confidence=0.7, mode="standard_conditional", risk_level="elevated"):
    return {
        "request_id": "bt_req",
        "task_id": "task_1",
        "parent_task_id": "task_1",
        "intent_family": "macro_market_impact",
        "symbol": "XAUUSD",
        "evidence_bundle_ref": "evidence_bundle:task_1",
        "allowed_source_refs": ["market_snapshot:XAUUSD", "ohlcv:XAUUSD"],
        "strategy": {
            "thesis_ref": "strategy_thesis:task_1:StrategyAgent",
            "thesis_direction": direction,
            "confidence": {"value": confidence},
            "limitations": ["conditional thesis"],
        },
        "risk": {
            "risk_ref": "risk_assessment:task_1:RiskAgent",
            "overall_risk_level": risk_level,
            "risk_posture": "conflicting_context" if risk_level in {"elevated", "high"} else "acceptable_with_conditions",
            "confidence_adjustment": {"adjusted_confidence": min(confidence, 0.55)},
            "limitations": ["event risk"],
        },
        "consistency": {
            "consistency_ref": "consistency_assessment:task_1:StrategyRiskConsistencyAgent",
            "final_presentation_mode": mode,
            "confidence_reconciliation": {"final_confidence": min(confidence, 0.55)},
            "limitations": ["present cautiously"],
        },
        "execution_allowed": False,
    }


def static_snapshot():
    return {
        "request_id": "bt_req",
        "task_id": "task_2",
        "parent_task_id": "task_2",
        "intent_family": "book_concept_explanation",
        "symbol": "",
        "evidence_bundle_ref": "evidence_bundle:task_2",
        "allowed_source_refs": ["Reading Price Charts Bar by Bar - Al Brooks"],
        "execution_allowed": False,
    }


def journal_record(multi=False, quality="high_quality"):
    task_reviews = [
        {
            "task_id": "task_1",
            "intent_family": "macro_market_impact",
            "agent_status": "PASS",
            "compliance_status": "PASS",
            "completeness_status": "PASS",
            "source_reference_status": "PRESENT",
        }
    ]
    snapshots = {"task_1": market_snapshot()}
    if multi:
        task_reviews.append(
            {
                "task_id": "task_2",
                "intent_family": "book_concept_explanation",
                "agent_status": "NOT_REQUIRED",
                "compliance_status": "PASS",
                "completeness_status": "PASS",
                "source_reference_status": "PRESENT",
            }
        )
        snapshots["task_2"] = static_snapshot()
    status = "RECORDED" if quality == "high_quality" else "DEGRADED"
    outcome = "suitable_for_memory" if quality == "high_quality" else "needs_human_review"
    return {
        "journal_id": "journal_review:bt_req",
        "request_id": "bt_req",
        "created_at": "2026-07-12T00:00:00+00:00",
        "final_answer_sha256": "abc123",
        "status": status,
        "quality_label": quality,
        "review_outcome": outcome,
        "task_reviews": task_reviews,
        "evidence_summary": {
            "evidence_bundle_refs": ["evidence_bundle:task_1", "evidence_bundle:task_2"],
            "source_refs": ["market_snapshot:XAUUSD", "ohlcv:XAUUSD"],
            "source_reference_present": True,
        },
        "validation_summary": {
            "agent_answer_compliance": "PASS",
            "answer_completeness_status": "PASS",
            "memory_policy_action": "stored_with_quality_flag",
        },
        "compact_task_analysis_snapshots": snapshots,
        "safety_summary": {"execution_allowed": False},
    }


def window(direction="up", task_id="task_1", volatile=False):
    if direction == "up":
        start, end, high, low = 2400.0, 2424.0, 2430.0, 2398.0
    elif direction == "down":
        start, end, high, low = 2400.0, 2370.0, 2402.0, 2365.0
    elif direction == "sideways":
        start, end, high, low = 2400.0, 2402.0, 2405.0, 2395.0
    else:
        start, end, high, low = 2400.0, 2403.0, 2455.0, 2350.0
    return HistoricalObservationWindow(
        window_id=f"window:{task_id}",
        task_id=task_id,
        symbol="XAUUSD",
        start_time="2026-07-12T00:00:00Z",
        end_time="2026-07-13T00:00:00Z",
        timeframe="1h",
        start_price=start,
        end_price=end,
        high_price=high,
        low_price=low,
        net_change_pct=round((end - start) / start * 100, 4),
        realized_range_pct=round((high - low) / low * 100, 4),
        volatility_proxy=3.0 if volatile else round((high - low) / low * 100, 4),
        direction_label="volatile_mixed" if volatile else direction,
        notable_market_behavior=[f"direction_label:{'volatile_mixed' if volatile else direction}"],
        data_quality="complete",
    )


class BacktestEvaluationTests(unittest.TestCase):
    def test_input_historical_window_and_record_schema(self):
        built_window = HistoricalObservationWindow.from_observations(
            "w1",
            "task_1",
            "XAUUSD",
            "2026-07-12T00:00:00Z",
            "2026-07-12T03:00:00Z",
            "1h",
            [
                {"open": 2400, "high": 2410, "low": 2390, "close": 2405},
                {"open": 2405, "high": 2425, "low": 2400, "close": 2420},
            ],
        )
        evaluation_input = BacktestEvaluationInputBuilder.build(journal_record(), [built_window])
        record = BacktestEvaluationAgent.evaluate(evaluation_input)

        self.assertEqual(built_window.direction_label, "up")
        self.assertEqual(evaluation_input.final_answer_sha256, "abc123")
        self.assertEqual(evaluation_input.evaluation_policy["no_trade_simulation"], True)
        self.assertEqual(record.status, "EVALUATED")
        self.assertEqual(record.evaluation_type, "thesis_outcome_alignment")
        self.assertEqual(record.safety_summary["execution_allowed"], False)

    def test_missing_journal_and_missing_historical_data(self):
        skipped_input = BacktestEvaluationInputBuilder.build(None, [])
        skipped = BacktestEvaluationAgent.evaluate(skipped_input)
        insufficient = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), []))

        self.assertEqual(skipped.status, "SKIPPED")
        self.assertEqual(insufficient.status, "INSUFFICIENT_DATA")
        self.assertIn("missing_historical_observation_window", insufficient.limitations)

    def test_bullish_alignment_and_contradiction(self):
        aligned = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), [window("up")]))
        contradicted = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), [window("down")]))

        self.assertEqual(aligned.task_evaluations[0].thesis_alignment, "aligned")
        self.assertEqual(contradicted.task_evaluations[0].thesis_alignment, "contradicted")
        self.assertEqual(contradicted.task_evaluations[0].confidence_calibration, "overconfident")
        self.assertIn("task_1", contradicted.aggregate_review["contradicted_tasks"])

    def test_mixed_thesis_and_mixed_observation_aligns_with_reasonable_calibration(self):
        journal = journal_record()
        journal["compact_task_analysis_snapshots"]["task_1"] = market_snapshot(
            direction="mixed",
            confidence=0.5,
            mode="mixed_or_uncertain",
            risk_level="elevated",
        )
        record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal, [window("mixed", volatile=True)]))

        self.assertEqual(record.task_evaluations[0].thesis_alignment, "aligned")
        self.assertEqual(record.task_evaluations[0].risk_materialization, "materialized")
        self.assertEqual(record.task_evaluations[0].confidence_calibration, "reasonable")

    def test_elevated_risk_materialization_and_calm_non_materialization(self):
        volatile_record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), [window("mixed", volatile=True)]))
        calm_record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), [window("sideways")]))

        self.assertEqual(volatile_record.task_evaluations[0].risk_materialization, "materialized")
        self.assertEqual(calm_record.task_evaluations[0].risk_materialization, "not_materialized")

    def test_static_book_task_is_not_applicable_and_multi_intent_is_scoped(self):
        record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(multi=True), [window("up", "task_1")]))
        task_1 = next(item for item in record.task_evaluations if item.task_id == "task_1")
        task_2 = next(item for item in record.task_evaluations if item.task_id == "task_2")

        self.assertEqual(record.status, "EVALUATED")
        self.assertEqual(task_1.status, "EVALUATED")
        self.assertEqual(task_2.status, "SKIPPED")
        self.assertEqual(task_2.thesis_alignment, "not_applicable")
        self.assertEqual(task_2.observation_window_id, "")
        self.assertNotIn("XAUUSD", json.dumps(task_2.as_dict()))

    def test_degraded_journal_and_hash_mismatch_produce_warning_or_skip(self):
        degraded = journal_record(quality="failed_validation")
        record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(degraded, [window("up")]))

        self.assertEqual(record.status, "EVALUATED_WITH_WARNINGS")
        self.assertEqual(record.quality_label, "limited_review")
        self.assertIn("journal_record_degraded", record.limitations)

    def test_evaluation_does_not_mutate_journal_final_answer_or_evidence(self):
        journal = journal_record()
        before = copy.deepcopy(journal)
        artifacts = {"journal_review": journal, "evidence_bundles": [{"task_id": "task_1"}]}

        record = record_backtest_evaluation(artifacts, [window("up")])

        self.assertIsNotNone(record)
        self.assertEqual(journal, before)
        self.assertEqual(artifacts["evidence_bundles"], [{"task_id": "task_1"}])
        self.assertIn("backtest_evaluation", artifacts)
        self.assertEqual(artifacts["backtest_evaluation"]["original_answer_sha256"], "abc123")
        self.assertNotIn("EvidenceItem", str(artifacts["backtest_evaluation"]))

    def test_safety_validator_rejects_trading_and_execution_terms_but_allows_observation_terms(self):
        safe = BacktestEvaluationRecord(
            evaluation_id="safe",
            request_id="req",
            journal_id="journal",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="thesis_outcome_alignment",
            quality_label="useful_for_review",
            task_evaluations=[BacktestTaskEvaluation(task_id="task_1", intent_family="macro_market_impact", review_notes=["historical observation and volatility calibration only"])],
            safety_summary={"execution_allowed": False},
        )
        unsafe = BacktestEvaluationRecord(
            evaluation_id="unsafe",
            request_id="req",
            journal_id="journal",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="thesis_outcome_alignment",
            quality_label="useful_for_review",
            task_evaluations=[BacktestTaskEvaluation(task_id="task_1", intent_family="macro_market_impact", review_notes=["buy now with entry 2400, SL 2390, TP 2450, use 1 lot on MT5"])],
            safety_summary={"execution_allowed": False},
        )
        record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal_record(), [window("up")]))

        self.assertEqual(BacktestEvaluationSafetyValidator.validate_record(safe)["safety_status"], "PASS")
        self.assertEqual(BacktestEvaluationSafetyValidator.validate_record(unsafe)["safety_status"], "FAIL")
        self.assertEqual(record.safety_summary["no_execution"], True)
        self.assertFalse(record.prohibited_outputs_detected)

    def test_execution_allowed_true_if_simulated_creates_safety_failure(self):
        record = BacktestEvaluationRecord(
            evaluation_id="unsafe_exec",
            request_id="req",
            journal_id="journal",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="thesis_outcome_alignment",
            quality_label="useful_for_review",
            safety_summary={"execution_allowed": True},
        )

        self.assertEqual(BacktestEvaluationSafetyValidator.validate_record(record)["safety_status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)

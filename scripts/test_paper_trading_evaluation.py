import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_backtest_evaluation import (  # noqa: E402
    BacktestEvaluationAgent,
    BacktestEvaluationInputBuilder,
    journal_record,
    market_snapshot,
    window,
)
from src.services.agents.paper_trading_evaluation import (  # noqa: E402
    PaperTaskEvaluation,
    PaperTradingEvaluationAgent,
    PaperTradingEvaluationInputBuilder,
    PaperTradingEvaluationRecord,
    PaperTradingEvaluationSafetyValidator,
    SimulatedObservationPoint,
    record_paper_trading_evaluation,
)


def backtest_record(journal=None, status="EVALUATED"):
    journal = journal or journal_record()
    record = BacktestEvaluationAgent.evaluate(BacktestEvaluationInputBuilder.build(journal, [window("up")]))
    data = record.as_dict()
    data["status"] = status
    data["quality_label"] = "useful_for_review" if status == "EVALUATED" else "limited_review"
    return data


def point(
    observation_id,
    task_id="task_1",
    direction="up",
    confirmation="confirmed",
    invalidation="not_invalidated",
    risk="risk_not_materialized",
    volatile=False,
):
    return SimulatedObservationPoint(
        observation_id=observation_id,
        task_id=task_id,
        symbol="XAUUSD",
        timestamp=f"2026-07-12T0{observation_id[-1]}:00:00Z",
        timeframe="1h",
        observed_price=2420.0,
        previous_price=2410.0,
        net_change_pct_from_start=0.8,
        range_pct_from_start=3.0 if volatile else 0.9,
        volatility_proxy=3.0 if volatile else 0.9,
        direction_label="volatile_mixed" if volatile else direction,
        confirmation_state=confirmation,
        invalidation_state=invalidation,
        risk_state=risk,
        context_notes=[f"simulated observation {observation_id}"],
        data_quality="complete",
    )


class PaperTradingEvaluationTests(unittest.TestCase):
    def test_input_point_and_record_schema(self):
        journal = journal_record()
        backtest = backtest_record(journal)
        evaluation_input = PaperTradingEvaluationInputBuilder.build(journal, backtest, [point("obs1")])
        record = PaperTradingEvaluationAgent.evaluate(evaluation_input)

        self.assertEqual(evaluation_input.final_answer_sha256, "abc123")
        self.assertEqual(evaluation_input.evaluation_policy["no_trade_simulation"], True)
        self.assertEqual(evaluation_input.evaluation_policy["no_account_data"], True)
        self.assertEqual(record.status, "EVALUATED")
        self.assertEqual(record.evaluation_type, "advisory_followup_evaluation")
        self.assertEqual(record.safety_summary["execution_allowed"], False)

    def test_high_quality_journal_backtest_and_timeline_evaluates(self):
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(journal_record(), backtest_record(), [point("obs1"), point("obs2")])
        )

        task = record.task_evaluations[0]
        self.assertEqual(record.quality_label, "useful_for_review")
        self.assertEqual(task.advisory_followup_outcome, "thesis_remained_valid")
        self.assertEqual(task.confirmation_review, "confirmation_observed")
        self.assertEqual(task.invalidation_review, "invalidation_not_observed")
        self.assertEqual(task.risk_review, "risk_not_materialized")

    def test_degraded_journal_or_warn_backtest_limited_review(self):
        degraded = journal_record(quality="failed_validation")
        warn_backtest = backtest_record(degraded, status="EVALUATED_WITH_WARNINGS")
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(degraded, warn_backtest, [point("obs1")])
        )

        self.assertEqual(record.status, "EVALUATED_WITH_WARNINGS")
        self.assertEqual(record.quality_label, "limited_review")
        self.assertIn("journal_record_degraded", record.limitations)

    def test_missing_backtest_or_missing_timeline(self):
        missing_backtest = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(journal_record(), None, [point("obs1")])
        )
        missing_timeline = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(journal_record(), backtest_record(), [])
        )

        self.assertEqual(missing_backtest.status, "SKIPPED")
        self.assertIn("missing_backtest_evaluation_record", missing_backtest.limitations)
        self.assertEqual(missing_timeline.status, "INSUFFICIENT_DATA")
        self.assertIn("missing_simulated_observation_timeline", missing_timeline.limitations)

    def test_static_task_not_applicable_and_multi_intent_scoped(self):
        journal = journal_record(multi=True)
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(journal, backtest_record(journal), [point("obs1", "task_1")])
        )
        task_1 = next(item for item in record.task_evaluations if item.task_id == "task_1")
        task_2 = next(item for item in record.task_evaluations if item.task_id == "task_2")

        self.assertEqual(task_1.status, "EVALUATED")
        self.assertEqual(task_2.status, "SKIPPED")
        self.assertEqual(task_2.advisory_followup_outcome, "not_applicable")
        self.assertNotIn("XAUUSD", json.dumps(task_2.as_dict()))

    def test_mixed_thesis_and_mixed_timeline_reasonable(self):
        journal = journal_record()
        journal["compact_task_analysis_snapshots"]["task_1"] = market_snapshot(
            direction="mixed",
            confidence=0.5,
            mode="mixed_or_uncertain",
            risk_level="elevated",
        )
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(
                journal,
                backtest_record(journal),
                [
                    point("obs1", direction="sideways", confirmation="partially_confirmed", volatile=True, risk="risk_materialized"),
                    point("obs2", direction="sideways", confirmation="not_confirmed", volatile=True, risk="risk_partially_materialized"),
                ],
            )
        )
        task = record.task_evaluations[0]

        self.assertEqual(task.confidence_review, "reasonable")
        self.assertIn(task.advisory_followup_outcome, {"thesis_remained_valid", "thesis_partially_valid"})
        self.assertEqual(task.risk_review, "risk_materialized")

    def test_one_sided_thesis_repeated_contradictions_invalidates(self):
        journal = journal_record()
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(
                journal,
                backtest_record(journal),
                [
                    point("obs1", direction="down", confirmation="contradicted", invalidation="partially_invalidated"),
                    point("obs2", direction="down", confirmation="contradicted", invalidation="invalidated"),
                ],
            )
        )
        task = record.task_evaluations[0]

        self.assertEqual(task.advisory_followup_outcome, "thesis_invalidated")
        self.assertEqual(task.invalidation_review, "invalidation_observed")
        self.assertEqual(task.confidence_review, "overconfident")

    def test_confirmation_and_invalidation_states_are_counted(self):
        record = PaperTradingEvaluationAgent.evaluate(
            PaperTradingEvaluationInputBuilder.build(
                journal_record(),
                backtest_record(),
                [
                    point("obs1", confirmation="confirmed", invalidation="not_invalidated"),
                    point("obs2", confirmation="contradicted", invalidation="partially_invalidated"),
                ],
            )
        )
        summary = record.task_evaluations[0].timeline_summary

        self.assertEqual(summary["confirmed_count"], 1)
        self.assertEqual(summary["contradicted_count"], 1)
        self.assertEqual(summary["partially_invalidated_count"], 1)

    def test_records_hash_and_does_not_mutate_inputs_or_evidence(self):
        journal = journal_record()
        backtest = backtest_record(journal)
        journal_before = copy.deepcopy(journal)
        backtest_before = copy.deepcopy(backtest)
        artifacts = {
            "journal_review": journal,
            "backtest_evaluation": backtest,
            "evidence_bundles": [{"task_id": "task_1"}],
        }

        record = record_paper_trading_evaluation(artifacts, [point("obs1")])

        self.assertIsNotNone(record)
        self.assertEqual(journal, journal_before)
        self.assertEqual(backtest, backtest_before)
        self.assertEqual(artifacts["evidence_bundles"], [{"task_id": "task_1"}])
        self.assertEqual(artifacts["paper_trading_evaluation"]["original_answer_sha256"], "abc123")
        self.assertNotIn("EvidenceItem", str(artifacts["paper_trading_evaluation"]))

    def test_safety_validator_rejects_trading_terms_and_allows_safe_terms(self):
        safe = PaperTradingEvaluationRecord(
            paper_evaluation_id="safe",
            request_id="req",
            journal_id="journal",
            backtest_evaluation_id="backtest",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="advisory_followup_evaluation",
            quality_label="useful_for_review",
            task_evaluations=[
                PaperTaskEvaluation(
                    task_id="task_1",
                    intent_family="macro_market_impact",
                    review_notes=["simulated observation timeline and advisory follow-up review only"],
                )
            ],
            safety_summary={"execution_allowed": False},
        )
        unsafe = PaperTradingEvaluationRecord(
            paper_evaluation_id="unsafe",
            request_id="req",
            journal_id="journal",
            backtest_evaluation_id="backtest",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="advisory_followup_evaluation",
            quality_label="useful_for_review",
            task_evaluations=[
                PaperTaskEvaluation(
                    task_id="task_1",
                    intent_family="macro_market_impact",
                    review_notes=["buy now with entry 2400, SL 2390, TP 2450, lot size 1, MT5 broker order, PnL optimization"],
                )
            ],
            safety_summary={"execution_allowed": False},
        )

        self.assertEqual(PaperTradingEvaluationSafetyValidator.validate_record(safe)["safety_status"], "PASS")
        self.assertEqual(PaperTradingEvaluationSafetyValidator.validate_record(unsafe)["safety_status"], "FAIL")

    def test_execution_allowed_true_if_simulated_creates_safety_failure(self):
        record = PaperTradingEvaluationRecord(
            paper_evaluation_id="unsafe_exec",
            request_id="req",
            journal_id="journal",
            backtest_evaluation_id="backtest",
            created_at="now",
            original_answer_sha256="hash",
            status="EVALUATED",
            evaluation_type="advisory_followup_evaluation",
            quality_label="useful_for_review",
            safety_summary={"execution_allowed": True},
        )

        self.assertEqual(PaperTradingEvaluationSafetyValidator.validate_record(record)["safety_status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)

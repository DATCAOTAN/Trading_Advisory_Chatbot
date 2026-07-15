import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents.answer_compliance import (
    AgentAnswerComplianceGate,
    AgentAnswerComplianceInput,
    AgentAnswerComplianceInputBuilder,
)
from src.ui.tab_chatbot import _answer_sha256, check_answer_completeness


def strategy(task="task_1", thesis_type="mixed", direction="mixed", confidence=0.6):
    return {
        "task_id": f"{task}:StrategyAgent",
        "parent_task_id": task,
        "thesis_ref": f"strategy_thesis:{task}:StrategyAgent",
        "thesis_type": thesis_type,
        "thesis_direction": direction,
        "confidence": {"value": confidence, "ceiling": "medium"},
        "evidence_refs": [f"evidence_bundle:{task}"],
        "market_context_refs": [f"market_context_assessment:{task}:MarketContextAgent"],
    }


def risk(task="task_1", level="elevated", posture="conflicting_context", adjusted=0.55):
    return {
        "task_id": f"{task}:RiskAgent",
        "parent_task_id": task,
        "risk_ref": f"risk_assessment:{task}:RiskAgent",
        "overall_risk_level": level,
        "risk_posture": posture,
        "confidence_adjustment": {
            "original_strategy_confidence": 0.6,
            "adjusted_confidence": adjusted,
        },
        "evidence_refs": [f"evidence_bundle:{task}"],
        "market_context_refs": [f"market_context_assessment:{task}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{task}:StrategyAgent"],
    }


def consistency(task="task_1", mode="mixed_or_uncertain", status="risk_weakened", strength="weak", final_confidence=0.55):
    return {
        "task_id": f"{task}:StrategyRiskConsistencyAgent",
        "parent_task_id": task,
        "consistency_ref": f"consistency_assessment:{task}:StrategyRiskConsistencyAgent",
        "assessed_strategy_thesis_ref": f"strategy_thesis:{task}:StrategyAgent",
        "assessed_risk_assessment_ref": f"risk_assessment:{task}:RiskAgent",
        "consistency_status": status,
        "final_presentation_mode": mode,
        "thesis_strength_after_risk": strength,
        "confidence_reconciliation": {
            "strategy_confidence": 0.6,
            "risk_adjusted_confidence": 0.55,
            "final_confidence": final_confidence,
        },
        "evidence_refs": [f"evidence_bundle:{task}"],
        "market_context_refs": [f"market_context_assessment:{task}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{task}:StrategyAgent"],
        "risk_assessment_refs": [f"risk_assessment:{task}:RiskAgent"],
    }


def compliance_input(answer, task_ids=None, with_agents=True, task_scope_map=None):
    task_ids = task_ids or ["task_1"]
    return AgentAnswerComplianceInput(
        request_id="compliance_req",
        final_answer_text=answer,
        final_answer_sha256=_answer_sha256(answer),
        answer_type="market_analysis",
        parent_intent="market_state_analysis",
        task_ids=task_ids,
        evidence_bundle_refs_by_task={task: f"evidence_bundle:{task}" for task in task_ids},
        market_context_assessments_by_task={"task_1": {"assessment_ref": "market_context_assessment:task_1:MarketContextAgent"}} if with_agents else {},
        strategy_theses_by_task={"task_1": strategy()} if with_agents else {},
        risk_assessments_by_task={"task_1": risk()} if with_agents else {},
        consistency_assessments_by_task={"task_1": consistency()} if with_agents else {},
        confidence_ceiling_by_task={task: "medium" for task in task_ids},
        task_scope_map=task_scope_map or {task: "market_analysis" for task in task_ids},
        execution_allowed=False,
    )


def cautious_answer():
    return (
        "### Thị trường\n"
        "- Luận điểm hiện tại chỉ nên xem là kịch bản có điều kiện.\n"
        "- Bối cảnh còn mixed và cần xác nhận thêm trước khi diễn giải mạnh.\n"
        "- Rủi ro đang elevated, nên phần kết luận phải thận trọng.\n\n"
        "Kết luận: đây là phân tích xác suất có điều kiện, không phải hướng dẫn thực thi."
    )


def static_book_sources():
    return [{"metadata": {"title": "Reading Price Charts Bar by Bar", "author": "Al Brooks", "knowledge_type": "book"}}]


def static_book_runtime_artifacts(answer, compliance_status="PASS"):
    return {
        "answer_contracts": [
            {
                "answer_type": "static_explanation",
                "required_sections": ["source_used", "short_conclusion"],
                "required_evidence_roles": ["direct_book_passage"],
                "required_source_refs": ["Reading Price Charts Bar by Bar - Al Brooks"],
            }
        ],
        "evidence_sufficiency": {"status": "COMPLETE", "missing_roles": [], "warnings": []},
        "claim_validation": {"status": "PASS"},
        "contract_evaluation": {"status": "PASS", "reason_codes": [], "repair_status": "NOT_ATTEMPTED"},
        "agent_answer_compliance": {"status": compliance_status},
        "final_answer_artifact": {"sha256": _answer_sha256(answer)},
    }


class AgentAnswerComplianceTests(unittest.TestCase):
    def test_compliance_input_construction_from_runtime_artifacts(self):
        answer = cautious_answer()
        runtime_artifacts = {
            "agent_runtime": {
                "execution_plan": {"request_id": "req", "parent_intent": "market_state_analysis", "execution_allowed": False},
                "handoff": {
                    "request_id": "req",
                    "agent_results": [
                        {"agent_type": "StrategyAgent", "status": "SUCCESS", "parent_task_id": "task_1", "task_id": "task_1:StrategyAgent", "structured_payload": strategy()},
                        {"agent_type": "RiskAgent", "status": "SUCCESS", "parent_task_id": "task_1", "task_id": "task_1:RiskAgent", "structured_payload": risk()},
                        {"agent_type": "StrategyRiskConsistencyAgent", "status": "SUCCESS", "parent_task_id": "task_1", "task_id": "task_1:StrategyRiskConsistencyAgent", "structured_payload": consistency()},
                    ],
                },
            },
            "evidence_bundles": [{"task_id": "task_1"}],
        }

        built = AgentAnswerComplianceInputBuilder.build(answer, runtime_artifacts, answer_contracts=[])

        self.assertEqual(built.request_id, "req")
        self.assertEqual(built.task_ids, ["task_1"])
        self.assertIn("task_1", built.risk_assessments_by_task)
        self.assertFalse(built.execution_allowed)

    def test_pass_when_final_answer_matches_cautious_consistency_mode(self):
        result = AgentAnswerComplianceGate.evaluate(compliance_input(cautious_answer()))

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.final_answer_action, "accept")

    def test_fail_for_overstatement_trading_instruction_and_consistency_violation(self):
        answer = "XAUUSD chắc chắn sẽ tăng mạnh, nên mua ngay."
        result = AgentAnswerComplianceGate.evaluate(compliance_input(answer))

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.overstatement_detected)
        self.assertTrue(result.trading_instruction_detected)
        self.assertTrue(result.consistency_violation_detected)
        self.assertIn("trading_instruction", result.reason_codes)

    def test_fail_when_elevated_risk_is_omitted(self):
        answer = "XAUUSD có thể dao động trong vùng hiện tại. Kết luận: phân tích thị trường ở trạng thái cân bằng."
        result = AgentAnswerComplianceGate.evaluate(compliance_input(answer))

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.risk_omission_detected)
        self.assertIn("risk_omission", result.reason_codes)

    def test_trading_instruction_patterns_fail(self):
        cases = [
            "buy now",
            "sell now",
            "entry price 4100",
            "set stop-loss",
            "stop-loss 4090",
            "SL: 4090",
            "set take-profit",
            "take-profit 4200",
            "TP: 4200",
            "lot size 0.01",
            "position size 0.01",
            "risk 1%",
            "account risk 1%",
            "place order in MT5",
            "vào lệnh",
            "điểm vào",
            "cắt lỗ",
            "chốt lời",
            "khối lượng lệnh",
            "phần trăm tài khoản",
            "đặt lệnh",
        ]
        for text in cases:
            with self.subTest(text=text):
                result = AgentAnswerComplianceGate.evaluate(compliance_input(f"{cautious_answer()} {text}"))
                self.assertEqual(result.status, "FAIL")
                self.assertTrue(result.trading_instruction_detected)

    def test_safe_caution_and_conditional_scenario_phrasing_pass(self):
        answer = (
            "Kịch bản tăng chỉ có ý nghĩa nếu dữ liệu xác nhận thêm. "
            "Rủi ro vẫn cần được quản trị chặt chẽ và đây không phải khuyến nghị giao dịch. "
            "Kết luận: giữ cách diễn giải có điều kiện."
        )
        result = AgentAnswerComplianceGate.evaluate(compliance_input(answer))

        self.assertEqual(result.status, "PASS")

    def test_educational_trading_terms_without_execution_context_pass(self):
        answer = (
            "Al Brooks explains entry price, stop-loss, take-profit, and position size as trading concepts. "
            "This is educational context only, not a recommendation to analyze a live setup."
        )
        result = AgentAnswerComplianceGate.evaluate(
            compliance_input(answer, with_agents=False, task_scope_map={"task_1": "static_explanation"})
        )

        self.assertEqual(result.status, "PASS")

    def test_agent_output_as_evidence_fails(self):
        answer = f"{cautious_answer()} RiskAssessment evidence shows the market must follow this thesis."
        result = AgentAnswerComplianceGate.evaluate(compliance_input(answer))

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.agent_output_as_evidence_detected)
        self.assertIn("agent_output_as_evidence", result.reason_codes)

    def test_absent_consistency_but_strategy_and_risk_degrades_gracefully(self):
        answer = cautious_answer()
        ci = compliance_input(answer)
        ci.consistency_assessments_by_task = {}

        result = AgentAnswerComplianceGate.evaluate(ci)

        self.assertEqual(result.status, "PASS")

    def test_multi_intent_task_scope_pass_and_static_not_judged_against_agents(self):
        answer = (
            "### Phần 1 - XAUUSD\n"
            "Luận điểm macro chỉ nên đọc theo điều kiện. Rủi ro elevated và cần xác nhận thêm.\n\n"
            "### Phần 2 - Al Brooks price action\n"
            "Al Brooks mô tả price action là cách đọc từng thanh giá theo bối cảnh thị trường."
        )
        ci = compliance_input(
            answer,
            task_ids=["task_1", "task_2"],
            with_agents=True,
            task_scope_map={"task_1": "scenario_analysis", "task_2": "static_explanation"},
        )

        result = AgentAnswerComplianceGate.evaluate(ci)

        self.assertEqual(result.status, "PASS")

    def test_multi_intent_market_agent_leakage_into_book_section_fails(self):
        answer = (
            "### Phần 1 - XAUUSD\n"
            "Luận điểm macro có điều kiện, rủi ro elevated và cần xác nhận thêm.\n\n"
            "### Phần 2 - Al Brooks price action\n"
            "RiskAssessment shows XAUUSD thesis is mixed, nên phần price action phải theo risk posture."
        )
        ci = compliance_input(
            answer,
            task_ids=["task_1", "task_2"],
            with_agents=True,
            task_scope_map={"task_1": "scenario_analysis", "task_2": "static_explanation"},
        )

        result = AgentAnswerComplianceGate.evaluate(ci)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.sibling_scope_violation_detected)
        self.assertIn("sibling_scope_violation", result.reason_codes)

    def test_no_agent_static_path_passes(self):
        answer = "Al Brooks mô tả price action là phương pháp đọc hành động giá theo bối cảnh. Kết luận: đây là giải thích sách."
        result = AgentAnswerComplianceGate.evaluate(
            compliance_input(answer, with_agents=False, task_scope_map={"task_1": "static_explanation"})
        )

        self.assertEqual(result.status, "PASS")

    def test_static_book_answer_with_source_reference_passes_completeness(self):
        answer = (
            "Nguon da dung: Reading Price Charts Bar by Bar - Al Brooks.\n\n"
            "- Al Brooks mo ta price action nhu cach doc tung thanh gia trong boi canh, "
            "bao gom xu huong, breakout, pullback va nhung lan that bai cua thi truong.\n"
            "- Diem quan trong la nguoi doc khong tach rieng mot nen gia, ma dat no vao "
            "chuoi hanh vi truoc do de hieu ben mua va ben ban dang lam gi.\n"
            "- Vi vay, price action la mot khung dien giai hanh vi gia, khong phai mot "
            "lenh giao dich tu dong hay cam ket ket qua.\n\n"
            "Ket luan: theo nguon sach cua Al Brooks, price action nhan manh viec doc "
            "hanh vi gia theo ngu canh va gioi han dien giai trong pham vi bang chung."
        )
        result = check_answer_completeness(
            answer,
            "STOP",
            min_chars=1,
            intent="FINANCIAL_RAG",
            query="Al Brooks noi gi ve price action?",
            sources=static_book_sources(),
            runtime_artifacts=static_book_runtime_artifacts(answer, compliance_status="PASS"),
        )

        self.assertTrue(result["complete"])
        self.assertEqual(result["level"], "pass")
        self.assertTrue(result["has_source_reference"])

    def test_static_book_answer_without_source_reference_still_fails_completeness(self):
        answer = (
            "- Price action la cach doc tung thanh gia theo boi canh thi truong, gom "
            "xu huong, breakout, pullback va cac lan that bai.\n"
            "- Cach tiep can nay nhan manh hanh vi cua nguoi tham gia thi truong thay "
            "vi dua vao mot chi bao duy nhat.\n"
            "- Phan dien giai can gan voi ngu canh va khong bien thanh loi hua loi "
            "nhuan hay tin hieu giao dich.\n\n"
            "Ket luan: price action la khung doc hanh vi gia theo ngu canh va can "
            "duoc hieu nhu kien thuc sach, khong phai du lieu thi truong live."
        )
        result = check_answer_completeness(
            answer,
            "STOP",
            min_chars=1,
            intent="FINANCIAL_RAG",
            query="Al Brooks noi gi ve price action?",
            sources=static_book_sources(),
            runtime_artifacts=static_book_runtime_artifacts(answer, compliance_status="PASS"),
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "missing_source_reference")
        self.assertEqual(result["agent_answer_compliance_status"], "PASS")

    def test_answer_completeness_respects_compliance_warn_fail_for_memory_policy(self):
        answer = (
            "### Thị trường\n"
            "- MarketSnapshot cho thấy bối cảnh hiện tại cần đọc thận trọng.\n"
            "- Rủi ro còn elevated và cần xác nhận thêm.\n"
            "- Đây là phân tích có điều kiện, không phải hướng dẫn thực thi.\n\n"
            "Kết luận: MarketSnapshot được dùng làm nguồn bối cảnh, còn luận điểm chỉ là điều kiện. "
            "Phần trả lời giữ cấu trúc phân tích thị trường, nhắc rõ yếu tố xác nhận, bất định và giới hạn diễn giải."
        )
        base_artifacts = {
            "answer_contracts": [{"answer_type": "market_analysis", "required_evidence_roles": ["market_snapshot"]}],
            "evidence_sufficiency": {"status": "COMPLETE"},
            "claim_validation": {"status": "PASS"},
            "contract_evaluation": {"status": "PASS", "reason_codes": []},
            "final_answer_artifact": {"sha256": _answer_sha256(answer)},
        }
        fail_artifacts = dict(base_artifacts)
        fail_artifacts["agent_answer_compliance"] = {"status": "FAIL"}
        fail = check_answer_completeness(
            answer,
            "STOP",
            min_chars=1,
            intent="FINANCIAL_RAG",
            query="market",
            runtime_artifacts=fail_artifacts,
        )

        warn_artifacts = dict(base_artifacts)
        warn_artifacts["agent_answer_compliance"] = {"status": "WARN"}
        warn = check_answer_completeness(
            answer,
            "STOP",
            min_chars=1,
            intent="FINANCIAL_RAG",
            query="market",
            runtime_artifacts=warn_artifacts,
        )

        self.assertEqual(fail["level"], "fail")
        self.assertEqual(fail["reason"], "agent_answer_compliance_failed")
        self.assertEqual(warn["level"], "warn")
        self.assertIn("agent_answer_compliance_warn", warn["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

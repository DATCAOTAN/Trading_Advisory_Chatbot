import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.knowledge.models import RuntimeContextPack  # noqa: E402
from src.services.trading.reasoning import (  # noqa: E402
    DeterministicMethodSelector,
    LLMReasoningAdapter,
    MethodReasoningOutputParser,
    MethodReasoningPromptBuilder,
    MethodSelectionValidator,
    MethodSelectorService,
    StubLLMReasoningAdapter,
)


def context_pack(mode="autonomous_live", primary_regime="PULLBACK_UPTREND", calendar_risk="CLEAR"):
    return RuntimeContextPack(
        context_pack_id="runtime_context_pack_fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={
            "feature_snapshot_id": "feature_fixture",
            "source_snapshot_ids": ["market_bundle_fixture"],
            "symbol": "XAUUSD",
            "broker_symbol": "XAUUSDm",
            "timeframes": ["M15", "H1"],
            "trend_direction": "UP",
            "trend_strength": 0.55,
            "volatility_state": "NORMAL",
            "momentum_state": "BULLISH",
            "pullback_detected": True,
            "range_chop_score": 0.25,
            "data_quality_status": "COMPLETE",
        },
        calendar_context_summary={
            "context_id": "calendar_context_fixture",
            "calendar_risk_state": calendar_risk,
            "relevant_event_count": 1,
        },
        market_regime_summary={
            "regime_snapshot_id": "regime_fixture",
            "source_feature_snapshot_id": "feature_fixture",
            "source_calendar_context_id": "calendar_context_fixture",
            "primary_regime": primary_regime,
            "confidence": 0.82,
        },
        selected_method_cards=[
            {
                "method_id": "al_brooks_trend_pullback",
                "method_name": "Al Brooks trend pullback analysis",
                "domains": ["price_action", "trend", "pullback"],
                "suitable_regimes": ["PULLBACK_UPTREND", "TRENDING_UP"],
                "bad_regimes": ["NEWS_RISK", "CHOPPY"],
                "required_features": ["trend_direction", "trend_strength", "pullback_detected"],
                "source_refs": ["data/knowledge_repository/book/technical/price_action/al_brooks"],
            },
            {
                "method_id": "risk_management_core",
                "method_name": "Risk management review framework",
                "domains": ["risk", "review"],
                "suitable_regimes": ["PULLBACK_UPTREND", "NEWS_RISK", "UNKNOWN"],
                "bad_regimes": [],
                "required_features": ["data_quality_status"],
                "source_refs": ["data/knowledge_repository/book/risk/position_sizing/van_tharp"],
            },
        ],
        selected_macro_cards=[
            {
                "macro_id": "usd_high_impact_calendar_risk",
                "title": "USD high impact calendar risk",
                "event_type": "calendar_risk",
                "source_refs": ["data/knowledge_repository/report/macro"],
                "key_points": ["Calendar context is risk context only."],
            }
        ],
        selected_playbooks=[
            {
                "playbook_id": "trend_pullback_v1",
                "method_id": "al_brooks_trend_pullback",
                "name": "Trend pullback analytical playbook",
                "compatible_regimes": ["PULLBACK_UPTREND"],
                "source_refs": ["data/knowledge_repository/book/technical/price_action/al_brooks"],
            }
        ],
        rejected_or_blocked_knowledge=[],
        source_refs=[
            "data/knowledge_repository/book/technical/price_action/al_brooks",
            "data/knowledge_repository/book/risk/position_sizing/van_tharp",
            "data/knowledge_repository/report/macro",
        ],
        token_budget_estimate=1000,
        payload_size_chars=4000,
    )


def valid_llm_json(primary="al_brooks_trend_pullback"):
    return json.dumps(
        {
            "primary_method_id": primary,
            "supporting_method_ids": ["risk_management_core"],
            "rejected_method_ids": [],
            "selected_playbook_ids": ["trend_pullback_v1"],
            "relevant_macro_ids": ["usd_high_impact_calendar_risk"],
            "overall_context_fit": 0.82,
            "confidence": 0.78,
            "blockers": [],
            "warnings": [],
            "reasoning_summary": "Selected bounded method context from the supplied runtime pack.",
            "candidate_assessments": [
                {
                    "method_id": primary,
                    "role": "PRIMARY_CANDIDATE",
                    "compatibility_score": 0.82,
                    "reasons": ["regime_fit"],
                    "conflicts": [],
                    "source_refs": ["data/knowledge_repository/book/technical/price_action/al_brooks"],
                }
            ],
        }
    )


class MethodSelectorReasoningAdapterTests(unittest.TestCase):
    def test_prompt_builder_uses_runtime_context_pack_only_and_includes_summaries(self):
        prompt = MethodReasoningPromptBuilder().build(context_pack()).compact_prompt
        data = json.loads(prompt)
        self.assertEqual(data["context_pack_id"], "runtime_context_pack_fixture")
        self.assertIn("feature_summary", data)
        self.assertIn("calendar_summary", data)
        self.assertIn("market_regime_summary", data)
        self.assertIn("selected_method_cards", data)
        self.assertIn("selected_macro_cards", data)
        self.assertIn("selected_playbooks", data)
        self.assertNotIn("raw_candles", prompt)
        self.assertNotIn("full_pdf_text", prompt)
        self.assertNotIn("raw_book_text", prompt)

    def test_prompt_builder_includes_forbidden_output_rules(self):
        prompt = MethodReasoningPromptBuilder().build(context_pack()).compact_prompt
        self.assertIn("BUY", prompt)
        self.assertIn("SELL", prompt)
        self.assertIn("entry", prompt)
        self.assertIn("stop loss", prompt)
        self.assertIn("take profit", prompt)

    def test_deterministic_selector_works_when_llm_disabled(self):
        result = MethodSelectorService().select(context_pack(), use_llm=False)
        self.assertEqual(result.primary_method_id, "al_brooks_trend_pullback")
        self.assertIn("llm_disabled_deterministic_fallback", result.warnings)

    def test_deterministic_selector_preserves_human_confirmed_method(self):
        pack = context_pack(mode="human_confirmed_live")
        result = DeterministicMethodSelector().select(pack, "human_confirmed_live", "risk_management_core")
        self.assertEqual(result.primary_method_id, "risk_management_core")

    def test_deterministic_selector_selects_by_regime_and_avoids_bad_regime(self):
        result = DeterministicMethodSelector().select(context_pack(primary_regime="NEWS_RISK", calendar_risk="IMMEDIATE_HIGH_IMPACT"))
        self.assertEqual(result.primary_method_id, "risk_management_core")
        self.assertIn("CALENDAR_RISK_IMMEDIATE_HIGH_IMPACT", result.blockers)

    def test_stub_llm_valid_json_result_parses_successfully(self):
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter(valid_llm_json()))
        result = service.select(context_pack(), use_llm=True)
        self.assertTrue(service.last_used_llm)
        self.assertEqual(result.primary_method_id, "al_brooks_trend_pullback")

    def test_invalid_llm_json_falls_back(self):
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter("not json"))
        result = service.select(context_pack(), use_llm=True)
        self.assertFalse(service.last_used_llm)
        self.assertIn("llm_parse_failed_fallback", result.warnings)

    def test_llm_selecting_unknown_method_is_rejected(self):
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter(valid_llm_json("unknown_method")))
        result = service.select(context_pack(), use_llm=True)
        self.assertFalse(service.last_used_llm)
        self.assertIn("llm_validation_failed_fallback", result.warnings)

    def test_llm_changing_mode_one_method_is_rejected(self):
        pack = context_pack(mode="human_confirmed_live")
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter(valid_llm_json("al_brooks_trend_pullback")))
        result = service.select(pack, mode="human_confirmed_live", user_selected_method_id="risk_management_core", use_llm=True)
        self.assertFalse(service.last_used_llm)
        self.assertEqual(result.primary_method_id, "risk_management_core")

    def test_llm_forbidden_output_is_rejected(self):
        unsafe = valid_llm_json().replace("Selected bounded", "BUY now Selected bounded")
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter(unsafe))
        result = service.select(context_pack(), use_llm=True)
        self.assertFalse(service.last_used_llm)
        self.assertIn("llm_forbidden_output_fallback", result.warnings)

    def test_llm_output_containing_entry_sl_tp_lot_is_rejected(self):
        unsafe = valid_llm_json().replace("Selected bounded", "entry stop loss take profit lot Selected bounded")
        service = MethodSelectorService(llm_adapter=StubLLMReasoningAdapter(unsafe))
        result = service.select(context_pack(), use_llm=True)
        self.assertFalse(service.last_used_llm)
        self.assertIn("llm_forbidden_output_fallback", result.warnings)

    def test_result_preserves_source_refs_and_confidence_validates(self):
        result = MethodSelectorService().select(context_pack(), use_llm=False)
        validation = MethodSelectionValidator().validate(result, context_pack())
        self.assertTrue(validation.passed, validation.issues)
        self.assertTrue(result.source_refs)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_method_selection_result_contains_no_actionable_markers(self):
        result = MethodSelectorService().select(context_pack(), use_llm=False)
        payload = json.dumps(result.as_dict()).lower()
        for forbidden in ["buy", "sell", "trade decision", "trade_decision", "entry", "stop-loss", "take-profit", "lot", "account-risk"]:
            self.assertNotIn(forbidden, payload)

    def test_llm_adapter_default_disabled_does_not_call_provider(self):
        request = MethodReasoningPromptBuilder().build(context_pack())
        response = LLMReasoningAdapter().complete(request)
        self.assertEqual(response.parse_status, "FAILED")
        self.assertIn("trading_reasoning_llm_disabled", response.errors)

    def test_output_parser_parses_json(self):
        parsed = MethodReasoningOutputParser().parse(
            valid_llm_json(),
            "autonomous_live",
            "XAUUSD",
            "runtime_context_pack_fixture",
            context_pack().source_refs,
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.primary_method_id, "al_brooks_trend_pullback")

    def test_reasoning_modules_do_not_import_metatrader5_or_live_data_facade(self):
        root = PROJECT_ROOT / "src" / "services" / "trading" / "reasoning"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.py"))
        self.assertNotIn("Meta" + "Trader5", text)
        self.assertNotIn("live_data_service", text)
        self.assertNotIn("get_live_price", text)
        self.assertNotIn("get_economic_calendar", text)

    def test_unit_tests_do_not_call_real_llm_mt5_or_live_calendar(self):
        text = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("Meta" + "Trader5", text)
        self.assertNotIn("ff_calendar" + "_thisweek", text)
        self.assertNotIn("api-fxtrade" + ".oanda.com", text)

    def test_no_order_send_qdrant_reset_or_rag_behavior_in_reasoning_modules(self):
        root = PROJECT_ROOT / "src" / "services" / "trading" / "reasoning"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.py"))
        self.assertNotIn("order" + "_send", text)
        self.assertNotIn("delete" + "_collection", text)
        self.assertNotIn("recreate" + "_collection", text)
        self.assertNotIn("ContextAcquisitionExecutor", text)


if __name__ == "__main__":
    unittest.main()

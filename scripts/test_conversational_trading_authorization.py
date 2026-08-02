from pathlib import Path

import pytest

from src.config import Config
from src.services.trading.decision.conversational_authorization import (
    ConversationalTradingRequest,
    parse_conversational_trading_request,
)


@pytest.mark.parametrize(
    ("text", "mode", "policy"),
    (
        ("Chi phan tich BTCUSD, khong gui lenh.", "advisory_only", "NO_EXECUTION"),
        (
            "Theo doi BTCUSD va de toi duyet truoc khi vao MT5 demo.",
            "human_confirmed_live",
            "CONFIRM_EVERY_TRADE",
        ),
        (
            "Co co hoi BTCUSD thi bao toi xac nhan tren tai khoan demo.",
            "human_confirmed_live",
            "CONFIRM_EVERY_TRADE",
        ),
        (
            "Tu giao dich BTCUSD trong gioi han mandate tren tai khoan demo.",
            "autonomous_live",
            "STANDING_MANDATE",
        ),
    ),
)
def test_varied_wording_maps_to_typed_modes(text, mode, policy):
    request = parse_conversational_trading_request(text, conversation_id="chat-1")

    assert request is not None
    assert request.requested_mode == mode
    assert request.confirmation_policy == policy
    assert request.canonical_symbol == "BTCUSD"
    assert request.broker_symbol == "BTCUSDm"
    assert request.timeframe_profile == ("M1", "H1", "H4")
    assert request.to_public_dict()["execution_authority"] is False


def test_conflicting_automatic_wording_uses_safer_human_confirmation():
    request = parse_conversational_trading_request(
        "Trade automatically on BTCUSD demo but ask before every order.",
        conversation_id="chat-2",
    )

    assert request.requested_mode == "human_confirmed_live"
    assert request.confirmation_policy == "CONFIRM_EVERY_TRADE"
    assert request.mandate_required is False


def test_unicode_operator_wording_is_normalized_without_a_phrase_special_case():
    request = parse_conversational_trading_request(
        "Hãy theo dõi BTCUSD, tự động tìm cơ hội nhưng hỏi tôi trước mỗi lệnh "
        "và chỉ dùng tài khoản MT5 demo.",
        conversation_id="chat-unicode",
    )

    assert request.requested_mode == "human_confirmed_live"
    assert request.strategy_description == "CURRENT_CONFIGURED_STRATEGY"


def test_live_mode_without_demo_scope_blocks_before_authority():
    request = parse_conversational_trading_request(
        "Track XAUUSD and ask before every trade.",
        conversation_id="chat-3",
    )

    assert request.account_scope == "UNKNOWN"
    assert request.allowed_next_action == "BLOCKED"
    assert request.blockers == ("DEMO_ACCOUNT_SCOPE_REQUIRED",)


def test_configured_symbol_is_not_btc_specific(monkeypatch):
    monkeypatch.setattr(Config, "MARKET_BROKER_SYMBOL_EURUSD", "EURUSD.demo", raising=False)
    request = parse_conversational_trading_request(
        "Analyze EURUSD only; do not trade.",
        conversation_id="chat-4",
    )

    assert request.canonical_symbol == "EURUSD"
    assert request.broker_symbol == "EURUSD.demo"
    assert request.timeframe_profile == tuple(Config.MARKET_DEFAULT_TIMEFRAMES)


def test_request_id_is_stable_and_public_reload_revalidates_bindings():
    first = parse_conversational_trading_request(
        "Analyze BTCUSD only; do not submit.", conversation_id="chat-5"
    )
    second = parse_conversational_trading_request(
        "Analyze BTCUSD only; do not submit.", conversation_id="chat-5"
    )

    assert first.request_id == second.request_id
    assert ConversationalTradingRequest.from_public_dict(first.to_public_dict()) == first
    changed = first.to_public_dict()
    changed["broker_symbol"] = "XAUUSDm"
    with pytest.raises(ValueError, match="CONVERSATIONAL_TRADING_REQUEST_INVALID"):
        ConversationalTradingRequest.from_public_dict(changed)


def test_plain_financial_question_does_not_create_authorization_request():
    assert (
        parse_conversational_trading_request(
            "What is the current BTCUSD trend?", conversation_id="chat-6"
        )
        is None
    )


def test_chat_ui_reuses_existing_authority_and_candidate_controls():
    chatbot = Path("src/ui/tab_chatbot.py").read_text(encoding="utf-8")
    dashboard = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")

    assert "_render_autonomous_decision_review_card" in chatbot
    assert 'key_prefix="chat_trade_"' in chatbot
    assert '"Generate Candidate"' in dashboard
    assert '"Generate Autonomous Candidate"' not in dashboard
    assert 'key=f"{key_prefix}generate_autonomous_candidate"' in dashboard
    assert "mode=active_mode" in dashboard
    assert "mode_idempotency_key=generation_request_id" in dashboard
    assert "idempotency_key=mode_idempotency_key" in dashboard
    assert 'st.success("Authoritative mode updated.")\n                    st.rerun()' in dashboard
    assert "Grant MT5 Demo Access" in dashboard
    assert "generation_request_id or secrets.token_hex(16)" in dashboard
    assert "controlled-submit" not in chatbot
    assert ".order_send(" not in chatbot
    assert "LLMClient" not in Path(
        "src/services/trading/decision/conversational_authorization.py"
    ).read_text(encoding="utf-8")

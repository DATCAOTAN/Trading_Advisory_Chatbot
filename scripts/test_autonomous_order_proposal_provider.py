from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs, service
from scripts.test_method_selector_llm_reasoning_adapter import valid_llm_json
from src.config import Config
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousOrderIntentProposal,
    AutonomousOrderMarketSnapshot,
)
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalProvider,
    AutonomousOrderProposalRequest,
)
from src.services.trading.reasoning.llm_adapter import (
    LLMReasoningAdapter,
    ProjectLLMReasoningProvider,
)
from src.services.trading.reasoning.models import LLMReasoningRequest


class StaticModel:
    def __init__(self, output):
        self.output = output
        self.calls = 0
        self.prompt = ""

    def complete(self, prompt, max_tokens, temperature):
        self.calls += 1
        self.prompt = prompt
        return self.output


class RaisingModel:
    def __init__(self, error):
        self.error = error

    def complete(self, prompt, max_tokens, temperature):
        raise self.error


def feature_result(**changes):
    inputs = make_inputs()
    broker_symbol = changes.pop("broker_symbol", inputs.runtime_context.broker_symbol)
    symbol = changes.pop("symbol", inputs.runtime_context.symbol)
    created_at = changes.pop("created_at", NOW.isoformat())
    tick = SimpleNamespace(
        timestamp=changes.pop("tick_timestamp", NOW.isoformat()),
        bid=changes.pop("bid", "100"),
        ask=changes.pop("ask", "101"),
    )
    indicator = SimpleNamespace(
        latest_close="100.5",
        atr="1.2",
        swing_high="103",
        swing_low="98",
        support_zones=["99"],
        resistance_zones=["102"],
    )
    feature = SimpleNamespace(
        feature_snapshot_id=changes.pop("feature_snapshot_id", "feature-fixture"),
        created_at=created_at,
        symbol=symbol,
        broker_symbol=broker_symbol,
        primary_timeframe="M15",
        indicator_snapshots={"M15": indicator},
        trend_direction="UP",
        trend_strength=0.8,
        volatility_state="NORMAL",
        momentum_state="POSITIVE",
        pullback_detected=True,
        breakout_candidate=False,
        multi_timeframe_alignment="ALIGNED",
        source_snapshot_ids=["snapshot-safe-ref"],
    )
    bundle = SimpleNamespace(
        bundle_id=changes.pop("bundle_id", "market-bundle-fixture"),
        created_at=created_at,
        symbol=symbol,
        broker_symbol=broker_symbol,
        provider_name="mt5_bridge",
        tick=tick,
    )
    assert not changes
    return SimpleNamespace(feature_snapshot=feature, bundle=bundle)


def request(**feature_changes):
    inputs = make_inputs()
    return AutonomousOrderProposalRequest(
        feature_result=feature_result(**feature_changes),
        runtime_context=inputs.runtime_context,
        method_selection=inputs.method_selection,
        score_report=inputs.score_report,
        risk_decision=inputs.risk_result,
        evaluated_at=NOW,
        maximum_age_seconds=300,
    )


def model_output(order_type="BUY_LIMIT", **changes):
    values = {
        "status": "PROPOSE",
        "order_type": order_type,
        "entry_price": "99",
        "trigger_price": None,
        "limit_price": None,
        "stop_loss": "98",
        "take_profit": "103",
        "proposed_volume": None,
        "reason_codes": ["METHOD_ALIGNED", "RISK_REVIEWED"],
        "blockers": [],
    }
    if order_type in {"BUY", "SELL"}:
        values["entry_price"] = None
        values["stop_loss"] = "99" if order_type == "BUY" else "102"
        values["take_profit"] = "102" if order_type == "BUY" else "99"
    elif order_type == "SELL_LIMIT":
        values.update(entry_price="102", stop_loss="103", take_profit="99")
    elif order_type == "BUY_STOP":
        values.update(entry_price="102", stop_loss="99", take_profit="103")
    elif order_type == "SELL_STOP":
        values.update(entry_price="99", stop_loss="102", take_profit="98")
    elif order_type == "BUY_STOP_LIMIT":
        values.update(entry_price=None, trigger_price="102", limit_price="101.5", stop_loss="99", take_profit="103")
    elif order_type == "SELL_STOP_LIMIT":
        values.update(entry_price=None, trigger_price="99", limit_price="99.5", stop_loss="102", take_profit="98")
    values.update(changes)
    return json.dumps(values)


def no_proposal_output(**changes):
    values = {
        "status": "NO_PROPOSAL",
        "order_type": None,
        "entry_price": None,
        "trigger_price": None,
        "limit_price": None,
        "stop_loss": None,
        "take_profit": None,
        "proposed_volume": None,
        "reason_codes": ["NO_PROPOSAL"],
        "blockers": [],
    }
    values.update(changes)
    return json.dumps(values)


def produced_raw(raw, proposal_request=None):
    model = StaticModel(raw)
    result = AutonomousOrderProposalProvider(model).produce(
        proposal_request or request()
    )
    return result, model


def produced(order_type="BUY_LIMIT", **changes):
    return produced_raw(model_output(order_type, **changes))


def inputs_with(result, *, risk_action="REVIEW_READY", requested_intent="OPEN_POSITION"):
    inputs = make_inputs(risk_action=risk_action, requested_intent=requested_intent)
    return replace(
        inputs,
        direction=result.direction,
        semantic_parameter_references=result.semantic_parameter_references,
        order_proposal=result.order_proposal,
        order_market_snapshot=result.order_market_snapshot,
    )


def test_provider_receives_typed_authoritative_inputs_once():
    result, model = produced()
    prompt = json.loads(model.prompt)
    assert result.valid
    assert model.calls == 1
    assert prompt["symbol"] == "TEST_SYMBOL"
    assert prompt["market"]["bid"] == "100"
    assert prompt["analysis"]["method_id"] == "method-fixture"
    assert prompt["analysis"]["readiness_action"] == "REVIEW_READY"


def test_prompt_field_and_enum_contract_matches_authoritative_validator():
    _result, model = produced()
    prompt = json.loads(model.prompt)
    expected_fields = {
        "status", "order_type", "entry_price", "trigger_price", "limit_price",
        "stop_loss", "take_profit", "proposed_volume", "reason_codes", "blockers",
    }
    assert set(prompt["required_json_schema"]) == expected_fields
    assert set(prompt["required_fields"]) == expected_fields
    assert set(prompt["no_proposal_example"]) == expected_fields
    assert prompt["required_json_schema"]["status"] == "PROPOSE|NO_PROPOSAL"
    assert prompt["required_json_schema"]["order_type"] == (
        "BUY|SELL|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|"
        "BUY_STOP_LIMIT|SELL_STOP_LIMIT|null"
    )
    assert prompt["no_proposal_example"] == json.loads(no_proposal_output())


def test_valid_structured_output_becomes_complete_typed_result():
    result, _model = produced()
    assert isinstance(result.order_proposal, AutonomousOrderIntentProposal)
    assert isinstance(result.order_market_snapshot, AutonomousOrderMarketSnapshot)
    assert result.direction == "BUY"
    assert result.order_proposal.order_type == "BUY_LIMIT"
    assert result.order_proposal.entry_intent == "PULLBACK"
    assert result.order_proposal.proposed_action == "PENDING"
    assert result.order_market_snapshot.snapshot_reference == "market-bundle-fixture"
    assert result.proposal_reference in result.semantic_parameter_references
    assert result.provenance_hash


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"order_type": None}, "STRUCTURED_PROPOSAL_ORDER_TYPE_INVALID"),
        ({"entry_price": None}, "STRUCTURED_PROPOSAL_ENTRY_PRICE_MISSING"),
        ({"reason_codes": []}, "STRUCTURED_PROPOSAL_REASON_CODES_MISSING"),
        ({"entry_price": "not-a-number"}, "STRUCTURED_PROPOSAL_ENTRY_PRICE_INVALID"),
    ],
)
def test_incomplete_or_invalid_output_returns_ordered_blockers(changes, blocker):
    result, model = produced(**changes)
    assert not result.valid
    assert result.blockers[0] == blocker
    assert model.calls == 1


def test_stale_market_evidence_blocks_before_model_call():
    model = StaticModel(model_output())
    result = AutonomousOrderProposalProvider(model).produce(
        request(tick_timestamp="2026-07-22T00:00:00+00:00")
    )
    assert result.blockers == ("PROPOSAL_INPUT_STALE",)
    assert model.calls == 0


def test_conflicting_symbol_metadata_blocks_before_model_call():
    model = StaticModel(model_output())
    result = AutonomousOrderProposalProvider(model).produce(
        request(broker_symbol="OTHERm")
    )
    assert result.blockers == ("PROPOSAL_SYMBOL_METADATA_CONFLICT",)
    assert model.calls == 0


def test_formatted_prose_is_not_parsed_for_values():
    model = StaticModel("proposal: " + model_output())
    result = AutonomousOrderProposalProvider(model).produce(request())
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON",)


def test_one_outer_json_fence_is_normalized():
    result, _model = produced_raw("```json\n" + model_output() + "\n```")
    assert result.valid


def test_double_encoded_json_object_is_decoded_once():
    result, _model = produced_raw(json.dumps(model_output()))
    assert result.valid


def test_more_than_one_json_encoding_layer_is_not_decoded():
    result, _model = produced_raw(json.dumps(json.dumps(model_output())))
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID",)


@pytest.mark.parametrize("raw", ["", "{", '{"status": NaN}', '{"status": Infinity}'])
def test_empty_malformed_or_non_finite_json_fails_closed(raw):
    result, _model = produced_raw(raw)
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON",)


def test_extra_json_key_is_rejected():
    payload = json.loads(model_output())
    payload["unexpected"] = "value"
    result, _model = produced_raw(json.dumps(payload))
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID",)
    assert result.order_proposal is None


def test_required_json_key_missing_is_rejected():
    payload = json.loads(model_output())
    del payload["take_profit"]
    result, _model = produced_raw(json.dumps(payload))
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID",)


def test_live_no_proposal_field_set_failure_is_reproduced_without_provider_call():
    raw = json.dumps({
        "status": "NO_PROPOSAL",
        "reason_codes": ["NO_PROPOSAL"],
        "blockers": [],
    })
    result, model = produced_raw(raw)
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID",)
    assert model.calls == 1


def test_no_proposal_uses_deterministic_blocker_without_fallback():
    result, model = produced_raw(no_proposal_output())
    assert result.blockers == ("STRUCTURED_PROPOSAL_NOT_AVAILABLE",)
    assert result.order_proposal is None
    assert model.calls == 1


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"order_type": "BUY"}, "STRUCTURED_PROPOSAL_NO_PROPOSAL_ORDER_TYPE_NOT_NULL"),
        ({"entry_price": "100"}, "STRUCTURED_PROPOSAL_NO_PROPOSAL_ENTRY_PRICE_NOT_NULL"),
        ({"stop_loss": "99"}, "STRUCTURED_PROPOSAL_NO_PROPOSAL_STOP_LOSS_NOT_NULL"),
        ({"reason_codes": []}, "STRUCTURED_PROPOSAL_NO_PROPOSAL_REASON_CODES_MISSING"),
    ],
)
def test_no_proposal_requires_complete_neutral_trade_fields(changes, blocker):
    result, _model = produced_raw(no_proposal_output(**changes))
    assert result.blockers[0] == blocker


def test_no_action_status_is_not_an_alias_for_no_proposal():
    result, _model = produced_raw(no_proposal_output(status="NO_ACTION"))
    assert result.blockers == ("STRUCTURED_PROPOSAL_STATUS_INVALID",)


def test_wrong_numeric_container_type_remains_rejected():
    result, _model = produced(entry_price=["99"])
    assert result.blockers[0] == "STRUCTURED_PROPOSAL_ENTRY_PRICE_INVALID"


@pytest.mark.parametrize(
    ("field", "blocker"),
    [
        ("reason_codes", "STRUCTURED_PROPOSAL_REASON_CODES_INVALID"),
        ("blockers", "STRUCTURED_PROPOSAL_BLOCKERS_INVALID"),
    ],
)
def test_code_collections_reject_non_string_items(field, blocker):
    result, _model = produced(**{field: [True]})
    assert result.blockers == (blocker,)


def test_invalid_actionable_market_relationship_remains_rejected():
    result, _model = produced("BUY_LIMIT", entry_price="102")
    assert result.blockers == ("STRUCTURED_PROPOSAL_MARKET_RELATION_INVALID",)


def test_invalid_direction_field_is_rejected():
    payload = json.loads(model_output())
    payload["direction"] = "SIDEWAYS"
    result, _model = produced_raw(json.dumps(payload))
    assert result.blockers == ("STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID",)


def test_source_reference_mismatch_blocks_before_model_call():
    proposal_request = request()
    proposal_request = replace(
        proposal_request,
        method_selection=replace(
            proposal_request.method_selection,
            source_context_pack_id="different-context",
        ),
    )
    result, model = produced_raw(model_output(), proposal_request)
    assert result.blockers == ("PROPOSAL_INPUT_REFERENCE_CONFLICT",)
    assert model.calls == 0


@pytest.mark.parametrize("feature_snapshot_id", ["", "   "])
def test_empty_or_whitespace_feature_binding_blocks_before_model_call(
    feature_snapshot_id,
):
    model = StaticModel(model_output())
    result = AutonomousOrderProposalProvider(model).produce(
        request(feature_snapshot_id=feature_snapshot_id)
    )
    assert result.blockers == ("PROPOSAL_PROVENANCE_MISSING",)
    assert model.calls == 0


def test_empty_bundle_binding_blocks_before_model_call():
    model = StaticModel(model_output())
    result = AutonomousOrderProposalProvider(model).produce(request(bundle_id=""))
    assert result.blockers == ("PROPOSAL_PROVENANCE_MISSING",)
    assert model.calls == 0


def test_empty_readiness_binding_blocks_before_model_call():
    proposal_request = request()
    proposal_request = replace(
        proposal_request,
        risk_decision=replace(proposal_request.risk_decision, decision_id=""),
    )
    result, model = produced_raw(model_output(), proposal_request)
    assert result.blockers == ("PROPOSAL_PROVENANCE_MISSING",)
    assert model.calls == 0

def test_downstream_human_approval_lock_is_not_provider_input():
    source = Path(
        "src/services/trading/decision/autonomous_proposal_provider.py"
    ).read_text(encoding="utf-8")
    assert "HumanValueApprovalLock" not in source
    assert "as_dict()" not in source
    assert "to_public_dict" not in source


def reasoning_request():
    return LLMReasoningRequest(
        request_id="reasoning-request-fixture",
        created_at=NOW.isoformat(),
        mode="autonomous_live",
        symbol="TEST_SYMBOL",
        context_pack_id="context-fixture",
        compact_prompt="{}",
        max_tokens=200,
        temperature=0.0,
        provider_name="test",
    )


def consume_project_response(monkeypatch, project_response):
    class FakeProjectClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, *args, **kwargs):
            return project_response

    monkeypatch.setattr("src.core.llm_client.LLMClient", FakeProjectClient)
    return LLMReasoningAdapter(
        provider=ProjectLLMReasoningProvider("test")
    ).complete(reasoning_request())


@pytest.mark.parametrize(
    "project_response",
    [
        lambda content: {"message": {"content": content}},
        lambda content: content,
    ],
)
def test_project_provider_content_reaches_existing_consumer_unchanged(
    monkeypatch, project_response
):
    content = valid_llm_json()
    response = consume_project_response(monkeypatch, project_response(content))
    assert response.parse_status == "OK"
    assert response.raw_text_redacted == content
    assert response.parsed_result.primary_method_id == "al_brooks_trend_pullback"


def test_structured_project_provider_requests_supported_json_mode_without_fallback(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(Config, "GROQ_API_KEY", "hermetic-test-placeholder")

    class FakeProjectClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, *args, **kwargs):
            calls.append(kwargs)
            return {"message": {"content": model_output()}}

    monkeypatch.setattr("src.core.llm_client.LLMClient", FakeProjectClient)
    output = ProjectLLMReasoningProvider(
        "groq", structured_json=True
    ).complete("{}", 200, 0.0)

    assert output == model_output()
    assert calls == [{
        "stream": False,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "max_tokens": 200,
        "allow_fallback": False,
    }]


def test_unsupported_structured_response_format_is_detected():
    from src.core.llm_client import LLMClient

    client = object.__new__(LLMClient)
    client.provider = "ollama"
    with pytest.raises(
        RuntimeError, match="STRUCTURED_RESPONSE_FORMAT_UNSUPPORTED"
    ):
        client.chat([], response_format={"type": "json_object"})


def test_groq_json_mode_reaches_sdk_once_with_bounded_arguments(capsys):
    from src.core.llm_client import LLMClient

    calls = []
    client_options = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=model_output()))]
            )

    class FakeGroqClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def with_options(self, **kwargs):
            client_options.append(kwargs)
            return self

    client = object.__new__(LLMClient)
    client.provider = "groq"
    client.groq_model = "test-model"
    client.groq_client = FakeGroqClient()
    response = client.chat(
        [{"role": "user", "content": "{}"}],
        temperature=0.0,
        response_format={"type": "json_object"},
        max_tokens=200,
        allow_fallback=False,
    )

    assert response == {"message": {"content": model_output()}}
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["max_tokens"] == 200
    assert calls[0]["stream"] is False
    assert client_options == [{
        "max_retries": 0,
        "timeout": float(Config.TRADING_REASONING_TIMEOUT_SECONDS),
    }]
    assert capsys.readouterr().out.isascii()


def test_project_provider_missing_groq_credential_fails_before_client(monkeypatch):
    constructed = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            constructed.append(True)

    monkeypatch.setattr(Config, "GROQ_API_KEY", "")
    monkeypatch.setattr("src.core.llm_client.LLMClient", UnexpectedClient)

    with pytest.raises(RuntimeError, match="^GROQ_CREDENTIAL_MISSING$"):
        ProjectLLMReasoningProvider("groq", structured_json=True).complete(
            "{}", 32, 0.0
        )
    assert constructed == []


@pytest.mark.parametrize(
    ("error", "blocker"),
    [
        (RuntimeError("GROQ_CREDENTIAL_MISSING"), "STRUCTURED_PROPOSAL_CREDENTIAL_MISSING"),
        (RuntimeError("STRUCTURED_RESPONSE_FORMAT_UNSUPPORTED"), "STRUCTURED_PROPOSAL_REQUEST_UNSUPPORTED"),
        (type("AuthenticationError", (Exception,), {})(), "STRUCTURED_PROPOSAL_AUTHENTICATION_FAILED"),
        (type("PermissionDeniedError", (Exception,), {})(), "STRUCTURED_PROPOSAL_AUTHORIZATION_FAILED"),
        (type("NotFoundError", (Exception,), {})(), "STRUCTURED_PROPOSAL_MODEL_UNAVAILABLE"),
        (type("BadRequestError", (Exception,), {})(), "STRUCTURED_PROPOSAL_REQUEST_INVALID"),
        (type("RateLimitError", (Exception,), {})(), "STRUCTURED_PROPOSAL_RATE_LIMITED"),
        (type("APITimeoutError", (Exception,), {})(), "STRUCTURED_PROPOSAL_REQUEST_TIMEOUT"),
        (type("APIConnectionError", (Exception,), {})("fixture-key"), "STRUCTURED_PROPOSAL_TRANSPORT_UNAVAILABLE"),
    ],
)
def test_provider_failure_mapping_is_specific_and_redacted(error, blocker):
    result = AutonomousOrderProposalProvider(RaisingModel(error)).produce(request())
    assert result.blockers == (blocker,)
    assert "fixture-key" not in json.dumps(result.blockers)


def test_structured_groq_failure_does_not_fallback(monkeypatch):
    from src.core.llm_client import LLMClient

    client = object.__new__(LLMClient)
    client.provider = "groq"
    client.groq_client = object()
    client.ollama_model = "unused"
    fallback_calls = []
    monkeypatch.setattr(
        client, "_chat_groq_sync", lambda *args: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(
        client, "_chat_ollama_sync", lambda *args: fallback_calls.append(args)
    )

    with pytest.raises(RuntimeError, match="boom"):
        client.chat(
            [],
            response_format={"type": "json_object"},
            allow_fallback=False,
        )
    assert fallback_calls == []


@pytest.mark.parametrize(
    "project_response",
    [
        {},
        {"message": {}},
        {"message": {"content": None}},
        {"message": {"reasoning": "PRIVATE_CHAIN"}},
    ],
)
def test_project_provider_missing_content_uses_existing_error_contract(
    monkeypatch, project_response
):
    response = consume_project_response(monkeypatch, project_response)
    assert response.parse_status == "FAILED"
    assert response.warnings == ["provider_error"]
    assert response.errors == ["RuntimeError"]
    assert response.raw_text_redacted == ""


def test_full_provider_response_and_hidden_metadata_are_not_persisted(monkeypatch):
    response = consume_project_response(
        monkeypatch,
        {
            "message": {"content": valid_llm_json()},
            "hidden_reasoning": "PRIVATE_CHAIN",
            "credentials": "PRIVATE_CREDENTIAL",
        },
    )
    persisted = json.dumps(response.as_dict(), sort_keys=True)
    assert "PRIVATE_CHAIN" not in persisted
    assert "PRIVATE_CREDENTIAL" not in persisted

def test_complete_proposal_still_allows_no_action(tmp_path):
    result, _model = produced("BUY")
    run = service(tmp_path).run_once(inputs_with(result, risk_action="NO_TRADE"), now=NOW)
    assert run.candidate.intent == "NO_ACTION"
    assert run.candidate.action == "MARKET"


def test_complete_proposal_still_allows_human_review(tmp_path):
    result, _model = produced("BUY")
    run = service(tmp_path).run_once(
        inputs_with(result, requested_intent="REQUIRE_HUMAN_REVIEW"), now=NOW
    )
    assert run.candidate.intent == "REQUIRE_HUMAN_REVIEW"


@pytest.mark.parametrize(
    ("order_type", "action"),
    [("BUY", "MARKET"), ("SELL_STOP", "PENDING")],
)
def test_market_and_pending_are_natural_unforced_results(tmp_path, order_type, action):
    result, _model = produced(order_type)
    run = service(tmp_path).run_once(inputs_with(result), now=NOW)
    assert run.validation.valid
    assert run.candidate.intent == "OPEN_POSITION"
    assert run.candidate.action == action
    assert run.candidate.execution_authority is False
    assert run.candidate.execution_permission_requested is False
    assert run.candidate.executable is False
    assert run.candidate.order_send_allowed is False
    assert run.candidate.order_sent is False


def test_provider_has_no_export_submission_bridge_or_execution_calls():
    source = Path(
        "src/services/trading/decision/autonomous_proposal_provider.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "controlled-submit", "controlled_manage", "reconcile(",
        ".order_send(", "write_pending_candidate_handoff(",
    ):
        assert marker not in source

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.services.semantic.capability_registry import CapabilityRegistry
from src.services.semantic.context_acquisition import ContextAcquisitionExecutor
from src.services.semantic.context_execution import ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.structured_semantics import SEMANTIC_SCHEMA_VERSION, StructuredSemanticResult
from src.services.semantic.structured_interpreter import StructuredSemanticInterpreter
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5PositionSupervisorConfig,
)
from src.services.trading.position_read_model import PositionReadModelService, render_position_read_model
from src.ui import tab_chatbot


HASH_A = "a" * 64
HASH_B = "b" * 64
FINGERPRINT = "c" * 64


class FakeBridge:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    def lifecycle_snapshot(self, history_window_seconds, tags, auth_token):
        self.calls += 1
        assert history_window_seconds == 3600
        assert auth_token == "token"
        return self.snapshot


class FakeExecutionJournal:
    def __init__(self, records=()):
        self._records = list(records)

    def execution_records(self):
        return list(self._records)


class FakeLifecycleJournal:
    def __init__(self, rows=None):
        self.rows = dict(rows or {})

    def latest_by_execution(self):
        return dict(self.rows)


class FakeCandidateJournal:
    def load_candidate(self, reference):
        if reference != "candidate_ref":
            return None
        return SimpleNamespace(strategy_id="strategy_ref", proposal_source_reference="draft_ref")


def snapshot(*, positions=(), orders=(), deals=(), timestamp=None, status="OK"):
    return {
        "status": status,
        "reason": "" if status == "OK" else "MT5_CONTEXT_UNAVAILABLE",
        "terminal_connected": status == "OK",
        "terminal_trade_allowed": False,
        "account_trade_allowed": False,
        "account_context_fingerprint": FINGERPRINT,
        "active_orders": list(orders),
        "recent_orders": [],
        "recent_deals": list(deals),
        "positions": list(positions),
        "active_position_count": len(positions),
        "trades_today": len(deals),
        "loss_today": "0",
        "snapshot_reference": "snapshot_ref",
        "snapshot_timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "metadata_redacted": True,
    }


def position(reference=HASH_A, symbol="BTCUSDm", pnl=25.5, tags=()):
    return {
        "broker_reference_hash": reference,
        "order_reference_hash": "",
        "position_reference_hash": reference,
        "symbol": symbol,
        "direction": "BUY",
        "volume": 0.1,
        "time": "2026-08-09T01:00:00+00:00",
        "entry": "UNKNOWN",
        "matched_correlation_tags": list(tags),
        "open_price": 62000.0,
        "current_price": 62250.0,
        "unrealized_pnl": pnl,
        "stop_loss": 61000.0,
        "take_profit": 64000.0,
        "protection_reference_hash": "d" * 64,
        "metadata_redacted": True,
    }


def order(reference=HASH_B):
    return {
        "broker_reference_hash": reference,
        "order_reference_hash": "",
        "position_reference_hash": "",
        "symbol": "BTCUSDm",
        "direction": "BUY",
        "volume": 0.1,
        "time": "2026-08-09T01:00:00+00:00",
        "entry": "UNKNOWN",
        "matched_correlation_tags": [],
        "order_status": "ACTIVE",
        "order_type": "BUY_LIMIT",
        "entry_price": 61500.0,
        "trigger_price": None,
        "stop_loss": 60500.0,
        "take_profit": 63500.0,
        "metadata_redacted": True,
    }


def closing_deal(reference=HASH_B, tags=()):
    return {
        "broker_reference_hash": reference,
        "order_reference_hash": "",
        "position_reference_hash": HASH_A,
        "symbol": "BTCUSDm",
        "direction": "SELL",
        "volume": 0.1,
        "time": "2026-08-09T02:00:00+00:00",
        "entry": "OUT",
        "matched_correlation_tags": list(tags),
        "price": 63000.0,
        "profit": 100.0,
        "commission": -2.0,
        "swap": -1.0,
        "fee": 0.0,
        "metadata_redacted": True,
    }


def opening_deal(reference="f" * 64):
    row = closing_deal(reference)
    row.update(
        position_reference_hash=HASH_A,
        direction="BUY",
        entry="IN",
        time="2026-08-09T01:00:00+00:00",
        price=62000.0,
        profit=0.0,
        commission=0.0,
        swap=0.0,
        fee=0.0,
    )
    return row


def execution_record(state="RESULT_CONFIRMED"):
    return {
        "account_context_fingerprint": FINGERPRINT,
        "state": state,
        "protected_execution": {
            "correlation_tag": "mt5rabc",
            "protected_execution_reference": "execution_ref",
            "source_artifact_reference": "candidate_ref",
            "human_confirmation_reference": "confirmation_ref",
        },
    }


def service(snapshot_value, *, records=(), lifecycle=None, candidates=False, now=None):
    config = MT5PositionSupervisorConfig(
        history_window_seconds=3600,
        interval_seconds=30,
        auth_token="token",
    )
    return PositionReadModelService(
        config=config,
        bridge_client=FakeBridge(snapshot_value),
        execution_journal=FakeExecutionJournal(records),
        lifecycle_journal=FakeLifecycleJournal(lifecycle),
        candidate_journal=FakeCandidateJournal() if candidates else None,
        now=(lambda: now) if now else None,
    )


def semantic(**changes):
    payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "primary_intent": "POSITION_MANAGEMENT",
        "secondary_intents": [],
        "action": "NONE",
        "direction": "",
        "subtype": "",
        "domain": "trading",
        "symbols": [],
        "indicators": [],
        "requested_data": ["positions"],
        "conditions": [],
        "context_references": [],
        "requested_mode": "",
        "account_scope": "",
        "explicit_fields": ["requested_data"],
        "unresolved_fields": [],
        "negated": False,
        "hypothetical": False,
    }
    payload.update(changes)
    return StructuredSemanticResult.from_payload(payload)


def test_empty_snapshot_is_authoritative_not_an_error():
    result = service(snapshot()).read()
    assert result.status == "AVAILABLE"
    assert result.open_positions == ()
    assert result.pending_orders == ()
    assert result.history == ()


def test_open_position_uses_broker_values_and_current_pnl():
    result = service(snapshot(positions=[position()])).read()
    item = result.open_positions[0]
    assert (item.canonical_symbol, item.direction, item.volume, item.state) == (
        "BTCUSD", "BUY", 0.1, "POSITION_OPEN"
    )
    assert (item.entry_price, item.current_price, item.unrealized_pnl) == (62000.0, 62250.0, 25.5)
    assert item.pnl_source == "BROKER_CURRENT"


def test_unavailable_pnl_is_explicit_and_not_calculated():
    result = service(snapshot(positions=[position(pnl=None)])).read()
    assert result.open_positions[0].unrealized_pnl is None
    assert result.open_positions[0].pnl_source == "UNAVAILABLE"


def test_pending_order_is_not_projected_as_position():
    result = service(snapshot(orders=[order()])).read(query_type="PENDING")
    assert result.open_positions == ()
    assert result.pending_orders[0].state == "ORDER_ACTIVE"
    assert result.pending_orders[0].order_type == "BUY_LIMIT"


def test_closed_history_uses_authoritative_broker_components():
    result = service(snapshot(deals=[opening_deal(), closing_deal()])).read(query_type="HISTORY")
    item = result.history[0]
    assert item.realized_pnl == 97.0
    assert item.pnl_source == "BROKER_COMPONENTS"
    assert (item.entry_price, item.current_price) == (62000.0, 63000.0)
    assert (item.open_time, item.close_time) == (
        "2026-08-09T01:00:00+00:00", "2026-08-09T02:00:00+00:00"
    )


def test_unique_symbol_selects_and_multiple_symbol_positions_are_ambiguous():
    one = service(snapshot(positions=[position()])).read(
        query_type="PNL", canonical_symbol="BTCUSD", singular=True
    )
    assert one.selected_position == one.open_positions[0]
    two = service(snapshot(positions=[position(), position(HASH_B)])).read(
        query_type="PNL", canonical_symbol="BTCUSD", singular=True
    )
    assert two.selected_position is None
    assert two.blockers == ("AMBIGUOUS_POSITION_REFERENCE",)


def test_exact_reference_selects_and_stale_reference_fails_closed():
    found = service(snapshot(positions=[position()])).read(
        query_type="DETAIL", protected_reference=HASH_A, singular=True
    )
    assert found.selected_position is not None
    stale = service(snapshot(positions=[position()])).read(
        query_type="DETAIL", protected_reference=HASH_B, singular=True
    )
    assert stale.blockers == ("STALE_POSITION_REFERENCE",)


def test_account_mismatch_and_stale_snapshot_fail_closed():
    record = execution_record()
    record["account_context_fingerprint"] = "e" * 64
    mismatch = service(
        snapshot(positions=[position(tags=["mt5rabc"])]), records=[record]
    ).read()
    assert mismatch.blockers == ("ACCOUNT_CONTEXT_MISMATCH",)
    now = datetime.now(timezone.utc)
    stale = service(snapshot(timestamp=(now - timedelta(minutes=5)).isoformat()), now=now).read()
    assert stale.blockers == ("POSITION_SNAPSHOT_STALE",)


@pytest.mark.parametrize("execution_state", ["RESULT_UNKNOWN", "SUBMISSION_STARTED"])
def test_unknown_execution_state_surfaces_reconciliation_lifecycle(execution_state):
    lifecycle = {
        "execution_ref": {
            "observation_id": "lifecycle_ref",
            "lifecycle_state": "RECONCILIATION_REQUIRED",
        }
    }
    result = service(
        snapshot(positions=[position(tags=["mt5rabc"])]),
        records=[execution_record(execution_state)],
        lifecycle=lifecycle,
    ).read()
    assert result.open_positions[0].state == "RECONCILIATION_REQUIRED"


def test_provenance_joins_existing_protected_references_and_marks_missing_fields():
    lifecycle = {"execution_ref": {"observation_id": "lifecycle_ref", "lifecycle_state": "POSITION_OPEN"}}
    joined = service(
        snapshot(positions=[position(tags=["mt5rabc"])]),
        records=[execution_record()], lifecycle=lifecycle, candidates=True,
    ).read().open_positions[0].provenance
    assert (joined.strategy_reference, joined.draft_reference, joined.candidate_reference) == (
        "strategy_ref", "draft_ref", "candidate_ref"
    )
    assert joined.authorization_reference == "confirmation_ref"
    assert joined.execution_reference == "execution_ref"
    assert joined.lifecycle_reference == "lifecycle_ref"
    assert joined.unavailable == ("MANAGEMENT_REFERENCE",)
    missing = service(snapshot(positions=[position()])).read().open_positions[0].provenance
    assert missing.unavailable == ("CONTROLLED_EXECUTION_REFERENCE",)


def test_provenance_query_selects_closed_trade_and_renders_only_safe_references():
    lifecycle = {"execution_ref": {"observation_id": "lifecycle_ref", "lifecycle_state": "POSITION_CLOSED"}}
    result = service(
        snapshot(deals=[opening_deal(), closing_deal(tags=["mt5rabc"])]),
        records=[execution_record()], lifecycle=lifecycle, candidates=True,
    ).read(query_type="PROVENANCE", canonical_symbol="BTCUSD", singular=True)
    rendered = render_position_read_model(result)
    assert result.selected_position == result.history[0]
    assert "Stored provenance:" in rendered
    assert "strategy=strategy_ref..." in rendered
    assert "management=UNAVAILABLE" in rendered
    assert "confirmation_ref" not in rendered


def test_public_projection_is_redacted_and_contains_no_raw_broker_identifiers():
    payload = service(snapshot(positions=[position()])).read().to_public_dict()
    text = repr(payload)
    assert payload["metadata_redacted"] is True
    assert "account_login" not in text and "ticket" not in text and "deal_id" not in text


def test_structured_position_read_routes_to_one_read_capability_without_execution():
    plan = QueryPlanAssembler().assemble(
        "wording is not parsed here",
        structured_semantics=semantic(symbols=["BTCUSD"], requested_data=["pnl"]),
    )
    requirements = ContextRequirementPlanner().plan(plan)
    execution = ContextExecutionPlanner(CapabilityRegistry()).plan(requirements)
    assert plan.primary_intent == "position_state_read"
    assert plan.requires_execution is False
    assert [need.capability for need in requirements.needs] == ["position_read"]
    assert [task.capability for task in execution.deduplicated_tasks] == ["position_read"]


def test_semantic_contract_assigns_existing_trade_reads_to_position_management():
    prompt = StructuredSemanticInterpreter._prompt("arbitrary position-state wording")
    assert "Before choosing KNOWLEDGE" in prompt
    assert "in any language" in prompt
    assert "Interpret multilingual requests directly without requiring translation" in prompt
    assert "current/latest/now request" in prompt
    assert "must not be used for account-specific current or historical trade facts" in prompt
    assert "existing positions, pending orders, current or realized P/L" in prompt
    assert "as POSITION_MANAGEMENT with action NONE or EXPLAIN" in prompt
    assert "Do not classify such reads as STRATEGY" in prompt


def test_position_capability_executes_typed_service_once():
    plan = QueryPlanAssembler().assemble(
        "ignored", structured_semantics=semantic(requested_data=["pending_orders"])
    )
    requirements = ContextRequirementPlanner().plan(plan)
    execution = ContextExecutionPlanner(CapabilityRegistry()).plan(requirements)
    read_service = service(snapshot(orders=[order()]))
    executor = ContextAcquisitionExecutor(position_read_service=read_service)
    batch = executor.execute(plan, requirements, execution, registry=CapabilityRegistry())
    assert batch.success_count == 1
    assert batch.results[0].data.pending_orders[0].order_type == "BUY_LIMIT"
    assert read_service.bridge_client.calls == 1


def test_pending_management_target_uses_the_same_exact_protected_selector():
    model = service(snapshot(orders=[order()])).read(
        query_type="PENDING",
        canonical_symbol="BTCUSD",
        protected_reference=HASH_B,
        singular=True,
    )
    assert model.status == "AVAILABLE"
    assert model.selected_position == model.pending_orders[0]
    assert "account_context_fingerprint" not in model.to_public_dict()


def test_streamlit_renderer_consumes_public_typed_artifact(monkeypatch):
    events = []

    class Column:
        def metric(self, label, value):
            events.append((label, value))

    fake = SimpleNamespace(
        subheader=lambda value: events.append(("heading", value)),
        columns=lambda count: [Column() for _ in range(count)],
        warning=lambda value: events.append(("warning", value)),
        markdown=lambda value: events.append(("markdown", value)),
        write=lambda value: events.append(("write", value)),
        caption=lambda value: events.append(("caption", value)),
    )
    monkeypatch.setattr(tab_chatbot, "st", fake)
    payload = service(snapshot(positions=[position()])).read().to_public_dict()
    tab_chatbot._render_position_read_card(payload)
    assert ("Open positions", 1) in events
    assert any(event[0] == "write" and "BTCUSD" in event[1] for event in events)
    assert any(event[0] == "caption" and "NON_EXECUTABLE" in event[1] for event in events)

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.test_mt5_request_dict_final_validation_and_bridge_skeleton import _config as _final_validation_config
from scripts.test_mt5_request_dict_final_validation_and_bridge_skeleton import _inputs as _final_validation_inputs
from src.services.trading.execution.mt5_bridge_write_skeleton import (
    MT5BridgeWriteSkeletonCheckResult,
    MT5BridgeWriteSkeletonServiceResult,
    MT5BridgeWriteSkeletonValidationResult,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit import (
    MT5_IDEMPOTENCY_STATUSES,
    MT5_KILL_SWITCH_STATES,
    MT5_LIVE_ADAPTER_DISABLED_STATUSES,
    MT5_PRE_SUBMIT_GATE_STATUSES,
    MT5KillSwitchService,
    MT5LiveAdapterDisabled,
    MT5LiveAdapterPreSubmitConfig,
    MT5LiveAdapterPreSubmitFormatter,
    MT5LiveAdapterPreSubmitService,
    MT5LiveAdapterPreSubmitValidator,
    MT5PreSubmitGate,
    MT5PreSubmitIdempotencyGuard,
    MT5PreSubmitJournalStore,
)
from src.services.trading.execution.mt5_request_dict_final_validation import MT5RequestDictFinalValidationService


class _FakeBridgeService:
    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1
        check = MT5BridgeWriteSkeletonCheckResult(
            check_id="bridge-check",
            created_at="2026-07-20T00:00:00+00:00",
            bridge_url="http://127.0.0.1:8765",
            endpoint="/execution/write-skeleton/check",
            reachable=True,
            status="BLOCKED",
            write_skeleton_available=True,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            order_sent=False,
            ticket=None,
            deal=None,
            metadata_redacted=True,
        )
        return MT5BridgeWriteSkeletonServiceResult(
            check=check,
            validation=MT5BridgeWriteSkeletonValidationResult(passed=True),
        )


def _config(tmp_path: Path, **kwargs):
    values = {
        "journal_path": str(tmp_path / "mt5_pre_submit_checks.jsonl"),
        "idempotency_path": str(tmp_path / "mt5_pre_submit_idempotency.jsonl"),
    }
    values.update(kwargs)
    return MT5LiveAdapterPreSubmitConfig(**values)


def _final_validation(tmp_path: Path):
    final_config = _final_validation_config(tmp_path)
    final_config.journal_enabled = False
    result = MT5RequestDictFinalValidationService(config=final_config).run(**_final_validation_inputs(tmp_path))
    return result.final_validation, result.validation_report


def _service_result(tmp_path: Path):
    final_validation, final_report = _final_validation(tmp_path)
    config = _config(tmp_path)
    adapter = MT5LiveAdapterDisabled(config=config, bridge_service=_FakeBridgeService())
    return MT5LiveAdapterPreSubmitService(config=config, adapter=adapter).run(final_validation, final_report)


def test_enums_exist():
    assert "BLOCKED_BY_DISABLED_ADAPTER" in MT5_LIVE_ADAPTER_DISABLED_STATUSES
    assert "PASSED_DISABLED_PRE_SUBMIT_CHECK" in MT5_PRE_SUBMIT_GATE_STATUSES
    assert "ENGAGED" in MT5_KILL_SWITCH_STATES
    assert "CHECK_REGISTERED" in MT5_IDEMPOTENCY_STATUSES


def test_kill_switch_default_is_engaged_and_blocks_live_submission(tmp_path):
    check = MT5KillSwitchService(_config(tmp_path)).check()
    assert check.state == "ENGAGED"
    assert check.engaged is True
    assert check.live_execution_allowed is False
    assert check.order_send_allowed is False
    assert "KILL_SWITCH_ENGAGED" in check.blockers


def test_idempotency_registers_check_only_and_duplicate_blocks(tmp_path):
    guard = MT5PreSubmitIdempotencyGuard(_config(tmp_path))
    first = guard.check("idem-key")
    second = guard.check("idem-key")
    assert first.status == "CHECK_REGISTERED"
    assert first.registered_for_check_only is True
    assert first.live_execution_reservation_created is False
    assert first.order_send_reservation_created is False
    assert second.status == "DUPLICATE_BLOCKED"
    assert second.duplicate is True


def test_disabled_adapter_health_bridge_call_and_submit_disabled(tmp_path):
    fake = _FakeBridgeService()
    adapter = MT5LiveAdapterDisabled(config=_config(tmp_path), bridge_service=fake)
    assert adapter.health_check()["adapter_enabled"] is False
    bridge_result = adapter.check_bridge_write_skeleton()
    assert fake.calls == 1
    assert bridge_result.check.endpoint == "/execution/write-skeleton/check"
    receipt = adapter.submit_disabled(bridge_result.check)
    assert receipt.adapter_status == "BLOCKED_BY_DISABLED_ADAPTER"
    assert receipt.adapter_enabled is False
    assert receipt.order_sent is False
    assert receipt.ticket is None
    assert receipt.deal is None
    assert receipt.order_send_allowed is False


def test_pre_submit_gate_requires_inputs_and_keeps_execution_disabled(tmp_path):
    final_validation, final_report = _final_validation(tmp_path)
    fake = _FakeBridgeService().run().check
    kill = MT5KillSwitchService(_config(tmp_path)).check()
    idem = MT5PreSubmitIdempotencyGuard(_config(tmp_path)).check(final_validation.idempotency_key)
    adapter = MT5LiveAdapterDisabled(config=_config(tmp_path), bridge_service=_FakeBridgeService())
    receipt = adapter.submit_disabled(fake)
    report = MT5PreSubmitGate(_config(tmp_path)).evaluate(final_validation, final_report, fake, kill, idem, receipt)
    assert report.valid is True
    assert report.controlled_demo_integration_workflow_allowed is True
    assert report.live_submission_allowed is False
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.order_sent is False
    assert report.ticket is None
    assert report.deal is None
    assert report.hard_live_block_required is True

    blocked = MT5PreSubmitGate(_config(tmp_path)).evaluate(None, None, fake, kill, idem, receipt)
    assert "MISSING_FINAL_VALIDATION" in blocked.blockers
    blocked = MT5PreSubmitGate(_config(tmp_path)).evaluate(final_validation, final_report, None, kill, idem, receipt)
    assert "BRIDGE_WRITE_SKELETON_UNREACHABLE" in blocked.blockers
    bad_bridge = fake
    bad_bridge.status = "OK"
    blocked = MT5PreSubmitGate(_config(tmp_path)).evaluate(final_validation, final_report, bad_bridge, kill, idem, receipt)
    assert "BRIDGE_WRITE_SKELETON_NOT_BLOCKED" in blocked.blockers
    blocked = MT5PreSubmitGate(_config(tmp_path)).evaluate(final_validation, final_report, fake, kill, None, receipt)
    assert "IDEMPOTENCY_MISSING" in blocked.blockers


def test_service_journal_formatter_and_corrupt_jsonl(tmp_path):
    result = _service_result(tmp_path)
    assert result.report.valid is True
    assert result.report.controlled_demo_integration_workflow_allowed is True
    assert result.journal_record is not None
    store = MT5PreSubmitJournalStore(_config(tmp_path).journal_path)
    assert len(store.read_latest()) == 1
    assert store.summarize().total_records == 1
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{bad-json}\n")
    assert store.summarize().warnings
    card = MT5LiveAdapterPreSubmitFormatter().to_card(result.report, result.adapter_receipt, result.journal_record)
    markdown = MT5LiveAdapterPreSubmitFormatter().to_markdown_summary(result.report, result.adapter_receipt, result.journal_record)
    assert card["live_submission_allowed"] is False
    assert "raw_account_id" not in markdown


@pytest.mark.parametrize(
    "marker",
    [
        "." + "order_" + "send(",
        "MetaTrader5." + "order_" + "send(",
        "mt5." + "order_" + "send(",
        "order_" + "send(",
    ],
)
def test_validator_rejects_real_function_call_markers(marker):
    assert MT5LiveAdapterPreSubmitValidator().validate_payload_text(marker).passed is False


def test_validator_does_not_reject_order_send_allowed_name():
    assert MT5LiveAdapterPreSubmitValidator().validate_payload_text("order_send_allowed=false").passed is True


def test_dashboard_bridge_and_static_safety():
    dashboard_text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    bridge_text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    src_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path("src").rglob("*.py"))
    assert "MT5 Live Adapter Disabled + Pre-Submit Gate" in dashboard_text
    assert "Run MT5 Pre-Submit Safety Check" in dashboard_text
    assert "Confirm Trade" not in dashboard_text
    assert "Execute Trade" not in dashboard_text
    assert "Place Order" not in dashboard_text
    assert "Buy" not in dashboard_text
    assert "Sell" not in dashboard_text
    for endpoint in ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]:
        assert endpoint not in bridge_text
    assert "/execution/write-skeleton/check" in bridge_text
    assert "import MetaTrader5" not in src_text
    assert "from MetaTrader5" not in src_text
    assert "qdrant_client.delete_collection" not in src_text
    assert "recreate_collection" not in src_text

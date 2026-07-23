from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.manual_mt5_controlled_execution as manual
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    ProtectedRequestExportError,
)


EXECUTION_PHRASE = "SUBMIT CONTROLLED MT5 ORDER"
FINGERPRINT = "a" * 64


def _config(**overrides):
    values = {
        "controlled_execution_enabled": True,
        "live_adapter_enabled": True,
        "live_adapter_hard_block": False,
        "allow_live_submission": True,
        "allow_order_send": True,
        "kill_switch_engaged": False,
        "execution_auth_token": "redacted-test-token",
        "execution_confirmation_phrase": EXECUTION_PHRASE,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _verified():
    return SimpleNamespace(
        approval_lock=object(),
        final_validation=object(),
        final_validation_report=object(),
        pre_submit_report=object(),
        account_fingerprint=FINGERPRINT,
        semantic_hash="b" * 64,
    )


class FakeAdapter:
    def __init__(self, fingerprint=FINGERPRINT, receipt_reason=""):
        self.fingerprint = fingerprint
        self.receipt_reason = receipt_reason
        self.submissions = []

    def capture_account_context(self):
        return {
            "account_context_fingerprint": self.fingerprint,
            "server_redacted": "re***ed",
            "currency": "USD",
            "trade_mode": 0,
        }

    def submit_controlled(self, *artifacts, **kwargs):
        self.submissions.append((artifacts, kwargs))
        return SimpleNamespace(
            status="REJECTED",
            idempotency_status="RESULT_REJECTED",
            order_sent=False,
            ticket_present=False,
            deal_present=False,
            reason=self.receipt_reason,
        )


def _wire(monkeypatch, adapter, *, verified=None, config=None):
    monkeypatch.setattr(
        manual.MT5LiveAdapterPreSubmitConfig,
        "from_config",
        staticmethod(lambda: config or _config()),
    )
    monkeypatch.setattr(
        manual,
        "verify_protected_artifact_bundle",
        lambda bundle: {"proposal_artifact": "proposal.json"},
    )
    monkeypatch.setattr(
        manual,
        "load_verified_protected_execution_artifacts",
        lambda **kwargs: verified or _verified(),
    )
    monkeypatch.setattr(manual, "MT5LiveAdapterDisabled", lambda config: adapter)


def test_manual_cli_builds_execution_request_from_verified_artifacts(monkeypatch, capsys):
    adapter = FakeAdapter()
    verified = _verified()
    _wire(monkeypatch, adapter, verified=verified)
    prompts = []
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: prompts.append(prompt) or EXECUTION_PHRASE,
    )

    exit_code = manual.main(["--artifact-bundle", "protected-bundle"])

    assert exit_code == 0
    assert len(adapter.submissions) == 1
    artifacts, kwargs = adapter.submissions[0]
    assert artifacts == (
        verified.approval_lock,
        verified.final_validation,
        verified.final_validation_report,
        verified.pre_submit_report,
    )
    assert kwargs == {
        "expected_account_context_fingerprint": FINGERPRINT,
        "typed_confirmation": EXECUTION_PHRASE,
    }
    assert len(prompts) == 1
    assert EXECUTION_PHRASE in prompts[0]
    assert EXECUTION_PHRASE not in capsys.readouterr().out


def test_manual_cli_blocks_account_mismatch_before_prompt_or_submit(monkeypatch):
    adapter = FakeAdapter("c" * 64)
    _wire(monkeypatch, adapter)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: pytest.fail("confirmation prompt must not open"),
    )

    assert manual.main(["--artifact-bundle", "protected-bundle"]) == 4
    assert adapter.submissions == []


def test_manual_cli_blocks_invalid_or_stale_bundle_before_adapter(monkeypatch):
    monkeypatch.setattr(
        manual.MT5LiveAdapterPreSubmitConfig,
        "from_config",
        staticmethod(_config),
    )
    monkeypatch.setattr(
        manual,
        "verify_protected_artifact_bundle",
        lambda bundle: {"proposal_artifact": "proposal.json"},
    )
    monkeypatch.setattr(
        manual,
        "load_verified_protected_execution_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(ProtectedRequestExportError("artifact is stale")),
    )
    monkeypatch.setattr(
        manual,
        "MT5LiveAdapterDisabled",
        lambda config: pytest.fail("adapter must not be created"),
    )

    assert manual.main(["--artifact-bundle", "protected-bundle"]) == 3


def test_manual_cli_blocks_when_runtime_controls_are_disabled(monkeypatch):
    monkeypatch.setattr(
        manual.MT5LiveAdapterPreSubmitConfig,
        "from_config",
        staticmethod(lambda: _config(controlled_execution_enabled=False)),
    )
    monkeypatch.setattr(
        manual,
        "verify_protected_artifact_bundle",
        lambda bundle: pytest.fail("bundle must not be read"),
    )

    assert manual.main(["--artifact-bundle", "protected-bundle"]) == 2


def test_manual_cli_never_promotes_export_only_request_file_directly():
    source = Path(manual.__file__).read_text(encoding="utf-8")
    assert "--request-file" not in source
    assert "submit_prepared_request" not in source
    assert "MT5ControlledExecutionRequest(**" not in source
    assert "load_verified_protected_execution_artifacts" in source
    assert "adapter.submit_controlled(" in source


def test_manual_cli_redacts_unsafe_receipt_reason(monkeypatch, capsys):
    sensitive_reason = "blocked for account 123456"
    adapter = FakeAdapter(receipt_reason=sensitive_reason)
    _wire(monkeypatch, adapter)
    monkeypatch.setattr("builtins.input", lambda prompt: EXECUTION_PHRASE)

    assert manual.main(["--artifact-bundle", "protected-bundle"]) == 0

    output = capsys.readouterr().out
    assert "reason_code=UNSPECIFIED" in output
    assert sensitive_reason not in output

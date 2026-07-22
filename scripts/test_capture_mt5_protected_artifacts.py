from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.capture_mt5_protected_artifacts import main as cli_main
from scripts.test_controlled_live_parameter_value_proposal import _inputs as _proposal_inputs
from src.config import Config
from src.services.trading.execution.live_value_approval_lock.policy import (
    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
)
from src.services.trading.execution.mt5_bridge_write_skeleton import (
    MT5BridgeWriteSkeletonCheckResult,
    MT5BridgeWriteSkeletonServiceResult,
    MT5BridgeWriteSkeletonValidationResult,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    OperatorProtectedArtifactCaptureService,
    PROTECTED_ARTIFACT_FILENAMES,
    ProtectedArtifactCaptureError,
    ProtectedArtifactCaptureResult,
    ProtectedCaptureUpstreamArtifacts,
    verify_protected_artifact_bundle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    export_protected_request,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.service import (
    MT5LiveAdapterPreSubmitService,
)


ACCOUNT_FINGERPRINT = "a" * 64
OTHER_ACCOUNT_FINGERPRINT = "b" * 64
EXPORT_CONFIRMATION = EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE


class _FakeBridgeService:
    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1
        check = MT5BridgeWriteSkeletonCheckResult(
            check_id="capture-bridge-check",
            created_at=datetime.now(timezone.utc).isoformat(),
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


class _FakeAccountClient:
    def __init__(self, fingerprints=None):
        self.fingerprints = list(fingerprints or [ACCOUNT_FINGERPRINT, ACCOUNT_FINGERPRINT])
        self.calls = 0

    def account_context(self):
        index = min(self.calls, len(self.fingerprints) - 1)
        self.calls += 1
        return {
            "status": "OK",
            "account_context_fingerprint": self.fingerprints[index],
            "account_id_hash": "c" * 64,
            "server_redacted": "re***ed",
            "currency": "USD",
            "trade_mode": 0,
        }


def _semantic_values():
    return {
        "action": "MARKET",
        "symbol": "SYNTHETIC_TEST_SYMBOL",
        "volume": "1.00",
        "order_type": "BUY",
        "price": "100.25",
        "stop_loss": "99.50",
        "take_profit": "102.00",
        "deviation": 5,
        "magic": 34001,
        "comment": "fixture-only-comment",
        "idempotency": "fixture-only-idempotency",
        "audit": "fixture-only-audit",
    }


def _write_semantics(tmp_path: Path, payload=None):
    path = tmp_path / "semantic-input.json"
    path.write_text(json.dumps(_semantic_values() if payload is None else payload), encoding="utf-8")
    return path


def _upstream_builder(tmp_path: Path):
    calls = 0

    def build(_bridge_url, _mode):
        nonlocal calls
        calls += 1
        return ProtectedCaptureUpstreamArtifacts(
            **_proposal_inputs(tmp_path / f"upstream-{calls}-{uuid4().hex}")
        )

    return build


def _adapter_factory(fingerprints=None):
    client = _FakeAccountClient(fingerprints)

    def build(_bridge_url):
        config = MT5LiveAdapterPreSubmitConfig(
            bridge_url="http://127.0.0.1:8765",
            journal_path="capture-pre-submit.jsonl",
            idempotency_path="capture-idempotency.jsonl",
        )
        return MT5LiveAdapterDisabled(
            config=config,
            bridge_service=_FakeBridgeService(),
            execution_client=client,
        )

    return build, client


def _pre_submit_factory(tmp_path: Path):
    def build(_bridge_url):
        config = MT5LiveAdapterPreSubmitConfig(
            bridge_url="http://127.0.0.1:8765",
            journal_path=str(tmp_path / "pre-submit.jsonl"),
            idempotency_path=str(tmp_path / "idempotency.jsonl"),
        )
        adapter = MT5LiveAdapterDisabled(config=config, bridge_service=_FakeBridgeService())
        return MT5LiveAdapterPreSubmitService(config=config, adapter=adapter)

    return build


def _service(tmp_path: Path, fingerprints=None):
    adapter_factory, client = _adapter_factory(fingerprints)
    service = OperatorProtectedArtifactCaptureService(
        upstream_builder=_upstream_builder(tmp_path),
        adapter_factory=adapter_factory,
        pre_submit_service_factory=_pre_submit_factory(tmp_path),
    )
    return service, client


def _capture(tmp_path: Path, *, fingerprints=None, output_name="capture-one"):
    service, client = _service(tmp_path, fingerprints)
    result = service.capture(
        semantic_input=_write_semantics(tmp_path),
        output_dir=Path("data/trading/protected_requests") / output_name,
        approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
        export_confirmation_phrase=EXPORT_CONFIRMATION,
    )
    return result, client


def _cleanup_bundle(result):
    bundle = Path(result.bundle_path)
    for path in bundle.iterdir():
        path.unlink()
    bundle.rmdir()


def test_complete_genuine_artifact_chain_and_protected_lock(tmp_path):
    result, client = _capture(tmp_path)
    try:
        paths = verify_protected_artifact_bundle(result.bundle_path)
        lock = json.loads(paths["lock_artifact"].read_text(encoding="utf-8"))
        confirmation = json.loads(paths["human_confirmation_artifact"].read_text(encoding="utf-8"))
        assert result.artifact_count == 9
        assert confirmation["purpose"] == "export_only"
        assert confirmation["non_executable"] is True
        assert set(paths) == set(PROTECTED_ARTIFACT_FILENAMES)
        assert lock["approved_semantic_parameters"]["symbol"] == _semantic_values()["symbol"]
        assert lock["approved_semantic_values_hash"] == (
            lock["approved_semantic_parameters"]["canonical_values_hash"]
        )
        assert client.calls == 2
    finally:
        _cleanup_bundle(result)


def test_public_serialization_remains_redacted(tmp_path):
    result, _ = _capture(tmp_path)
    try:
        lock = json.loads(
            (Path(result.bundle_path) / "approval-lock.json").read_text(encoding="utf-8")
        )
        from src.services.trading.execution.live_value_approval_lock.models import (
            ApprovedSemanticExecutionParameters,
            HumanValueApprovalLock,
        )

        parameters = ApprovedSemanticExecutionParameters.from_protected_dict(
            lock["approved_semantic_parameters"]
        )
        model_fields = set(HumanValueApprovalLock.__dataclass_fields__)
        model = HumanValueApprovalLock(
            **{
                key: value
                for key, value in lock.items()
                if key in model_fields and key not in {"approved_semantic_parameters", "slot_locks"}
            },
            approved_semantic_parameters=parameters,
        )
        public = json.dumps(model.as_dict(), sort_keys=True)
        assert _semantic_values()["symbol"] not in public
        assert _semantic_values()["comment"] not in public
        assert model.as_dict()["approved_semantic_parameters"]["values_redacted"] is True
    finally:
        _cleanup_bundle(result)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda values: values.update({"unknown": "blocked"}),
        lambda values: values.pop("price"),
        lambda values: values.clear(),
        lambda values: values.update({"symbol": "REFERENCE_ONLY"}),
    ],
)
def test_unknown_missing_and_schema_only_semantics_fail_closed(tmp_path, mutate):
    values = _semantic_values()
    mutate(values)
    semantic_path = _write_semantics(tmp_path, values)
    service, _ = _service(tmp_path)
    with pytest.raises(ProtectedArtifactCaptureError):
        service.capture(
            semantic_input=semantic_path,
            output_dir=Path("data/trading/protected_requests") / f"invalid-{id(mutate)}",
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )


def test_confirmation_whitespace_is_stripped_and_accepted(tmp_path):
    service, _ = _service(tmp_path)
    result = service.capture(
        semantic_input=_write_semantics(tmp_path),
        output_dir=Path("data/trading/protected_requests/whitespace-confirmations"),
        approval_confirmation_phrase=f"  {EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE}  ",
        export_confirmation_phrase=f"  {EXPORT_CONFIRMATION}  ",
    )
    _cleanup_bundle(result)


@pytest.mark.parametrize("approval_phrase", ["", "wrong approval phrase"])
def test_empty_or_wrong_approval_confirmation_fails_without_partial_bundle(tmp_path, approval_phrase):
    service, _ = _service(tmp_path)
    output = Path("data/trading/protected_requests/invalid-approval-confirmation")
    with pytest.raises(ProtectedArtifactCaptureError, match="approval confirmation is invalid"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=output,
            approval_confirmation_phrase=approval_phrase,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )
    assert not output.exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("export_phrase", ["", "wrong export phrase"])
def test_empty_or_wrong_export_confirmation_fails_without_partial_bundle(tmp_path, export_phrase):
    service, _ = _service(tmp_path)
    output = Path("data/trading/protected_requests/invalid-export-confirmation")
    with pytest.raises(ProtectedArtifactCaptureError, match="export confirmation is invalid"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=output,
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=export_phrase,
        )
    assert not output.exists()
    assert not (output / "manifest.json").exists()


def test_approval_lock_hash_mismatch_fails_closed(tmp_path, monkeypatch):
    from src.services.trading.execution.live_value_approval_lock.service import HumanValueApprovalLockService

    original = HumanValueApprovalLockService.run

    def changed(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        result.approval_lock.lock_value_hash = "0" * 64
        return result

    monkeypatch.setattr(HumanValueApprovalLockService, "run", changed)
    service, _ = _service(tmp_path)
    with pytest.raises(ProtectedArtifactCaptureError):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=Path("data/trading/protected_requests") / "hash-mismatch",
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )


def test_two_account_fingerprints_match_and_change_fails(tmp_path):
    result, _ = _capture(tmp_path, output_name="matching-account")
    _cleanup_bundle(result)
    service, _ = _service(tmp_path, [ACCOUNT_FINGERPRINT, OTHER_ACCOUNT_FINGERPRINT])
    with pytest.raises(ProtectedArtifactCaptureError, match="account context changed"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=Path("data/trading/protected_requests") / "changed-account",
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )


def test_stale_account_capture_and_human_confirmation_fail(tmp_path, monkeypatch):
    import src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture as capture

    original_capture = capture._capture_account_context

    def stale_account(adapter, captured_at):
        return original_capture(adapter, captured_at - timedelta(minutes=10))

    monkeypatch.setattr(capture, "_capture_account_context", stale_account)
    service, _ = _service(tmp_path)
    with pytest.raises(ProtectedArtifactCaptureError, match="stale"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=Path("data/trading/protected_requests") / "stale-account",
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )

    monkeypatch.setattr(capture, "_capture_account_context", original_capture)
    original_confirmation = capture.ProtectedExportConfirmation.confirm

    def stale_confirmation(*args, **kwargs):
        confirmation = original_confirmation(*args, **kwargs)
        stale = datetime.now(timezone.utc) - timedelta(minutes=10)
        return replace(
            confirmation,
            created_at=stale.isoformat(),
            expires_at=stale.isoformat(),
        )

    monkeypatch.setattr(
        capture.ProtectedExportConfirmation,
        "confirm",
        staticmethod(stale_confirmation),
    )
    with pytest.raises(ProtectedArtifactCaptureError, match="exporter-compatible"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=Path("data/trading/protected_requests") / "stale-confirmation",
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=EXPORT_CONFIRMATION,
        )


def test_existing_directory_is_not_overwritten_and_partial_bundle_is_rejected(tmp_path):
    existing = Path("data/trading/protected_requests/existing-capture")
    existing.mkdir(parents=True, exist_ok=True)
    marker = existing / "operator-owned"
    marker.write_text("preserve", encoding="utf-8")
    try:
        service, _ = _service(tmp_path)
        with pytest.raises(ProtectedArtifactCaptureError):
            service.capture(
                semantic_input=_write_semantics(tmp_path),
                output_dir=existing,
                approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
                export_confirmation_phrase=EXPORT_CONFIRMATION,
            )
        assert marker.read_text(encoding="utf-8") == "preserve"
        with pytest.raises(ProtectedArtifactCaptureError, match="incomplete"):
            verify_protected_artifact_bundle(existing)
    finally:
        marker.unlink()
        existing.rmdir()


def test_completed_bundle_is_accepted_by_existing_exporter(tmp_path):
    result, _ = _capture(tmp_path, output_name="export-compatible")
    output = tmp_path / "protected-request.json"
    try:
        paths = verify_protected_artifact_bundle(result.bundle_path)
        export_result = export_protected_request(
            **paths,
            output=output,
            expected_confirmation_phrase=EXPORT_CONFIRMATION,
        )
        assert export_result.validation_status == "VALID"
    finally:
        output.unlink(missing_ok=True)
        _cleanup_bundle(result)


def test_no_submission_reconciliation_or_execution_flag_changes(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden execution path called")

    monkeypatch.setattr(MT5LiveAdapterDisabled, "submit_controlled", forbidden)
    monkeypatch.setattr(MT5LiveAdapterDisabled, "reconcile_controlled", forbidden)
    names = (
        "TRADING_MT5_LIVE_ADAPTER_ENABLED",
        "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION",
        "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND",
        "TRADING_MT5_KILL_SWITCH_ENGAGED",
    )
    before = {name: getattr(Config, name) for name in names}
    environment_before = {name: os.environ.get(name) for name in names}
    journal_root = Path("data/trading/execution_journal")
    journals_before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in journal_root.glob("*.jsonl")
    }
    result, _ = _capture(tmp_path, output_name="safety-state")
    try:
        assert {name: getattr(Config, name) for name in names} == before
        assert {name: os.environ.get(name) for name in names} == environment_before
        assert {
            path.name: (path.stat().st_size, path.stat().st_mtime_ns)
            for path in journal_root.glob("*.jsonl")
        } == journals_before
        source = Path(
            "src/services/trading/execution/mt5_live_adapter_pre_submit/protected_artifact_capture.py"
        ).read_text(encoding="utf-8")
        assert ".order_" + "send(" not in source
        assert "submit_controlled(" not in source
        assert "reconcile_controlled(" not in source
    finally:
        _cleanup_bundle(result)


def test_export_confirmation_is_distinct_from_manual_execution_confirmation():
    assert EXPORT_CONFIRMATION == "EXPORT PROTECTED MT5 REQUEST WITHOUT SUBMISSION"
    assert MT5LiveAdapterPreSubmitConfig().execution_confirmation_phrase == "SUBMIT CONTROLLED MT5 ORDER"
    assert EXPORT_CONFIRMATION != MT5LiveAdapterPreSubmitConfig().execution_confirmation_phrase


def test_manual_execution_confirmation_does_not_authorize_capture(tmp_path):
    service, _ = _service(tmp_path)
    with pytest.raises(ProtectedArtifactCaptureError, match="export confirmation is invalid"):
        service.capture(
            semantic_input=_write_semantics(tmp_path),
            output_dir=Path("data/trading/protected_requests/manual-phrase-rejected"),
            approval_confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
            export_confirmation_phrase=MT5LiveAdapterPreSubmitConfig().execution_confirmation_phrase,
        )


def test_cli_uses_visible_input_and_strips_whitespace(monkeypatch, tmp_path):
    result = ProtectedArtifactCaptureResult(
        capture_reference_redacted="capture-ref...",
        semantic_hash_prefix="123456789abc",
        account_fingerprint_redacted="abcdef123456...",
        artifact_count=9,
        bundle_path=str(tmp_path / "bundle"),
    )
    captured_kwargs = {}

    def capture(self, **kwargs):
        captured_kwargs.update(kwargs)
        return result

    responses = iter([
        f"  {EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE}  ",
        f"  {EXPORT_CONFIRMATION}  ",
    ])
    monkeypatch.setattr(OperatorProtectedArtifactCaptureService, "capture", capture)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))
    assert cli_main([
        "--semantic-input", "protected-input.json",
        "--output-dir", str(tmp_path / "bundle"),
    ]) == 0
    assert captured_kwargs["approval_confirmation_phrase"] == EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE
    assert captured_kwargs["export_confirmation_phrase"] == EXPORT_CONFIRMATION


def test_cli_reports_redacted_domain_block_reason(monkeypatch, tmp_path, capsys):
    def blocked(self, **kwargs):
        raise ProtectedArtifactCaptureError("disabled pre-submit validation failed")

    monkeypatch.setattr(OperatorProtectedArtifactCaptureService, "capture", blocked)
    confirmations = iter([EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE, EXPORT_CONFIRMATION])
    assert cli_main(
        ["--semantic-input", "protected-input.json", "--output-dir", str(tmp_path / "bundle")],
        confirmation_reader=lambda _prompt: next(confirmations),
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "status=BLOCKED:DISABLED_PRE_SUBMIT_VALIDATION_FAILED"


def test_cli_output_is_redacted(monkeypatch, tmp_path, capsys):
    result = ProtectedArtifactCaptureResult(
        capture_reference_redacted="capture-ref...",
        semantic_hash_prefix="123456789abc",
        account_fingerprint_redacted="abcdef123456...",
        artifact_count=9,
        bundle_path=str(tmp_path / "bundle"),
    )
    monkeypatch.setattr(
        OperatorProtectedArtifactCaptureService,
        "capture",
        lambda self, **kwargs: result,
    )
    confirmations = iter([EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE, EXPORT_CONFIRMATION])
    assert (
        cli_main(
            ["--semantic-input", "protected-input.json", "--output-dir", str(tmp_path / "bundle")],
            confirmation_reader=lambda _prompt: next(confirmations),
        )
        == 0
    )
    output = capsys.readouterr().out
    assert set(line.split("=", 1)[0] for line in output.strip().splitlines()) == {
        "capture_reference",
        "semantic_hash_prefix",
        "account_fingerprint",
        "artifact_count",
        "bundle_path",
        "status",
    }
    for name in ("symbol", "comment", "idempotency", "audit"):
        assert str(_semantic_values()[name]) not in output
    assert EXPORT_CONFIRMATION not in output

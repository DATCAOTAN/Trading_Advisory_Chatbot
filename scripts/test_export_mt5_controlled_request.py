from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.export_mt5_controlled_request import main
from scripts.test_approved_semantic_execution_parameters import _bind_contract
from scripts.test_mt5_request_dict_dry_run_builder import _config as _dry_run_config
from scripts.test_mt5_request_dict_dry_run_builder import _inputs as _dry_run_inputs
from src.config import Config
from src.services.trading.execution.live_value_approval_lock.models import HumanValueApprovalConfirmation
from src.services.trading.execution.live_value_approval_lock.policy import EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE
from src.services.trading.execution.mt5_bridge_write_skeleton.models import MT5BridgeWriteSkeletonCheckResult
from src.services.trading.execution.mt5_live_adapter_pre_submit.gate import MT5PreSubmitGate
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5IdempotencyCheck,
    MT5KillSwitchCheck,
    MT5LiveAdapterDisabledReceipt,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    ProtectedRequestExportError,
    export_protected_request,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.builder import (
    MT5RequestDictDryRunBuilder,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.gate import (
    MT5RequestDictDryRunBuilderGate,
)
from src.services.trading.execution.mt5_request_dict_final_validation.builder import (
    MT5RequestDictFinalValidationBuilder,
)
from src.services.trading.execution.mt5_request_dict_final_validation.gate import (
    MT5RequestDictFinalValidationGate,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import (
    MT5RequestDictFinalValidationConfig,
)


ACCOUNT_FINGERPRINT = "a" * 64
MANUAL_CONTROLLED_CONFIRMATION = MT5LiveAdapterPreSubmitConfig().execution_confirmation_phrase
EXPORT_CONFIRMATION = EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return path


def _artifact_files(tmp_path: Path) -> dict[str, Path]:
    inputs = _dry_run_inputs(tmp_path)
    contract = _bind_contract(inputs["approval_lock"])
    for name in ("parameterization", "final_review", "request_draft", "draft_final_approval"):
        getattr(inputs[name], "__dict__")["artifact_hash"] = contract.canonical_values_hash

    dry_config = _dry_run_config(tmp_path)
    dry_config.journal_enabled = False
    dry_boundary = MT5RequestDictDryRunBuilder(dry_config).build(
        **inputs, require_approved_semantic_values=True
    )
    dry_report = MT5RequestDictDryRunBuilderGate(dry_config).validate(dry_boundary)
    assert dry_report.valid is True

    final_config = MT5RequestDictFinalValidationConfig(
        journal_enabled=False,
        journal_path=str(tmp_path / "final-validation.jsonl"),
    )
    final_validation = MT5RequestDictFinalValidationBuilder(final_config).build(
        dry_boundary, dry_report
    )
    final_report = MT5RequestDictFinalValidationGate(final_config).validate(final_validation)
    assert final_report.valid is True

    created_at = datetime.now(timezone.utc)
    bridge_check = MT5BridgeWriteSkeletonCheckResult(
        check_id="bridge-check",
        created_at=created_at.isoformat(),
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
    kill_switch = MT5KillSwitchCheck(
        check_id="kill-switch-check",
        created_at=created_at.isoformat(),
        state="ENGAGED",
        engaged=True,
        source="CONFIG",
        blockers=["KILL_SWITCH_ENGAGED"],
    )
    idempotency = MT5IdempotencyCheck(
        check_id="idempotency-check",
        created_at=created_at.isoformat(),
        idempotency_key=final_validation.idempotency_key,
        status="CHECK_REGISTERED",
        duplicate=False,
        registered_for_check_only=True,
        live_execution_reservation_created=False,
        order_send_reservation_created=False,
        expires_at=(created_at + timedelta(minutes=5)).isoformat(),
    )
    adapter_receipt = MT5LiveAdapterDisabledReceipt(
        receipt_id="adapter-receipt",
        created_at=created_at.isoformat(),
        adapter_status="BLOCKED_BY_DISABLED_ADAPTER",
        bridge_check_reachable=True,
        bridge_check_status="BLOCKED",
        bridge_endpoint="/execution/write-skeleton/check",
        blockers=["LIVE_ADAPTER_DISABLED"],
    )
    pre_submit = MT5PreSubmitGate(
        MT5LiveAdapterPreSubmitConfig(
            journal_path=str(tmp_path / "pre-submit.jsonl"),
            idempotency_path=str(tmp_path / "idempotency.jsonl"),
        )
    ).evaluate(
        final_validation,
        final_report,
        bridge_check,
        kill_switch,
        idempotency,
        adapter_receipt,
    )
    assert pre_submit.valid is True

    approval_lock = inputs["approval_lock"]
    approval = HumanValueApprovalConfirmation(
        confirmation_id=approval_lock.confirmation_id,
        created_at=contract.approved_at,
        phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
        expected_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
        phrase_valid=True,
        action="APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY",
        review_state="HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY",
        expires_at=approval_lock.expires_at,
        approved_semantic_values_hash=contract.canonical_values_hash,
        source_refs=list(approval_lock.source_refs),
    )
    account = {
        "status": "OK",
        "account_context_fingerprint": ACCOUNT_FINGERPRINT,
        "account_id_hash": "b" * 64,
        "server_redacted": "re***ed",
        "currency": "USD",
        "trade_mode": 0,
        "redacted": True,
        "captured_at": created_at.isoformat(),
    }
    confirmation = {
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(minutes=5)).isoformat(),
        "phrase": EXPORT_CONFIRMATION,
        "phrase_valid": True,
        "expected_account_context_fingerprint": ACCOUNT_FINGERPRINT,
        "metadata_redacted": True,
        "proposal_reference": inputs["value_proposal"].proposal_id,
        "approval_lock_reference": approval_lock.approval_lock_id,
        "final_validation_reference": final_validation.final_validation_id,
        "approved_semantic_values_hash": contract.canonical_values_hash,
        "purpose": "export_only",
        "non_executable": True,
    }
    return {
        "proposal_artifact": _write(tmp_path / "proposal.json", inputs["value_proposal"].as_dict()),
        "approval_artifact": _write(tmp_path / "approval.json", approval.as_dict()),
        "lock_artifact": _write(tmp_path / "lock.json", approval_lock.as_protected_dict()),
        "final_validation_artifact": _write(
            tmp_path / "final-validation.json", final_validation.as_dict()
        ),
        "final_validation_report_artifact": _write(
            tmp_path / "final-validation-report.json", final_report.as_dict()
        ),
        "pre_submit_artifact": _write(tmp_path / "pre-submit.json", pre_submit.as_dict()),
        "account_fingerprint_artifact": _write(tmp_path / "account.json", account),
        "account_fingerprint_submit_artifact": _write(tmp_path / "account-submit.json", account),
        "human_confirmation_artifact": _write(
            tmp_path / "execution-confirmation.json", confirmation
        ),
    }


def _export(tmp_path: Path, files: dict[str, Path], *, name: str = "request.json"):
    return export_protected_request(
        **files,
        output=tmp_path / name,
        expected_confirmation_phrase=EXPORT_CONFIRMATION,
    )


def _mutate(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    _write(path, payload)


def test_valid_export_uses_genuine_compatible_artifacts(tmp_path):
    files = _artifact_files(tmp_path)
    result = _export(tmp_path, files)
    payload = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))

    assert result.validation_status == "VALID"
    assert result.request_reference_redacted.endswith("...")
    assert payload["request_version"] == "controlled-mt5-execution/v1"
    assert payload["canonical_semantic_hash"].startswith(result.semantic_hash_prefix)
    assert payload["expected_account_context_fingerprint"] == ACCOUNT_FINGERPRINT
    assert payload["pre_submit_validation_valid"] is True
    assert payload["execution_permission_requested"] is False
    assert payload["human_confirmation_phrase"] == EXPORT_CONFIRMATION
    assert MANUAL_CONTROLLED_CONFIRMATION == "SUBMIT CONTROLLED MT5 ORDER"
    assert EXPORT_CONFIRMATION != MANUAL_CONTROLLED_CONFIRMATION


def test_modified_semantic_values_fail_closed(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(
        files["lock_artifact"],
        lambda payload: payload["approved_semantic_parameters"].__setitem__(
            "symbol", payload["approved_semantic_parameters"]["symbol"] + "-changed"
        ),
    )
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)
    assert not (tmp_path / "request.json").exists()


def test_approval_and_lock_hash_mismatch_fail_closed(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(files["lock_artifact"], lambda payload: payload.__setitem__("lock_value_hash", "0" * 64))
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)


def test_export_confirmation_must_be_export_only_and_non_executable(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(
        files["human_confirmation_artifact"],
        lambda payload: payload.update({"purpose": "execution", "non_executable": False}),
    )
    with pytest.raises(ProtectedRequestExportError, match="export confirmation is invalid"):
        _export(tmp_path, files)


def test_manual_execution_confirmation_does_not_authorize_export(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(
        files["human_confirmation_artifact"],
        lambda payload: payload.__setitem__("phrase", MANUAL_CONTROLLED_CONFIRMATION),
    )
    with pytest.raises(ProtectedRequestExportError, match="export confirmation is invalid"):
        _export(tmp_path, files)


def test_stale_confirmation_fails_closed(tmp_path):
    files = _artifact_files(tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    _mutate(
        files["human_confirmation_artifact"],
        lambda payload: payload.update({"created_at": stale, "expires_at": stale}),
    )
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)


def test_account_fingerprint_mismatch_fails_closed(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(
        files["account_fingerprint_submit_artifact"],
        lambda payload: payload.__setitem__("account_context_fingerprint", "c" * 64),
    )
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)


def test_schema_only_and_missing_artifacts_fail_closed(tmp_path):
    files = _artifact_files(tmp_path)
    _mutate(
        files["lock_artifact"],
        lambda payload: payload.__setitem__(
            "approved_semantic_parameters",
            {
                "schema_version": "approved-semantic-execution-parameters/v1",
                "values_redacted": True,
            },
        ),
    )
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)

    missing_root = tmp_path / "missing-case"
    files = _artifact_files(missing_root)
    files["proposal_artifact"].unlink()
    with pytest.raises(ProtectedRequestExportError):
        _export(missing_root, files)


def test_export_cli_bootstraps_project_root():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(project_root / "scripts/export_mt5_controlled_request.py"), "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_cli_prints_only_redacted_export_summary(tmp_path, capsys):
    files = _artifact_files(tmp_path)
    argv = []
    for name, path in files.items():
        argv.extend(["--" + name.replace("_", "-"), str(path)])
    argv.extend(["--output", str(tmp_path / "request.json")])

    assert main(argv) == 0
    output = capsys.readouterr().out
    protected = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    semantic = protected["approved_semantic_parameters"]
    assert {line.split("=", 1)[0] for line in output.strip().splitlines()} == {
        "request_reference",
        "semantic_hash_prefix",
        "account_fingerprint",
        "output_path",
        "validation_status",
    }
    for value in (
        semantic["symbol"],
        semantic["comment"],
        semantic["idempotency"],
        EXPORT_CONFIRMATION,
        ACCOUNT_FINGERPRINT,
    ):
        assert value not in output
    assert "validation_status=VALID" in output


def test_export_never_calls_bridge_or_order_send(tmp_path, monkeypatch):
    files = _artifact_files(tmp_path)

    def blocked_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr("urllib.request.urlopen", blocked_network)
    _export(tmp_path, files)
    source = Path(
        "src/services/trading/execution/mt5_live_adapter_pre_submit/protected_export.py"
    ).read_text(encoding="utf-8")
    assert "MT5BridgeWriteSkeletonClient" not in source
    assert ".order_" + "send(" not in source


def test_export_does_not_modify_execution_flags(tmp_path):
    files = _artifact_files(tmp_path)
    names = (
        "TRADING_MT5_LIVE_ADAPTER_ENABLED",
        "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION",
        "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND",
        "TRADING_MT5_KILL_SWITCH_ENGAGED",
    )
    before = {name: getattr(Config, name) for name in names}
    _export(tmp_path, files)
    assert {name: getattr(Config, name) for name in names} == before


def test_existing_output_is_never_overwritten(tmp_path):
    files = _artifact_files(tmp_path)
    output = tmp_path / "request.json"
    output.write_text("operator-owned", encoding="utf-8")
    with pytest.raises(ProtectedRequestExportError):
        _export(tmp_path, files)
    assert output.read_text(encoding="utf-8") == "operator-owned"

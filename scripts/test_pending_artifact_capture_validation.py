from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

import scripts.export_mt5_pending_artifact as pending_cli
from scripts.test_autonomous_decision_orchestrator import NOW, service
from scripts.test_controlled_pending_order_dry_run import (
    FINGERPRINT,
    account_context,
    confirmation_for,
    review_for,
)
from scripts.test_structured_market_pending_order_candidate import structured_inputs
from src.services.trading.execution.mt5_live_adapter_pre_submit import pending_artifact_export as exporter
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    PENDING_EXECUTION_REQUEST_VERSION,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_artifact_export import (
    PENDING_ARTIFACT_BUNDLE_SCHEMA,
    PendingArtifactExportError,
    PendingArtifactExportResult,
    export_pending_artifact_bundle,
    validate_pending_artifact_bundle,
    write_pending_candidate_handoff,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    SUPPORTED_PENDING_ORDER_TYPES,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
)


PHRASE = EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE


def _sources(tmp_path: Path, order_type: str = "BUY_LIMIT"):
    root = tmp_path / "protected"
    root.mkdir(exist_ok=True)
    run_result = service(tmp_path).run_once(structured_inputs(order_type), now=NOW)
    review = review_for(run_result.candidate)
    confirmation = confirmation_for(run_result.candidate, review)
    account_path = root / "account-context.json"
    account_path.write_text(json.dumps(account_context().as_dict()), encoding="utf-8")
    return root, run_result, review, confirmation, account_path


def _handoff(tmp_path: Path, order_type: str = "BUY_LIMIT", **overrides):
    root, run_result, review, confirmation, account_path = _sources(tmp_path, order_type)
    result = write_pending_candidate_handoff(
        run_result=overrides.get("run_result", run_result),
        review_artifact=overrides.get("review", review),
        confirmation_intent=overrides.get("confirmation", confirmation),
        output_dir=root / "candidates",
        confirmation_phrase=overrides.get("phrase", PHRASE),
        current_time=overrides.get("now", NOW),
        protected_root=root,
    )
    return root, run_result, review, confirmation, account_path, root / result.artifact_path


def _export(tmp_path: Path, order_type: str = "BUY_LIMIT", output_name: str = "bundle"):
    root, run_result, review, confirmation, account_path, handoff_path = _handoff(
        tmp_path, order_type
    )
    result = export_pending_artifact_bundle(
        candidate_artifact=handoff_path,
        account_context_artifact=account_path,
        output_dir=root / output_name,
        confirmation_phrase=PHRASE,
        current_time=NOW,
        protected_root=root,
    )
    return root, result, root / output_name, handoff_path, account_path


@pytest.mark.parametrize("order_type", SUPPORTED_PENDING_ORDER_TYPES)
def test_supported_pending_type_exports_existing_protected_schema(tmp_path, order_type):
    root, result, bundle, _, _ = _export(tmp_path, order_type)
    request = json.loads((bundle / "controlled-request.json").read_text(encoding="utf-8"))
    assert result.schema_version == PENDING_EXECUTION_REQUEST_VERSION
    assert request["request_version"] == PENDING_EXECUTION_REQUEST_VERSION
    assert result.validation_status == "VALID"
    assert Path(root / result.artifact_path) == bundle


@pytest.mark.parametrize("order_type", ["BUY_STOP_LIMIT", "SELL_STOP_LIMIT"])
def test_stop_limit_preserves_separate_trigger_and_limit_values(tmp_path, order_type):
    _, _, bundle, _, _ = _export(tmp_path, order_type)
    contract = json.loads((bundle / "pending-contract.json").read_text(encoding="utf-8"))
    assert contract["trigger_price"]
    assert contract["limit_price"]
    assert contract["trigger_price"] != contract["limit_price"]
    assert contract["entry_price"] == ""


def test_market_candidate_is_rejected(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path, "BUY")
    with pytest.raises(PendingArtifactExportError, match="PENDING_CANDIDATE_REQUIRED"):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_schema_v1_candidate_is_rejected(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    legacy = replace(run_result, candidate=replace(run_result.candidate, schema_version="autonomous-decision-candidate/v1"))
    with pytest.raises(PendingArtifactExportError, match="PENDING_CANDIDATE_SCHEMA_V2_REQUIRED"):
        write_pending_candidate_handoff(
            run_result=legacy,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_stale_candidate_is_blocked(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    with pytest.raises(PendingArtifactExportError):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW + timedelta(minutes=6),
            protected_root=root,
        )


def test_missing_review_binding_is_blocked(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    review.source_refs = [run_result.candidate.candidate_reference]
    with pytest.raises(PendingArtifactExportError, match="HUMAN_REVIEW_CANDIDATE_BINDING_MISMATCH"):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_missing_account_context_is_blocked(tmp_path):
    root, _, _, _, _, handoff_path = _handoff(tmp_path)
    with pytest.raises(PendingArtifactExportError, match="PROTECTED_ARTIFACT_MISSING_OR_INVALID"):
        export_pending_artifact_bundle(
            candidate_artifact=handoff_path,
            account_context_artifact=root / "missing-account.json",
            output_dir=root / "bundle",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_invalid_candidate_provenance_is_blocked(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    invalid = replace(run_result, candidate=replace(run_result.candidate, provenance_hash="f" * 64))
    with pytest.raises(PendingArtifactExportError):
        write_pending_candidate_handoff(
            run_result=invalid,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


@pytest.mark.parametrize("filename", ["pending-contract.json", "pending-draft.json"])
def test_contract_or_draft_mutation_invalidates_bundle(tmp_path, filename):
    root, _, bundle, _, _ = _export(tmp_path)
    payload = json.loads((bundle / filename).read_text(encoding="utf-8"))
    payload["order_type"] = "SELL_LIMIT"
    (bundle / filename).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PendingArtifactExportError, match="PENDING_ARTIFACT_HASH_MISMATCH"):
        validate_pending_artifact_bundle(bundle, protected_root=root)


def test_missing_symbol_metadata_is_blocked(tmp_path):
    inputs = structured_inputs("BUY_LIMIT")
    inputs = replace(inputs, order_market_snapshot=replace(inputs.order_market_snapshot, tick_size=None))
    root = tmp_path / "protected"
    root.mkdir()
    run_result = service(tmp_path).run_once(inputs, now=NOW)
    review = review_for(run_result.candidate)
    confirmation = confirmation_for(run_result.candidate, review)
    handoff = write_pending_candidate_handoff(
        run_result=run_result,
        review_artifact=review,
        confirmation_intent=confirmation,
        output_dir=root / "candidates",
        confirmation_phrase=PHRASE,
        current_time=NOW,
        protected_root=root,
    )
    account_path = root / "account-context.json"
    account_path.write_text(json.dumps(account_context().as_dict()), encoding="utf-8")
    with pytest.raises(PendingArtifactExportError, match="SYMBOL_METADATA_MISSING_OR_INVALID"):
        export_pending_artifact_bundle(
            candidate_artifact=root / handoff.artifact_path,
            account_context_artifact=account_path,
            output_dir=root / "bundle",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )

def test_candidate_validation_blockers_prevent_export(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    blocked = replace(run_result, validation=replace(run_result.validation, valid=False, issues=("BLOCKED",)))
    with pytest.raises(PendingArtifactExportError, match="CANDIDATE_VALIDATION_BLOCKED"):
        write_pending_candidate_handoff(
            run_result=blocked,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_identical_handoff_and_bundle_export_are_idempotent(tmp_path):
    root, run_result, review, confirmation, account_path, handoff_path = _handoff(tmp_path)
    again = write_pending_candidate_handoff(
        run_result=run_result,
        review_artifact=review,
        confirmation_intent=confirmation,
        output_dir=root / "candidates",
        confirmation_phrase=PHRASE,
        current_time=NOW + timedelta(seconds=1),
        protected_root=root,
    )
    assert again.export_status == "IDEMPOTENT"
    first = export_pending_artifact_bundle(
        candidate_artifact=handoff_path,
        account_context_artifact=account_path,
        output_dir=root / "bundle",
        confirmation_phrase=PHRASE,
        current_time=NOW,
        protected_root=root,
    )
    second = export_pending_artifact_bundle(
        candidate_artifact=handoff_path,
        account_context_artifact=account_path,
        output_dir=root / "bundle",
        confirmation_phrase=PHRASE,
        current_time=NOW + timedelta(seconds=1),
        protected_root=root,
    )
    assert first.export_status == "CREATED"
    assert second.export_status == "IDEMPOTENT"


def test_conflicting_duplicate_handoff_fails_closed(tmp_path):
    root, run_result, review, confirmation, _, _ = _handoff(tmp_path)
    changed_review = replace(review, grade="CHANGED")
    with pytest.raises(PendingArtifactExportError, match="CANDIDATE_HANDOFF_CONFLICT"):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=changed_review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_interrupted_write_leaves_no_valid_bundle(tmp_path, monkeypatch):
    root, _, _, _, account_path, handoff_path = _handoff(tmp_path)
    original = exporter._write_new_file
    calls = {"count": 0}

    def interrupted(path, payload):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated interruption")
        return original(path, payload)

    monkeypatch.setattr(exporter, "_write_new_file", interrupted)
    output = root / "interrupted"
    with pytest.raises(OSError, match="simulated interruption"):
        export_pending_artifact_bundle(
            candidate_artifact=handoff_path,
            account_context_artifact=account_path,
            output_dir=output,
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )
    assert not output.exists()
    assert not (output / "manifest.json").exists()


def test_cli_output_is_redacted(monkeypatch, capsys):
    fake = PendingArtifactExportResult(
        artifact_reference_redacted="abcdef123456...",
        schema_version=PENDING_EXECUTION_REQUEST_VERSION,
        pending_order_family="LIMIT",
        validation_status="VALID",
        blockers=(),
        freshness_status="VALID",
        account_context_match=True,
        export_status="CREATED",
        executable=False,
        order_send_allowed=False,
        artifact_path="acceptance/bundle",
    )
    monkeypatch.setattr(pending_cli, "export_pending_artifact_bundle", lambda **_: fake)
    assert pending_cli.main(
        [
            "--candidate-artifact", "candidate.json",
            "--account-context-artifact", "account.json",
            "--output-dir", "bundle",
        ],
        confirmation_reader=lambda _: PHRASE,
    ) == 0
    output = capsys.readouterr().out
    assert "abcdef123456..." in output
    assert FINGERPRINT not in output
    assert "trigger_price" not in output
    assert "controlled_submission=NOT_CALLED" in output


def test_cli_has_no_individual_trading_parameter_arguments():
    actions = {option for action in pending_cli.build_parser()._actions for option in action.option_strings}
    forbidden = {
        "--entry-price", "--trigger-price", "--limit-price", "--volume",
        "--stop-loss", "--take-profit", "--side", "--order-type",
    }
    assert not actions.intersection(forbidden)


def test_dashboard_refresh_cannot_export_without_button_branch():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_pending_candidate_handoff"
    )
    write_calls = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "write_pending_candidate_handoff"
    ]
    assert len(write_calls) == 1
    button_if = next(node for node in ast.walk(function) if isinstance(node, ast.If) and "st.button" in ast.unparse(node.test))
    assert write_calls[0] in list(ast.walk(button_if))


def test_export_module_has_no_llm_bridge_or_submission_call():
    source = Path(exporter.__file__).read_text(encoding="utf-8")
    assert "controlled-submit" not in source
    assert "controlled-manage" not in source
    assert ".order_send(" not in source
    assert "MetaTrader5" not in source
    assert "llm" not in source.lower()


def test_execution_journal_remains_unchanged(tmp_path):
    journal = tmp_path / "execution.jsonl"
    journal.write_bytes(b"existing-record\n")
    before = journal.read_bytes()
    _export(tmp_path)
    assert journal.read_bytes() == before


def test_generated_artifacts_remain_non_executable(tmp_path):
    _, _, bundle, _, _ = _export(tmp_path)
    contract = json.loads((bundle / "pending-contract.json").read_text(encoding="utf-8"))
    draft = json.loads((bundle / "pending-draft.json").read_text(encoding="utf-8"))
    request = json.loads((bundle / "controlled-request.json").read_text(encoding="utf-8"))
    for payload in (contract, draft, request["approved_semantic_parameters"]):
        assert payload["execution_permission_requested"] is False
        assert payload["executable"] is False
        assert payload["order_send_allowed"] is False
        assert payload["order_sent"] is False
    assert request["execution_permission_requested"] is False
    assert request["pre_submit_validation_valid"] is False


def test_wrong_export_confirmation_is_blocked(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    with pytest.raises(PendingArtifactExportError, match="EXPORT_ONLY_CONFIRMATION_INVALID"):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=root / "candidates",
            confirmation_phrase="wrong",
            current_time=NOW,
            protected_root=root,
        )


def test_protected_output_must_stay_under_ignored_root(tmp_path):
    root, run_result, review, confirmation, _ = _sources(tmp_path)
    with pytest.raises(PendingArtifactExportError, match="OUTPUT_OUTSIDE_PROTECTED_ROOT"):
        write_pending_candidate_handoff(
            run_result=run_result,
            review_artifact=review,
            confirmation_intent=confirmation,
            output_dir=tmp_path / "outside",
            confirmation_phrase=PHRASE,
            current_time=NOW,
            protected_root=root,
        )


def test_manifest_is_written_last_and_validates(tmp_path):
    root, _, bundle, _, _ = _export(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == PENDING_ARTIFACT_BUNDLE_SCHEMA
    assert manifest["validation_status"] == "VALID"
    assert validate_pending_artifact_bundle(bundle, protected_root=root).validation_status == "VALID"
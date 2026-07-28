from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.proposal.models import HumanConfirmedProposalIntent, ProposalIntentJournalRecord


@dataclass
class ProposalBoundaryValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class ProposalBoundaryValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = int(max_payload_chars)

    def validate_intent(self, intent: HumanConfirmedProposalIntent) -> ProposalBoundaryValidationResult:
        issues: list[str] = []
        payload = intent.as_dict()
        if not intent.source_review_artifact_id:
            issues.append("source_review_artifact_id_required")
        if not intent.candidate_reference and not intent.source_dry_run_receipt_id:
            issues.append("source_dry_run_receipt_id_required")
        if not intent.source_refs:
            issues.append("source_refs_required")
        if intent.dry_run_only is not True:
            issues.append("dry_run_only_must_be_true")
        if intent.executable is not False:
            issues.append("executable_must_be_false")
        if intent.proposal_workflow_allowed and intent.executable:
            issues.append("proposal_workflow_must_not_imply_live_execution")
        if intent.candidate_reference:
            issues.extend(_candidate_binding_issues(intent))
            payload = dict(payload)
            payload.pop("order_type", None)
        issues.extend(_forbidden_payload_issues(payload))
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return ProposalBoundaryValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))

    def validate_record(self, record: ProposalIntentJournalRecord) -> ProposalBoundaryValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        if not record.intent_id:
            issues.append("intent_id_required")
        if not record.candidate_reference and not record.dry_run_receipt_id:
            issues.append("dry_run_receipt_id_required")
        if not record.source_refs:
            issues.append("source_refs_required")
        if record.dry_run_only is not True:
            issues.append("dry_run_only_must_be_true")
        if record.executable is not False:
            issues.append("executable_must_be_false")
        if record.candidate_reference:
            issues.extend(_candidate_record_issues(record))
            payload = dict(payload)
            payload.pop("order_type", None)
        issues.extend(_forbidden_payload_issues(payload))
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except Exception:
            issues.append("record_not_json_serializable")
            serialized = ""
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return ProposalBoundaryValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))


def _candidate_binding_issues(intent: HumanConfirmedProposalIntent) -> list[str]:
    issues: list[str] = []
    for name in (
        "candidate_reference",
        "candidate_provenance_hash",
        "candidate_structured_order_hash",
        "account_context_reference",
        "account_fingerprint_hash",
        "order_type",
        "operator_action",
        "confirmation_nonce",
        "confirmation_expires_at",
    ):
        if not str(getattr(intent, name) or "").strip():
            issues.append(name + "_required")
    if not intent.timeframe_profile:
        issues.append("timeframe_profile_required")
    if intent.operator_action == "CONFIRM" and not intent.confirmation_binding_hash:
        issues.append("confirmation_binding_hash_required")
    if intent.operator_action not in {"CONFIRM", "REJECT"}:
        issues.append("operator_action_invalid")
    return issues


def _candidate_record_issues(record: ProposalIntentJournalRecord) -> list[str]:
    issues: list[str] = []
    for name in (
        "candidate_provenance_hash",
        "candidate_structured_order_hash",
        "account_context_reference",
        "account_fingerprint_hash",
        "symbol",
        "broker_symbol",
        "order_type",
        "operator_action",
        "confirmation_nonce",
        "confirmation_timestamp",
        "confirmation_expires_at",
        "record_hash",
    ):
        if not str(getattr(record, name) or "").strip():
            issues.append(name + "_required")
    if not record.timeframe_profile:
        issues.append("timeframe_profile_required")
    if record.operator_action == "CONFIRM" and not record.confirmation_binding_hash:
        issues.append("confirmation_binding_hash_required")
    return issues


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    checks = {
        "buy_marker_present": ["buy"],
        "sell_marker_present": ["sell"],
        "trade_side_marker_present": ["trade_side"],
        "price_or_size_marker_present": ["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"],
        "order_submission_marker_present": ["order" + "_send"],
        "executable_order_marker_present": ["real_order_id", "mt5_order_request", "executable_order"],
        "raw_candle_marker_present": ["raw_candles", "ohlcv_bars"],
        "raw_knowledge_marker_present": ["full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"],
        "account_or_credential_marker_present": ["account_id", "api_key", "password", "secret"],
        "metatrader_marker_present": ["meta" + "trader5"],
        "llm_prompt_marker_present": ["compact_prompt", "llm_prompt"],
    }
    issues: list[str] = []
    for issue, markers in checks.items():
        if any(marker in text for marker in markers):
            issues.append(issue)
    return issues

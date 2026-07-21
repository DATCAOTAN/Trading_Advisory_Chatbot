from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from src.services.trading.execution.adapter_models import SimulatedOrderContract, now_utc_iso
from src.services.trading.execution.adapter_policy import ExecutionAdapterPolicy
from src.services.trading.execution.adapter_validator import ExecutionAdapterContractValidator
from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.models import DryRunExecutionReceipt
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft, ProposalDraftJournalRecord
from src.services.trading.proposal.models import HumanConfirmedProposalIntent


class SimulatedOrderContractBuilder:
    def __init__(
        self,
        policy: ExecutionAdapterPolicy | None = None,
        validator: ExecutionAdapterContractValidator | None = None,
    ):
        self.policy = policy or ExecutionAdapterPolicy.from_config()
        self.validator = validator or ExecutionAdapterContractValidator(max_payload_chars=self.policy.max_payload_chars)

    def build(
        self,
        draft: NonExecutableTradeProposalDraft | None,
        intent: HumanConfirmedProposalIntent | None = None,
        dry_run_receipt: DryRunExecutionReceipt | None = None,
        execution_journal_record: ExecutionJournalRecord | None = None,
        proposal_draft_journal_record: ProposalDraftJournalRecord | None = None,
    ) -> SimulatedOrderContract:
        blockers: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []
        if draft is None:
            draft = _empty_draft()
            if self.policy.require_draft:
                blockers.append("proposal_draft_required")
        if self.policy.require_non_executable_draft and not draft.non_executable:
            blockers.append("draft_must_be_non_executable")
        if draft.executable:
            blockers.append("draft_executable_true")
        if self.policy.require_source_refs and not draft.source_refs:
            blockers.append("source_refs_required")
        if _age_seconds(draft.created_at) > self.policy.contract_ttl_seconds:
            blockers.append("proposal_draft_expired")
            status = "EXPIRED"
        elif draft.status in {"BLOCKED", "INVALID"}:
            status = "BLOCKED"
            reasons.append(f"draft_status_{draft.status.lower()}")
        elif draft.status == "EXPIRED":
            status = "EXPIRED"
        elif draft.status == "DUPLICATE":
            status = "DUPLICATE"
        elif blockers:
            status = "INVALID"
        else:
            status = "CREATED"
            reasons.append("simulated_contract_created")
        artifact_hash = _artifact_hash(draft)
        idempotency_key = _idempotency_key(draft.draft_id, artifact_hash, draft.mode, draft.symbol, draft.created_at)
        contract = SimulatedOrderContract(
            contract_id=_contract_id(draft.draft_id, artifact_hash),
            created_at=now_utc_iso(),
            mode=draft.mode,
            symbol=draft.symbol,
            broker_symbol=draft.broker_symbol,
            adapter_type="SIMULATED",
            contract_status=status,
            simulated_only=True,
            executable=False,
            source_draft_id=draft.draft_id,
            source_draft_status=draft.status,
            source_intent_id=draft.source_intent_id or (intent.intent_id if intent else ""),
            source_review_artifact_id=draft.source_review_artifact_id,
            source_dry_run_receipt_id=dry_run_receipt.receipt_id if dry_run_receipt else "",
            source_execution_journal_record_id=execution_journal_record.journal_record_id if execution_journal_record else "",
            source_proposal_draft_journal_record_id=(
                proposal_draft_journal_record.journal_record_id if proposal_draft_journal_record else ""
            ),
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            non_executable_proposal=True,
            readiness_action=draft.readiness_action,
            review_status=draft.review_status,
            proposal_boundary_status=intent.proposal_boundary_status if intent else "",
            draft_status=draft.status,
            blockers=_dedupe_strings(blockers + draft.blockers),
            warnings=_dedupe_strings(warnings + draft.warnings),
            reasons=_dedupe_strings(reasons),
            source_refs=_dedupe_strings(draft.source_refs),
        )
        contract.payload_size_chars = len(json.dumps(contract.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_contract(contract)
        if not validation.passed and contract.contract_status == "CREATED":
            contract.contract_status = "INVALID"
            contract.blockers.extend(validation.issues)
            contract.blockers = _dedupe_strings(contract.blockers)
            contract.payload_size_chars = len(json.dumps(contract.as_dict(), ensure_ascii=False, sort_keys=True))
        return contract


def _empty_draft() -> NonExecutableTradeProposalDraft:
    return NonExecutableTradeProposalDraft(
        draft_id="",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="",
        broker_symbol="",
        status="INVALID",
        source_refs=[],
    )


def _age_seconds(created_at: str) -> float:
    try:
        value = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds())
    except Exception:
        return 999999.0


def _artifact_hash(draft: NonExecutableTradeProposalDraft) -> str:
    payload = draft.as_dict()
    payload.pop("payload_size_chars", None)
    payload.pop("created_at", None)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotency_key(draft_id: str, artifact_hash: str, mode: str, symbol: str, created_at: str) -> str:
    raw = f"{draft_id}|{artifact_hash}|{mode}|{symbol}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _contract_id(draft_id: str, artifact_hash: str) -> str:
    digest = hashlib.sha256(f"{draft_id}|{artifact_hash}".encode("utf-8")).hexdigest()[:16]
    return f"simulated_contract_{digest}"


def _dedupe_strings(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            value = item
        else:
            try:
                value = json.dumps(item, ensure_ascii=False, sort_keys=True)
            except Exception:
                value = str(item)
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

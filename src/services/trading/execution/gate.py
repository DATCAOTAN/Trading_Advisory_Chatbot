from __future__ import annotations

import json
from datetime import datetime, timezone

from src.services.trading.execution.idempotency import IdempotencyKeyBuilder, InMemoryIdempotencyStore, artifact_hash
from src.services.trading.execution.kill_switch import KillSwitchState
from src.services.trading.execution.models import EXECUTION_MODES, ExecutionGateDecision, now_utc_iso
from src.services.trading.execution.policies import ExecutionGatePolicy
from src.services.trading.execution.validator import ExecutionGateValidator
from src.services.trading.review.models import HumanReviewArtifact, ReviewCard
from src.services.trading.review.validator import HumanReviewArtifactValidator


class ExecutionGate:
    def __init__(
        self,
        policy: ExecutionGatePolicy | None = None,
        kill_switch: KillSwitchState | None = None,
        idempotency_store: InMemoryIdempotencyStore | None = None,
        validator: ExecutionGateValidator | None = None,
    ):
        self.policy = policy or ExecutionGatePolicy.from_config()
        self.kill_switch = kill_switch or KillSwitchState(enabled=self.policy.kill_switch)
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self.validator = validator or ExecutionGateValidator(max_payload_chars=self.policy.max_payload_chars)
        self.key_builder = IdempotencyKeyBuilder()

    def evaluate(self, artifact: HumanReviewArtifact, card: ReviewCard | None = None, mode: str | None = None) -> ExecutionGateDecision:
        selected_mode = (mode or self.policy.mode or "REVIEW_ONLY").strip().upper()
        created_at = now_utc_iso()
        digest = artifact_hash(artifact)
        age_seconds = _artifact_age_seconds(artifact.created_at)
        idempotency_key = self.key_builder.build(artifact.artifact_id, digest, selected_mode, artifact.symbol, artifact.created_at)
        blockers: list[str] = []
        warnings: list[str] = []
        action = "UNKNOWN"
        allowed = False
        reason = ""

        artifact_validation = HumanReviewArtifactValidator(max_payload_chars=self.policy.max_payload_chars).validate(artifact)
        if selected_mode not in EXECUTION_MODES:
            action = "EXECUTION_DISABLED"
            reason = "execution_mode_invalid"
            blockers.append("execution_mode_invalid")
        elif selected_mode in {"DISABLED", "AUTONOMOUS_DISABLED", "HUMAN_CONFIRMED_LIVE_RESERVED"}:
            action = "EXECUTION_DISABLED"
            reason = "live_execution_disabled"
            blockers.append("live_execution_disabled")
        elif not self.policy.dry_run_enabled:
            action = "EXECUTION_DISABLED"
            reason = "dry_run_disabled"
            blockers.append("dry_run_disabled")
        elif not artifact_validation.passed:
            action = "INVALID_ARTIFACT"
            reason = "review_artifact_invalid"
            blockers.extend(artifact_validation.issues)
        elif self.policy.require_source_refs and not artifact.source_refs:
            action = "INVALID_ARTIFACT"
            reason = "source_refs_required"
            blockers.append("source_refs_required")
        elif age_seconds > self.policy.artifact_ttl_seconds:
            action = "ARTIFACT_EXPIRED"
            reason = "review_artifact_expired"
            blockers.append("review_artifact_expired")
        elif self.policy.idempotency_enabled and self.idempotency_store.seen(idempotency_key):
            action = "DUPLICATE_ARTIFACT"
            reason = "duplicate_review_artifact"
            blockers.append("duplicate_review_artifact")
        elif self.idempotency_store.dry_run_count >= self.policy.max_dry_runs_per_session:
            action = "BLOCKED"
            reason = "dry_run_session_limit_exceeded"
            blockers.append("dry_run_session_limit_exceeded")
        elif self.policy.require_review_ready and artifact.review_status != "READY_FOR_REVIEW":
            action = "BLOCKED"
            reason = f"review_status_{artifact.review_status.lower()}"
            blockers.append(f"review_status_{artifact.review_status.lower()}")
        elif self.policy.block_on_blockers and artifact.blockers:
            action = "BLOCKED"
            reason = "artifact_blockers_present"
            blockers.append("artifact_blockers_present")
        elif self.policy.block_on_warnings and artifact.warnings:
            action = "BLOCKED"
            reason = "artifact_warnings_present"
            blockers.append("artifact_warnings_present")
        else:
            action = "ALLOW_DRY_RUN"
            allowed = True
            reason = "dry_run_gate_passed"

        if self.kill_switch.enabled:
            warnings.append(f"kill_switch_active:{self.kill_switch.reason}")
        if card and card.status_label != artifact.review_status:
            warnings.append("review_card_status_mismatch")

        decision = ExecutionGateDecision(
            gate_decision_id=f"execution_gate_{digest[:16]}",
            created_at=created_at,
            mode=selected_mode,
            symbol=artifact.symbol,
            broker_symbol=artifact.broker_symbol,
            action=action,
            allowed=allowed,
            dry_run_only=True,
            reason=reason,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            artifact_id=artifact.artifact_id,
            artifact_hash=digest,
            artifact_age_seconds=age_seconds,
            source_review_artifact_id=artifact.artifact_id,
            source_readiness_decision_id=artifact.source_readiness_decision_id,
            source_refs=list(dict.fromkeys(artifact.source_refs)),
        )
        decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_decision(decision)
        if not validation.passed:
            decision.action = "INVALID_ARTIFACT"
            decision.allowed = False
            decision.blockers.extend(validation.issues)
            decision.blockers = list(dict.fromkeys(decision.blockers))
            decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
        if decision.action == "ALLOW_DRY_RUN" and self.policy.idempotency_enabled:
            self.idempotency_store.record(idempotency_key)
        return decision


def _artifact_age_seconds(created_at: str) -> float:
    try:
        value = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds())
    except Exception:
        return 999999.0

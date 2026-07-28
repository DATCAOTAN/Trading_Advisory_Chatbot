from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)
from src.ui.autonomous_candidate_review import store_autonomous_decision_run_result


AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY = "autonomous_candidate_generation_active"
AUTONOMOUS_GENERATION_REQUEST_SESSION_KEY = "autonomous_candidate_generation_request"


@dataclass(frozen=True)
class OperatorCandidateGenerationOutcome:
    status: str
    blocker: str = ""
    candidate_reference: str = ""
    intent: str = ""
    validation_valid: bool = False
    orchestrator_called: bool = False
    stored: bool = False


class OperatorCandidateGenerationController:
    def __init__(self, input_assembler: Any, decision_orchestrator: Any | None = None) -> None:
        self.input_assembler = input_assembler
        self.decision_orchestrator = decision_orchestrator or AutonomousDecisionOrchestrator()

    def generate(
        self,
        session_state: Any,
        request_id: str,
        *,
        symbol: str | None = None,
        timeframes: Iterable[str] | None = None,
    ) -> OperatorCandidateGenerationOutcome:
        normalized_request = str(request_id or "").strip()
        if not normalized_request:
            return OperatorCandidateGenerationOutcome("BLOCKED", "GENERATION_REQUEST_MISSING")
        if session_state.get(AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY) is True:
            return OperatorCandidateGenerationOutcome(
                "DUPLICATE_IGNORED", "GENERATION_ALREADY_ACTIVE"
            )
        if session_state.get(AUTONOMOUS_GENERATION_REQUEST_SESSION_KEY) == normalized_request:
            return OperatorCandidateGenerationOutcome(
                "DUPLICATE_IGNORED", "GENERATION_REQUEST_ALREADY_HANDLED"
            )

        session_state[AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY] = True
        session_state[AUTONOMOUS_GENERATION_REQUEST_SESSION_KEY] = normalized_request
        try:
            build_kwargs = {}
            if symbol is not None:
                build_kwargs["symbol"] = symbol
            if timeframes is not None:
                build_kwargs["timeframes"] = timeframes
            inputs = self.input_assembler.build(**build_kwargs)
            run_result = self.decision_orchestrator.run_once(inputs)
            if not isinstance(run_result, AutonomousDecisionRunResult):
                return OperatorCandidateGenerationOutcome(
                    "BLOCKED", "INVALID_ORCHESTRATOR_RESULT", orchestrator_called=True
                )
            if not run_result.validation.valid or not run_result.persistence_safe:
                blocker = run_result.journal_warning or (
                    run_result.validation.issues[0]
                    if run_result.validation.issues
                    else "RESULT_INVALID"
                )
                return OperatorCandidateGenerationOutcome(
                    "BLOCKED",
                    blocker,
                    intent=run_result.candidate.intent,
                    validation_valid=run_result.validation.valid,
                    orchestrator_called=True,
                )
            store_autonomous_decision_run_result(session_state, run_result)
            return OperatorCandidateGenerationOutcome(
                "GENERATED",
                candidate_reference=run_result.candidate.candidate_reference,
                intent=run_result.candidate.intent,
                validation_valid=True,
                orchestrator_called=True,
                stored=True,
            )
        except OperatorCandidateInputError as exc:
            if exc.blockers == ("STRUCTURED_PROPOSAL_NOT_AVAILABLE",):
                return OperatorCandidateGenerationOutcome(
                    "NO_ACTION", "STRUCTURED_PROPOSAL_NOT_AVAILABLE"
                )
            return OperatorCandidateGenerationOutcome("BLOCKED", str(exc))
        except Exception:
            return OperatorCandidateGenerationOutcome(
                "BLOCKED", "CANDIDATE_GENERATION_FAILED"
            )
        finally:
            session_state[AUTONOMOUS_GENERATION_ACTIVE_SESSION_KEY] = False

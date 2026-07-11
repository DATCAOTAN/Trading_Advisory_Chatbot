from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.decision_context import DecisionContext
from src.services.orchestrator_contract import OrchestratorOutput


@dataclass
class ResponseGateDecision:
    sufficiency: str
    answer_type: str
    normal_synthesis_allowed: bool
    message: str = ""
    missing_context: List[str] = field(default_factory=list)
    confidence_ceiling: str = "low"
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sufficiency": self.sufficiency,
            "answer_type": self.answer_type,
            "normal_synthesis_allowed": self.normal_synthesis_allowed,
            "message": self.message,
            "missing_context": list(self.missing_context),
            "confidence_ceiling": self.confidence_ceiling,
            "warnings": list(self.warnings),
        }


class ResponseGate:
    """Central contract that prevents unsupported synthesis when required context is missing."""

    BLOCKING_STATUSES = {"INSUFFICIENT", "BLOCKED"}

    @classmethod
    def evaluate(
        cls,
        decision_context: DecisionContext,
        orchestrator_output: Optional[OrchestratorOutput] = None,
    ) -> ResponseGateDecision:
        sufficiency = cls._sufficiency_status(decision_context)
        evidence_sufficiency = cls._evidence_sufficiency_status(decision_context)
        answer_type = orchestrator_output.answer_type if orchestrator_output else "insufficient_context"
        missing = cls._missing_required(decision_context)
        confidence_ceiling = cls._confidence_ceiling(decision_context)
        blocked = (
            sufficiency in cls.BLOCKING_STATUSES
            or evidence_sufficiency in cls.BLOCKING_STATUSES
            or answer_type == "insufficient_context"
        )
        if blocked:
            decision = ResponseGateDecision(
                sufficiency=sufficiency,
                answer_type="insufficient_context",
                normal_synthesis_allowed=False,
                message=cls._bounded_message(decision_context, missing, evidence_sufficiency=evidence_sufficiency),
                missing_context=missing,
                confidence_ceiling="low",
                warnings=list(decision_context.warnings),
            )
        else:
            decision = ResponseGateDecision(
                sufficiency=sufficiency,
                answer_type=answer_type,
                normal_synthesis_allowed=True,
                missing_context=missing,
                confidence_ceiling=confidence_ceiling,
                warnings=list(decision_context.warnings),
            )
        print(
            "[ResponseGate] "
            f"sufficiency={decision.sufficiency} "
            f"evidence_sufficiency={evidence_sufficiency} "
            f"normal_synthesis={str(decision.normal_synthesis_allowed).lower()} "
            f"answer_type={decision.answer_type}"
        )
        return decision

    @staticmethod
    def _sufficiency_status(ctx: DecisionContext) -> str:
        sufficiency = ctx.sufficiency or {}
        return str(sufficiency.get("status") or "UNKNOWN").upper()

    @staticmethod
    def _confidence_ceiling(ctx: DecisionContext) -> str:
        sufficiency = ctx.sufficiency or {}
        evidence = ctx.evidence_sufficiency or {}
        return str(evidence.get("confidence_ceiling") or sufficiency.get("confidence_ceiling") or ctx.confidence_ceiling or "low")

    @staticmethod
    def _evidence_sufficiency_status(ctx: DecisionContext) -> str:
        evidence = ctx.evidence_sufficiency or {}
        return str(evidence.get("status") or "UNKNOWN").upper()

    @staticmethod
    def _missing_required(ctx: DecisionContext) -> List[str]:
        sufficiency = ctx.sufficiency or {}
        missing = list(ctx.missing_required_context or [])
        missing.extend(str(item) for item in sufficiency.get("missing_required", []) if item not in missing)
        return [item for item in missing if item]

    @staticmethod
    def _bounded_message(ctx: DecisionContext, missing: List[str], evidence_sufficiency: str = "UNKNOWN") -> str:
        query_plan = ctx.query_plan or {}
        primary_intent = str(query_plan.get("primary_intent") or "")
        missing_text = ", ".join(_friendly_context_name(item) for item in missing) or "required evidence"
        evidence_missing = []
        if ctx.evidence_sufficiency:
            evidence_missing = list(ctx.evidence_sufficiency.get("missing_roles", []) or [])
        if evidence_sufficiency in {"INSUFFICIENT", "BLOCKED"}:
            roles = ", ".join(evidence_missing) or "useful direct evidence"
            return (
                "He thong da tim thay nguon tuong thich, nhung chua co du doan bang chung truc tiep de tra loi dang tin cay. "
                f"Vai tro evidence con thieu: {roles}. "
                "Vi vay he thong khong suy dien noi dung tu tieu de, metadata, hoac nguon gan dung."
            )
        if primary_intent == "book_concept_explanation":
            return (
                "Kho tri thuc hien tai chua tra ve nguon tuong thich de gan cau tra loi cho tac gia/sach duoc hoi. "
                f"Thieu ngu canh bat buoc: {missing_text}. "
                "Vi vay he thong khong the trinh bay quan diem cu the cua nguon nay mot cach dang tin cay."
            )
        if primary_intent in {"macro_report_summary", "macro_market_impact"}:
            return (
                "Chua du bang chung can thiet tu bao cao/su kien lien quan de tra loi co can cu. "
                f"Thieu ngu canh bat buoc: {missing_text}. "
                "He thong se khong suy dien them so lieu, tac dong thi truong, hoac nguon tham chieu khi bang chung chua du."
            )
        if primary_intent in {"market_state_analysis", "trade_opportunity_analysis", "position_sizing"}:
            return (
                "Chua du du lieu bat buoc de danh gia trang thai thi truong/rui ro hien tai. "
                f"Thieu ngu canh bat buoc: {missing_text}. "
                "He thong khong dua ra nhan dinh thi truong hoac kich thuoc vi the khi du lieu can thiet chua san sang."
            )
        return (
            "Chua du ngu canh bat buoc de tra loi co can cu. "
            f"Thieu ngu canh bat buoc: {missing_text}."
        )


def _friendly_context_name(value: str) -> str:
    text = str(value or "").strip()
    if ":" not in text:
        return text.replace("_", " ")
    capability, target = text.split(":", 1)
    labels = {
        "official_report": "official report",
        "static_knowledge": "book/source evidence",
        "market_knowledge": "market knowledge",
        "economic_event": "economic event data",
        "market_snapshot": "market snapshot",
        "ohlcv": "OHLCV data",
        "technical_snapshot": "technical snapshot",
        "account_state": "account state",
        "instrument_spec": "instrument specification",
        "stop_distance": "stop distance",
        "risk_limit": "risk limit",
    }
    return f"{labels.get(capability, capability.replace('_', ' '))} ({target})"

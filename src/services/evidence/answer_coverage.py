from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import re
import unicodedata

from src.services.evidence.coverage_requirements import CoverageRequirementPlanner


@dataclass
class AnswerCoverageValidationResult:
    status: str
    covered_topics: List[str] = field(default_factory=list)
    missing_topics: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    warnings: List[str] = field(default_factory=list)
    uncertain_topics: List[str] = field(default_factory=list)
    partial_topics: List[str] = field(default_factory=list)
    topic_statuses: Dict[str, str] = field(default_factory=dict)
    topic_confidences: Dict[str, float] = field(default_factory=dict)
    topic_reasons: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "covered_topics": list(self.covered_topics),
            "missing_topics": list(self.missing_topics),
            "coverage_ratio": self.coverage_ratio,
            "warnings": list(self.warnings),
            "uncertain_topics": list(self.uncertain_topics),
            "partial_topics": list(self.partial_topics),
            "topic_statuses": dict(self.topic_statuses),
            "topic_confidences": dict(self.topic_confidences),
            "topic_reasons": dict(self.topic_reasons),
        }


class AnswerCoverageValidator:
    """Validates whether the final answer covers the AnswerContract topics."""

    @staticmethod
    def evaluate(answer_text: str, required_topics: List[str]) -> AnswerCoverageValidationResult:
        if not required_topics:
            return AnswerCoverageValidationResult(status="PASS", coverage_ratio=1.0)

        covered = set()
        missing = set()
        uncertain = set()
        partial = set()
        topic_statuses: Dict[str, str] = {}
        topic_confidences: Dict[str, float] = {}
        topic_reasons: Dict[str, str] = {}

        normalized_text = AnswerCoverageValidator._normalize(answer_text)

        semantic_required = [t for t in required_topics if t != "source_used"]
        for topic in semantic_required:
            status, confidence, reason = AnswerCoverageValidator._check_topic(topic, normalized_text)
            topic_statuses[topic] = status
            topic_confidences[topic] = confidence
            topic_reasons[topic] = reason
            print(
                f"[AnswerCoverageTopic] task_id=validation topic={topic} "
                f"status={status} confidence={confidence:.2f} reason={reason}"
            )

            if status == "COVERED":
                covered.add(topic)
            elif status == "PARTIAL":
                partial.add(topic)
                covered.add(topic)  # Backward-compatible: partial topics are visible in covered_topics.
            elif status == "UNCERTAIN":
                uncertain.add(topic)
                covered.add(topic)  # Backward-compatible with earlier ratio behavior.
            else:
                missing.add(topic)

        denominator = len(semantic_required)
        weighted = len([t for t in covered if t not in uncertain and t not in partial])
        weighted += 0.65 * len(partial)
        weighted += 0.5 * len(uncertain)
        coverage_ratio = weighted / denominator if denominator else 1.0

        warnings = []
        if missing:
            warnings.append(f"Missing required contract topics: {', '.join(sorted(missing))}")
        if partial:
            warnings.append(f"Partial coverage for topics: {', '.join(sorted(partial))}")
        if uncertain:
            warnings.append(f"Uncertain coverage for topics: {', '.join(sorted(uncertain))}")

        status = "PASS" if not missing and not partial and not uncertain else "WARN"
        return AnswerCoverageValidationResult(
            status=status,
            covered_topics=sorted(covered),
            missing_topics=sorted(missing),
            coverage_ratio=coverage_ratio,
            warnings=warnings,
            uncertain_topics=sorted(uncertain),
            partial_topics=sorted(partial),
            topic_statuses=topic_statuses,
            topic_confidences=topic_confidences,
            topic_reasons=topic_reasons,
        )

    @staticmethod
    def _check_topic(topic: str, text: str) -> Tuple[str, float, str]:
        if topic == "short_conclusion":
            if AnswerCoverageValidator._has_any(
                text,
                ["ket luan", "tom lai", "nhin chung", "conclusion", "summary", "tong ket", "in short"],
            ):
                return "COVERED", 0.9, "closing_section_detected"
            return "MISSING", 0.1, "no_structural_match"

        if topic == "source_used":
            return "COVERED", 1.0, "ignored_in_semantic_validation"

        if topic == "short_interpretation":
            return AnswerCoverageValidator._check_short_interpretation(text)
        if topic.startswith("event_state"):
            return AnswerCoverageValidator._check_event_state(topic, text)
        if topic == "confirmation_or_invalidation":
            return AnswerCoverageValidator._check_confirmation_or_invalidation(text)

        definition = CoverageRequirementPlanner.topic_definition(topic)
        answer_signals = [
            AnswerCoverageValidator._normalize(sig)
            for sig in definition.answer_signals
            if str(sig or "").strip()
        ]

        if answer_signals:
            match_count = sum(1 for sig in answer_signals if sig and sig in text)
            if match_count >= 2:
                return "COVERED", 0.85, "semantic_match_strong"
            if match_count == 1:
                return "UNCERTAIN", 0.5, "semantic_match_weak"
            return "MISSING", 0.2, "no_semantic_match"

        literal = AnswerCoverageValidator._normalize(topic.replace("_", " "))
        if literal and literal in text:
            return "UNCERTAIN", 0.5, "fallback_literal_match"
        return "MISSING", 0.1, "unknown_topic"

    @staticmethod
    def _check_short_interpretation(text: str) -> Tuple[str, float, str]:
        synthesis_patterns = [
            r"\b(growth|increase|inflation|pressure|momentum)\b.{0,45}\b(slowed|accelerated|cooled|weakened|persistent|mixed)\b",
            r"\b(slowed|accelerated|cooled|weakened|persistent|mixed)\b.{0,45}\b(compared|overall|suggest|imply|indicate|pressure|momentum)\b",
            r"\b(rose|increased)\b.{0,45}\b(while|but|whereas)\b.{0,45}\b(fell|declined|decreased)\b",
            r"\b(some|certain)\b.{0,35}\b(rose|increased)\b.{0,55}\b(other|others)\b.{0,35}\b(fell|declined|decreased)\b",
            r"\bcho thay\b.{0,55}\b(ha nhiet|cham lai|dai dang|khong dong deu|ap luc)\b",
            r"\b(toc do tang)\b.{0,35}\b(cham lai|nhanh hon|tang toc)\b",
            r"\b(ap luc)\b.{0,45}\b(dai dang|ha nhiet|giam bot|van cao)\b",
            r"\b(dien bien|cac nhom|thanh phan)\b.{0,45}\b(khong dong deu|phan hoa|lan lon)\b",
            r"\b(mot so nhom)\b.{0,45}\b(tang)\b.{0,65}\b(nhom khac|cac nhom khac)\b.{0,45}\b(giam)\b",
        ]
        if AnswerCoverageValidator._matches_any(text, synthesis_patterns):
            return "COVERED", 0.86, "comparative_report_synthesis_detected"

        synthesis_terms = [
            "cho thay", "suggest", "imply", "indicate", "overall", "nhin chung",
            "ha nhiet", "cooling", "dai dang", "persistent", "khong dong deu",
            "mixed", "cham lai", "accelerated", "tang toc",
        ]
        numeric_or_report_terms = [
            "cpi", "inflation", "bao cao", "report", "percent", "%", "so lieu",
            "actual", "previous", "forecast", "thuc te", "ky truoc", "du bao",
        ]
        semantic_hits = sum(1 for term in synthesis_terms if term in text)
        raw_hits = sum(1 for term in numeric_or_report_terms if term in text)
        if semantic_hits >= 2:
            return "COVERED", 0.8, "interpretive_terms_detected"
        if semantic_hits == 1 and raw_hits:
            return "UNCERTAIN", 0.55, "single_interpretive_signal_with_report_context"
        if raw_hits >= 2:
            return "PARTIAL", 0.45, "raw_report_state_without_clear_synthesis"
        return "MISSING", 0.15, "no_report_interpretation_detected"

    @staticmethod
    def _check_event_state(topic: str, text: str) -> Tuple[str, float, str]:
        actual = AnswerCoverageValidator._has_any(
            text,
            ["actual", "reported", "release showed", "thuc te", "ket qua", "cong bo", "so lieu", "du lieu"],
        ) or AnswerCoverageValidator._has_percent_or_number_near(text, ["cpi", "inflation", "lam phat", "core"])
        previous = AnswerCoverageValidator._has_any(
            text,
            ["previous", "prior", "last month", "last period", "ky truoc", "truoc do", "thang truoc", "ky lien truoc"],
        )
        forecast = AnswerCoverageValidator._has_any(
            text,
            ["forecast", "expected", "consensus", "du bao", "ky vong", "thi truong du kien"],
        )
        surprise = AnswerCoverageValidator._has_any(
            text,
            ["surprise", "above expectations", "below expectations", "higher than expected", "lower than expected",
             "bat ngo", "cao hon du bao", "thap hon du bao", "vuot du bao", "kem du bao"],
        )
        period = AnswerCoverageValidator._has_any(
            text,
            ["period", "month", "year", "release", "thang", "nam", "ky bao cao", "moi nhat", "cong bo"],
        )
        surprise_mode = "surprise" in topic or "forecast" in topic
        if surprise_mode:
            required_fields = ["actual", "forecast", "previous"]
            missing = [
                field
                for field, present in {"actual": actual, "forecast": forecast, "previous": previous}.items()
                if not present
            ]
            if not missing:
                print(
                    "[EventStateCoverage] actual=true previous=true forecast=true surprise="
                    f"{str(surprise).lower()} required_fields={required_fields} status=COVERED"
                )
                return "COVERED", 0.9, "actual_forecast_previous_present"
            status = "PARTIAL" if len(missing) < len(required_fields) else "MISSING"
            print(
                f"[EventStateCoverage] actual={str(actual).lower()} previous={str(previous).lower()} "
                f"forecast={str(forecast).lower()} surprise={str(surprise).lower()} "
                f"required_fields={required_fields} status={status} missing={missing}"
            )
            return status, 0.65 if status == "PARTIAL" else 0.2, "surprise_event_state_fields_missing:" + ",".join(missing)

        required_fields = ["reported_or_actual_state", "comparison_or_period"]
        has_comparison_or_period = previous or forecast or surprise or period
        if actual and has_comparison_or_period:
            print(
                f"[EventStateCoverage] actual=true previous={str(previous).lower()} "
                f"forecast={str(forecast).lower()} surprise={str(surprise).lower()} "
                f"required_fields={required_fields} status=COVERED"
            )
            return "COVERED", 0.84, "minimum_event_state_present"
        if actual or has_comparison_or_period:
            print(
                f"[EventStateCoverage] actual={str(actual).lower()} previous={str(previous).lower()} "
                f"forecast={str(forecast).lower()} surprise={str(surprise).lower()} "
                f"required_fields={required_fields} status=PARTIAL"
            )
            return "PARTIAL", 0.62, "event_state_partially_present"
        if AnswerCoverageValidator._has_any(text, ["cpi", "nfp", "gdp", "fomc", "event", "report", "bao cao", "su kien"]):
            print(
                f"[EventStateCoverage] actual=false previous=false forecast=false surprise=false "
                f"required_fields={required_fields} status=UNCERTAIN"
            )
            return "UNCERTAIN", 0.5, "event_named_without_required_state"
        print(
            f"[EventStateCoverage] actual=false previous=false forecast=false surprise=false "
            f"required_fields={required_fields} status=MISSING"
        )
        return "MISSING", 0.15, "event_state_not_detected"

    @staticmethod
    def _check_confirmation_or_invalidation(text: str) -> Tuple[str, float, str]:
        conditional = AnswerCoverageValidator._has_any(
            text,
            [
                "if", "when", "unless", "as long as", "provided that",
                "neu", "khi", "tru khi", "trong truong hop", "neu nhu",
            ],
        )
        observable = AnswerCoverageValidator._has_any(
            text,
            [
                "break", "breakout", "above", "below", "hold", "fails to hold",
                "support", "resistance", "yield", "dxy", "dollar", "reaction",
                "strengthens", "weakens", "level", "close above", "close below",
                "pha", "pha len", "pha xuong", "vuot", "tren", "duoi",
                "giu", "ho tro", "khang cu", "loi suat", "dong usd",
                "phan ung", "manh len", "suy yeu", "dong cua",
            ],
        )
        confirm_or_invalidate = AnswerCoverageValidator._has_any(
            text,
            [
                "confirm", "confirmed", "confirmation", "invalidate", "invalidated",
                "weaken the thesis", "strengthen the thesis", "risk to the scenario",
                "xac nhan", "vo hieu", "phu nhan", "lam manh", "lam yeu",
                "cung co", "pha vo kich ban", "lam mat hieu luc",
            ],
        )
        vague_watch = AnswerCoverageValidator._matches_any(
            text,
            [
                r"\b(watch|monitor|observe)\b.{0,35}\b(market|reaction|carefully)\b",
                r"\b(theo doi)\b.{0,45}\b(thi truong|can than|phan ung)\b",
            ],
        )
        if conditional and observable and (confirm_or_invalidate or "scenario" in text or "kich ban" in text):
            return "COVERED", 0.86, "observable_scenario_conditions_detected"
        if conditional and observable:
            return "PARTIAL", 0.68, "observable_condition_without_explicit_scenario_link"
        if vague_watch:
            return "UNCERTAIN", 0.5, "vague_follow_up_without_observable_condition"
        if confirm_or_invalidate or observable:
            return "PARTIAL", 0.6, "scenario_signal_without_condition_structure"
        return "MISSING", 0.15, "no_confirmation_or_invalidation_detected"

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFD", str(text or ""))
        value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
        value = value.replace("đ", "d").replace("Đ", "D").lower()
        value = re.sub(r"\s+", " ", value)
        return value

    @staticmethod
    def _has_any(text: str, terms: List[str]) -> bool:
        return any(AnswerCoverageValidator._normalize(term) in text for term in terms if term)

    @staticmethod
    def _matches_any(text: str, patterns: List[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _has_percent_or_number_near(text: str, anchors: List[str]) -> bool:
        for anchor in anchors:
            anchor_norm = AnswerCoverageValidator._normalize(anchor)
            if not anchor_norm:
                continue
            pattern_a = rf"{re.escape(anchor_norm)}.{{0,45}}(\d+(?:[.,]\d+)?\s?%|\d+(?:[.,]\d+)?)"
            pattern_b = rf"(\d+(?:[.,]\d+)?\s?%|\d+(?:[.,]\d+)?).{{0,45}}{re.escape(anchor_norm)}"
            if re.search(pattern_a, text) or re.search(pattern_b, text):
                return True
        return False

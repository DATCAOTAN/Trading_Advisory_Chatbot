from dataclasses import dataclass, field
from typing import Dict, Any, List, Set, Optional

from src.services.evidence.coverage_requirements import CoverageRequirementSet, CoverageRequirement
from src.services.evidence.evidence_pipeline import EvidenceBundle, EvidenceItem

@dataclass
class EvidenceTopicAttributionResult:
    evidence_id: str
    covered_topics: List[str]
    topic_scores: Dict[str, float]
    attribution_confidence: str
    attribution_reasons: Dict[str, str]

class EvidenceTopicAttributor:
    @staticmethod
    def attribute(item: EvidenceItem, req_set: CoverageRequirementSet) -> EvidenceTopicAttributionResult:
        text = str(item.content).lower()
        title = str(item.source_title).lower()
        
        covered = set()
        scores = {}
        reasons = {}
        
        all_reqs = req_set.required_topics + req_set.optional_topics
        
        for req in all_reqs:
            score = 0.0
            
            # Base text matching using semantic signals
            if any(sig.lower() in text for sig in req.semantic_signals):
                score += 0.6
                reasons[req.topic_role] = "semantic_signal_match"
                
            if any(sig.lower() in text for sig in req.evidence_signals):
                score += 0.5
                reasons[req.topic_role] = "evidence_signal_match"
                
            if req.topic_role in {"important_components", "supporting_details", "main_ideas"} and len(text) > 300:
                score += 0.4
                reasons[req.topic_role] = "length_heuristic"
                
            if item.evidence_type == "official_report_passage" and req.topic_role in {"headline_findings", "official_source_context"}:
                if "report" in title or "release" in title:
                    score += 0.7
                    reasons[req.topic_role] = "report_metadata_match"
                    
            if item.evidence_type in {"market_snapshot", "ohlcv_summary", "technical_snapshot"} and req.topic_role in {"current_market_context", "current_state", "recent_market_behavior"}:
                dynamic_score, dynamic_reason = EvidenceTopicAttributor._dynamic_market_topic_score(item, req.topic_role)
                if dynamic_score:
                    score += dynamic_score
                    reasons[req.topic_role] = dynamic_reason

            if item.evidence_type == "economic_event_record" and req.topic_role in {"event_state", "report_period"}:
                score += 0.8
                reasons[req.topic_role] = "event_data_type_match"

            if item.evidence_type == "economic_event_record" and req.topic_role in {"macro_event_context", "main_drivers"}:
                score += 0.65
                reasons[req.topic_role] = "macro_event_driver_context"

            if item.evidence_type == "technical_snapshot" and req.topic_role in {"technical_context", "confirmation_or_risk_factors"}:
                score += 0.65
                reasons[req.topic_role] = "technical_risk_context"

            if item.evidence_type == "market_commentary_passage" and req.topic_role in {"main_drivers", "macro_event_context", "confirmation_or_risk_factors"}:
                score += 0.65
                reasons[req.topic_role] = "market_knowledge_context"
                
            if score >= req.min_usefulness:
                covered.add(req.topic_role)
                scores[req.topic_role] = min(1.0, score)
                
        # Also include legacy fallback logic for topics not in req_set
        fallback_topics = EvidenceTopicAttributor._fallback_topics(item, text, title)
        for ft in fallback_topics:
            if ft not in covered:
                covered.add(ft)
                scores[ft] = 0.5
                reasons[ft] = "fallback_heuristic"

        result = EvidenceTopicAttributionResult(
            evidence_id=item.evidence_id,
            covered_topics=list(covered),
            topic_scores=scores,
            attribution_confidence="high" if all(s > 0.7 for s in scores.values()) else "medium",
            attribution_reasons=reasons
        )
        
        print(f"[EvidenceTopicAttribution] task_id={req_set.task_id} evidence_id={item.evidence_id} topics={result.covered_topics} confidence={result.attribution_confidence}")
        return result

    @staticmethod
    def _fallback_topics(item: EvidenceItem, text: str, title: str) -> Set[str]:
        topics = set()
        if item.evidence_type in {"book_passage", "static_knowledge"}:
            topics.add("core_concept")
            if any(term in text for term in ["use", "apply", "trade", "strategy", "entry", "stop", "signal", "setup"]):
                topics.add("practical_application")
            if any(term in text for term in ["market", "trend", "range", "condition", "context", "environment"]):
                topics.add("context_or_conditions")
            if any(term in text for term in ["method", "process", "step", "how to", "rule"]):
                topics.add("methodology_or_process")
            if any(term in text for term in ["example", "figure", "chart"]):
                topics.add("examples")
        return topics

    @staticmethod
    def _dynamic_market_topic_score(item: EvidenceItem, topic_role: str) -> tuple[float, str]:
        if topic_role in {"current_market_context", "current_state"}:
            if item.evidence_type == "market_snapshot" and EvidenceTopicAttributor._has_current_price(item):
                return 0.8, "current_market_snapshot_fields"
            if item.evidence_type == "ohlcv_summary" and EvidenceTopicAttributor._has_latest_ohlcv_value(item):
                return 0.55, "latest_ohlcv_state_fields"
            if item.evidence_type == "technical_snapshot" and EvidenceTopicAttributor._has_technical_state(item):
                return 0.5, "technical_state_fields"
            return 0.0, ""

        if topic_role != "recent_market_behavior":
            return 0.0, ""

        if item.evidence_type == "ohlcv_summary":
            if EvidenceTopicAttributor._has_explicit_ohlcv_behavior(item):
                return 0.8, "ohlcv_temporal_behavior_fields"
            return 0.0, ""

        if item.evidence_type == "technical_snapshot":
            if EvidenceTopicAttributor._has_trend_or_momentum_fields(item):
                return 0.75, "technical_trend_momentum_fields"
            return 0.0, ""

        if item.evidence_type == "market_snapshot":
            if EvidenceTopicAttributor._has_snapshot_behavior_fields(item):
                return 0.5, "market_snapshot_behavior_fields"
            return 0.0, ""

        return 0.0, ""

    @staticmethod
    def _has_current_price(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        return raw.get("latest_price") not in {None, ""} or "price=" in str(item.content or "").lower()

    @staticmethod
    def _has_latest_ohlcv_value(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        return bool(raw.get("count")) or "latest_close=" in str(item.content or "").lower()

    @staticmethod
    def _has_technical_state(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        text = EvidenceTopicAttributor._item_text(item)
        return bool(raw) or any(term in text for term in ["rsi", "ema", "indicator", "technical", "momentum", "trend"])

    @staticmethod
    def _has_explicit_ohlcv_behavior(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        behavior = raw.get("behavior") if isinstance(raw.get("behavior"), dict) else {}
        if behavior and int(behavior.get("count") or raw.get("count") or 0) >= 2:
            return any(key in behavior for key in ["change_pct", "direction", "range_pct", "high", "low"])
        text = EvidenceTopicAttributor._item_text(item)
        count = int(raw.get("count") or 0)
        return count >= 2 and any(term in text for term in ["change_pct", "direction=", "range_pct", "first_close", "last_close", "trend", "volatility", "momentum"])

    @staticmethod
    def _has_trend_or_momentum_fields(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        text = EvidenceTopicAttributor._item_text(item)
        if any(key in raw for key in ["trend", "momentum", "volatility", "support_resistance", "interpretation"]):
            raw_text = " ".join(str(value).lower() for value in raw.values())
            if any(term in raw_text for term in ["trend", "momentum", "volatility", "support", "resistance", "bullish", "bearish", "neutral"]):
                return True
        return any(term in text for term in ["trend", "momentum", "volatility", "support", "resistance", "bullish", "bearish"])

    @staticmethod
    def _has_snapshot_behavior_fields(item: EvidenceItem) -> bool:
        raw = item.raw or {}
        text = EvidenceTopicAttributor._item_text(item)
        trend = str(raw.get("recent_trend") or "").strip().lower()
        volatility = str(raw.get("volatility_note") or "").strip().lower()
        if trend and trend not in {"unknown", "none", "n/a"}:
            return True
        if volatility and volatility not in {"unknown", "none", "n/a"}:
            return True
        return any(term in text for term in ["trend=", "volatility=", "avg_range", "range_pct", "momentum"])

    @staticmethod
    def _item_text(item: EvidenceItem) -> str:
        return f"{item.content} {item.content_summary}".lower()

@dataclass
class TopicCoverageStrength:
    topic_role: str
    required: bool
    present: bool = False
    strongest_support_score: float = 0.0
    supporting_evidence_count: int = 0
    strength_status: str = "UNSUPPORTED" # STRONG, ADEQUATE, WEAK, UNSUPPORTED
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "topic_role": self.topic_role,
            "required": self.required,
            "present": self.present,
            "strongest_support_score": self.strongest_support_score,
            "supporting_evidence_count": self.supporting_evidence_count,
            "strength_status": self.strength_status
        }

@dataclass
class EvidenceCoverageResult:
    task_id: str
    status: str
    topic_presence_ratio: float = 0.0
    required_supported_ratio: float = 0.0
    required_strong_ratio: float = 0.0
    
    strong_required_topics: List[str] = field(default_factory=list)
    adequate_required_topics: List[str] = field(default_factory=list)
    weak_required_topics: List[str] = field(default_factory=list)
    unsupported_required_topics: List[str] = field(default_factory=list)
    
    optional_supported_topics: List[str] = field(default_factory=list)
    
    covered_required_topics: List[str] = field(default_factory=list) # Legacy, keeping for compatibility if needed
    missing_required_topics: List[str] = field(default_factory=list) # Legacy
    
    evidence_by_topic: Dict[str, List[str]] = field(default_factory=dict)
    refinement_recommended: bool = False
    warnings: List[str] = field(default_factory=list)
    topic_strengths: Dict[str, TopicCoverageStrength] = field(default_factory=dict)

    @property
    def coverage_ratio(self) -> float:
        return self.topic_presence_ratio

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "topic_presence_ratio": self.topic_presence_ratio,
            "required_supported_ratio": self.required_supported_ratio,
            "required_strong_ratio": self.required_strong_ratio,
            "strong_required_topics": list(self.strong_required_topics),
            "adequate_required_topics": list(self.adequate_required_topics),
            "weak_required_topics": list(self.weak_required_topics),
            "unsupported_required_topics": list(self.unsupported_required_topics),
            "optional_supported_topics": list(self.optional_supported_topics),
            "covered_required_topics": list(self.covered_required_topics),
            "missing_required_topics": list(self.missing_required_topics),
            "coverage_ratio": self.coverage_ratio,
            "evidence_by_topic": {k: list(v) for k, v in self.evidence_by_topic.items()},
            "refinement_recommended": self.refinement_recommended,
            "warnings": list(self.warnings),
            "topic_strengths": {k: v.as_dict() for k, v in self.topic_strengths.items()}
        }

class EvidenceCoverageEvaluator:
    """Evaluates if the evidence bundle meets the required semantic coverage."""
    
    @staticmethod
    def evaluate(bundle: EvidenceBundle, req_set: CoverageRequirementSet, phase: str = "pre_refinement") -> EvidenceCoverageResult:
        input_ids = [item.evidence_id for item in bundle.all_items]
        print(
            "[EvidenceCoverageInput] "
            f"phase={phase} task_id={req_set.task_id} count={len(input_ids)} ids={input_ids[:12]}"
        )
        for item in bundle.all_items:
            attr_res = EvidenceTopicAttributor.attribute(item, req_set)
            item.covered_topics = attr_res.covered_topics
            item.topic_scores = attr_res.topic_scores
                
        all_covered_topics = set()
        evidence_by_topic: Dict[str, List[str]] = {}
        topic_strengths: Dict[str, TopicCoverageStrength] = {}
        
        # Init strengths
        for req in req_set.required_topics:
            topic_strengths[req.topic_role] = TopicCoverageStrength(topic_role=req.topic_role, required=True)
        for req in req_set.optional_topics:
            topic_strengths[req.topic_role] = TopicCoverageStrength(topic_role=req.topic_role, required=False)
        
        for item in bundle.all_items:
            for topic, score in getattr(item, "topic_scores", {}).items():
                all_covered_topics.add(topic)
                if topic not in evidence_by_topic:
                    evidence_by_topic[topic] = []
                evidence_by_topic[topic].append(item.evidence_id)
                
                if topic in topic_strengths:
                    ts = topic_strengths[topic]
                    ts.present = True
                    ts.supporting_evidence_count += 1
                    ts.strongest_support_score = max(ts.strongest_support_score, score)
                else:
                    topic_strengths[topic] = TopicCoverageStrength(topic_role=topic, required=False, present=True, strongest_support_score=score, supporting_evidence_count=1)
        
        # Calculate strength statuses
        for ts in topic_strengths.values():
            if not ts.present:
                ts.strength_status = "UNSUPPORTED"
            elif ts.strongest_support_score >= 0.7:
                ts.strength_status = "STRONG"
            elif ts.strongest_support_score >= 0.45:
                ts.strength_status = "ADEQUATE"
            else:
                ts.strength_status = "WEAK"
                
        strong_req = []
        adequate_req = []
        weak_req = []
        unsupported_req = []
        covered_required = []
        missing_required = []
        
        for req in req_set.required_topics:
            ts = topic_strengths[req.topic_role]
            if ts.strength_status == "STRONG":
                strong_req.append(req.topic_role)
            elif ts.strength_status == "ADEQUATE":
                adequate_req.append(req.topic_role)
            elif ts.strength_status == "WEAK":
                weak_req.append(req.topic_role)
            else:
                unsupported_req.append(req.topic_role)
                
            if ts.present:
                covered_required.append(req.topic_role)
            else:
                missing_required.append(req.topic_role)
                
        optional_supported = [req.topic_role for req in req_set.optional_topics if topic_strengths[req.topic_role].strength_status in {"STRONG", "ADEQUATE", "WEAK"}]
        
        total_req = len(req_set.required_topics)
        presence_ratio = len(covered_required) / total_req if total_req > 0 else 1.0
        supported_ratio = (len(strong_req) + len(adequate_req) + len(weak_req)) / total_req if total_req > 0 else 1.0
        strong_ratio = len(strong_req) / total_req if total_req > 0 else 1.0
        
        status = "COMPLETE"
        if unsupported_req:
            status = "INSUFFICIENT"
        elif weak_req:
            status = "DEGRADED"
            
        refinement_recommended = status in {"DEGRADED", "INSUFFICIENT"} and len(missing_required) > 0 and req_set.refinement_allowed
        
        warnings = []
        if unsupported_req:
            warnings.append(f"Missing required topics: {','.join(unsupported_req)}")
        if weak_req:
            warnings.append(f"Weak required topics: {','.join(weak_req)}")
            
        result = EvidenceCoverageResult(
            task_id=req_set.task_id,
            status=status,
            topic_presence_ratio=presence_ratio,
            required_supported_ratio=supported_ratio,
            required_strong_ratio=strong_ratio,
            strong_required_topics=strong_req,
            adequate_required_topics=adequate_req,
            weak_required_topics=weak_req,
            unsupported_required_topics=unsupported_req,
            optional_supported_topics=optional_supported,
            covered_required_topics=covered_required,
            missing_required_topics=missing_required,
            evidence_by_topic=evidence_by_topic,
            refinement_recommended=refinement_recommended,
            warnings=warnings,
            topic_strengths=topic_strengths
        )
        
        print(f"[EvidenceCoverage] phase={phase} task_id={result.task_id} presence={result.topic_presence_ratio:.2f} strong={result.required_strong_ratio:.2f} missing={result.unsupported_required_topics} weak={result.weak_required_topics}")
        return result

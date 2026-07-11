from dataclasses import dataclass, field
from typing import Dict, Any, List, Set

from src.services.semantic.query_plan import QueryPlan
from src.services.evidence.answer_depth import AnswerDepthPlan

@dataclass
class CoverageRequirement:
    topic_role: str
    required: bool = True
    description: str = ""
    explanation_goal: str = ""
    compatible_evidence_types: List[str] = field(default_factory=list)
    retrieval_descriptors: List[str] = field(default_factory=list)
    semantic_signals: List[str] = field(default_factory=list)
    evidence_signals: List[str] = field(default_factory=list)
    answer_signals: List[str] = field(default_factory=list)
    min_directness: float = 0.5
    min_usefulness: float = 0.5

    def __post_init__(self) -> None:
        if not self.description and self.explanation_goal:
            self.description = self.explanation_goal
        if not self.explanation_goal and self.description:
            self.explanation_goal = self.description

    def as_dict(self) -> Dict[str, Any]:
        return {
            "topic_role": self.topic_role,
            "required": self.required,
            "description": self.description,
            "explanation_goal": self.explanation_goal,
            "compatible_evidence_types": list(self.compatible_evidence_types),
            "retrieval_descriptors": list(self.retrieval_descriptors),
            "semantic_signals": list(self.semantic_signals),
            "evidence_signals": list(self.evidence_signals),
            "answer_signals": list(self.answer_signals),
            "min_directness": self.min_directness,
            "min_usefulness": self.min_usefulness,
        }

@dataclass
class CoverageRequirementSet:
    task_id: str
    required_topics: List[CoverageRequirement] = field(default_factory=list)
    optional_topics: List[CoverageRequirement] = field(default_factory=list)
    minimum_required_coverage_ratio: float = 0.8
    refinement_allowed: bool = True
    max_missing_critical: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "required_topics": [r.as_dict() for r in self.required_topics],
            "optional_topics": [r.as_dict() for r in self.optional_topics],
            "minimum_required_coverage_ratio": self.minimum_required_coverage_ratio,
            "refinement_allowed": self.refinement_allowed,
            "max_missing_critical": self.max_missing_critical,
        }

@dataclass(frozen=True)
class TopicDefinition:
    topic_role: str
    description: str
    semantic_signals: List[str] = field(default_factory=list)
    evidence_signals: List[str] = field(default_factory=list)
    answer_signals: List[str] = field(default_factory=list)
    structural_signals: List[str] = field(default_factory=list)
    multilingual_signals: List[str] = field(default_factory=list)
    minimum_semantic_requirements: Dict[str, Any] = field(default_factory=dict)


def _dedupe_signals(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        key = str(value or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out

class CoverageRequirementPlanner:
    """Plans topic coverage requirements based on AnswerDepthPlan and answer_type."""

    @staticmethod
    def topic_definition(role: str) -> TopicDefinition:
        registry = CoverageRequirementPlanner._topic_definition_registry()
        if role in registry:
            return registry[role]
        sem, ev, ans = CoverageRequirementPlanner._signals(role)
        return TopicDefinition(
            topic_role=role,
            description=role.replace("_", " "),
            semantic_signals=sem,
            evidence_signals=ev,
            answer_signals=ans,
        )

    @staticmethod
    def _topic_definition_registry() -> Dict[str, TopicDefinition]:
        return {
            "short_interpretation": TopicDefinition(
                topic_role="short_interpretation",
                description=(
                    "Concise synthesis of what report findings imply: direction, "
                    "acceleration or deceleration, persistence, cooling, mixed "
                    "components, or overall momentum."
                ),
                semantic_signals=[
                    "interpretation", "synthesis", "implication", "suggests",
                    "implies", "indicates", "cooling", "mixed", "persistent",
                    "accelerated", "slowed", "decelerated", "momentum weakened",
                    "pressure remained", "some categories rose", "others declined",
                ],
                evidence_signals=[
                    "slowed", "accelerated", "mixed", "persistent", "cooling",
                    "rose while", "declined while", "overall", "suggest",
                ],
                answer_signals=[
                    "growth slowed", "growth accelerated", "slowed compared",
                    "accelerated compared", "cooling trend", "price pressure",
                    "remained persistent", "mixed behavior", "mixed components",
                    "overall momentum", "some groups rose", "others fell",
                    "toc do tang cham lai", "toc do tang nhanh hon",
                    "ap luc van dai dang", "dien bien khong dong deu",
                    "cho thay xu huong ha nhiet", "ha nhiet",
                    "mot so nhom tang", "nhom khac giam",
                    "so voi ky truoc", "so voi thang truoc",
                ],
                structural_signals=["interpretation", "what it means", "y nghia"],
                multilingual_signals=[
                    "toc do tang cham lai", "ap luc gia", "dai dang",
                    "khong dong deu", "ha nhiet", "cho thay",
                ],
                minimum_semantic_requirements={
                    "requires_synthesis": True,
                    "raw_numbers_alone_sufficient": False,
                },
            ),
            "event_state": TopicDefinition(
                topic_role="event_state",
                description=(
                    "State of the triggering event or release. Minimum state is "
                    "period or reported state plus a current/previous comparison; "
                    "full surprise analysis additionally needs forecast and surprise."
                ),
                semantic_signals=[
                    "event state", "actual", "forecast", "previous", "surprise",
                    "release", "period", "reported", "latest data",
                ],
                evidence_signals=[
                    "actual", "forecast", "previous", "surprise", "release",
                    "period", "reported", "month", "year",
                ],
                answer_signals=[
                    "actual", "forecast", "previous", "surprise", "release",
                    "reported", "period", "latest", "month", "year",
                    "thuc te", "du bao", "ky truoc", "truoc do", "cong bo",
                    "bat ngo", "ky bao cao", "thang", "nam", "moi nhat",
                    "du lieu", "so lieu", "ket qua",
                ],
                structural_signals=["event data", "release data", "so lieu"],
                multilingual_signals=[
                    "thuc te", "du bao", "ky truoc", "cong bo", "bat ngo",
                    "so voi ky truoc", "so voi du bao",
                ],
                minimum_semantic_requirements={
                    "minimum": ["reported_or_actual_state", "comparison_or_period"],
                    "surprise_analysis": ["actual", "forecast", "previous"],
                },
            ),
            "confirmation_or_invalidation": TopicDefinition(
                topic_role="confirmation_or_invalidation",
                description=(
                    "Observable future conditions, reactions, or follow-up signals "
                    "that would strengthen, weaken, confirm, or invalidate a scenario."
                ),
                semantic_signals=[
                    "confirmation", "invalidation", "condition", "observable",
                    "if", "when", "above", "below", "break", "hold",
                    "strengthen", "weaken", "confirm", "invalidate",
                ],
                evidence_signals=[
                    "confirm", "invalidate", "condition", "reaction", "break",
                    "hold", "above", "below", "yield", "dxy", "rate",
                ],
                answer_signals=[
                    "if", "when", "unless", "confirm", "invalidate",
                    "confirmed if", "invalidated if", "break above",
                    "break below", "hold above", "hold below", "fails to hold",
                    "strengthens", "weakens", "market reaction",
                    "neu", "khi", "tru khi", "xac nhan", "vo hieu",
                    "phu nhan", "pha len", "pha xuong", "vuot len",
                    "roi xuong", "giu tren", "giu duoi", "suy yeu",
                    "manh len", "phan ung thi truong", "loi suat", "dong usd",
                ],
                structural_signals=[
                    "confirmation", "invalidation", "conditions to watch",
                    "dieu kien xac nhan", "dieu kien vo hieu",
                ],
                multilingual_signals=[
                    "neu", "khi", "xac nhan", "vo hieu", "pha len",
                    "pha xuong", "phan ung", "suy yeu", "manh len",
                ],
                minimum_semantic_requirements={
                    "requires_observable_condition": True,
                    "vague_watch_market_alone_sufficient": False,
                },
            ),
        }
    
    @staticmethod
    def _signals(role: str) -> Dict[str, List[str]]:
        # Map of topic_role to (semantic_signals, evidence_signals, answer_signals)
        smap = {
            "core_concept": (
                ["definition", "core concept", "meaning", "how it works", "basics", "khái niệm", "định nghĩa", "bản chất"],
                ["refers to", "defined as", "is a", "concept", "meaning", "stands for"],
                ["khái niệm", "định nghĩa", "là gì", "cơ bản", "bản chất", "có nghĩa là", "là một"]
            ),
            "methodology_or_process": (
                ["analysis sequence", "decision process", "practical procedure", "entry logic", "signal interpretation", "rule application", "conditions for action", "phương pháp", "quy trình", "các bước", "quy tắc"],
                ["method", "process", "step", "how to", "rule", "signal bar", "entry bar", "entering on stops", "order-entry", "procedure"],
                ["phương pháp", "quy trình", "bước", "cách áp dụng", "quy tắc", "chiến lược", "vào lệnh", "tín hiệu", "thực hiện"]
            ),
            "context_or_conditions": (
                ["market environment", "context", "conditions", "bối cảnh", "điều kiện thị trường", "môi trường"],
                ["market", "trend", "range", "condition", "context", "environment", "when to", "scenario"],
                ["bối cảnh", "điều kiện", "môi trường", "khi nào", "thị trường", "trạng thái"]
            ),
            "practical_application": (
                ["practical application", "trading setup", "entry rules", "áp dụng thực tế", "thiết lập giao dịch"],
                ["use", "apply", "trade", "strategy", "entry", "stop", "signal", "setup", "in practice"],
                ["áp dụng", "thực tế", "giao dịch", "vào lệnh", "cắt lỗ", "chiến lược", "sử dụng"]
            ),
            "examples": (
                ["examples", "case study", "ví dụ", "minh họa"],
                ["example", "figure", "chart", "for instance", "case"],
                ["ví dụ", "minh họa", "trường hợp", "biểu đồ"]
            ),
            "limitations": (
                ["risks", "limitations", "drawbacks", "rủi ro", "hạn chế"],
                ["risk", "limit", "however", "but", "unless", "invalidation", "drawback", "caveat"],
                ["rủi ro", "hạn chế", "tuy nhiên", "nhược điểm", "lưu ý", "ngoại trừ"]
            ),
            "headline_findings": (
                ["main findings", "headline numbers", "kết quả chính", "số liệu chính"],
                ["finding", "headline", "result", "showed", "reported", "increased", "decreased"],
                ["kết quả", "số liệu", "chính", "báo cáo", "tăng", "giảm", "cho thấy"]
            ),
            "important_components": (
                ["key components", "details", "sub-indices", "thành phần", "chi tiết"],
                ["component", "detail", "sub-index", "category", "sector"],
                ["thành phần", "chi tiết", "chỉ số phụ", "hạng mục", "lĩnh vực"]
            ),
            "report_period": (
                ["period", "month over month", "year over year", "kỳ báo cáo", "thời gian"],
                ["period", "month", "year", "quarter", "y/y", "m/m", "q/q", "annual", "monthly"],
                ["tháng", "năm", "quý", "kỳ", "so với cùng kỳ"]
            ),
            "official_source_context": (
                ["official statement", "press release", "nguồn chính thức", "báo cáo"],
                ["report", "release", "statement", "press", "official", "published"],
                ["báo cáo", "công bố", "tuyên bố", "chính thức", "phát hành"]
            ),
            "short_interpretation": (
                ["interpretation", "analysis", "phân tích", "đánh giá"],
                ["interpret", "analysis", "suggest", "imply", "mean", "indicate"],
                ["phân tích", "đánh giá", "cho thấy", "ý nghĩa", "ngụ ý"]
            ),
            "event_state": (
                ["event state", "actual release", "trạng thái sự kiện", "kết quả công bố"],
                ["actual", "forecast", "previous", "surprise", "release"],
                ["thực tế", "dự báo", "kỳ trước", "công bố", "bất ngờ"]
            ),
            "transmission_mechanism": (
                ["impact", "affect", "lead to", "cause", "tác động", "ảnh hưởng"],
                ["impact", "affect", "cause", "lead to", "result", "drive"],
                ["tác động", "ảnh hưởng", "gây ra", "dẫn đến", "kết quả"]
            ),
            "current_market_context": (
                ["market reaction", "current price action", "phản ứng thị trường", "diễn biến giá"],
                ["market", "price", "reaction", "currently", "trading at"],
                ["thị trường", "giá", "phản ứng", "hiện tại", "giao dịch"]
            ),
            "bullish_scenario": (
                ["bullish scenario", "upside potential", "kịch bản tăng", "triển vọng tăng"],
                ["bull", "up", "rise", "support", "buy", "long", "rally", "gain"],
                ["tăng", "hỗ trợ", "mua", "tích cực", "đi lên", "triển vọng"]
            ),
            "bearish_scenario": (
                ["bearish scenario", "downside risk", "kịch bản giảm", "rủi ro giảm"],
                ["bear", "down", "fall", "resistance", "sell", "short", "drop", "loss"],
                ["giảm", "kháng cự", "bán", "tiêu cực", "đi xuống", "rủi ro"]
            ),
            "confirmation_or_invalidation": (
                ["confirmation", "invalidation", "risk factor", "xác nhận", "phủ nhận", "rủi ro"],
                ["confirm", "invalidate", "break", "hold", "unless"],
                ["xác nhận", "phủ nhận", "phá vỡ", "giữ vững", "trừ khi"]
            ),
            "current_state": (
                ["current state", "price action", "trend", "trạng thái hiện tại", "xu hướng"],
                ["current", "price", "trend", "state", "action", "trading"],
                ["hiện tại", "giá", "xu hướng", "trạng thái", "giao dịch"]
            ),
            "main_drivers": (
                ["market drivers", "catalysts", "động lực chính", "chất xúc tác"],
                ["driver", "catalyst", "due to", "driven by", "cause"],
                ["động lực", "chất xúc tác", "do", "thúc đẩy bởi", "nguyên nhân"]
            ),
            "recent_market_behavior": (
                ["recent behavior", "momentum", "diễn biến gần đây", "động lượng"],
                ["recent", "momentum", "behavior", "past", "last"],
                ["gần đây", "động lượng", "diễn biến", "vừa qua"]
            ),
            "technical_context": (
                ["technical context", "levels", "patterns", "phân tích kỹ thuật", "mức giá", "mô hình"],
                ["technical", "level", "pattern", "support", "resistance", "moving average", "indicator"],
                ["kỹ thuật", "mức", "mô hình", "hỗ trợ", "kháng cự", "đường trung bình", "chỉ báo"]
            ),
            "macro_event_context": (
                ["macro context", "fundamental drivers", "bối cảnh vĩ mô", "yếu tố cơ bản"],
                ["macro", "fundamental", "event", "economic", "news", "data"],
                ["vĩ mô", "cơ bản", "sự kiện", "kinh tế", "tin tức", "dữ liệu"]
            ),
            "confirmation_or_risk_factors": (
                ["risk factors", "trend reversal risks", "yếu tố rủi ro", "đảo chiều"],
                ["risk", "reversal", "threat", "danger", "caution"],
                ["rủi ro", "đảo chiều", "đe dọa", "thận trọng", "nguy hiểm"]
            ),
            "main_ideas": (
                ["main ideas", "core concepts", "ý chính"],
                ["main", "idea", "concept", "key", "primary"],
                ["chính", "ý tưởng", "khái niệm", "trọng tâm"]
            ),
            "supporting_details": (
                ["supporting details", "context", "chi tiết hỗ trợ"],
                ["detail", "support", "context", "specific", "note"],
                ["chi tiết", "hỗ trợ", "bối cảnh", "cụ thể", "lưu ý"]
            ),
        }
        base = smap.get(role, ([], [], []))
        definition = CoverageRequirementPlanner._topic_definition_registry().get(role)
        if not definition:
            return base
        return (
            _dedupe_signals(list(base[0]) + definition.semantic_signals),
            _dedupe_signals(list(base[1]) + definition.evidence_signals),
            _dedupe_signals(
                list(base[2])
                + definition.answer_signals
                + definition.structural_signals
                + definition.multilingual_signals
            ),
        )

    @staticmethod
    def _make_req(role: str, req: bool, desc: str, rdesc: List[str]) -> CoverageRequirement:
        sem, ev, ans = CoverageRequirementPlanner._signals(role)
        return CoverageRequirement(role, req, desc, retrieval_descriptors=rdesc, semantic_signals=sem, evidence_signals=ev, answer_signals=ans)

    @staticmethod
    def plan(query_plan: QueryPlan, depth_plan: AnswerDepthPlan, answer_type: str) -> CoverageRequirementSet:
        required = []
        optional = []
        
        # Define general topics for different answer types
        if answer_type == "static_explanation":
            required.extend([
                CoverageRequirementPlanner._make_req("core_concept", True, "Main concept definition and mechanics", ["core concept", "definition", "how it works"]),
                CoverageRequirementPlanner._make_req("methodology_or_process", True, "How the concept is applied or processed", ["how the method is applied", "analysis process", "decision sequence", "practical rules"]),
                CoverageRequirementPlanner._make_req("context_or_conditions", True, "Market conditions or contexts where it applies", ["market environment", "context", "conditions", "when the approach applies"]),
            ])
            if depth_plan.practical_interpretation_required:
                required.append(CoverageRequirementPlanner._make_req("practical_application", True, "How a trader uses this practically", ["practical application", "trading setup", "entry rules"]))
                
            optional.extend([
                CoverageRequirementPlanner._make_req("examples", False, "Specific examples", ["examples", "case study", "figure"]),
                CoverageRequirementPlanner._make_req("limitations", False, "Limitations or risks", ["limitations", "risks", "drawbacks"])
            ])
            
        elif answer_type == "report_summary":
            required.extend([
                CoverageRequirementPlanner._make_req("headline_findings", True, "Main numbers or conclusions", ["main findings", "headline numbers", "conclusions"]),
                CoverageRequirementPlanner._make_req("important_components", True, "Key sub-components of the report", ["key components", "details", "sub-indices"]),
                CoverageRequirementPlanner._make_req("report_period", True, "Time period covered", ["period", "month over month", "year over year"]),
                CoverageRequirementPlanner._make_req("official_source_context", True, "Context from the issuing entity", ["official statement", "press release"]),
                CoverageRequirementPlanner._make_req("short_interpretation", True, "General interpretation of the report", ["interpretation", "analysis"])
            ])
            
        elif answer_type == "scenario_analysis":
            required.extend([
                CoverageRequirementPlanner._make_req("event_state", True, "The state of the triggering event or data", ["event state", "actual release", "data point"]),
                CoverageRequirementPlanner._make_req("transmission_mechanism", True, "How the event impacts the asset", ["impact", "affect", "lead to", "cause"]),
                CoverageRequirementPlanner._make_req("current_market_context", True, "Current market reaction or state", ["market reaction", "current price action"]),
                CoverageRequirementPlanner._make_req("bullish_scenario", True, "Bullish outcome scenario", ["bullish scenario", "upside potential", "resistance"]),
                CoverageRequirementPlanner._make_req("bearish_scenario", True, "Bearish outcome scenario", ["bearish scenario", "downside risk", "support"]),
                CoverageRequirementPlanner._make_req("confirmation_or_invalidation", True, "What confirms or invalidates the scenarios", ["confirmation", "invalidation", "risk factor"])
            ])
            if depth_plan.limitations_required:
                required.append(CoverageRequirementPlanner._make_req("limitations", True, "Risks or missing data points", ["risks", "limitations"]))
                
        elif answer_type == "market_analysis":
            required.extend([
                CoverageRequirementPlanner._make_req("current_state", True, "Current price action or market state", ["current state", "price action", "trend"]),
                CoverageRequirementPlanner._make_req("recent_market_behavior", True, "Recent price behavior or trends", ["recent behavior", "momentum"])
            ])
            optional.extend([
                CoverageRequirementPlanner._make_req("main_drivers", False, "Primary drivers when driver evidence is available", ["market drivers", "catalysts"]),
                CoverageRequirementPlanner._make_req("technical_context", False, "Technical levels or patterns", ["technical context", "levels", "patterns"]),
                CoverageRequirementPlanner._make_req("macro_event_context", False, "Relevant macro events", ["macro context", "fundamental drivers"]),
                CoverageRequirementPlanner._make_req("confirmation_or_risk_factors", False, "Risks to the current trend when risk evidence is available", ["risk factors", "trend reversal risks"])
            ])
                
        else:
            # Fallback default
            required.append(CoverageRequirementPlanner._make_req("main_ideas", True, "Main ideas from the context", ["main ideas", "core concepts"]))
            if depth_plan.detail_level in {"detailed", "deep", "standard_detailed"}:
                required.append(CoverageRequirementPlanner._make_req("supporting_details", True, "Supporting facts or context", ["supporting details", "context"]))
        
        req_set = CoverageRequirementSet(
            task_id=depth_plan.task_id,
            required_topics=required,
            optional_topics=optional,
            minimum_required_coverage_ratio=0.75 if depth_plan.detail_level in {"detailed", "deep"} else 0.5,
            refinement_allowed=True
        )
        
        req_names = [r.topic_role for r in required]
        opt_names = [r.topic_role for r in optional]
        print(f"[CoverageRequirements] task_id={req_set.task_id} required={req_names} optional={opt_names}")
        return req_set

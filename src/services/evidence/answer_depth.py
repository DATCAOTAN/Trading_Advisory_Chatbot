from dataclasses import dataclass, field
from typing import Dict, Any, List

from src.services.semantic.query_plan import QueryPlan

@dataclass
class AnswerDepthPlan:
    task_id: str
    detail_level: str
    expected_explanation_depth: str
    expected_topic_count_range: tuple[int, int]
    comparison_required: bool = False
    practical_interpretation_required: bool = False
    scenario_structure_required: bool = False
    current_data_required: bool = False
    limitations_required: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "detail_level": self.detail_level,
            "expected_explanation_depth": self.expected_explanation_depth,
            "expected_topic_count_range": list(self.expected_topic_count_range),
            "comparison_required": self.comparison_required,
            "practical_interpretation_required": self.practical_interpretation_required,
            "scenario_structure_required": self.scenario_structure_required,
            "current_data_required": self.current_data_required,
            "limitations_required": self.limitations_required,
        }

class AnswerDepthPlanner:
    """Plans answer depth based on semantic intent and answer type."""
    
    @staticmethod
    def plan(query_plan: QueryPlan, answer_type: str, task_id: str, is_multi_intent: bool = False) -> AnswerDepthPlan:
        intent = query_plan.primary_intent
        
        detail_level = "standard"
        depth = "moderate"
        topics = (2, 4)
        comparison = False
        practical = False
        scenario = False
        current = False
        limitations = False
        
        # Simple factual lookup
        if intent in {"simple_fact", "calendar_lookup"} or answer_type in {"factual_lookup", "calendar_summary"}:
            detail_level = "brief"
            depth = "shallow"
            topics = (1, 2)
            
        # Book concept explanation
        elif intent == "book_concept_explanation" or answer_type == "static_explanation":
            detail_level = "standard_detailed"
            depth = "deep"
            topics = (3, 5)
            practical = True
            
        # Macro report summary
        elif intent == "macro_report_summary" or answer_type == "report_summary":
            detail_level = "standard"
            depth = "moderate"
            topics = (3, 5)
            
        # Macro market impact
        elif intent == "macro_market_impact" or answer_type == "scenario_analysis":
            detail_level = "detailed"
            depth = "deep"
            topics = (4, 6)
            scenario = True
            current = True
            limitations = True
            
        # Market state analysis
        elif intent == "market_state_analysis" or answer_type == "market_analysis":
            detail_level = "detailed"
            depth = "deep"
            topics = (4, 6)
            current = True
            limitations = True
            
        # Strategy or risk
        elif intent in {"strategy_formulation", "risk_evaluation"}:
            detail_level = "standard_detailed"
            depth = "deep"
            topics = (4, 5)
            practical = True
            limitations = True
            
        # Comparisons
        if "comparison" in query_plan.requested_analysis:
            comparison = True
            detail_level = "detailed" if detail_level == "standard" else detail_level
            
        # Multi-intent constraints
        if is_multi_intent and detail_level in {"detailed", "deep"}:
            detail_level = "standard_detailed" # Slightly condense to fit composite answer
        
        plan = AnswerDepthPlan(
            task_id=task_id,
            detail_level=detail_level,
            expected_explanation_depth=depth,
            expected_topic_count_range=topics,
            comparison_required=comparison,
            practical_interpretation_required=practical,
            scenario_structure_required=scenario,
            current_data_required=current,
            limitations_required=limitations
        )
        
        print(f"[AnswerDepth] task_id={task_id} detail_level={detail_level}")
        return plan

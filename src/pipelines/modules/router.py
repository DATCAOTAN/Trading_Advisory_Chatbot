from enum import Enum
from typing import List, Dict, Tuple
from src.pipelines.intent_router import IntentRouter as OldIntentRouter, IntentType

class RouteAction(Enum):
    VECTOR_SEARCH = "vector_search"
    MEMORY_SEARCH = "memory_search"
    LIVE_API = "live_api"
    EARLY_EXIT = "early_exit"

class RouterModule:
    """Bộ điều hướng Modular RAG. Chịu trách nhiệm lái luồng dữ liệu."""
    @staticmethod
    def process_structured(primary_intent: str, query: str) -> Tuple[RouteAction, str]:
        """Map validated semantic intent to the existing cheap early exits."""
        if primary_intent == "SOCIAL":
            return RouteAction.EARLY_EXIT, OldIntentRouter.get_greeting_response(query)
        if primary_intent in {"SYSTEM", "OUT_OF_SCOPE"}:
            return RouteAction.EARLY_EXIT, OldIntentRouter.get_trash_response()
        return RouteAction.VECTOR_SEARCH, ""

    def process(self, query: str, chat_history: List[Dict]) -> Tuple[RouteAction, str]:
        """Legacy fallback when no validated structured semantic result is available."""
        intent = OldIntentRouter.classify(query, chat_history)
        
        if intent == IntentType.GREETING:
            return RouteAction.EARLY_EXIT, OldIntentRouter.get_greeting_response(query)
            
        if intent == IntentType.TRASH:
            return RouteAction.EARLY_EXIT, OldIntentRouter.get_trash_response()
            
        # Trong tương lai có thể nâng cấp thêm LIVE_API hoặc MEMORY_SEARCH tại đây
        return RouteAction.VECTOR_SEARCH, ""

from typing import Any, Dict

from src.config import Config


USE_KNOWLEDGE_V3_KEY = "use_knowledge_v3"
KNOWLEDGE_V3_FALLBACK_KEY = "knowledge_v3_fallback_to_legacy"


def ensure_knowledge_v3_flags(session_state: Any) -> None:
    if not _has_key(session_state, USE_KNOWLEDGE_V3_KEY):
        _set_value(session_state, USE_KNOWLEDGE_V3_KEY, Config.USE_KNOWLEDGE_V3)
    if not _has_key(session_state, KNOWLEDGE_V3_FALLBACK_KEY):
        _set_value(
            session_state,
            KNOWLEDGE_V3_FALLBACK_KEY,
            Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY,
        )


def get_knowledge_v3_flags(session_state: Any) -> Dict[str, bool]:
    ensure_knowledge_v3_flags(session_state)
    return {
        "use_knowledge_v3": bool(_get_value(session_state, USE_KNOWLEDGE_V3_KEY)),
        "knowledge_v3_fallback_to_legacy": bool(_get_value(session_state, KNOWLEDGE_V3_FALLBACK_KEY)),
    }


def _has_key(session_state: Any, key: str) -> bool:
    if isinstance(session_state, dict):
        return key in session_state
    return key in session_state


def _get_value(session_state: Any, key: str) -> Any:
    if isinstance(session_state, dict):
        return session_state[key]
    return getattr(session_state, key)


def _set_value(session_state: Any, key: str, value: Any) -> None:
    if isinstance(session_state, dict):
        session_state[key] = value
    else:
        setattr(session_state, key, value)

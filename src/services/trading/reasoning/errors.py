class MethodSelectionError(RuntimeError):
    """Raised for unrecoverable method selection errors."""


class LLMReasoningError(RuntimeError):
    """Raised when optional method reasoning LLM flow fails."""

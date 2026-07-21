class KnowledgeStoreError(RuntimeError):
    """Raised for unrecoverable compiled knowledge store errors."""


class KnowledgeRoutingError(RuntimeError):
    """Raised when deterministic knowledge routing cannot build a candidate set."""

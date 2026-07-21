class CalendarProviderError(RuntimeError):
    """Raised when a structured calendar provider cannot fetch or parse events."""


class CalendarContextError(RuntimeError):
    """Raised when calendar context construction fails unexpectedly."""

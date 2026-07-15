class MarketDataError(Exception):
    """Base market data error."""


class ProviderUnavailableError(MarketDataError):
    """Raised when a provider is unavailable."""


class ProviderMisconfiguredError(MarketDataError):
    """Raised when a provider is selected but missing required configuration."""


class CrossTalkerError(Exception):
    """Base application error."""


class ConfigurationError(CrossTalkerError):
    """The requested provider setup is invalid or incomplete."""


class ProviderCallError(CrossTalkerError):
    """A model provider request failed."""

class ResearchFlowError(Exception):
    """Expected user-facing failure."""


class ValidationError(ResearchFlowError):
    """A persisted record violates a contract."""


class CompositeError(Exception):
    """Base class for all Composite API exceptions."""


class InvalidStateError(CompositeError):
    """Raised when subrequest or node is in an invalid state for attempted operation."""

from httpx import Response


class SalesforceWarning(Warning):
    """Base class for all Salesforce warnings."""


class SalesforceError(Exception):
    """Base class for all Salesforce errors."""

    def __init__(self, message: str, response: Response) -> None:
        super().__init__(message)
        self.response = response


class AuthenticationError(SalesforceError):
    """Raised when authentication fails."""


class AuthorizationError(SalesforceError):
    """Raised when user is not authorized to perform an action."""


class RequestLimitExceededError(SalesforceError):
    """Raised when org REST API request limit is exceeded."""


class MalformedQueryError(SalesforceError):
    """Raised when query is malformed."""


class InvalidTypeError(SalesforceError):
    """Raised when invalid type is used."""


class NotFoundError(SalesforceError):
    """Raised when resource is not found."""

class SalesforceError(Exception):
    """Base class for all Salesforce errors."""


class AuthenticationError(SalesforceError):
    """Raised when authentication fails."""


class AuthorizationError(SalesforceError):
    """Raised when user is not authorized to perform an action."""


class RequestLimitError(SalesforceError):
    """Raised when org REST API request limit is reached."""

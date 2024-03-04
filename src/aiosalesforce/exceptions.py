from typing import NoReturn

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


class RequiredFieldMissingError(SalesforceError):
    """Raised when a required field is missing."""


class EntityIsDeletedError(SalesforceError):
    """Raised when the entity is deleted."""


EXCEPTIONS: dict[str, type[SalesforceError]] = {
    "REQUEST_LIMIT_EXCEEDED": RequestLimitExceededError,
    "MALFORMED_QUERY": MalformedQueryError,
    "INVALID_TYPE": InvalidTypeError,
    "NOT_FOUND": NotFoundError,
    "REQUIRED_FIELD_MISSING": RequiredFieldMissingError,
    "ENTITY_IS_DELETED": EntityIsDeletedError,
}


def raise_salesforce_error(response: Response) -> NoReturn:
    """
    Raise an exception group containing Salesforce errors.

    Parameters
    ----------
    response : Response
        HTTPX response.

    Raises
    ------
    ExceptionGroup

    """
    errors: list[SalesforceError] = []
    if isinstance(response_json := response.json(), list):
        for error in response_json:
            try:
                errors.append(
                    EXCEPTIONS[error["errorCode"]](error["message"], response)
                )
            except KeyError:
                errors.append(
                    SalesforceError(
                        f"{error['errorCode']}: {error['message']}", response
                    )
                )
    else:
        errors.append(SalesforceError(response.text, response))
    raise ExceptionGroup(
        "\n".join(
            [
                "",
                f"{response.status_code}: {response.reason_phrase}",
                f"{response.request.method} {response.request.url}",
            ]
        ),
        errors,
    )

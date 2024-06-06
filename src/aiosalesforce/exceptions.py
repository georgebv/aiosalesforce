from typing import NoReturn, TypedDict

from httpx import Response

from aiosalesforce.utils import json_loads


class SalesforceWarning(Warning):
    """Base class for all Salesforce warnings."""


class SalesforceError(Exception):
    """Base class for all Salesforce errors."""

    response: Response | None
    error_code: str | None
    error_message: str | None

    def __init__(
        self,
        message: str,
        response: Response | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.error_code = error_code
        self.error_message = error_message


class MoreThanOneRecordError(SalesforceError):
    """Raised when more than one record is found by external ID."""


class _DuplicateRecord(TypedDict):
    id: str
    sobject: str
    match_confidence: float
    match_engine: str
    rule: str


class DuplicatesDetectedError(SalesforceError):
    """Raised when duplicates are detected, e.g. when creating a new record."""

    @property
    def duplicates(self) -> list[_DuplicateRecord]:
        assert self.response is not None
        response_json = json_loads(self.response.content)
        return [
            _DuplicateRecord(
                id=match_record["record"]["Id"],
                sobject=match_record["record"]["attributes"]["type"],
                match_confidence=match_record["matchConfidence"],
                match_engine=match_result["matchEngine"],
                rule=match_result["rule"],
            )
            for match_result in response_json[0]["duplicateResult"]["matchResults"]
            for match_record in match_result["matchRecords"]
        ]


class AuthenticationError(SalesforceError):
    """Raised when authentication fails."""


class AuthorizationError(SalesforceError):
    """Raised when user has insufficient permissions to perform an action."""


class RequestLimitExceededError(SalesforceError):
    """Raised when org REST API request limit is exceeded."""


class NotFoundError(SalesforceError):
    """Raised when a resource is not found."""


class ServerError(SalesforceError):
    """Base class for 5xx errors."""


def raise_salesforce_error(response: Response) -> NoReturn:
    """
    Given an HTTP response, raise an appropriate SalesforceError.

    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/errorcodes.htm

    Parameters
    ----------
    response : httpx.Response
        HTTP response.

    Raises
    ------
    SalesforceError

    """
    try:
        response_json = json_loads(response.content)
        error_code = response_json[0]["errorCode"]
        error_message = response_json[0]["message"]
        if error_code == "DUPLICATES_DETECTED":
            error_message = "\n".join(
                [
                    error_message,
                    *[
                        "  %s (%s, %s, %s)"
                        % (
                            duplicate["id"],
                            f"{duplicate['match_confidence']:.1f}%",
                            duplicate["match_engine"],
                            duplicate["rule"],
                        )
                        for duplicate in DuplicatesDetectedError(
                            "", response
                        ).duplicates
                    ],
                ]
            )
    except Exception:
        error_code = None
        error_message = response.text

    exc_class: type[SalesforceError]
    match (response.status_code, error_code):
        case (300, _):
            exc_class = MoreThanOneRecordError
            try:
                records = [f"  {record}" for record in json_loads(response.content)]
            except Exception as exc:
                records = [f"  Failed to parse response: {exc}"]
            if error_code is None:
                error_message = "\n".join(
                    [
                        "More than one record found for external ID.",
                        f"{response.url}",
                        *records,
                    ]
                )
        case (_, "REQUEST_LIMIT_EXCEEDED"):
            exc_class = RequestLimitExceededError
        case (400, "DUPLICATES_DETECTED"):
            exc_class = DuplicatesDetectedError
        case (403, _):
            exc_class = AuthorizationError
        case (404, _):
            exc_class = NotFoundError
        case (status_code, _) if status_code >= 500:
            exc_class = ServerError
        case _:
            exc_class = SalesforceError

    raise exc_class(
        f"[{error_code}] {error_message}" if error_code else error_message,
        response=response,
        error_code=error_code,
        error_message=error_message,
    )

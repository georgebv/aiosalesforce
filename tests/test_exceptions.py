import orjson
import pytest

from aiosalesforce.exceptions import (
    AuthorizationError,
    MoreThanOneRecordError,
    NotFoundError,
    RequestLimitExceededError,
    SalesforceError,
    ServerError,
    raise_salesforce_error,
)
from httpx import Request, Response


def test_more_than_one_record_error():
    with pytest.raises(
        MoreThanOneRecordError,
        match="More than one record found.+\nhttps://example.com\n  /services/data.+",
    ):
        raise_salesforce_error(
            Response(
                300,
                content=orjson.dumps(
                    [
                        "/services/data/v60.0/sobjects/Contact/0033h00000Kzv3AAAR",
                        "/services/data/v60.0/sobjects/Contact/0033h00000Kzv3BAAZ",
                    ]
                ),
                request=Request(
                    "GET",
                    "https://example.com",
                ),
            )
        )


def test_more_than_one_record_error_bad_response():
    with pytest.raises(
        MoreThanOneRecordError,
        match="More than one record.*\n.*\n  Failed to parse response",
    ):
        raise_salesforce_error(
            Response(300, request=Request("GET", "https://example.com"))
        )


@pytest.mark.parametrize(
    "status_code,error_code,expected_exc",
    [
        (429, "REQUEST_LIMIT_EXCEEDED", RequestLimitExceededError),
        (403, None, AuthorizationError),
        (404, None, NotFoundError),
        (500, None, ServerError),
        (502, None, ServerError),
        (503, None, ServerError),
        (499, None, SalesforceError),
    ],
    ids=[
        "REQUEST_LIMIT_EXCEEDED",
        "403",
        "404",
        "500",
        "502",
        "503",
        "generic",
    ],
)
def test_exceptions(
    status_code: int, error_code: str, expected_exc: type[SalesforceError]
):
    with pytest.raises(expected_exc) as exc_info:
        raise_salesforce_error(
            Response(
                status_code,
                content=orjson.dumps(
                    [{"errorCode": error_code, "message": "error message"}]
                ),
            )
        )
    # pytest checks using isinstance, but we need to check the exact type
    assert exc_info.type is expected_exc

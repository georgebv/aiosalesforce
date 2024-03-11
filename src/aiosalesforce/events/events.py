import re

from dataclasses import dataclass
from functools import cached_property
from typing import Literal

from httpx import Request, Response


class ResponseMixin:
    response: Response

    @property
    def consumed(self) -> int | None:
        return self.__api_usage[0]

    @property
    def remaining(self) -> int | None:
        return self.__api_usage[1]

    @cached_property
    def __api_usage(self) -> tuple[int, int] | tuple[None, None]:
        if "application/json" not in self.response.headers.get("content-type", None):
            return (None, None)
        try:
            match_ = re.fullmatch(
                r"^api-usage=(\d+)/(\d+)$",
                str(self.response.headers["Sforce-Limit-Info"]).strip(),
            )
        except KeyError:
            return (None, None)
        if match_ is None:
            return (None, None)
        consumed, remaining = match_.groups()
        return int(consumed), int(remaining)


@dataclass
class Event:
    type: Literal[
        "request",
        "response",
        "retry",
        "rest_api_call_consumption",
        "bulk_api_batch_consumption",
    ]


@dataclass
class RequestEvent(Event):
    """Emitted before a request is sent for the first time."""

    type: Literal["request"]
    request: Request


@dataclass
class ResponseEvent(Event, ResponseMixin):
    """Emitted after an OK response is received after the last retry attempt."""

    type: Literal["response"]
    response: Response


@dataclass
class RetryEvent(Event, ResponseMixin):
    """Emitted immediately before a request is retried."""

    type: Literal["retry"]
    response: Response


@dataclass
class RestApiCallConsumptionEvent(Event, ResponseMixin):
    """Emitted after a REST API call is consumed."""

    type: Literal["rest_api_call_consumption"]
    response: Response


@dataclass
class BulkApiBatchConsumptionEvent(Event, ResponseMixin):
    """Emitted after a Bulk API batch is consumed."""

    type: Literal["bulk_api_batch_consumption"]
    response: Response

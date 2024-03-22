import re

from dataclasses import dataclass
from functools import cached_property
from typing import Literal

from httpx import Request, Response


class ResponseMixin:
    """Mixin class providing properties for events which may have response."""

    response: Response | None

    @property
    def consumed(self) -> int | None:
        """Number of API calls consumed in the current 24-hour period."""
        return self.__api_usage[0]

    @property
    def remaining(self) -> int | None:
        """Number of API calls remaining in the current 24-hour period."""
        return self.__api_usage[1]

    @cached_property
    def __api_usage(self) -> tuple[int, int] | tuple[None, None]:
        if self.response is None:
            return (None, None)
        try:
            match_ = re.fullmatch(
                r"^api-usage=(\d+)/(\d+)$",
                str(self.response.headers["Sforce-Limit-Info"]).strip(),
            )
        except KeyError:
            return (None, None)
        if match_ is None:  # pragma: no cover
            return (None, None)
        consumed, remaining = match_.groups()
        return int(consumed), int(remaining)


@dataclass
class Event:
    """Base class for all events."""

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
class RetryEvent(Event, ResponseMixin):
    """Emitted immediately before a request is retried."""

    type: Literal["retry"]
    attempt: int
    request: Request
    response: Response | None = None
    exception: Exception | None = None


@dataclass
class ResponseEvent(Event, ResponseMixin):
    """Emitted after an OK (status code < 300) response is received."""

    type: Literal["response"]
    response: Response


@dataclass
class RestApiCallConsumptionEvent(Event, ResponseMixin):
    """Emitted after a REST API call is consumed."""

    type: Literal["rest_api_call_consumption"]
    response: Response
    count: int


@dataclass
class BulkApiBatchConsumptionEvent(Event, ResponseMixin):
    """Emitted after a Bulk API batch is consumed."""

    type: Literal["bulk_api_batch_consumption"]
    response: Response
    count: int

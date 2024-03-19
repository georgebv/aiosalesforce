import asyncio
import random
import time

from typing import TypedDict

from httpx import Response

from .rules import ExceptionRule, ResponseRule


class RetryCounts(TypedDict):
    total: int
    exception: dict[ExceptionRule, int]
    response: dict[ResponseRule, int]


class RetryContext:
    """
    Context for retrying a particular request.

    Parameters
    ----------
    response_rules : list[ResponseRule]
        Rules for retrying requests based on their responses.
    exception_rules : list[ExceptionRule]
        Rules for retrying requests after an exception.
    max_retries : int
        Maximum total number of retries.

    """

    __slots__ = (
        "response_rules",
        "exception_rules",
        "max_retries",
        "timeout",
        "start",
        "retry_count",
    )

    response_rules: list[ResponseRule]
    exception_rules: list[ExceptionRule]
    max_retries: int
    timeout: float
    start: float
    retry_count: RetryCounts

    def __init__(
        self,
        response_rules: list[ResponseRule],
        exception_rules: list[ExceptionRule],
        max_retries: int,
        timeout: float,
    ) -> None:
        self.response_rules = response_rules
        self.exception_rules = exception_rules
        self.max_retries = max_retries
        self.timeout = timeout

        self.start = time.time()
        self.retry_count = {
            "total": 0,
            "response": {rule: 0 for rule in self.response_rules},
            "exception": {rule: 0 for rule in self.exception_rules},
        }

    async def should_retry(self, value: Response | Exception) -> bool:
        """
        Determine if the request should be retried.

        Parameters
        ----------
        value : Response | Exception
            Response or Exception from the request.

        Returns
        -------
        bool
            True if the request should be retried, False otherwise.

        """
        if (
            self.retry_count["total"] >= self.max_retries
            or time.time() - self.start > self.timeout
        ):
            return False
        condition: bool = False
        if isinstance(value, Response):
            condition = await self.__evaluate_response_rules(value)
        elif isinstance(value, Exception):
            condition = await self.__evaluate_exception_rules(value)
        else:
            raise TypeError(  # pragma: no cover
                "Value must be a Response or an Exception"
            )
        if condition:
            self.retry_count["total"] += 1
        return condition

    async def __evaluate_response_rules(self, response: Response) -> bool:
        for rule in self.response_rules:
            if self.retry_count["response"][rule] >= rule.max_retries:
                return False
            if await rule.should_retry(response):
                self.retry_count["response"][rule] += 1
                return True
        return False

    async def __evaluate_exception_rules(self, exception: Exception) -> bool:
        for rule in self.exception_rules:
            if self.retry_count["exception"][rule] >= rule.max_retries:
                return False
            if await rule.should_retry(exception):
                self.retry_count["exception"][rule] += 1
                return True
        return False


class RetryPolicy:
    """
    Policy for retrying requests.

    Parameters
    ----------
    response_rules : list[ResponseRule], optional
        Rules for retrying requests based on their responses.
    exception_rules : list[ExceptionRule], optional
        Rules for retrying requests after an exception.
    max_retries : int, optional
        Maximum total number of retries. By default 3.
    timeout : float, optional
        Maximum time to retry. By default 60 seconds.
        Timeout is best effort and may exceed the specified time
        by up to `backoff_max` seconds.
    backoff_base : float, optional
        Base time to sleep between retries. By default 0.5 seconds.
    backoff_factor : float, optional
        Factor to increase sleep time between retries. By default 2.
    backoff_max : float, optional
        Maximum time to sleep between retries. By default 10 seconds.
    backoff_jitter : bool, optional
        If True, adds jitter to sleep time. By default True.

    """

    response_rules: list[ResponseRule]
    exception_rules: list[ExceptionRule]
    max_retries: int
    timeout: float
    backoff_base: float
    backoff_factor: float
    backoff_max: float
    backoff_jitter: bool

    def __init__(
        self,
        response_rules: list[ResponseRule] | None = None,
        exception_rules: list[ExceptionRule] | None = None,
        max_retries: int = 3,
        timeout: float = 60,
        backoff_base: float = 0.5,
        backoff_factor: float = 2,
        backoff_max: float = 10,
        backoff_jitter: bool = True,
    ) -> None:
        self.exception_rules = exception_rules or []
        self.response_rules = response_rules or []
        self.max_retries = max_retries
        self.timeout = timeout
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.backoff_jitter = backoff_jitter

    def create_context(self) -> RetryContext:
        """
        Create a new retry context.

        Retry context is used to track the state of a retry operation.

        """
        return RetryContext(
            response_rules=self.response_rules,
            exception_rules=self.exception_rules,
            max_retries=self.max_retries,
            timeout=self.timeout,
        )

    async def sleep(self, attempt: int) -> None:
        """
        Sleep between retries.

        Calculated for current attempt using the configured backoff policy.

        Parameters
        ----------
        attempt : int
            Current retry attempt. First attempt is 0.

        """
        sleep_time = min(
            self.backoff_base * (self.backoff_factor**attempt),
            self.backoff_max,
        )
        if self.backoff_jitter:
            sleep_time = random.uniform(0, sleep_time)  # noqa: S311
        await asyncio.sleep(sleep_time)

import asyncio
import random
import time

from typing import TypedDict

from httpx import AsyncClient, Request, Response

from aiosalesforce.events import EventBus, RestApiCallConsumptionEvent, RetryEvent

from .rules import ExceptionRule, ResponseRule


class RetryBase:
    __slots__ = (
        "response_rules",
        "exception_rules",
        "max_retries",
        "timeout",
        "backoff_base",
        "backoff_factor",
        "backoff_max",
        "backoff_jitter",
    )

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
        self.response_rules = response_rules or []
        self.exception_rules = exception_rules or []
        self.max_retries = max_retries
        self.timeout = timeout
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.backoff_jitter = backoff_jitter


class RetryCounts(TypedDict):
    total: int
    exception: dict[ExceptionRule, int]
    response: dict[ResponseRule, int]


class RetryContext(RetryBase):
    """Context for handling retries for a single request."""

    __slots__ = ("start", "retry_count")

    start: float
    retry_count: RetryCounts

    def __init__(
        self,
        response_rules: list[ResponseRule],
        exception_rules: list[ExceptionRule],
        max_retries: int,
        timeout: float,
        backoff_base: float,
        backoff_factor: float,
        backoff_max: float,
        backoff_jitter: bool,
    ) -> None:
        super().__init__(
            response_rules=response_rules,
            exception_rules=exception_rules,
            max_retries=max_retries,
            timeout=timeout,
            backoff_base=backoff_base,
            backoff_factor=backoff_factor,
            backoff_max=backoff_max,
            backoff_jitter=backoff_jitter,
        )

        self.start = time.time()
        self.retry_count = {
            "total": 0,
            "response": {rule: 0 for rule in self.response_rules},
            "exception": {rule: 0 for rule in self.exception_rules},
        }

    async def send_request_with_retries(
        self,
        httpx_client: AsyncClient,
        event_bus: EventBus,
        semaphore: asyncio.Semaphore,
        request: Request,
    ) -> Response:
        """
        Send a request and retry it if necessary in accordance with the retry policy.

        Does not guarantee that the returned response is OK (status code < 300),
        only that the request was retried according to the policy.

        Emits the following events:\n
        * RetryEvent if the request is retried
        * RestApiCallConsumptionEvent for each request
            that did not raise an exception

        Parameters
        ----------
        httpx_client : AsyncClient
            HTTP client to send the request.
        event_bus : EventBus
            Event bus to publish events.
        semaphore : asyncio.Semaphore
            Semaphore to limit the number of simultaneous requests.
        request : Request
            Request to send.

        Returns
        -------
        Response
            Response from the request.
            Not guaranteed to be OK (status code < 300).

        """
        while True:
            try:
                async with semaphore:
                    response = await httpx_client.send(request)
            except Exception as exc:
                if await self.should_retry(exc):
                    await asyncio.gather(
                        self.sleep(),
                        event_bus.publish_event(
                            RetryEvent(
                                type="retry",
                                attempt=self.retry_count["total"],
                                request=request,
                                exception=exc,
                            )
                        ),
                    )
                    continue
                raise
            await event_bus.publish_event(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption",
                    response=response,
                    count=1,
                )
            )
            if not response.is_success and await self.should_retry(response):
                await asyncio.gather(
                    self.sleep(),
                    event_bus.publish_event(
                        RetryEvent(
                            type="retry",
                            attempt=self.retry_count["total"],
                            request=request,
                            response=response,
                        )
                    ),
                )
                continue
            return response

    async def should_retry(self, value: Response | Exception) -> bool:
        """
        Determine if the request should be retried.

        If the request should be retried, the total retry count and the retry count
        for the rule responsible for the retry are incremented.

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
        match value:
            case Response():
                condition = await self.__evaluate_response_rules(value)
            case Exception():
                condition = await self.__evaluate_exception_rules(value)
            case _:  # pragma: no cover
                raise TypeError("Value must be a Response or an Exception")
        if condition:
            self.retry_count["total"] += 1
        return condition

    async def __evaluate_response_rules(self, response: Response) -> bool:
        for rule in self.response_rules:
            if self.retry_count["response"][
                rule
            ] < rule.max_retries and await rule.should_retry(response):
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

    async def sleep(self) -> None:
        """Sleep between retries based on the backoff policy."""
        # (total - 1) because this is called after incrementing the total count
        sleep_time = min(
            self.backoff_base
            * (self.backoff_factor ** (self.retry_count["total"] - 1)),
            self.backoff_max,
        )
        if self.backoff_jitter:
            sleep_time = random.uniform(0, sleep_time)  # noqa: S311
        await asyncio.sleep(sleep_time)


class RetryPolicy(RetryBase):
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

    def create_context(self) -> RetryContext:
        """
        Create a new retry context.

        Retry context is used to handle retries for a single request.

        """
        return RetryContext(
            response_rules=self.response_rules,
            exception_rules=self.exception_rules,
            max_retries=self.max_retries,
            timeout=self.timeout,
            backoff_base=self.backoff_base,
            backoff_factor=self.backoff_factor,
            backoff_max=self.backoff_max,
            backoff_jitter=self.backoff_jitter,
        )

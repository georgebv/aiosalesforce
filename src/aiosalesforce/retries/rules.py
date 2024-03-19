import asyncio
import inspect

from typing import Awaitable, Callable, Generic, TypeVar

from httpx import Response

from aiosalesforce.exceptions import SalesforceError

E = TypeVar("E", bound=Exception)


class ResponseRule:
    """
    Rule for deciding if a request should be retried based its response.

    Parameters
    ----------
    func : Callable[[Response], Awaitable[bool] | bool]
        Function or coroutine to determine if the request should be retried.
    max_retries : int, optional
        Maximum number of retries. By default 3.

    """

    func: Callable[[Response], Awaitable[bool] | bool]
    max_retries: int

    def __init__(
        self,
        func: Callable[[Response], Awaitable[bool] | bool],
        /,
        max_retries: int = 3,
    ) -> None:
        self.func = func
        self.max_retries = max_retries

    async def should_retry(self, response: Response) -> bool:
        """
        Determine if the request should be retried.

        Parameters
        ----------
        response : Response
            Response from the request.

        Returns
        -------
        bool
            True if the request should be retried, False otherwise.

        """
        if inspect.iscoroutinefunction(self.func):
            return await self.func(response)
        else:
            return await asyncio.to_thread(
                self.func,  # type: ignore
                response,
            )


class ExceptionRule(Generic[E]):
    """
    Rule for deciding if a request should be retried after an exception.

    Parameters
    ----------
    exc_type : type[Exception]
        Type of exception to retry.
    func : Callable[[Exception], Awaitable[bool]  |  bool] | None, optional
        Function or coroutine to determine if the request should be retried.
        By default the provided exception is always retried.
    max_retries : int, optional
        Maximum number of retries. By default 3.

    """

    exception_type: type[E]
    func: Callable[[E], Awaitable[bool] | bool]
    max_retries: int

    def __init__(
        self,
        exc_type: type[E],
        func: Callable[[E], Awaitable[bool] | bool] | None = None,
        /,
        max_retries: int = 3,
    ) -> None:
        if issubclass(exc_type, SalesforceError):
            raise ValueError(
                "aiosalesforce exceptions cannot be retried by aiosalesforce because "
                "they are raised at the end of the request lifecycle - after all "
                "retries have been exhausted. This could lead to an infinite loop. "
                "If you need to retry aiosalesforce exceptions, consider using "
                "ResponseRule instead."
            )
        if exc_type is Exception:
            raise ValueError("Retrying built-in Exception is not allowed.")
        self.exception_type = exc_type
        self.func = func or (lambda _: True)
        self.max_retries = max_retries

    async def should_retry(self, exc: E) -> bool:
        """
        Determine if the request should be retried.

        Parameters
        ----------
        exc : Exception
            Exception from the request.

        Returns
        -------
        bool
            True if the request should be retried, False otherwise.

        """
        if not isinstance(exc, self.exception_type):
            return False
        if inspect.iscoroutinefunction(self.func):
            return await self.func(exc)
        else:
            return await asyncio.to_thread(
                self.func,  # type: ignore
                exc,
            )

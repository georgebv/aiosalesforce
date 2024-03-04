__all__ = [
    "Always",
    "Retry",
]

import asyncio
import logging
import random
import time

from httpx import Response

from .always import Always
from .base import RetryHook

logger = logging.getLogger(__name__)


class Retry:
    def __init__(
        self,
        retry_hooks: list[RetryHook],
        max_retries: int = 10,
        timeout: float = 60.0,
        backoff_base: float = 0.5,
        backoff_factor: float = 2.0,
        backoff_max: float = 20.0,
        backoff_jitter: bool = True,
    ) -> None:
        self.retry_hooks = retry_hooks
        self.max_retries = max_retries
        self.timeout = timeout
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.backoff_jitter = backoff_jitter

        self._start = time.time()
        self._attempt_count = 0

    def should_retry(self, response: Response) -> bool:
        if self._attempt_count >= self.max_retries:
            logger.debug("Max retries reached")
            return False
        if time.time() - self._start > self.timeout:
            logger.debug("Timeout reached")
            return False
        for hook in self.retry_hooks:
            if hook.should_retry(response):
                logger.debug(
                    "Retrying '%s %s' due to %s, this is attempt %d/%d",
                    response.request.method,
                    response.request.url,
                    hook.__class__.__name__,
                    self._attempt_count + 1,
                    self.max_retries,
                )
                self._attempt_count += 1
                return True
        return False

    async def sleep(self) -> None:
        delay = min(
            self.backoff_max,
            self.backoff_base
            * (self.backoff_factor ** max(0, self._attempt_count - 1)),
        )
        if self.backoff_jitter:
            delay = random.uniform(0, delay)  # noqa: S311
        logger.debug("Sleeping for %s seconds", delay)
        await asyncio.sleep(delay)

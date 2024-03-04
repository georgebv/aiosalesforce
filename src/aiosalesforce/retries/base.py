from abc import ABC, abstractmethod
from typing import final

from httpx import Response


class RetryHook(ABC):
    def __init__(self, max_retries: int = 10) -> None:
        """
        Configure retry behavior.

        Parameters
        ----------
        max_retries : int, optional
            Maximum number of retries. Defaults to 10.

        """
        self.max_retries = max_retries
        self._attempt_count = 0

    @final
    def should_retry(self, response: Response) -> bool:
        if self._attempt_count >= self.max_retries:
            return False
        if decision := self._decide(response):
            self._attempt_count += 1
        return decision

    @abstractmethod
    def _decide(self, response: Response) -> bool:
        pass

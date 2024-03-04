from httpx import Response

from .base import RetryHook


class Always(RetryHook):
    """
    Always retry the request.

    """

    def _decide(self, response: Response) -> bool:
        return True

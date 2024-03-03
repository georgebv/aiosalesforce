from abc import ABC, abstractmethod
from asyncio import Lock
from typing import final

from httpx import AsyncClient


class Auth(ABC):
    def __init__(self) -> None:
        self._access_token: str | None = None
        self._lock = Lock()

    @final
    async def get_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        if self._access_token is not None:
            return self._access_token
        async with self._lock:
            if self._access_token is None:
                self._access_token = await self._acquire_new_access_token(
                    client=client,
                    base_url=base_url,
                    version=version,
                )
            return self._access_token

    @final
    async def refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        if self._access_token is None:
            raise RuntimeError("No access token to refresh")
        token = self._access_token
        async with self._lock:
            if token == self._access_token:
                self._access_token = await self._refresh_access_token(
                    client=client,
                    base_url=base_url,
                    version=version,
                )
            return self._access_token

    @abstractmethod
    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        """
        Acquire a new access token from Salesforce.

        Parameters
        ----------
        client : AsyncClient
            HTTP client.
        base_url : str
            Salesforce base URL.
            E.g., "https://mydomain.my.salesforce.com".
        version : str
            REST API version.
            E.g., "57.0".

        Returns
        -------
        str
            Access token

        """

    @abstractmethod
    async def _refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        """
        Refresh the access token.

        Parameters
        ----------
        client : AsyncClient
            HTTP client.
        base_url : str
            Salesforce base URL.
            E.g., "https://mydomain.my.salesforce.com".
        version : str
            REST API version.
            E.g., "57.0".

        Returns
        -------
        str
            Access token

        """

import asyncio
import logging

from abc import ABC, abstractmethod
from typing import final

from httpx import AsyncClient

logger = logging.getLogger(__name__)


class Auth(ABC):
    def __init__(self) -> None:
        self.__access_token: str | None = None
        self.__lock = asyncio.Lock()

    @final
    async def get_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        """
        Get access token.

        If this is the first time this method is called, it will acquire a new
        access token from Salesforce.

        Parameters
        ----------
        client : httpx.AsyncClient
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
        if self.__access_token is not None:
            return self.__access_token
        async with self.__lock:
            if self.__access_token is None:
                logger.debug(
                    "Acquiring new access token using %s for %s",
                    self.__class__.__name__,
                    base_url,
                )
                self.__access_token = await self._acquire_new_access_token(
                    client=client,
                    base_url=base_url,
                    version=version,
                )
            return self.__access_token

    @final
    async def refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        """
        Refresh the access token.

        Parameters
        ----------
        client : httpx.AsyncClient
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
        if self.__access_token is None:
            raise RuntimeError("No access token to refresh")
        token_before_refresh = self.__access_token
        async with self.__lock:
            if self.__access_token == token_before_refresh:
                logger.debug(
                    "Refreshing access token using %s for %s",
                    self.__class__.__name__,
                    base_url,
                )
                self.__access_token = await self._refresh_access_token(
                    client=client,
                    base_url=base_url,
                    version=version,
                )
            return self.__access_token

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
        client : httpx.AsyncClient
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
        client : httpx.AsyncClient
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
        return await self._acquire_new_access_token(
            client=client,
            base_url=base_url,
            version=version,
        )

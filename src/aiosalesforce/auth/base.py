import asyncio
import logging

from abc import ABC, abstractmethod
from typing import final

from httpx import AsyncClient

from aiosalesforce.events import EventBus
from aiosalesforce.retries import RetryPolicy

logger = logging.getLogger(__name__)


class Auth(ABC):
    """
    Base class for Salesforce authentication.

    """

    def __init__(self) -> None:
        self.__access_token: str | None = None
        self.__lock = asyncio.Lock()

    @final
    async def get_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
        retry_policy: RetryPolicy,
        semaphore: asyncio.Semaphore,
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
        event_bus : aiosalesforce.events.EventBus
            Event bus.
        retry_policy : aiosalesforce.retries.RetryPolicy
            Retry policy.
        semaphore : asyncio.Semaphore
            Semaphore to limit the number of simultaneous requests.

        Returns
        -------
        str
            Access token

        """
        async with self.__lock:
            if self.__access_token is None:
                logger.debug(
                    "Acquiring new access token using %s for %s",
                    self.__class__.__name__,
                    base_url,
                )
                async with semaphore:
                    self.__access_token = await self._acquire_new_access_token(
                        client=client,
                        base_url=base_url,
                        version=version,
                        event_bus=event_bus,
                        retry_policy=retry_policy,
                    )
            elif self.expired:
                logger.debug(
                    "Token expired, refreshing access token using %s for %s",
                    self.__class__.__name__,
                    base_url,
                )
                async with semaphore:
                    self.__access_token = await self._refresh_access_token(
                        client=client,
                        base_url=base_url,
                        version=version,
                        event_bus=event_bus,
                        retry_policy=retry_policy,
                    )
            return self.__access_token

    @final
    async def refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
        retry_policy: RetryPolicy,
        semaphore: asyncio.Semaphore,
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
        event_bus : aiosalesforce.events.EventBus
            Event bus.
        retry_policy : aiosalesforce.retries.RetryPolicy
            Retry policy.
        semaphore : asyncio.Semaphore
            Semaphore to limit the number of simultaneous requests.

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
                async with semaphore:
                    self.__access_token = await self._refresh_access_token(
                        client=client,
                        base_url=base_url,
                        version=version,
                        event_bus=event_bus,
                        retry_policy=retry_policy,
                    )
            return self.__access_token

    @abstractmethod
    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
        retry_policy: RetryPolicy,
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
        event_bus : aiosalesforce.events.EventBus
            Event bus.
        retry_policy : aiosalesforce.retries.RetryPolicy
            Retry policy.

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
        event_bus: EventBus,
        retry_policy: RetryPolicy,
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
        event_bus : aiosalesforce.events.EventBus
            Event bus.
        retry_policy : aiosalesforce.retries.RetryPolicy
            Retry policy.

        Returns
        -------
        str
            Access token

        """
        return await self._acquire_new_access_token(
            client=client,
            base_url=base_url,
            version=version,
            event_bus=event_bus,
            retry_policy=retry_policy,
        )

    @property
    def expired(self) -> bool:
        """True if the access token is expired."""
        if self.__access_token is None:  # pragma: no cover
            raise RuntimeError("Cannot check expiration of a non-existent access token")
        # By default, assumes the access token never expires
        # Salesforce client automatically refreshes the token after 401 response
        return False

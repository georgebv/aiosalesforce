import asyncio
import logging

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class Auth(ABC):
    """
    Base class for Salesforce authentication.

    """

    def __init__(self) -> None:
        self.__access_token: str | None = None
        self.__lock = asyncio.Lock()

    @final
    async def get_access_token(self, client: "Salesforce") -> str:
        """
        Get access token.

        If this is the first time this method is called, it will acquire a new
        access token from Salesforce.

        Parameters
        ----------
        client : Salesforce
            Salesforce client.

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
                    client.base_url,
                )
                self.__access_token = await self._acquire_new_access_token(client)
            elif self.expired:
                logger.debug(
                    "Token expired, refreshing access token using %s for %s",
                    self.__class__.__name__,
                    client.base_url,
                )
                self.__access_token = await self._refresh_access_token(client)
            return self.__access_token

    @final
    async def refresh_access_token(self, client: "Salesforce") -> str:
        """
        Refresh the access token.

        Parameters
        ----------
        client : Salesforce
            Salesforce client.

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
                    client.base_url,
                )
                self.__access_token = await self._refresh_access_token(client)
            return self.__access_token

    @abstractmethod
    async def _acquire_new_access_token(self, client: "Salesforce") -> str:
        """
        Acquire a new access token from Salesforce.

        Implementation is responsible for emitting RequestEvent and ResponseEvent.

        Parameters
        ----------
        client : Salesforce
            Salesforce client.

        Returns
        -------
        str
            Access token

        """

    async def _refresh_access_token(self, client: "Salesforce") -> str:
        """
        Refresh the access token.

        Implementation is responsible for emitting RequestEvent and ResponseEvent.

        Parameters
        ----------
        client : Salesforce
            Salesforce client.

        Returns
        -------
        str
            Access token

        """
        return await self._acquire_new_access_token(client)

    @property
    def expired(self) -> bool:
        """True if the access token is expired."""
        if self.__access_token is None:  # pragma: no cover
            raise RuntimeError("Cannot check expiration of a non-existent access token")
        # By default, assumes the access token never expires
        # Salesforce client automatically refreshes the token after 401 response
        return False

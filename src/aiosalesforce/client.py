import logging
import re
import warnings

from functools import wraps
from typing import AsyncIterator

from httpx import AsyncClient, Response

from aiosalesforce import __version__
from aiosalesforce.auth import Auth
from aiosalesforce.exceptions import SalesforceWarning, raise_salesforce_error
from aiosalesforce.retries import Retry
from aiosalesforce.sobject import AsyncSobjectClient

logger = logging.getLogger(__name__)


class AsyncSalesforce:
    """
    Asynchronous Salesforce client.

    Parameters
    ----------
    http_client : AsyncClient
        Asynchronous HTTP client.
    base_url : str
        Base URL of the Salesforce instance.
        Must be in the format:
            - https://[MyDomainName].my.salesforce.com
            - https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com
    auth : Auth
        Authentication object.
    version : str, optional
        Salesforce API version.
        Uses the latest version

    """

    def __init__(
        self,
        http_client: AsyncClient,
        base_url: str,
        auth: Auth,
        version: str = "60.0",
        retry: Retry | None = None,
    ) -> None:
        self.http_client = http_client
        self.auth = auth
        self.version = version
        self.retry = retry

        # Validate url
        match_ = re.fullmatch(
            r"(https://[a-zA-Z0-9-]+(\.sandbox)?\.my\.salesforce\.com).*",
            base_url.strip(" ").lower(),
        )
        if not match_:
            raise ValueError(
                f"Invalid Salesforce URL in '{base_url}'. "
                f"Must be in the format "
                f"https://[MyDomainName].my.salesforce.com for production "
                f"or "
                f"https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com "
                f"for sandbox."
            )
        self.base_url = match_.groups()[0]

        self.__sobject_client: AsyncSobjectClient | None = None

    @wraps(AsyncClient.request)
    async def _request(self, *args, **kwargs) -> Response:
        while True:
            response = await self.__request(*args, **kwargs)
            request_failed = not response.is_success or response.status_code == 300
            if not request_failed:
                return response
            if self.retry is None or not self.retry.should_retry(response):
                raise_salesforce_error(response)
            await self.retry.sleep()

    async def __request(self, *args, **kwargs) -> Response:
        access_token = await self.auth.get_access_token(
            client=self.http_client,
            base_url=self.base_url,
            version=self.version,
        )
        headers: dict = kwargs.pop("headers", {})
        headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": f"aiosalesforce/{__version__}",
            }
        )
        request = self.http_client.build_request(*args, **kwargs, headers=headers)
        response = await self.http_client.send(request)
        if response.status_code == 401:
            access_token = await self.auth.refresh_access_token(
                client=self.http_client,
                base_url=self.base_url,
                version=self.version,
            )
            request.headers["Authorization"] = f"Bearer {access_token}"
            response = await self.http_client.send(request)
        if "Warning" in response.headers:
            warnings.warn(response.headers["Warning"], SalesforceWarning)
        return response

    async def query(self, query: str) -> AsyncIterator[dict]:
        """
        Execute a SOQL query.

        Includes only active records (NOT deleted/archived).

        Parameters
        ----------
        query : str
            SOQL query.

        Returns
        -------
        AsyncIterator[dict]
            An asynchronous iterator of query results.

        """
        next_url: str | None = None
        while True:
            if next_url is None:
                response = await self._request(
                    "GET",
                    f"{self.base_url}/services/data/v{self.version}/query",
                    params={"q": query},
                )
            else:
                response = await self._request("GET", f"{self.base_url}{next_url}")
            response_json: dict = response.json()
            for record in response_json["records"]:
                yield record
            next_url = response_json.get("nextRecordsUrl", None)
            if next_url is None:
                break

    async def query_all(self, query: str) -> AsyncIterator[dict]:
        """
        Execute a SOQL query.

        Includes all (active/deleted/archived) records.

        Parameters
        ----------
        query : str
            SOQL query.

        Returns
        -------
        AsyncIterator[dict]
            An asynchronous iterator of query results.

        """
        next_url: str | None = None
        while True:
            if next_url is None:
                response = await self._request(
                    "GET",
                    f"{self.base_url}/services/data/v{self.version}/queryAll",
                    params={"q": query},
                )
            else:
                response = await self._request("GET", f"{self.base_url}{next_url}")
            response_json: dict = response.json()
            for record in response_json["records"]:
                yield record
            next_url = response_json.get("nextRecordsUrl", None)
            if next_url is None:
                break

    @property
    def sobject(self) -> AsyncSobjectClient:
        """
        Salesforce REST API sObject client.

        """
        if self.__sobject_client is None:
            self.__sobject_client = AsyncSobjectClient(self)
        return self.__sobject_client

import logging
import re
import warnings

from functools import cached_property, wraps
from typing import AsyncIterator, Awaitable, Callable

import httpx

from aiosalesforce import __version__
from aiosalesforce.auth import Auth
from aiosalesforce.events import (
    Event,
    EventBus,
    RequestEvent,
    ResponseEvent,
    RestApiCallConsumptionEvent,
)
from aiosalesforce.exceptions import SalesforceWarning, raise_salesforce_error
from aiosalesforce.sobject import SobjectClient

logger = logging.getLogger(__name__)


class Salesforce:
    """
    Salesforce API client.

    Parameters
    ----------
    httpx_client : httpx.AsyncClient
        HTTP client.
    base_url : str
        Base URL of the Salesforce instance.
        Must be in the format:
            - Production    : https://[MyDomainName].my.salesforce.com
            - Sandbox       : https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com
            - Developer org : https://[MyDomainName].develop.my.salesforce.com
    auth : Auth
        Authentication object.
    version : str, optional
        Salesforce API version.
        By default, uses the latest version.
    event_hooks : list[Callable[[Event], Awaitable[None] | None]], optional
        List of event hooks.
        An event hook is a function taking a single argument which contains
        information (type and context) about the event.
        When an event occurs, all event hooks are called concurrently.
        Therefore, the order of execution is not guaranteed and it is the
        responsibility of the event hook to determine if it should react to the event.
        Asynchronous event hooks are awaited concurrently and synchronous hooks
        are executed using the running event loop's executor.

    """

    httpx_client: httpx.AsyncClient
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com"""
    auth: Auth
    version: str
    event_bus: EventBus

    def __init__(
        self,
        httpx_client: httpx.AsyncClient,
        base_url: str,
        auth: Auth,
        version: str = "60.0",
        event_hooks: list[Callable[[Event], Awaitable[None] | None]] | None = None,
    ) -> None:
        self.httpx_client = httpx_client
        self.auth = auth
        self.version = version

        # Validate url
        match_ = re.fullmatch(
            r"(https://[a-zA-Z0-9-]+(\.(sandbox|develop))?\.my\.salesforce\.com).*",
            base_url.strip(" ").lower(),
        )
        if not match_:
            raise ValueError(
                "\n".join(
                    [
                        f"Invalid Salesforce URL: {base_url}",
                        "Supported formats:",
                        "  Production    : https://[MyDomainName].my.salesforce.com",
                        "  Sandbox       : https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com",
                        "  Developer org : https://[MyDomainName].develop.my.salesforce.com",
                    ]
                )
            )
        self.base_url = str(match_.groups()[0])

        self.event_bus = EventBus(event_hooks)

    @wraps(httpx.AsyncClient.request)
    async def request(self, *args, **kwargs) -> httpx.Response:
        """
        Make an HTTP request to Salesforce.

        """
        request = self.httpx_client.build_request(*args, **kwargs)
        access_token = await self.auth.get_access_token(
            client=self.httpx_client,
            base_url=self.base_url,
            version=self.version,
            event_bus=self.event_bus,
        )
        request.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": f"aiosalesforce/{__version__}",
                "Sforce-Call-Options": f"client=aiosalesforce/{__version__}",
                "Sforce-Line-Ending": "LF",
            }
        )
        await self.event_bus.publish_event(
            RequestEvent(type="request", request=request)
        )
        refreshed: bool = False
        while True:
            response = await self.httpx_client.send(request)
            await self.event_bus.publish_event(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption", response=response
                )
            )
            if response.status_code < 300:
                break
            if response.status_code == 401:
                if refreshed:
                    raise_salesforce_error(response)
                access_token = await self.auth.refresh_access_token(
                    client=self.httpx_client,
                    base_url=self.base_url,
                    version=self.version,
                    event_bus=self.event_bus,
                )
                request.headers["Authorization"] = f"Bearer {access_token}"
                refreshed = True
                continue
            # TODO Check retry policies; emit retry event
            raise_salesforce_error(response)
        if "Warning" in response.headers:
            warnings.warn(response.headers["Warning"], SalesforceWarning)
        await self.event_bus.publish_event(
            ResponseEvent(type="response", response=response)
        )
        return response

    async def query(
        self,
        query: str,
        include_deleted_records: bool = False,
    ) -> AsyncIterator[dict]:
        """
        Execute a SOQL query.

        Parameters
        ----------
        query : str
            SOQL query.
        include_deleted_records : bool, optional
            If True, includes all (active/deleted/archived) records.

        Returns
        -------
        AsyncIterator[dict]
            An asynchronous iterator of query results.

        """
        operation = "query" if not include_deleted_records else "queryAll"

        next_url: str | None = None
        while True:
            if next_url is None:
                response = await self.request(
                    "GET",
                    f"{self.base_url}/services/data/v{self.version}/{operation}",
                    params={"q": query},
                )
            else:
                response = await self.request("GET", f"{self.base_url}{next_url}")
            response_json: dict = response.json()
            for record in response_json["records"]:
                yield record
            next_url = response_json.get("nextRecordsUrl", None)
            if next_url is None:
                break

    @cached_property
    def sobject(self) -> SobjectClient:
        """
        Salesforce REST API sObject client.

        Use this client to perform CRUD operations on individual sObjects.

        """
        return SobjectClient(self)

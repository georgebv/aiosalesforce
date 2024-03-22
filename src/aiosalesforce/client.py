import asyncio
import itertools
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
    RetryEvent,
)
from aiosalesforce.exceptions import SalesforceWarning, raise_salesforce_error
from aiosalesforce.retries import POLICY_DEFAULT, RetryPolicy
from aiosalesforce.sobject import SobjectClient
from aiosalesforce.utils import json_loads

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
            Production    : https://[MyDomainName].my.salesforce.com
            Sandbox       : https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com
            Developer org : https://[MyDomainName].develop.my.salesforce.com
    auth : Auth
        Authentication object.
    version : str, optional
        Salesforce API version.
        By default, uses the latest version.
    event_hooks : list[Callable[[Event], Awaitable[None] | None]], optional
        List of functions or coroutines executed when an event occurs.
        Hooks are executed concurrently and order of execution is not guaranteed.
        All hooks must be thread-safe.
    retry_policy : RetryPolicy, optional
        Retry policy for requests.
        The default policy retries requests up to 3 times with exponential backoff
        and retries the following:
            httpx Transport errors (excluding timeouts)
            Server errors (5xx)
            Row lock errors
            Rate limit errors
        Set to None to disable retries.
    concurrency_limit : int, optional
        Maximum number of simultaneous requests to Salesforce.
        The default is 100.

    """

    httpx_client: httpx.AsyncClient
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com"""
    auth: Auth
    version: str
    event_bus: EventBus
    retry_policy: RetryPolicy
    __semaphore: asyncio.Semaphore

    def __init__(
        self,
        httpx_client: httpx.AsyncClient,
        base_url: str,
        auth: Auth,
        version: str = "60.0",
        event_hooks: list[Callable[[Event], Awaitable[None] | None]] | None = None,
        retry_policy: RetryPolicy | None = POLICY_DEFAULT,
        concurrency_limit: int = 100,
    ) -> None:
        self.httpx_client = httpx_client
        self.auth = auth

        # Validate version
        if not (match_ := re.fullmatch(r"^(v)?(\d+)(\.(0)?)?$", version)):
            raise ValueError(
                f"Invalid Salesforce API version: '{version}'. "
                f"A valid version should look like '60.0'."
            )
        self.version = f"{match_.groups()[1]}.0"

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
        self.retry_policy = retry_policy or RetryPolicy()
        self.__semaphore = asyncio.Semaphore(concurrency_limit)

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
            retry_policy=self.retry_policy,
            semaphore=self.__semaphore,
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

        retry_context = self.retry_policy.create_context()
        refreshed: bool = False
        for attempt in itertools.count():
            try:
                async with self.__semaphore:
                    response = await self.httpx_client.send(request)
            except Exception as exc:
                if await retry_context.should_retry(exc):
                    await asyncio.gather(
                        self.retry_policy.sleep(attempt),
                        self.event_bus.publish_event(
                            RetryEvent(
                                type="retry",
                                attempt=attempt + 1,
                                request=request,
                                exception=exc,
                            )
                        ),
                    )
                    continue
                raise
            await self.event_bus.publish_event(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption",
                    response=response,
                    count=1,
                )
            )
            if response.is_success:
                break
            if response.status_code == 401:
                if refreshed:
                    raise_salesforce_error(response)
                access_token = await self.auth.refresh_access_token(
                    client=self.httpx_client,
                    base_url=self.base_url,
                    version=self.version,
                    event_bus=self.event_bus,
                    retry_policy=self.retry_policy,
                    semaphore=self.__semaphore,
                )
                request.headers["Authorization"] = f"Bearer {access_token}"
                refreshed = True
                continue
            if await retry_context.should_retry(response):
                await asyncio.gather(
                    self.retry_policy.sleep(attempt),
                    self.event_bus.publish_event(
                        RetryEvent(
                            type="retry",
                            attempt=attempt + 1,
                            request=request,
                            response=response,
                        )
                    ),
                )
                continue
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
        include_all_records: bool = False,
    ) -> AsyncIterator[dict]:
        """
        Execute a SOQL query.

        Parameters
        ----------
        query : str
            SOQL query.
        include_all_records : bool, default False
            If True, includes all (active/deleted/archived) records.

        Returns
        -------
        AsyncIterator[dict]
            An asynchronous iterator of query results.

        """
        operation = "query" if not include_all_records else "queryAll"

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
            response_json: dict = json_loads(response.content)
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

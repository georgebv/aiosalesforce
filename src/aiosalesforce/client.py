import re
import warnings

from typing import AsyncIterator

from httpx import AsyncClient, Response

from aiosalesforce import __version__
from aiosalesforce.exceptions import (
    InvalidTypeError,
    MalformedQueryError,
    NotFoundError,
    RequestLimitExceededError,
    SalesforceError,
    SalesforceWarning,
)

from .auth import Auth


class AsyncSalesforce:
    def __init__(
        self,
        http_client: AsyncClient,
        base_url: str,
        auth: Auth,
        version: str = "60.0",
    ) -> None:
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
        self.http_client = http_client
        self.auth = auth
        self.version = version

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

    async def _request(self, *args, **kwargs) -> Response:
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
        if not response.is_success:
            errors: list[SalesforceError] = []
            for error in response.json():
                match (response.status_code, error["errorCode"]):
                    case (_, "REQUEST_LIMIT_EXCEEDED"):
                        errors.append(
                            RequestLimitExceededError(
                                error["message"],
                                response,
                            )
                        )
                    case (_, "MALFORMED_QUERY"):
                        errors.append(
                            MalformedQueryError(
                                error["message"],
                                response,
                            )
                        )
                    case (_, "INVALID_TYPE"):
                        errors.append(
                            InvalidTypeError(
                                error["message"],
                                response,
                            )
                        )
                    case (_, "NOT_FOUND"):
                        errors.append(
                            NotFoundError(
                                error["message"],
                                response,
                            )
                        )
                    case _:
                        errors.append(
                            SalesforceError(
                                f"{error['errorCode']}: {error['message']}",
                                response,
                            )
                        )
            raise ExceptionGroup(
                "\n".join(
                    [
                        "",
                        f"{response.status_code}: {response.reason_phrase}",
                        f"{request.method} {request.url}",
                    ]
                ),
                errors,
            )
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

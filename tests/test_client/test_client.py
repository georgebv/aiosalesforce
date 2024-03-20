import functools

from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx

from aiosalesforce import (
    ExceptionRule,
    RequestEvent,
    ResponseEvent,
    RestApiCallConsumptionEvent,
    RetryPolicy,
    Salesforce,
)
from aiosalesforce.auth import SoapLogin


class TestInit:
    def test_default(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        soap_auth: SoapLogin,
    ):
        salesforce = Salesforce(
            httpx_client=httpx_client,
            base_url=config["base_url"],
            auth=soap_auth,
        )
        assert salesforce.httpx_client is httpx_client
        assert salesforce.base_url == config["base_url"]
        assert salesforce.auth is soap_auth

    @pytest.mark.parametrize("version", ["v57.0", "69.4"])
    def test_invalid_version(
        self, version: str, config: dict[str, str], httpx_client: httpx.AsyncClient
    ):
        with pytest.raises(ValueError):
            Salesforce(
                httpx_client=httpx_client,
                base_url=config["base_url"],
                auth=SoapLogin(
                    username=config["username"],
                    password=config["password"],
                    security_token=config["security_token"],
                ),
                version=version,
            )

    @pytest.mark.parametrize(
        "base_url,expected_url",
        [
            (
                "https://example.com",
                None,
            ),
            (
                "https://example.my.salesforce.com",
                "https://example.my.salesforce.com",
            ),
            (
                "https://Example.my.Salesforce.com",
                "https://example.my.salesforce.com",
            ),
            (
                "https://Example.my.Salesforce.com/some/path?query=string",
                "https://example.my.salesforce.com",
            ),
            (
                "https://Example.sandbox.my.Salesforce.com",
                "https://example.sandbox.my.salesforce.com",
            ),
            (
                "https://example-partial.sandbox.my.Salesforce.com",
                "https://example-partial.sandbox.my.salesforce.com",
            ),
            (
                "https://Example.develop.my.Salesforce.com",
                "https://example.develop.my.salesforce.com",
            ),
            (
                "https://Example.staging.my.Salesforce.com",
                None,
            ),
            (
                "https://Example.my.develop.Salesforce.com",
                None,
            ),
            (
                "https://subdomain.example.my.salesforce.com",
                None,
            ),
            (
                "https://login.salesforce.com",
                None,
            ),
        ],
        ids=[
            "not salesforce",
            "production",
            "production (case insensitive)",
            "production (with path)",
            "sandbox",
            "sandbox (with dash)",
            "developer org",
            "invalid-1",
            "invalid-2",
            "invalid-3",
            "invalid-4",
        ],
    )
    def test_base_url_validation(
        self,
        base_url: str,
        expected_url: str | None,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
    ):
        partial = functools.partial(
            Salesforce,
            httpx_client=httpx_client,
            auth=SoapLogin(
                username=config["username"],
                password=config["password"],
                security_token=config["security_token"],
            ),
            version=config["api_version"],
        )
        if expected_url is None:
            with pytest.raises(ValueError):
                partial(base_url=base_url)
        else:
            salesforce = partial(base_url=base_url)
            assert salesforce.base_url == expected_url


class TestRequest:
    async def test_request(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        """Simple request (no retries, warnings, etc.)."""
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(return_value=httpx.Response(status_code=200))

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request
        response = await salesforce.request("GET", url)
        assert response.status_code == 200

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 3 for request (request, consumption, response)
        # We only test events related to request itself
        assert event_hook.await_count == 6
        event_hook.assert_has_awaits(
            [
                call(RequestEvent(type="request", request=response.request)),
                call(
                    RestApiCallConsumptionEvent(
                        type="rest_api_call_consumption", response=response
                    )
                ),
                call(ResponseEvent(type="response", response=response)),
            ]
        )

    async def test_retry_on_exception(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.ConnectError,
                httpx.ConnectError,
                httpx.ConnectError,
                httpx.Response(status_code=200),
            ],
        )

        # Configure retry policy
        salesforce.retry_policy = RetryPolicy(
            max_retries=3,
            exception_rules=[ExceptionRule(httpx.ConnectError)],
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            response = await salesforce.request("GET", url)
        assert response.status_code == 200

        # Assert event hook was called:
        # - 3 for auth
        # - 3 for request (request, consumption, response)
        # - 3 for retry (exception retries don't consume API calls)
        assert event_hook.await_count == 9
        assert sleep_mock.await_count == 3

    async def test_retry_on_exception_exceed_limit(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.ConnectError,
                httpx.ConnectError,
                httpx.ConnectError,
                httpx.ConnectError,
                httpx.Response(status_code=200),
            ],
        )

        # Configure retry policy
        salesforce.retry_policy = RetryPolicy(
            max_retries=3,
            exception_rules=[ExceptionRule(httpx.ConnectError)],
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with (
            patch("asyncio.sleep", sleep_mock),
            pytest.raises(httpx.ConnectError),
        ):
            await salesforce.request("GET", url)

        # Assert event hook was called:
        # - 3 for auth
        # - 1 for request (request)
        # - 3 for retry (exception retries don't consume API calls)
        assert event_hook.await_count == 7
        assert sleep_mock.await_count == 3

    # TODO Response retry
    # TODO Reauthentication + failed reauthentication
    # TODO Error handling
    # TODO Warnings
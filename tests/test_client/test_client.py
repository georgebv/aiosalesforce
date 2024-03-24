import functools

from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx

from aiosalesforce import (
    ExceptionRule,
    RequestEvent,
    ResponseEvent,
    ResponseRule,
    RestApiCallConsumptionEvent,
    RetryPolicy,
    Salesforce,
)
from aiosalesforce.auth import SoapLogin
from aiosalesforce.exceptions import SalesforceError, SalesforceWarning, ServerError


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

    @pytest.mark.parametrize(
        "version,expected_version",
        [
            ("57", "57.0"),
            ("57.", "57.0"),
            ("57.0", "57.0"),
            ("v57", "57.0"),
            ("v57.", "57.0"),
            ("v57.0", "57.0"),
            ("69.4", None),
            ("69.4", None),
        ],
        ids=[
            "57 - valid",
            "57. - valid",
            "57.0 - valid",
            "v57 - valid",
            "v57. - valid",
            "v57.0 - valid",
            "69.4 - invalid",
            "69.1.2 - invalid",
        ],
    )
    def test_invalid_version(
        self,
        version: str,
        expected_version: str | None,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
    ):
        partial = functools.partial(
            Salesforce,
            httpx_client=httpx_client,
            base_url=config["base_url"],
            auth=SoapLogin(
                username=config["username"],
                password=config["password"],
                security_token=config["security_token"],
            ),
        )
        if expected_version is None:
            with pytest.raises(ValueError, match="Invalid Salesforce API version"):
                partial(version=version)
        else:
            salesforce = partial(version=version)
            assert salesforce.version == expected_version

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
            with pytest.raises(ValueError, match=r"Invalid Salesforce URL"):
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
        assert event_hook.await_count == 6
        # Only test events related to request itself
        event_hook.assert_has_awaits(
            [
                call(RequestEvent(type="request", request=response.request)),
                call(
                    RestApiCallConsumptionEvent(
                        type="rest_api_call_consumption",
                        response=response,
                        count=1,
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
        # - 3 for auth (request, consumption, response)
        # - 1 for initial request (request)
        # - 3 for retry (retry) (exception retries don't consume API calls)
        # - 2 for response (consumption, response)
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
        # - 3 for auth (request, consumption, response)
        # - 1 for initial request (request)
        # - 3 for retry (retry) (exception retries don't consume API calls)
        assert event_hook.await_count == 7
        assert sleep_mock.await_count == 3

    async def test_retry_on_response(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=500),
                httpx.Response(status_code=503),
                httpx.Response(status_code=200),
            ],
        )

        # Configure retry policy
        salesforce.retry_policy = RetryPolicy(
            max_retries=3,
            response_rules=[ResponseRule(lambda r: r.status_code >= 500)],
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
        # - 3 for auth (request, consumption, response)
        # - 1 for initial request (request, consumption)
        # - 3 for retry (retry)
        # - 2 for response (consumption, response)
        assert event_hook.await_count == 10
        assert sleep_mock.await_count == 2

    async def test_retry_on_response_exceed_limit(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=500),
                httpx.Response(status_code=503),
                httpx.Response(status_code=500),
                httpx.Response(status_code=503),
                httpx.Response(status_code=200),
            ],
        )

        # Configure retry policy
        salesforce.retry_policy = RetryPolicy(
            max_retries=3,
            response_rules=[ResponseRule(lambda r: r.status_code >= 500)],
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with (
            patch("asyncio.sleep", sleep_mock),
            pytest.raises(ServerError),
        ):
            await salesforce.request("GET", url)

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 2 for initial request (request, consumption)
        # - 6 for retry (3 retry + 3 consumption)
        assert event_hook.await_count == 11
        assert sleep_mock.await_count == 3

    async def test_expired_authentication_refresh(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=401),
                httpx.Response(status_code=200),
            ],
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request
        response = await salesforce.request("GET", url)
        assert response.status_code == 200

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 2 for initial failed request (request, consumption)
        # - 3 for auth retry (request, consumption, response)
        # - 2 for request (consumption, response)
        assert event_hook.await_count == 10

    async def test_expired_authentication_refresh_failure(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        """Authentication refresh is attempted only once, second attempt fails."""
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=401),
                httpx.Response(status_code=401),
            ],
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request
        with pytest.raises(SalesforceError):
            await salesforce.request("GET", url)

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 2 for initial failed request (request, consumption)
        # - 3 for auth retry (request, consumption, response)
        # - 1 for second failed request (consumption)
        assert event_hook.await_count == 9

    async def test_salesforce_warning(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        """Test warning response header causes a warning to be issued."""
        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            return_value=httpx.Response(
                status_code=200,
                headers={"Warning": '299 - "example warning"'},
            ),
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute request
        with pytest.warns(SalesforceWarning, match=r'299 - "example warning"'):
            response = await salesforce.request("GET", url)
        assert response.status_code == 200

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 3 for request (request, consumption, response)
        assert event_hook.await_count == 6


async def test_get_limits(
    httpx_mock_router: respx.MockRouter,
    salesforce: Salesforce,
):
    # Mock request
    expected_response = {"test": {"get": "limits"}}
    httpx_mock_router.get(
        f"{salesforce.base_url}/services/data/v{salesforce.version}/limits",
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=expected_response,
        ),
    )

    # Execute request
    response = await salesforce.get_limits()
    assert response == expected_response


class TestSoql:
    @pytest.mark.parametrize(
        "expected_records",
        [
            [],
            [{"Id": "003000000000001"}],
            [{"Id": "003000000000001"}, {"Id": "003000000000002"}],
        ],
        ids=["no records", "single record", "multiple records"],
    )
    async def test_single_page(
        self,
        expected_records: list[dict[str, str]],
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        query = "SELECT Id FROM Contact WHERE Email = 'jdoe@example.com'"

        # Mock request
        httpx_mock_router.get(
            f"{config['base_url']}/services/data/v{config['api_version']}/query",
            params={"q": query},
        ).mock(
            return_value=httpx.Response(
                status_code=200,
                json={
                    "done": True,
                    "totalSize": len(expected_records),
                    "records": expected_records,
                },
            ),
        )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute query
        records = []
        async for record in salesforce.query(query):
            records.append(record)
        assert records == expected_records

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 3 for request (request, consumption, response)
        assert event_hook.await_count == 6

    async def test_multiple_pages(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        salesforce: Salesforce,
    ):
        query = "SELECT Id FROM Contact WHERE Email = 'jdoe@example.com'"

        # Mock requests
        url = f"{config['base_url']}/services/data/v{config['api_version']}/query"
        for i in range(3):
            response_json = {
                "done": i == 2,
                "totalSize": 6000,
                "records": [
                    {"Id": f"00300000000000{j}"}
                    for j in range(i * 2000, (i + 1) * 2000)
                ],
            }
            if i < 2:
                response_json["nextRecordsUrl"] = (
                    f"/services/data/v{config['api_version']}/query/01g00000000000{i+1}"
                )
            httpx_mock_router.get(
                url if i == 0 else url + f"/01g00000000000{i}",
                params={"q": query} if i == 0 else None,
            ).mock(
                return_value=httpx.Response(
                    status_code=200,
                    json=response_json,
                ),
            )

        # Subscribe a mock event hook
        event_hook = AsyncMock()
        salesforce.event_bus.subscribe_callback(event_hook)

        # Execute query
        records = []
        async for record in salesforce.query(query):
            records.append(record)
        assert len(records) == 6000

        # Assert event hook was called:
        # - 3 for auth (request, consumption, response)
        # - 9 for request (request, consumption, response) x 3
        assert event_hook.await_count == 12

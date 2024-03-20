import asyncio
import time

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
import time_machine

from aiosalesforce.auth import Auth, ClientCredentialsFlow, SoapLogin
from aiosalesforce.events import EventBus
from aiosalesforce.exceptions import AuthenticationError


class TestBaseAuth:
    async def test_get_access_token(self):
        """Token is acquired only once when called multiple times."""
        func = AsyncMock()
        func.return_value = "test-token"
        httpx_client = MagicMock()
        event_bus = EventBus()
        auth = type("CustomAuth", (Auth,), {"_acquire_new_access_token": func})()
        tokens = await asyncio.gather(
            *[
                auth.get_access_token(
                    client=httpx_client,
                    base_url="https://example.com",
                    version="60.0",
                    event_bus=event_bus,
                )
                for _ in range(10)
            ],
        )
        assert len(tokens) == 10
        assert len(set(tokens)) == 1
        assert tokens[0] == "test-token"
        func.assert_awaited_once_with(
            client=httpx_client,
            base_url="https://example.com",
            version="60.0",
            event_bus=event_bus,
        )

    async def test_refresh_access_token_error(self):
        auth = type(
            "CustomAuth",
            (Auth,),
            {"_acquire_new_access_token": lambda: "test"},
        )()
        with pytest.raises(RuntimeError, match="No access token to refresh"):
            await auth.refresh_access_token(
                client=MagicMock(),
                base_url="https://example.com",
                version="60.0",
                event_bus=EventBus(),
            )

    async def test_refresh_access_token_concurrent(self):
        """Token is refreshed only once when called multiple times concurrently."""
        get_func = AsyncMock()
        get_func.return_value = "test-token-before"
        refresh_func = AsyncMock()
        refresh_func.return_value = "test-token-after"
        httpx_client = MagicMock()
        event_bus = EventBus()
        auth = type(
            "CustomAuth",
            (Auth,),
            {
                "_acquire_new_access_token": get_func,
                "_refresh_access_token": refresh_func,
            },
        )()

        # Get the token before refreshing it
        token = await auth.get_access_token(
            client=httpx_client,
            base_url="https://example.com",
            version="60.0",
            event_bus=event_bus,
        )
        assert token == "test-token-before"  # noqa: S105
        get_func.assert_awaited_once_with(
            client=httpx_client,
            base_url="https://example.com",
            version="60.0",
            event_bus=event_bus,
        )

        # To ensure all refreshes are concurrent lock is held until
        # all of the tasks are waiting for it
        tasks: list[asyncio.Task[str]] = []
        async with asyncio.TaskGroup() as tg:
            await auth._Auth__lock.acquire()
            for _ in range(10):
                tasks.append(
                    tg.create_task(
                        auth.refresh_access_token(
                            client=httpx_client,
                            base_url="https://example.com",
                            version="60.0",
                            event_bus=event_bus,
                        ),
                    )
                )
            # Yield control to the event loop to allow the tasks to start
            # and reach a point where they are waiting for the lock
            await asyncio.sleep(0)
            auth._Auth__lock.release()
        tokens = [task.result() for task in tasks]
        assert len(tokens) == 10
        assert len(set(tokens)) == 1
        assert tokens[0] == "test-token-after"
        refresh_func.assert_awaited_once_with(
            client=httpx_client,
            base_url="https://example.com",
            version="60.0",
            event_bus=event_bus,
        )


class TestSoapLogin:
    async def test_soap_login(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        mock_soap_login: str,
    ):
        event_hook = AsyncMock()
        event_bus = EventBus([event_hook])
        auth = SoapLogin(
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"],
        )
        received_session_id = await auth.get_access_token(
            client=httpx_client,
            base_url=config["base_url"],
            version=config["api_version"],
            event_bus=event_bus,
        )
        assert received_session_id == mock_soap_login
        assert event_hook.await_count == 3

    @pytest.mark.usefixtures("mock_soap_login")
    async def test_soap_login_expiration(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
    ):
        auth = SoapLogin(
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"],
        )
        await auth.get_access_token(
            client=httpx_client,
            base_url=config["base_url"],
            version=config["api_version"],
            event_bus=EventBus(),
        )
        assert auth._expiration_time is not None
        assert auth._expiration_time > time.time()
        assert not auth.expired
        with time_machine.travel(
            time.time() + 60 * 60 * 24,
            tick=False,
        ):
            assert auth.expired
            await auth.get_access_token(
                client=httpx_client,
                base_url=config["base_url"],
                version=config["api_version"],
                event_bus=EventBus(),
            )
            assert not auth.expired

    @pytest.mark.usefixtures("mock_soap_login")
    async def test_soap_login_invalid_credentials(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
    ):
        auth = SoapLogin(
            username=config["username"],
            password="wrong-password",  # noqa: S106
            security_token=config["security_token"],
        )
        with pytest.raises(
            AuthenticationError,
            match=r"\[INVALID_LOGIN\] Invalid username, .*",
        ):
            await auth.get_access_token(
                client=httpx_client,
                base_url=config["base_url"],
                version=config["api_version"],
                event_bus=EventBus(),
            )


class TestClientCredentialsFlow:
    async def test_client_credentials_flow(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        expected_access_token = "SUPER-SECRET-ACCESS-TOKEN"  # noqa: S105

        httpx_mock_router.post(
            f"{config['base_url']}/services/oauth2/token",
        ).mock(
            httpx.Response(
                status_code=200,
                json={
                    "access_token": expected_access_token,
                    "instance_url": "https://example.salesforce.com",
                    "id": (
                        "https://login.salesforce.com/id"
                        "/00Dxx0000000000AAA/005xx0000000xxxAAA"
                    ),
                    "token_type": "Bearer",
                    "scope": "full",
                    "issued_at": int(time.time()),
                    "signature": "SUPER-SECRET-SIGNATURE",
                },
            )
        )

        event_hook = AsyncMock()
        event_bus = EventBus([event_hook])
        auth = ClientCredentialsFlow(
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",  # noqa: S106
        )
        access_token = await auth.get_access_token(
            client=httpx_client,
            base_url=config["base_url"],
            version=config["api_version"],
            event_bus=event_bus,
        )
        assert access_token == expected_access_token
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            # Access token for the Client Credentials Flow never expires
            assert not auth.expired
        assert event_hook.await_count == 3

    async def test_client_credentials_flow_invalid_credentials(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        httpx_mock_router.post(
            f"{config['base_url']}/services/oauth2/token",
        ).mock(
            httpx.Response(
                status_code=401,
                json={
                    "error": "invalid_client_id",
                    "error_description": "client identifier invalid",
                },
            )
        )

        auth = ClientCredentialsFlow(
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",  # noqa: S106
        )
        with pytest.raises(
            AuthenticationError,
            match=r"\[invalid_client_id\] client identifier invalid",
        ):
            await auth.get_access_token(
                client=httpx_client,
                base_url=config["base_url"],
                version=config["api_version"],
                event_bus=EventBus(),
            )

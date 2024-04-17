import asyncio
import pathlib
import time

from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
import respx
import time_machine

from aiosalesforce.auth import Auth, ClientCredentialsFlow, JwtBearerFlow, SoapLogin
from aiosalesforce.client import Salesforce
from aiosalesforce.events import EventBus
from aiosalesforce.exceptions import AuthenticationError
from aiosalesforce.retries import RetryPolicy
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key


@pytest.fixture(scope="function")
def pseudo_client(config: dict[str, str], httpx_client: httpx.AsyncClient):
    """Imitate a Salesforce client to test authentication."""
    request_func = AsyncMock()
    yield type(
        "Salesforce",
        (),
        {
            "httpx_client": httpx_client,
            "base_url": config["base_url"],
            # auth is not mocked because it's not used in these tests
            "version": config["api_version"],
            "event_bus": EventBus(),
            "retry_policy": RetryPolicy(),
            "_semaphore": asyncio.Semaphore(100),
            "request": request_func,
        },
    )
    request_func.assert_not_awaited()


class TestBaseAuth:
    async def test_get_access_token(self, pseudo_client: Salesforce):
        """Token is acquired only once when called multiple times."""
        func = AsyncMock()
        func.return_value = "test-token"
        auth = type("CustomAuth", (Auth,), {"_acquire_new_access_token": func})()
        tokens = await asyncio.gather(
            *[auth.get_access_token(pseudo_client) for _ in range(10)],
        )
        assert len(tokens) == 10
        assert len(set(tokens)) == 1
        assert tokens[0] == "test-token"
        func.assert_awaited_once_with(pseudo_client)

    async def test_refresh_access_token_error(self, pseudo_client: Salesforce):
        auth = type(
            "CustomAuth",
            (Auth,),
            {"_acquire_new_access_token": lambda: "test"},
        )()
        with pytest.raises(RuntimeError, match="No access token to refresh"):
            await auth.refresh_access_token(pseudo_client)

    async def test_refresh_access_token_concurrent(self, pseudo_client: Salesforce):
        """Token is refreshed only once when called multiple times concurrently."""
        get_func = AsyncMock()
        get_func.return_value = "test-token-before"
        refresh_func = AsyncMock()
        refresh_func.return_value = "test-token-after"
        auth = type(
            "CustomAuth",
            (Auth,),
            {
                "_acquire_new_access_token": get_func,
                "_refresh_access_token": refresh_func,
            },
        )()

        # Get the token before refreshing it
        token = await auth.get_access_token(pseudo_client)
        assert token == "test-token-before"  # noqa: S105
        get_func.assert_awaited_once_with(pseudo_client)

        # To ensure all refreshes are concurrent lock is held until
        # all of the tasks are waiting for it
        tasks: list[asyncio.Task[str]] = []
        async with asyncio.TaskGroup() as tg:
            await auth._Auth__lock.acquire()
            for _ in range(10):
                tasks.append(
                    tg.create_task(
                        auth.refresh_access_token(pseudo_client),
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
        refresh_func.assert_awaited_once_with(pseudo_client)


class TestSoapLogin:
    async def test_auth(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
        mock_soap_login: str,
    ):
        event_hook = AsyncMock()
        pseudo_client.event_bus.subscribe_callback(event_hook)
        auth = SoapLogin(
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"],
        )
        received_session_id = await auth.get_access_token(pseudo_client)
        assert received_session_id == mock_soap_login
        assert event_hook.await_count == 3

    @pytest.mark.usefixtures("mock_soap_login")
    async def test_expiration(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
    ):
        auth = SoapLogin(
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"],
        )
        await auth.get_access_token(pseudo_client)
        assert auth._expiration_time is not None
        assert auth._expiration_time > time.time()
        assert not auth.expired
        with time_machine.travel(
            time.time() + 60 * 60 * 24,
            tick=False,
        ):
            assert auth.expired
            await auth.get_access_token(pseudo_client)
            assert not auth.expired

    @pytest.mark.usefixtures("mock_soap_login")
    async def test_invalid_credentials(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
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
            await auth.get_access_token(pseudo_client)


class TestClientCredentialsFlow:
    async def test_auth(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
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
        pseudo_client.event_bus.subscribe_callback(event_hook)
        auth = ClientCredentialsFlow(
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",  # noqa: S106
        )
        access_token = await auth.get_access_token(pseudo_client)
        assert access_token == expected_access_token
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            # Access token for the Client Credentials Flow never expires
            # if timeout is not set
            assert not auth.expired
        assert event_hook.await_count == 3

    async def test_expiration(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
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
        pseudo_client.event_bus.subscribe_callback(event_hook)
        auth = ClientCredentialsFlow(
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",  # noqa: S106
            timeout=15 * 60,  # 15 minutes
        )
        access_token = await auth.get_access_token(pseudo_client)
        assert event_hook.await_count == 3
        assert access_token == expected_access_token
        assert auth._expiration_time is not None
        assert auth._expiration_time > time.time()
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            assert auth.expired
            access_token = await auth.get_access_token(pseudo_client)
            assert access_token == expected_access_token
            assert not auth.expired
        assert event_hook.await_count == 6

    async def test_invalid_credentials(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
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
            await auth.get_access_token(pseudo_client)


class TestJwtBearerFlow:
    async def test_auth(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
        httpx_mock_router: respx.MockRouter,
        tmp_path: pathlib.Path,
    ):
        rsa_private_key = generate_private_key(public_exponent=65537, key_size=2048)
        private_key_path = tmp_path / "private.pem"
        with open(private_key_path, "wb") as f:
            f.write(
                rsa_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        client_id = "somewhat-secret-client-id"
        expected_access_token = "SUPER-SECRET-ACCESS-TOKEN"  # noqa: S105

        async def side_effect(
            request: httpx.Request,
            route: respx.Route,
        ) -> httpx.Response:
            data = parse_qs(request.content.decode("utf-8"))
            assert data["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
            assertion = data["assertion"][0]
            payload = jwt.decode(
                assertion,
                rsa_private_key.public_key(),
                algorithms=["RS256"],
                verify=True,
                audience="https://login.salesforce.com",
                issuer=client_id,
            )
            assert payload["sub"] == config["username"]
            return httpx.Response(
                status_code=200,
                json={
                    "access_token": expected_access_token,
                    "scope": "full",
                    "instance_url": "https://example.salesforce.com",
                    "id": (
                        "https://login.salesforce.com/id"
                        "/00Dxx0000000000AAA/005xx0000000xxxAAA"
                    ),
                    "token_type": "Bearer",
                },
            )

        httpx_mock_router.post(f"{config['base_url']}/services/oauth2/token").mock(
            side_effect=side_effect
        )

        event_hook = AsyncMock()
        pseudo_client.event_bus.subscribe_callback(event_hook)
        auth = JwtBearerFlow(
            client_id=client_id,
            username=config["username"],
            private_key_file=private_key_path,
        )
        access_token = await auth.get_access_token(pseudo_client)
        assert access_token == expected_access_token
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            # Access token for the JWT Bearer Flow never expires if timeout is not set
            assert not auth.expired
        assert event_hook.await_count == 3

    async def test_expiration(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
        httpx_mock_router: respx.MockRouter,
        tmp_path: pathlib.Path,
    ):
        rsa_private_key = generate_private_key(public_exponent=65537, key_size=2048)
        private_key_path = tmp_path / "private.pem"
        with open(private_key_path, "wb") as f:
            f.write(
                rsa_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        client_id = "somewhat-secret-client-id"
        expected_access_token = "SUPER-SECRET-ACCESS-TOKEN"  # noqa: S105

        async def side_effect(
            request: httpx.Request,
            route: respx.Route,
        ) -> httpx.Response:
            data = parse_qs(request.content.decode("utf-8"))
            assert data["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
            assertion = data["assertion"][0]
            payload = jwt.decode(
                assertion,
                rsa_private_key.public_key(),
                algorithms=["RS256"],
                verify=True,
                audience="https://login.salesforce.com",
                issuer=client_id,
            )
            assert payload["sub"] == config["username"]
            return httpx.Response(
                status_code=200,
                json={
                    "access_token": expected_access_token,
                    "scope": "full",
                    "instance_url": "https://example.salesforce.com",
                    "id": (
                        "https://login.salesforce.com/id"
                        "/00Dxx0000000000AAA/005xx0000000xxxAAA"
                    ),
                    "token_type": "Bearer",
                },
            )

        httpx_mock_router.post(f"{config['base_url']}/services/oauth2/token").mock(
            side_effect=side_effect
        )

        event_hook = AsyncMock()
        pseudo_client.event_bus.subscribe_callback(event_hook)
        auth = JwtBearerFlow(
            client_id=client_id,
            username=config["username"],
            private_key_file=private_key_path,
            timeout=15 * 60,  # 15 minutes
        )
        access_token = await auth.get_access_token(pseudo_client)
        assert event_hook.await_count == 3
        assert access_token == expected_access_token
        assert auth._expiration_time is not None
        assert auth._expiration_time > time.time()
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            assert auth.expired
            access_token = await auth.get_access_token(pseudo_client)
            assert access_token == expected_access_token
            assert not auth.expired
        assert event_hook.await_count == 6

    async def test_invalid_credentials(
        self,
        config: dict[str, str],
        pseudo_client: Salesforce,
        httpx_mock_router: respx.MockRouter,
        tmp_path: pathlib.Path,
    ):
        rsa_private_key = generate_private_key(public_exponent=65537, key_size=2048)
        private_key_path = tmp_path / "private.pem"
        with open(private_key_path, "wb") as f:
            f.write(
                rsa_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

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

        auth = JwtBearerFlow(
            client_id="somewhat-secret-client-id",
            username=config["username"],
            private_key_file=private_key_path,
        )
        with pytest.raises(
            AuthenticationError,
            match=r"\[invalid_client_id\] client identifier invalid",
        ):
            await auth.get_access_token(pseudo_client)

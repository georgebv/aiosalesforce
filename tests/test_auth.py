import time

import httpx
import pytest
import respx
import time_machine

from aiosalesforce.auth import ClientCredentialsFlow, SoapLogin
from aiosalesforce.events import EventBus
from aiosalesforce.exceptions import AuthenticationError


class TestSoapLogin:
    async def test_soap_login(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        mock_soap_login: str,
    ):
        auth = SoapLogin(
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"],
        )
        received_session_id = await auth.get_access_token(
            client=httpx_client,
            base_url=config["base_url"],
            version=config["api_version"],
            event_bus=EventBus(),
        )
        assert received_session_id == mock_soap_login

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

        auth = ClientCredentialsFlow(
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",  # noqa: S106
        )
        access_token = await auth.get_access_token(
            client=httpx_client,
            base_url=config["base_url"],
            version=config["api_version"],
            event_bus=EventBus(),
        )
        assert access_token == expected_access_token
        assert not auth.expired
        with time_machine.travel(
            time.time() + 1e9,
            tick=False,
        ):
            # Access token for the Client Credentials Flow never expires
            assert not auth.expired

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

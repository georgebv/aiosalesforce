import time

import httpx
import pytest
import time_machine

from aiosalesforce.auth import SoapLogin
from aiosalesforce.events import EventBus
from aiosalesforce.exceptions import AuthenticationError


class TestAuth:
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
    async def test_soap_login_failure(
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

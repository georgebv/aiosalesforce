from typing import Generator

import httpx
import pytest

from aiosalesforce import Salesforce
from aiosalesforce.auth import SoapLogin


@pytest.fixture(scope="function")
def soap_auth(
    config: dict[str, str],
    mock_soap_login: str,
) -> Generator[SoapLogin, None, None]:
    # We need to request this fixture but we don't use its value
    # This line is for the linter
    del mock_soap_login

    yield SoapLogin(
        username=config["username"],
        password=config["password"],
        security_token=config["security_token"],
    )


@pytest.fixture(scope="function")
def salesforce(
    config: dict[str, str],
    httpx_client: httpx.AsyncClient,
    soap_auth: SoapLogin,
) -> Generator[Salesforce, None, None]:
    yield Salesforce(
        httpx_client=httpx_client,
        base_url=config["base_url"],
        auth=soap_auth,
        version=config["api_version"],
        event_hooks=[],
        retry_policy=None,
        concurrency_limit=10,
    )

from typing import AsyncGenerator, Generator

import httpx
import pytest
import respx


@pytest.fixture(scope="function")
def httpx_mock_router() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(
        assert_all_called=True,
        assert_all_mocked=True,
    ) as respx_mock:
        yield respx_mock


@pytest.fixture(scope="function")
async def httpx_client(
    httpx_mock_router: respx.MockRouter,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient() as client:
        yield client

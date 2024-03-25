import asyncio

from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import httpx
import pytest
import respx
import time_machine

from aiosalesforce.events import EventBus, RestApiCallConsumptionEvent, RetryEvent
from aiosalesforce.exceptions import SalesforceError
from aiosalesforce.retries import (
    ExceptionRule,
    ResponseRule,
    RetryPolicy,
)
from httpx import Response


class TestRules:
    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_response_rule(self, sync: bool, decision: bool):
        func = MagicMock() if sync else AsyncMock()
        func.return_value = decision
        rule = ResponseRule(func)
        response = Response(500)
        assert await rule.should_retry(response) == decision
        func.assert_called_with(response)

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_exception_rule(self, sync: bool, decision: bool):
        func = MagicMock() if sync else AsyncMock()
        func.return_value = decision
        rule = ExceptionRule(ValueError, func)

        # Matching exception
        exception_1 = ValueError("Test")
        assert await rule.should_retry(exception_1) == decision
        func.assert_called_with(exception_1)

        # Different exception (always False, doesn't call the function)
        exception_2 = TypeError("Test")
        assert not await rule.should_retry(exception_2)  # type: ignore
        func.assert_called_once()

    @pytest.mark.parametrize(
        "exception, pattern",
        [
            (Exception, "Retrying built-in Exception is not allowed."),
            (SalesforceError, "aiosalesforce exceptions cannot be retried.+"),
        ],
        ids=["base python exception", "base aiosalesforce exception"],
    )
    async def test_exception_rule_illegal_exception(
        self,
        exception: type[Exception],
        pattern: str,
    ):
        with pytest.raises(ValueError, match=pattern):
            ExceptionRule(exception)


class TestRetryPolicy:
    async def test_without_rules(self):
        policy = RetryPolicy()
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert not await context.should_retry(Response(500))
        assert context.retry_count["total"] == 0

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_with_response_rule(self, sync: bool, decision: bool):
        rule_callback = MagicMock() if sync else AsyncMock()
        rule_callback.return_value = decision
        rule = ResponseRule(rule_callback, 3)
        policy = RetryPolicy([rule], max_retries=10)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert await context.should_retry(Response(500)) == decision
        assert context.retry_count["total"] == int(decision)

        # Exhaust rule retries (policy retries are not exhausted)
        if decision:
            for _ in range(2):
                assert await context.should_retry(Response(500)) == decision
            assert context.retry_count["total"] == 3
            assert not await context.should_retry(Response(500))

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_with_exception_rule(self, sync: bool, decision: bool):
        rule_callback = MagicMock() if sync else AsyncMock()
        rule_callback.return_value = decision
        rule = ExceptionRule(ValueError, rule_callback, 3)
        policy = RetryPolicy([], [rule], max_retries=10)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert await context.should_retry(ValueError("Test")) == decision
        assert context.retry_count["total"] == int(decision)

        # Exhaust rule retries (policy retries are not exhausted)
        if decision:
            for _ in range(2):
                assert await context.should_retry(ValueError("Test")) == decision
            assert context.retry_count["total"] == 3
            assert not await context.should_retry(ValueError("Test"))

    async def test_retry_exhaustion(self):
        rule_callback = MagicMock()
        rule_callback.return_value = True
        rule = ResponseRule(rule_callback, 10)
        policy = RetryPolicy([rule], max_retries=3)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        for _ in range(3):
            assert await context.should_retry(Response(500))
        assert context.retry_count["total"] == 3
        assert not await context.should_retry(Response(500))

    async def test_timeout(self):
        rule_callback = MagicMock()
        rule_callback.return_value = True
        rule = ResponseRule(rule_callback, 10)
        policy = RetryPolicy([rule], max_retries=10, timeout=10)
        with time_machine.travel(0, tick=False):
            context = policy.create_context()
            assert context.retry_count["total"] == 0
            with time_machine.travel(1, tick=False):
                assert await context.should_retry(Response(500))
                assert context.retry_count["total"] == 1
            with time_machine.travel(11, tick=False):
                assert not await context.should_retry(Response(500))
                assert context.retry_count["total"] == 1

    async def test_sleep(self):
        policy = RetryPolicy(
            backoff_base=1,
            backoff_factor=2,
            backoff_max=10,
        )
        context = policy.create_context()
        new_sleep = AsyncMock()
        with (
            patch("asyncio.sleep", new_sleep),
            patch("random.uniform", lambda _, b: b),
        ):
            new_sleep.assert_not_awaited()

            context.retry_count["total"] = 1
            await context.sleep()
            new_sleep.assert_awaited_once_with(1)

            for attempt in range(1, 10):
                context.retry_count["total"] += 1
                await context.sleep()
                new_sleep.assert_awaited_with(min(2**attempt, 10))

    async def test_request(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        """Simple request (no retries, warnings, etc.)."""
        # Prepare retry policy context
        retry_policy = RetryPolicy()
        context = retry_policy.create_context()

        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(return_value=httpx.Response(status_code=200))

        # Subscribe a mock event hook
        event_bus = EventBus()
        event_hook = AsyncMock()
        event_bus.subscribe_callback(event_hook)

        # Execute request
        response = await context.send_request_with_retries(
            httpx_client=httpx_client,
            event_bus=event_bus,
            semaphore=asyncio.Semaphore(),
            request=httpx.Request("GET", url),
        )
        assert response.status_code == 200

        # Assert event hook was called:
        # - 1 for consumption
        assert event_hook.await_count == 1
        event_hook.assert_has_awaits(
            [
                call(
                    RestApiCallConsumptionEvent(
                        type="rest_api_call_consumption",
                        response=response,
                        count=1,
                    )
                ),
            ]
        )

    async def test_request_retry_on_exception(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        # Prepare retry policy context
        retry_policy = RetryPolicy(
            max_retries=3,
            exception_rules=[ExceptionRule(httpx.ConnectError)],
        )
        context = retry_policy.create_context()

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

        # Subscribe a mock event hook
        event_bus = EventBus()
        event_hook = AsyncMock()
        event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            response = await context.send_request_with_retries(
                httpx_client=httpx_client,
                event_bus=event_bus,
                semaphore=asyncio.Semaphore(),
                request=httpx.Request("GET", url),
            )
        assert response.status_code == 200

        # Assert event hook was called:
        assert event_hook.await_count == 4
        assert sleep_mock.await_count == 3
        event_hook.assert_has_awaits(
            [
                # 3 retries (exceptions don't consume API calls)
                *[
                    call(
                        RetryEvent(
                            type="retry",
                            attempt=i,
                            request=ANY,
                            response=None,
                            exception=ANY,
                        )
                    )
                    for i in range(1, 4)
                ],
                # 1 consumption on success
                call(
                    RestApiCallConsumptionEvent(
                        type="rest_api_call_consumption",
                        response=response,
                        count=1,
                    )
                ),
            ]
        )

    async def test_request_retry_on_exception_exceed_limit(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        # Prepare retry policy context
        retry_policy = RetryPolicy(
            max_retries=3,
            exception_rules=[ExceptionRule(httpx.ConnectError)],
        )
        context = retry_policy.create_context()

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

        # Subscribe a mock event hook
        event_bus = EventBus()
        event_hook = AsyncMock()
        event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with (
            patch("asyncio.sleep", sleep_mock),
            pytest.raises(httpx.ConnectError),
        ):
            await context.send_request_with_retries(
                httpx_client=httpx_client,
                event_bus=event_bus,
                semaphore=asyncio.Semaphore(),
                request=httpx.Request("GET", url),
            )

        # Assert event hook was called:
        assert event_hook.await_count == 3
        assert sleep_mock.await_count == 3
        event_hook.assert_has_awaits(
            [
                # 3 retries (exceptions don't consume API calls)
                *[
                    call(
                        RetryEvent(
                            type="retry",
                            attempt=i,
                            request=ANY,
                            response=None,
                            exception=ANY,
                        )
                    )
                    for i in range(1, 4)
                ],
            ]
        )

    async def test_request_retry_on_response(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        # Prepare retry policy context
        retry_policy = RetryPolicy(
            max_retries=3,
            response_rules=[ResponseRule(lambda r: r.status_code >= 500)],
        )
        context = retry_policy.create_context()

        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=500),
                httpx.Response(status_code=503),
                httpx.Response(status_code=200),
            ],
        )

        # Subscribe a mock event hook
        event_bus = EventBus()
        event_hook = AsyncMock()
        event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            response = await context.send_request_with_retries(
                httpx_client=httpx_client,
                event_bus=event_bus,
                semaphore=asyncio.Semaphore(),
                request=httpx.Request("GET", url),
            )
        assert response.status_code == 200

        # Assert event hook was called:
        assert event_hook.await_count == 5
        assert sleep_mock.await_count == 2
        calls = []
        # 2 retries with 1 consumption each
        for i in range(1, 3):
            calls.extend(
                [
                    call(
                        RestApiCallConsumptionEvent(
                            type="rest_api_call_consumption",
                            response=ANY,
                            count=1,
                        )
                    ),
                    call(
                        RetryEvent(
                            type="retry",
                            attempt=i,
                            request=ANY,
                            response=ANY,
                            exception=None,
                        )
                    ),
                ]
            )
        # 1 consumption on final successfull request
        calls.append(
            call(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption",
                    response=response,
                    count=1,
                )
            )
        )
        event_hook.assert_has_awaits(calls)

    async def test_request_retry_on_response_exceed_limit(
        self,
        config: dict[str, str],
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        # Prepare retry policy context
        retry_policy = RetryPolicy(
            max_retries=3,
            response_rules=[ResponseRule(lambda r: r.status_code >= 500)],
        )
        context = retry_policy.create_context()

        # Mock request
        url = f"{config['base_url']}/some/path"
        httpx_mock_router.get(url).mock(
            side_effect=[
                httpx.Response(status_code=500),
                httpx.Response(status_code=503),
                httpx.Response(status_code=500),
                httpx.Response(status_code=504),
                httpx.Response(status_code=200),
            ],
        )

        # Subscribe a mock event hook
        event_bus = EventBus()
        event_hook = AsyncMock()
        event_bus.subscribe_callback(event_hook)

        # Execute request (mock sleeping in retry policy)
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            response = await context.send_request_with_retries(
                httpx_client=httpx_client,
                event_bus=event_bus,
                semaphore=asyncio.Semaphore(),
                request=httpx.Request("GET", url),
            )
        assert response.status_code == 504

        # Assert event hook was called:
        assert event_hook.await_count == 7
        assert sleep_mock.await_count == 3
        calls = []
        # 3 retries with 1 consumption each
        for i in range(1, 4):
            calls.extend(
                [
                    call(
                        RestApiCallConsumptionEvent(
                            type="rest_api_call_consumption",
                            response=ANY,
                            count=1,
                        )
                    ),
                    call(
                        RetryEvent(
                            type="retry",
                            attempt=i,
                            request=ANY,
                            response=ANY,
                            exception=None,
                        )
                    ),
                ]
            )
        # 1 consumption on final failed request
        calls.append(
            call(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption",
                    response=response,
                    count=1,
                )
            )
        )
        event_hook.assert_has_awaits(calls)

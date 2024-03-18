from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import time_machine

from aiosalesforce.exceptions import SalesforceError
from aiosalesforce.retries import ExceptionRule, ResponseRule, RetryPolicy
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
    async def test_sleep(self):
        policy = RetryPolicy(
            backoff_base=1,
            backoff_factor=2,
            backoff_max=10,
        )
        new_sleep = AsyncMock()
        with (
            patch("asyncio.sleep", new_sleep),
            patch("random.uniform", lambda _, b: b),
        ):
            new_sleep.assert_not_awaited()

            await policy.sleep(0)
            new_sleep.assert_awaited_once_with(1)

            for attempt in range(1, 10):
                await policy.sleep(attempt)
                new_sleep.assert_awaited_with(min(2**attempt, 10))

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

    async def test_policy_retry_exhaustion(self):
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

    async def test_policy_timeout(self):
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

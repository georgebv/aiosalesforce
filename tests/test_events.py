from unittest.mock import AsyncMock, MagicMock

import pytest

from aiosalesforce.events import EventBus, RequestEvent, ResponseEvent, RetryEvent
from httpx import Request, Response


class TestEventBus:
    def test_callback_sub_unsub(self):
        default_callback = MagicMock()
        event_bus = EventBus([default_callback])
        assert len(event_bus._callbacks) == 1
        assert default_callback in event_bus._callbacks

        another_callback = AsyncMock()
        event_bus.subscribe_callback(another_callback)
        assert len(event_bus._callbacks) == 2
        assert another_callback in event_bus._callbacks

        event_bus.unsubscribe_callback(another_callback)
        assert len(event_bus._callbacks) == 1
        assert another_callback not in event_bus._callbacks
        event_bus.unsubscribe_callback(default_callback)
        assert len(event_bus._callbacks) == 0

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    async def test_with_sync_callback(self, sync: bool):
        event_bus = EventBus()
        callback = MagicMock() if sync else AsyncMock()
        event_bus.subscribe_callback(callback)
        request = Request("GET", "https://example.com")
        event = RequestEvent(type="request", request=request)
        await event_bus.publish_event(event)
        callback.assert_called_once_with(event)

    async def test_with_multiple_callbacks(self):
        event_bus = EventBus()
        callback1 = MagicMock()
        callback2 = AsyncMock()
        event_bus.subscribe_callback(callback1)
        event_bus.subscribe_callback(callback2)
        request = Request("GET", "https://example.com")
        event = RequestEvent(type="request", request=request)
        await event_bus.publish_event(event)
        callback1.assert_called_once_with(event)
        callback2.assert_called_once_with(event)


class TestResponseMixin:
    def test_with_no_response(self):
        response_event = RetryEvent(
            type="retry",
            request=Request("GET", "https://example.com"),
            response=None,
        )
        assert response_event.consumed is None
        assert response_event.remaining is None

    def test_without_api_usage_header(self):
        response = Response(200, content=b"")
        response_event = ResponseEvent(type="response", response=response)
        assert response_event.consumed is None
        assert response_event.remaining is None

    def test_with_api_usage_header(self):
        response = Response(
            200,
            content=b"",
            headers={"Sforce-Limit-Info": "api-usage=69/100000"},
        )
        response_event = ResponseEvent(type="response", response=response)
        assert response_event.consumed == 69
        assert response_event.remaining == 100000

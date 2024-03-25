import asyncio
import inspect

from typing import Awaitable, Callable, Iterable, TypeAlias

from .events import Event

CallbackType: TypeAlias = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """
    Event bus used to dispatch events to subscribed callbacks.

    Parameters
    ----------
    callbacks : Iterable[Callable[[Event], Awaitable[None] | None]], optional
        Callbacks to subscribe to the event bus.

    """

    _callbacks: set[CallbackType]

    def __init__(self, callbacks: Iterable[CallbackType] | None = None) -> None:
        self._callbacks = set()
        for callback in callbacks or []:
            self.subscribe_callback(callback)

    def subscribe_callback(self, callback: CallbackType) -> None:
        """
        Subscribe a callback to the event bus.

        Parameters
        ----------
        callback : CallbackType
            Function to be called when an event is published.

        """
        self._callbacks.add(callback)

    def unsubscribe_callback(self, callback: CallbackType) -> None:
        """
        Unsubscribe a callback from the event bus.

        Parameters
        ----------
        callback : CallbackType
            Function to be unsubscribed.

        """
        self._callbacks.discard(callback)

    @staticmethod
    async def __dispatch_event_to_callback(
        callback: CallbackType, event: Event
    ) -> None:
        if inspect.iscoroutinefunction(callback):
            await callback(event)
        else:
            await asyncio.to_thread(callback, event)

    async def publish_event(self, event: Event) -> None:
        """Publish an event and dispatch it to all subscribed callbacks."""
        async with asyncio.TaskGroup() as tg:
            for callback in self._callbacks:
                tg.create_task(self.__dispatch_event_to_callback(callback, event))

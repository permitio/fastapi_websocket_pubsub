import asyncio
import contextlib
from typing import Any

from broadcaster import Broadcast
from fastapi_websocket_rpc.utils import gen_uid
from pydantic.main import BaseModel

from .event_notifier import ALL_TOPICS, EventNotifier, Subscription, TopicList
from .logger import get_logger
from .util import pydantic_serialize

logger = get_logger("EventBroadcaster")


# Cross service broadcast consts
NotifierId = str


class BroadcastNotification(BaseModel):
    notifier_id: NotifierId
    topics: TopicList
    data: Any = None


class EventBroadcasterContextManager:
    """
    Manages the context for the EventBroadcaster
    Friend-like class of EventBroadcaster (accessing "protected" members )
    """

    def __init__(
        self,
        event_broadcaster: "EventBroadcaster",
        listen: bool = True,
        share: bool = True,
    ) -> None:
        """
        Provide a context manager for an EventBroadcaster, managing if it listens to events coming from the broadcaster
        and if it subscribes to the internal notifier to share its events with the broadcaster

        Args:
            event_broadcaster (EventBroadcaster): the broadcaster we manage the context for.
            share (bool, optional): Should we share events with the broadcaster. Defaults to True.
            listen (bool, optional): Should we listen for incoming events from the broadcaster. Defaults to True.
        """
        self._event_broadcaster = event_broadcaster
        self._share: bool = share
        self._listen: bool = listen

    async def __aenter__(self):
        await self._event_broadcaster.connect(self._listen, self._share)

    async def __aexit__(self, exc_type, exc, tb):
        await self._event_broadcaster.close(self._listen, self._share)


class EventBroadcasterException(Exception):
    pass


class BroadcasterAlreadyStarted(EventBroadcasterException):
    pass


class EventBroadcaster:
    """
    Bridge EventNotifier to work across processes and machines by sharing their events through a broadcasting channel

    Usage:
    uri = "postgres://localhost:5432/db_name" #postgres example (also supports REDIS, Kafka, ...)
    # start litsening for broadcast publications notifying the internal event-notifier, and subscribing to the internal notifier, broadcasting its notes
    broadcaster = EventBroadcaster(uri, notifier):
    async with broadcaster.get_context():
        <Your Code>
    """

    def __init__(
        self,
        broadcast_url: str,
        notifier: EventNotifier,
        channel="EventNotifier",
        broadcast_type=None,
        is_publish_only=False,
    ) -> None:
        """

        Args:
            broadcast_url (str): the URL of the broadcasting service
            notifier (EventNotifier): the event notifier managing our internal events - which will be bridge via the broadcaster
            channel (str, optional): Channel name. Defaults to "EventNotifier".
            broadcast_type (Broadcast, optional): Broadcast class to use. None - Defaults to Broadcast.
            is_publish_only (bool, optional): [For default context] Should the broadcaster only transmit events and not listen to any. Defaults to False
        """
        self._broadcast_url = broadcast_url
        self._broadcast_type = broadcast_type or Broadcast
        self._channel = channel
        self._subscription_task = None
        self._id = gen_uid()
        self._notifier = notifier
        self._broadcast_channel = None
        self._connect_lock = asyncio.Lock()
        self._listen_refcount = 0
        self._share_refcount = 0
        self._is_publish_only = is_publish_only

    async def connect(self, listen=True, share=True):
        """
        This connects the listening channel
        """
        async with self._connect_lock:
            if listen:
                await self._connect_listen()
                self._listen_refcount += 1

            if share:
                await self._connect_share()
                self._share_refcount += 1

    async def close(self, listen=True, share=True):
        async with self._connect_lock:
            if listen:
                await self._close_listen()
                self._listen_refcount -= 1

            if share:
                await self._close_share()
                self._share_refcount -= 1

    async def __aenter__(self):
        await self.connect(listen=not self._is_publish_only)

    async def __aexit__(self, exc_type, exc, tb):
        await self.close(listen=not self._is_publish_only)

    def get_context(self, listen=True, share=True):
        """
        Create a new context manager you can call 'async with' on, configuring the broadcaster for listening, sharing, or both.

        Args:
            listen (bool, optional): Should we listen for events incoming from the broadcast channel. Defaults to True.
            share (bool, optional): Should we share events with the broadcast channel. Defaults to True.

        Returns:
            EventBroadcasterContextManager: the context
        """
        return EventBroadcasterContextManager(self, listen=listen, share=share)

    def get_listening_context(self):
        return EventBroadcasterContextManager(self, listen=True, share=False)

    def get_sharing_context(self):
        return EventBroadcasterContextManager(self, listen=False, share=True)

    async def __broadcast_notifications__(self, subscription: Subscription, data):
        """
        Share incoming internal notifications with the entire broadcast channel

        Args:
            subscription (Subscription): the subscription that got triggered
            data: the event data
        """
        logger.info(
            "Broadcasting incoming event: {}".format(
                {"topic": subscription.topic, "notifier_id": self._id}
            )
        )

        note = BroadcastNotification(
            notifier_id=self._id, topics=[subscription.topic], data=data
        )

        # Publish event to broadcast using a new connection from connection pool
        async with self._broadcast_type(
            self._broadcast_url
        ) as sharing_broadcast_channel:
            await sharing_broadcast_channel.publish(
                self._channel, pydantic_serialize(note)
            )

    async def _connect_share(self):
        if self._share_refcount == 0:
            return await self._notifier.subscribe(
                self._id, ALL_TOPICS, self.__broadcast_notifications__
            )

    async def _close_share(self):
        if self._share_refcount == 1:
            return await self._notifier.unsubscribe(self._id)

    async def _connect_listen(self):
        if self._listen_refcount == 0:
            if self._listen_refcount == 0:
                try:
                    self._broadcast_channel = self._broadcast_type(self._broadcast_url)
                    await self._broadcast_channel.connect()
                except Exception as e:
                    logger.error(
                        f"Failed to connect to broadcast channel for reading incoming events: {e}"
                    )
                    raise e
                self._subscription_task = asyncio.create_task(
                    self.__read_notifications__()
                )
        return await self._notifier.subscribe(
            self._id, ALL_TOPICS, self.__broadcast_notifications__
        )

    async def _close_listen(self):
        if self._listen_refcount == 1 and self._broadcast_channel is not None:
            await self._broadcast_channel.disconnect()
            await self.wait_until_done()
            self._broadcast_channel = None

    def get_reader_task(self):
        return self._subscription_task

    async def wait_until_done(self):
        if self._subscription_task is not None:
            await self._subscription_task
            self._subscription_task = None

    async def __read_notifications__(self):
        """
        read incoming broadcasts and posting them to the intreal notifier
        """
        logger.debug("Starting broadcaster listener")

        notify_tasks = set()
        try:
            # Subscribe to our channel
            async with self._broadcast_channel.subscribe(
                channel=self._channel
            ) as subscriber:
                async for event in subscriber:
                    notification = BroadcastNotification.parse_raw(event.message)
                    # Avoid re-publishing our own broadcasts
                    if notification.notifier_id != self._id:
                        logger.debug(
                            "Handling incoming broadcast event: {}".format(
                                {
                                    "topics": notification.topics,
                                    "src": notification.notifier_id,
                                }
                            )
                        )
                        # Notify subscribers of message received from broadcast
                        task = asyncio.create_task(
                            self._notifier.notify(
                                notification.topics,
                                notification.data,
                                notifier_id=self._id,
                            )
                        )

                        notify_tasks.add(task)

                        def cleanup(t):
                            notify_tasks.remove(t)

                        task.add_done_callback(cleanup)
                logger.info(
                    "No more events to read from subscriber (underlying connection closed)"
                )
        finally:
            await asyncio.gather(*notify_tasks, return_exceptions=True)

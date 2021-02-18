import asyncio
from typing import Any, Union
from pydantic.main import BaseModel
from .event_notifier import EventNotifier, Subscription, TopicList, ALL_TOPICS
from broadcaster import Broadcast

from .logger import get_logger
from fastapi_websocket_rpc.utils import gen_uid


logger = get_logger('EventBroadcaster')


# Cross service broadcast consts
NotifierId = str


class BroadcastNotification(BaseModel):
    notifier_id: NotifierId
    topics: TopicList
    data: Any


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
    async with EventBroadcaster(uri, notifier) as broadcaster:
        <Your Code>
    """

    def __init__(self, broadcast_url: str, notifier: EventNotifier, channel="EventNotifier",
                 broadcast_type=None, is_publish_only=False) -> None:
        """

        Args:
            broadcast_url (str): the URL of the broadcasting service
            notifier (EventNotifier): the event notifier managing our internal events - which will be bridge via the broadcaster
            channel (str, optional): Channel name. Defaults to "EventNotifier".
            broadcast_type (Broadcast, optional): Broadcast class to use. None - Defaults to Broadcast.
            is_publish_only (bool, optional): Should the broadcaster only transmit events and not listen to any. Defaults to False
        """
        # Broadcast init params
        self._broadcast_url = broadcast_url
        self._broadcast_type = broadcast_type or Broadcast
        # Publish broadcast (initialized within async with statement)
        self._broadcast = None
        # channel to operate on
        self._channel = channel
        # Async-io task for reading broadcasts (initialized within async with statement)
        self._subscription_task = None
        # Uniqueue instance id (used to avoid reading own notifications sent in broadcast)
        self._id = gen_uid()
        # The internal events notifier
        self._notifier = notifier
        self._is_publish_only = is_publish_only
        self._lock = asyncio.Lock()
        self._publish_lock = asyncio.Lock()
        self._num_connections = 0

    async def __broadcast_notifications__(self, subscription: Subscription, data):
        """
        Share incoming internal notifications with the entire broadcast channel

        Args:
            subscription (Subscription): the subscription that got triggered
            data: the event data
        """
        logger.info("Broadcasting incoming event",
                    {'topic':subscription.topic, 'notifier_id':self._id})
        note = BroadcastNotification(notifier_id=self._id, topics=[
                                     subscription.topic], data=data)
        # Publish event to broadcast
        async with self._publish_lock:
            async with self._broadcast:
                await self._broadcast.publish(self._channel, note.json())

    async def __aenter__(self):
        async with self._lock:
            # Init the broadcast used for publishing (reading has its own)
            self._broadcast = self._broadcast_type(self._broadcast_url)
            if self._num_connections == 0:
                if not self._is_publish_only:
                    # Start task listening on incoming broadcasts
                    self.start_reader_task()

                logger.info("Subscribing to ALL TOPICS, first client connected")
                # Subscribe to internal events form our own event notifier and broadcast them
                await self._notifier.subscribe(self._id,
                                               ALL_TOPICS,
                                               self.__broadcast_notifications__)
            self._num_connections += 1

    async def __aexit__(self, exc_type, exc, tb):
        async with self._lock:
            self._num_connections -= 1
            if self._num_connections == 0:
                try:
                    # Unsubscribe from internal events
                    logger.info("Unsubscribing from ALL TOPICS, last client disconnected")
                    await self._notifier.unsubscribe(self._id)

                    # Cancel task reading broadcast subscriptions
                    if self._subscription_task is not None:
                        logger.info("Cancelling broadcast listen task")
                        self._subscription_task.cancel()
                        self._subscription_task = None
                except:
                    logger.exception("Failed to exit EventBroadcaster context")

    def start_reader_task(self):
        """Spawn a task reading incoming broadcasts and posting them to the intreal notifier
        Raises:
            BroadcasterAlreadyStarted: if called more than once per context
        Returns:
            the spawned task
        """
        # Make sure a task wasn't started already
        if self._subscription_task is not None:
            # we already started a task for this worker process
            logger.debug("No need for listen task, already started broadcast listen task for this notifier")
            return
        # Trigger the task
        logger.info("Spawning broadcast listen task")
        self._subscription_task = asyncio.create_task(
            self.__read_notifications__())
        return self._subscription_task

    async def __read_notifications__(self):
        """
        read incoming broadcasts and posting them to the intreal notifier
        """
        logger.info("Starting broadcaster listener")
        # Init new broadcast channel for reading
        broadcast_reader = self._broadcast_type(self._broadcast_url)
        async with broadcast_reader:
            # Subscribe to our channel
            async with broadcast_reader.subscribe(channel=self._channel) as subscriber:
                async for event in subscriber:
                    try:
                        notification = BroadcastNotification.parse_raw(
                            event.message)
                        # Avoid re-publishing our own broadcasts
                        if notification.notifier_id != self._id:
                            logger.debug("Handling incoming broadcast event",
                                        {'topics':notification.topics,
                                        'src':notification.notifier_id})
                            # Notify subscribers of message received from broadcast
                            await self._notifier.notify(notification.topics, notification.data, notifier_id=self._id)
                    except:
                        logger.exception("Failed handling incoming broadcast")

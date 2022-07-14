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


class EventBroadcasterContextManager:
    """
    Manages the context for the EventBroadcaster
    Friend-like class of EventBroadcaster (accessing "protected" members )
    """

    def __init__(self, event_broadcaster: "EventBroadcaster", listen: bool = True, share: bool = True) -> None:
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
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        async with self._lock:
            if self._listen:
                self._event_broadcaster._listen_count += 1
                if self._event_broadcaster._listen_count == 1:
                    # We have our first listener start the read-task for it (And all those who'd follow)
                    logger.info("Listening for incoming events from broadcast channel (first listener started)")
                    # Start task listening on incoming broadcasts
                    self._event_broadcaster.start_reader_task()

            if self._share:
                self._event_broadcaster._share_count += 1
                if self._event_broadcaster._share_count == 1:
                    # We have our first publisher
                    # Init the broadcast used for sharing (reading has its own)
                    self._event_broadcaster._acquire_sharing_broadcast_channel()
                    logger.debug("Subscribing to ALL_TOPICS, and sharing messages with broadcast channel")
                    # Subscribe to internal events form our own event notifier and broadcast them
                    await self._event_broadcaster._subscribe_to_all_topics()
                else:
                    logger.debug(f"Did not subscribe to ALL_TOPICS: share count == {self._event_broadcaster._share_count}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        async with self._lock:
            try:
                if self._listen:
                    self._event_broadcaster._listen_count -= 1
                    # if this was last listener - we can stop the reading task
                    if self._event_broadcaster._listen_count == 0:
                        # Cancel task reading broadcast subscriptions
                        if self._event_broadcaster._subscription_task is not None:
                            logger.info("Cancelling broadcast listen task")
                            self._event_broadcaster._subscription_task.cancel()
                            self._event_broadcaster._subscription_task = None

                if self._share:
                    self._event_broadcaster._share_count -= 1     
                    # if this was last sharer - we can stop subscribing to internal events - we aren't sharing anymore
                    if self._event_broadcaster._share_count == 0:
                        # Unsubscribe from internal events
                        logger.debug("Unsubscribing from ALL TOPICS")
                        await self._event_broadcaster._unsubscribe_from_topics()

            except:
                logger.exception("Failed to exit EventBroadcaster context")


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

    def __init__(self, broadcast_url: str, notifier: EventNotifier, channel="EventNotifier",
                 broadcast_type=None, is_publish_only=False) -> None:
        """

        Args:
            broadcast_url (str): the URL of the broadcasting service
            notifier (EventNotifier): the event notifier managing our internal events - which will be bridge via the broadcaster
            channel (str, optional): Channel name. Defaults to "EventNotifier".
            broadcast_type (Broadcast, optional): Broadcast class to use. None - Defaults to Broadcast.
            is_publish_only (bool, optional): [For default context] Should the broadcaster only transmit events and not listen to any. Defaults to False
        """
        # Broadcast init params
        self._broadcast_url = broadcast_url
        self._broadcast_type = broadcast_type or Broadcast
        # Publish broadcast (initialized within async with statement)
        self._sharing_broadcast_channel = None
        # channel to operate on
        self._channel = channel
        # Async-io task for reading broadcasts (initialized within async with statement)
        self._subscription_task = None
        # Uniqueue instance id (used to avoid reading own notifications sent in broadcast)
        self._id = gen_uid()
        # The internal events notifier
        self._notifier = notifier
        self._is_publish_only = is_publish_only
        self._publish_lock = None
        # used to track creation / removal of resources needed per type (reader task->listen, and subscription to internal events->share)
        self._listen_count: int = 0
        self._share_count: int = 0     
        # If we opt to manage the context directly (i.e. call async with on the event broadcaster itself)   
        self._context_manager = None


    async def __broadcast_notifications__(self, subscription: Subscription, data):
        """
        Share incoming internal notifications with the entire broadcast channel

        Args:
            subscription (Subscription): the subscription that got triggered
            data: the event data
        """
        logger.info("Broadcasting incoming event: {}".format({'topic': subscription.topic, 'notifier_id': self._id}))
        note = BroadcastNotification(notifier_id=self._id, topics=[
                                     subscription.topic], data=data)
        # Publish event to broadcast
        async with self._publish_lock:
            async with self._sharing_broadcast_channel:
                await self._sharing_broadcast_channel.publish(self._channel, note.json())

    def _acquire_sharing_broadcast_channel(self):
        """
        Initialize the elements needed for sharing events with the broadcast channel
        """
        self._publish_lock = asyncio.Lock()
        self._sharing_broadcast_channel = self._broadcast_type(self._broadcast_url)

    async def _subscribe_to_all_topics(self):
        return await self._notifier.subscribe(self._id,
                                              ALL_TOPICS,
                                              self.__broadcast_notifications__)

    async def _unsubscribe_from_topics(self):
        return await self._notifier.unsubscribe(self._id)

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
                                    
    async def __aenter__(self):
        """
        Convince caller (also backward compaltability)
        """
        if self._context_manager is None:
            self._context_manager = self.get_context(listen=not self._is_publish_only)
        return await self._context_manager.__aenter__()


    async def __aexit__(self, exc_type, exc, tb):
        await self._context_manager.__aexit__(exc_type, exc, tb)

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
        logger.debug("Spawning broadcast listen task")
        self._subscription_task = asyncio.create_task(
            self.__read_notifications__())
        return self._subscription_task
    
    def get_reader_task(self):
        return self._subscription_task

    async def __read_notifications__(self):
        """
        read incoming broadcasts and posting them to the intreal notifier
        """
        logger.info("Starting broadcaster listener")
        # Init new broadcast channel for reading
        listening_broadcast_channel = self._broadcast_type(self._broadcast_url)
        async with listening_broadcast_channel:
            # Subscribe to our channel
            async with listening_broadcast_channel.subscribe(channel=self._channel) as subscriber:
                async for event in subscriber:
                    try:
                        notification = BroadcastNotification.parse_raw(
                            event.message)
                        # Avoid re-publishing our own broadcasts
                        if notification.notifier_id != self._id:
                            logger.info("Handling incoming broadcast event: {}".format({'topics': notification.topics, 'src': notification.notifier_id}))
                            # Notify subscribers of message received from broadcast
                            await self._notifier.notify(notification.topics, notification.data, notifier_id=self._id)
                    except:
                        logger.exception("Failed handling incoming broadcast")

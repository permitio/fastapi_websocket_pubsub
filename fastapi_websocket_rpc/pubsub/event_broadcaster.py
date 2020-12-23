import asyncio
from typing import Any, Union
from pydantic.main import BaseModel
from .event_notifier import EventNotifier, Subscription, TopicList
from broadcaster import Broadcast

from ..logger import get_logger
from ..utils import gen_uid
from fastapi_websocket_rpc.pubsub import event_notifier

logger = get_logger('EventBroadcaster')



# Cross service broadcast consts
NotifierId = str

class BroadcastNotification(BaseModel):
    notifier_id: NotifierId
    topics: TopicList
    data: Any

class EventBroadcasterException(Exception):
    pass

class BroadcasterNotEntered(EventBroadcasterException):
    pass

class BroadcasterAlreadyStarted(EventBroadcasterException):
    pass


class EventBroadcaster:

    def __init__(self, broadcast: Union[Broadcast,str], notifier: EventNotifier, channel="EventNotifier", is_publish_only=False) -> None:
        # Broadcasting to more instances via message-queue
        # The broadcast source (either a Broadcast instance or a URL to init an instance)
        self._broadcast = broadcast if isinstance(broadcast, Broadcast) else Broadcast(broadcast)
        # Object for working on top of a broadcast (result of async with on broadcast)
        self._broadcaster = None
        # Object for reading notifications (result of async with on subscription)
        self._subscriber = None
        # Object with channel/top registration (result of broadcast.subscribe)
        self._subscription = None
        self._channel = channel
        self._subscription_task = None
        self._is_publish_only = is_publish_only
        # Uniqueue instance id (used to avoid reading own notifications sent in broadcast)
        self._id = gen_uid()
        self._notifier = notifier
        
    async def __broadcast_notifications__(self, subscription:Subscription, data):
        logger.info("Handling incoming event for broadcast")
        note = BroadcastNotification(notifier_id=self._id, topics=[subscription.topic], data=data)
        await self._broadcast.publish(self._channel, note.json())
        
    async def __aenter__(self):
        self._broadcaster =  await self._broadcast.__aenter__()

        # Subscribe to broadcasts and pass them to our own EventNotifier subscribers 
        if not self._is_publish_only:
            # TODO subscribe to channels based on current topics (self._topics)
            self._subscription = self._broadcast.subscribe(channel=self._channel)
            self._subscriber = await self._subscription.__aenter__()

        # Subscribe to internal events form our own event notifier and broadcat them 
        await self._notifier.subscribe(self._id, event_notifier.ALL_TOPICS, self.__broadcast_notifications__)

    async def __aexit__(self, exc_type, exc, tb):
        try:
            # Close subscription
            if self._subscriber is not None:
                await self._subscription.__aexit__()
            # Close broadcasting
            if self._broadcaster is not None:
                await self._broadcast.__aexit__()
            # Cancel task
            if self._subscription_task is not None:
                self._subscription_task.cancel()
        except Exception as err:
            logger.error("Failed to exit EventBroadcaster context", error=err)
        finally:
            # Clear state
            self._broadcaster = None
            self._subscription = None
            self._subscriber = None
            self._subscription_task = None

    def start_reader_task(self):
        # Make sure we have entered the context
        if self._subscriber is None:
            raise BroadcasterNotEntered("read notifications requires entering subscription context")       
        # Make sure a task wasn't started already
        if self._subscription_task is not None:
            raise BroadcasterAlreadyStarted("Can create one reader task per context")
        # Trigger the task       
        logger.info("Spawning broadcast listen task")
        self._subscription_task = asyncio.create_task(self.read_notifications())
        return self._subscription_task

    async def read_notifications(self):
        if self._subscriber is None:
            raise BroadcasterNotEntered("read notifications requires entering subscription context")
        logger.info("Starting broadcaster listener")
        async for event in self._subscriber:
            notification = BroadcastNotification.parse_raw(event.data)
            logger.info("Handling broadcast incoming event")
            # Avoid re-publishing our own broadcasts
            if notification.notifier_id != self._id:
                # Notify subscribers of message received from broadcast
                await self._notifier.notify(notification.topics, notification.data)
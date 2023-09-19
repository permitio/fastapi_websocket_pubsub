import asyncio
import copy
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from fastapi_websocket_rpc import RpcChannel
from fastapi_websocket_rpc.utils import gen_uid
from pydantic import BaseModel  # pylint: disable=no-name-in-module

from .logger import get_logger
from .util import pydantic_to_dict

logger = get_logger("EventNotifier")

# Magic topic - meaning subscribe to all topics
ALL_TOPICS = "__EventNotifier_ALL_TOPICS__"


# Basic Pub/Sub consts
SubscriberId = str
SubscriptionId = str
Topic = str
TopicList = List[Topic]


class Subscription(BaseModel):
    """
    Data model to be stored per subscription, and sent to each subscriber via the callback
    This allows for serializing the data down the line and sending to potential remote subscribers (via the callback),
    in which case the callback field itself should be removed first.
    """

    id: SubscriptionId
    subscriber_id: SubscriberId
    topic: Topic
    callback: Callable = None
    notifier_id: Optional[str] = None


# Publish event callback signature
def EventCallback(subscription: Subscription, data: Any):
    pass


class EventNotifier:
    """
    A Basic Pub/Sub class using callback functions as the
    Subscribers subscribe using self.subscribe, choosing topics to subscribe to
    and passing a callback that will be called on a publish/notify event (with the topic and data)


    Usage example:
        notifier = EventNotifier()

        #subscriber
        notifier.subscribe( notifier.gen_subscriber_id(), ["dinner is served", "breakfast is served"],
                            lambda topic, data: print(f"{topic}, let's eat. We have: {data}") )

        #publisher
        notifier.notify(["breakfast is served"], "Pancakes!")
    """

    def __init__(self):
        # Topics->subscribers->subscription mapping
        self._topics: Dict[Topic, Dict[SubscriberId, List[Subscription]]] = {}
        # Lock used to sync access to mapped subscriptions
        # Initialized JIT to be sure to grab the right asyncio-loop
        self._lock: asyncio.Lock = None
        # List of events to call when client subscribed
        self._on_subscribe_events = []
        # List of events to call when client unsubscribed
        self._on_unsubscribe_events = []
        # List of restriction checks to perform on every action on the channel
        self._channel_restrictions = []

    def gen_subscriber_id(self):
        return gen_uid()

    def gen_subscription_id(self):
        return gen_uid()

    def _get_subscribers_lock(self):
        """
        Init lock once - on current loop
        """
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def add_channel_restriction(self, restriction_callback):
        self._channel_restrictions.append(restriction_callback)

    async def subscribe(
        self,
        subscriber_id: SubscriberId,
        topics: Union[TopicList, ALL_TOPICS],
        callback: EventCallback,
        channel: Optional[RpcChannel] = None,
    ) -> List[Subscription]:
        """
        Subscribe to a set of topics.
        Once a notification (i.e. publish) of a topic is received the provided callback function will be called (with topic and data)


        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (TopicList, ALL_TOPICS): A list of topic to subscribe to (Each topic is saved in a separate subscription)
                                ALL_TOPICS can be passed to subscribe to  everything (all current and future topics)
            callback (Callable): the callback function to call upon a publish event
            channel (RpcChannel): Optional channel to handle on the registered restrictions
        """
        if channel:
            for restriction in self._channel_restrictions:
                await restriction(topics, channel)

        new_subscriptions = []
        async with self._get_subscribers_lock():
            if topics == ALL_TOPICS:
                topics = [ALL_TOPICS]
            for topic in topics:
                subscribers = self._topics[topic] = self._topics.get(topic, {})
                subscriptions = subscribers[subscriber_id] = subscribers.get(
                    subscriber_id, []
                )
                # Create new subscription for each Topic x Subscriber x Callback combo
                new_subscription = Subscription(
                    id=self.gen_subscription_id(),
                    subscriber_id=subscriber_id,
                    topic=topic,
                    callback=callback,
                )
                subscriptions.append(new_subscription)
                new_subscriptions.append(new_subscription)
                logger.debug(f"New subscription {pydantic_to_dict(new_subscription)}")
            await EventNotifier.trigger_events(
                self._on_subscribe_events, subscriber_id, topics
            )
            return new_subscriptions

    async def unsubscribe(
        self, subscriber_id: SubscriberId, topics: Union[TopicList, None] = None
    ):
        """
        Unsubscribe from given topics.
        Pass topics=None to unsubscribe the given subscriber from all topics

        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (Union[TopicList, None]): Topics to unsubscribe from
        """
        async with self._get_subscribers_lock():
            # if no topics are given then unsubscribe from all topics
            if topics is None:
                topics = list(self._topics.keys())
            for topic in topics:
                subscribers = self._topics[topic]
                if subscriber_id in subscribers:
                    logger.debug(
                        f"Removing Subscription of topic='{topic}' for subscriber={subscriber_id}"
                    )
                    del subscribers[subscriber_id]
            await EventNotifier.trigger_events(
                self._on_unsubscribe_events, subscriber_id, topics
            )

    @staticmethod
    async def trigger_events(event_callbacks: List[Coroutine], *args):
        callbacks_with_params = []
        for callback in event_callbacks:
            callbacks_with_params.append(callback(*args))
        await asyncio.gather(*callbacks_with_params)

    async def trigger_callback(
        self,
        data,
        topic: Topic,
        subscriber_id: SubscriberId,
        subscription: Subscription,
    ):
        await subscription.callback(subscription, data)

    async def callback_subscribers(
        self,
        subscribers: Dict[SubscriberId, List[Subscription]],
        topic: Topic,
        data,
        notifier_id: SubscriberId = None,
        override_topic=False,
    ):
        """
        Trigger callbacks for given subscribers
        Args:
            subscribers (Dict[SubscriberId,Subscription]): the subscribers to notify of the event
            topic (Topic): the topic of the event
            data:  event data
            notifier_id (SubscriberId, optional): id of the event sender. Defaults to None.
            override_topic (bool, optional): Should the event/subscription topic be updated to match the given topic. Defaults to False.
        """
        for subscriber_id, subscriptions in subscribers.items():
            try:
                # Don't notify the notifier
                if subscriber_id != notifier_id:
                    for subscription in subscriptions:
                        if override_topic:
                            # Report actual topic instead of ALL_TOPICS (or whatever is saved in the subscription)
                            event = subscription.copy()
                            event.topic = topic
                            original_topic = (
                                "ALL_TOPICS"
                                if (subscription.topic == ALL_TOPICS)
                                else subscription.topic
                            )
                            logger.debug(
                                f"calling subscription callbacks: topic={topic} ({original_topic}), subscription_id={subscription.id}, subscriber_id={subscriber_id}"
                            )
                        else:
                            event = subscription
                            logger.debug(
                                f"calling subscription callbacks: topic={topic}, subscription_id={subscription.id}, subscriber_id={subscriber_id}"
                            )
                        # call callback with subscription-info and provided data
                        await self.trigger_callback(data, topic, subscriber_id, event)
            except Exception:  # TODO: Narrow to more relevant exception?
                logger.exception(
                    f"Failed to notify subscriber sub_id={subscriber_id} with topic={topic}"
                )

    async def notify(
        self,
        topics: Union[TopicList, Topic],
        data=None,
        notifier_id=None,
        channel: Optional[RpcChannel] = None,
    ):
        """
        Notify subscribers of a new event per topic. (i.e. Publish events)

        Args:
            topics (Union[TopicList, Topic]): Topics to trigger a publish event for (Calling the callbacks of all their subscribers)
            data ([type], optional): Arbitrary data to pass each callback. Defaults to None.
            notifier_id (str): an id of the entity sending the notification, use the same id as subscriber id to avoid getting your own notifications
            channel (RpcChannel): Optional channel to handle on the registered restrictions
        """
        # allow caller to pass a single topic without a list
        if isinstance(topics, Topic):
            topics = [topics]

        if channel:
            for restriction in self._channel_restrictions:
                await restriction(topics, channel)

        # get ALL_TOPICS subscribers
        subscribers_to_all = self._topics.get(ALL_TOPICS, {})

        callbacks = []
        # TODO improve with reader/writer lock pattern - so multiple notifications can happen at once
        async with self._get_subscribers_lock():
            for topic in topics:
                subscribers = self._topics.get(topic, {})
                # handle direct topic subscribers (work on copy to avoid changes after we got the callbacks running)
                callbacks.append(
                    self.callback_subscribers(
                        copy.copy(subscribers), topic, data, notifier_id
                    )
                )
                # handle ALL_TOPICS subscribers (work on copy to avoid changes after we got the callbacks running)
                # Use actual topic instead of ALL_TOPICS
                callbacks.append(
                    self.callback_subscribers(
                        copy.copy(subscribers_to_all),
                        topic,
                        data,
                        notifier_id,
                        override_topic=True,
                    )
                )
        # call the subscribers outside of the lock - if they disconnect in the middle of the handling the with statement may fail
        # -- (issue with interrupts https://bugs.python.org/issue29988)
        await asyncio.gather(*callbacks)

    def register_subscribe_event(self, callback: Coroutine):
        """
        Add a callback function to be triggered when new subscriber joins.

        Args:
            callback (Callable): the callback function to call upon a new subscription
        """
        self._on_subscribe_events.append(callback)

    def register_unsubscribe_event(self, callback: Coroutine):
        """
        Add a callback function to be triggered when a subscriber disconnects.

        Args:
            callback (Callable): the callback function to call upon a client unsubscribe
        """
        self._on_unsubscribe_events.append(callback)

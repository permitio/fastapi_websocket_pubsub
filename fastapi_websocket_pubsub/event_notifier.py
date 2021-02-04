import asyncio
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi_websocket_rpc.utils import gen_uid
from pydantic import BaseModel  # pylint: disable=no-name-in-module

from .logger import get_logger

logger = get_logger('EventNotifier')

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
    id:  SubscriptionId
    subscriber_id: SubscriberId
    topic: Topic
    callback: Callable = None
    notifier_id: Optional[str] = None


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
        self._lock = asyncio.Lock()

    def gen_subscriber_id(self):
        return gen_uid()

    def gen_subscription_id(self):
        return gen_uid()

    async def subscribe(self, subscriber_id: SubscriberId, topics: Union[TopicList, ALL_TOPICS], callback: Callable) -> List[Subscription]:
        """
        Subscribe to a set of topics.
        Once a notification (i.e. publish) of a topic is received the provided callback function will be called (with topic and data)


        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (TopicList, ALL_TOPICS): A list of topic to subscribe to (Each topic is saved in a separate subscription)
                                ALL_TOPICS can be passed to subscribe to  everything (all current and future topics)
            callback (Callable): the callback function to call upon a publish event
        """
        new_subscriptions = []
        async with self._lock:
            if topics == ALL_TOPICS:
                topics = [ALL_TOPICS]
            for topic in topics:
                subscribers = self._topics[topic] = self._topics.get(topic, {})
                subscriptions = subscribers[subscriber_id] = subscribers.get(
                    subscriber_id, [])
                # Create new subscription for each Topic x Subscriber x Callback combo
                new_subscription = Subscription(id=self.gen_subscription_id(),
                                                subscriber_id=subscriber_id,
                                                topic=topic,
                                                callback=callback)
                subscriptions.append(new_subscription)
                new_subscriptions.append(new_subscription)
                logger.info("New subscription",
                            subscription=new_subscription.dict())
            return new_subscriptions

    async def unsubscribe(self, subscriber_id: SubscriberId, topics: Union[TopicList, None] = None):
        """
        Unsubscribe from given topics.
        Pass topics=None to unsubscribe the given subscriber from all topics

        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (Union[TopicList, None]): Topics to unsubscribe from
        """
        async with self._lock:
            # if no topics are given then unsubscribe from all topics
            if topics is None:
                topics = self._topics
            for topic in topics:
                subscribers = self._topics[topic]
                if subscriber_id in subscribers:
                    logger.info("Removing Subscription", topic=topic,
                                subscriber_id=subscriber_id)
                    del subscribers[subscriber_id]

    async def trigger_callback(self, data, topic: Topic, subscriber_id: SubscriberId, subscription: Subscription):
        await subscription.callback(subscription, data)

    async def callback_subscribers(self, subscribers: Dict[SubscriberId, Subscription],
                                   topic: Topic,
                                   data, notifier_id: SubscriberId = None, override_topic=False):
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
            # Don't notify the notifier
            if subscriber_id != notifier_id:
                logger.info("calling subscription callbacks",
                            subscriber_id=subscriber_id,
                            topic=topic, subscriptions=subscriptions)
                for subscription in subscriptions:
                    if override_topic:
                        # Report actual topic instead of ALL_TOPICS (or whatever is saved in the subscription)
                        event = subscription.copy()
                        event.topic = topic
                    else:
                        event = subscription
                    # call callback with subscription-info and provided data
                    await self.trigger_callback(data, topic, subscriber_id, event)

    async def notify(self, topics: Union[TopicList, Topic], data=None, notifier_id=None):
        """
        Notify subscribers of a new event per topic. (i.e. Publish events)

        Args:
            topics (Union[TopicList, Topic]): Topics to trigger a publish event for (Calling the callbacks of all their subscribers)
            data ([type], optional): Arbitrary data to pass each callback. Defaults to None.
            notifier_id (str): an id of the entity sending the notification, use the same id as subscriber id to avoid getting your own notifications
        """
        # allow caller to pass a single topic without a list
        if isinstance(topics, Topic):
            topics = [topics]

        # get ALL_TOPICS subscribers
        subscribers_to_all = self._topics.get(ALL_TOPICS, {})

        # TODO improve with reader/writer lock pattern - so multiple notifications can happen at once
        async with self._lock:
            for topic in topics:
                subscribers = self._topics.get(topic, {})
                # handle direct topic subscribers
                await self.callback_subscribers(subscribers, topic, data, notifier_id)
                # handle ALL_TOPICS subscribers
                # Use actual topic instead of ALL_TOPICS
                await self.callback_subscribers(subscribers_to_all, topic, data, notifier_id, override_topic=True)

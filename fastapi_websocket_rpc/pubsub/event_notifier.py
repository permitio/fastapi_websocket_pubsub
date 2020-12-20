import asyncio
from typing import Callable, Dict, List, Union

from pydantic import BaseModel  # pylint: disable=no-name-in-module

from ..logger import get_logger
from ..utils import gen_uid

SubscriberID = str
SubscriptionID = str
Topic = str
TopicList = List[Topic]

logger = get_logger('EventNotifier')

class Subscription(BaseModel):
    """
    Data model to be stored per subscription, and sent to each subscriber via the callback
    This allows for serializing the data down the line and sending to potential remote subscribers (via the callback),
    in which case the callback field itself should be removed first.
    """
    id:  SubscriptionID
    subscriber_id: SubscriberID
    topic: Topic
    callback: Callable = None


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
        self._topics: Dict[Topic, Dict[SubscriberID, List[Subscription]]] = {}
        # Lock used to sync access to mapped subscriptions
        self.lock = asyncio.Lock()

    def gen_subscriber_id(self):
        return gen_uid()

    def gen_subscription_id(self):
        return gen_uid()

    async def subscribe(self, subscriber_id: SubscriberID, topics: TopicList, callback: Callable):
        """
        Subscribe to a set of topics.
        Once a notification (i.e. publish) of a topic is received the provided callback function will be called (with topic and data)


        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (TopicList): A list of topic to subscribe to (Each topic is saved in a separate subscription)
            callback (Callable): the callback function to call upon a publish event
        """
        import pdb; pdb.set_trace()
        async with self.lock:
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
                logger.info("New subscription", subscription=new_subscription.dict())
        import pdb; pdb.set_trace()

    async def unsubscribe(self, subscriber_id: SubscriberID, topics: Union[TopicList, None]=None):
        """
        Unsubscribe from given topics.
        Pass topics=None to unsubscribe the given subscriber from all topics

        Args:
            subscriber_id (SubscriberID): A UUID identifying the subscriber
            topics (Union[TopicList, None]): Topics to unsubscribe from
        """
        import pdb; pdb.set_trace()
        async with self.lock:
            # if no topics are given then unsubscribe from all topics
            if topics is None:
                topics = self._topics
            for topic in topics:
                subscribers = self._topics[topic]
                logger.info("Removing Subscription", topic=topic, subscriber_id=subscriber_id)
                del subscribers[subscriber_id]

    async def notify(self, topics: Union[TopicList, Topic], data=None):
        """
        Notify subscribers of a new event per topic. (i.e. Publish events)

        Args:
            topics (Union[TopicList, Topic]): Topics to trigger a publish event for (Calling the callbacks of all their subscribers)
            data ([type], optional): Arbitrary data to pass each callback. Defaults to None.
        """
        import pdb; pdb.set_trace()
        # allow caller to pass a single topic without a list
        if isinstance(topics, Topic):
            topics = [topics]

        # TODO improve with reader/writer lock pattern - so multiple notifications can happen at once
        async with self.lock:
            for topic in topics:
                subscribers = self._topics.get(topic, {})
                for subscriber_id, subscriptions in subscribers.items():
                    for subscription in subscriptions:
                        # call callback with subscription-info and provided data
                        logger.info("calling subscription callback", subscriber_id=subscriber_id, topic=topic, subscription=subscription, data=data)
                        await subscription.callback(subscription, data)

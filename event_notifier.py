from lib.logger import logger
from lib.utils import gen_uid
from typing import List, Callable, Dict, Union
from pydantic import BaseModel  # pylint: disable=no-name-in-module
import asyncio

SubscriberID = str
SubscriptionID = str
Topic = str
TopicList = List[Topic]


class Subscription(BaseModel):
    id:  SubscriptionID
    subscriber_id: SubscriberID
    topic: Topic
    callback: Callable= None


class EventNotifier:

    def __init__(self):

        self._topics: Dict[Topic, Dict[SubscriberID, List[Subscription]]] = {}
        self.lock = asyncio.Lock()

    def gen_subscriber_id(self):
        return gen_uid()

    def gen_subscrition_id(self):
        return gen_uid()

    async def subscribe(self, subscriber_id: SubscriberID, topics: TopicList, callback: Callable):
        async with self.lock:
            for topic in topics:
                subscribers = self._topics[topic] = self._topics.get(topic, {})
                subscriptions = subscribers[subscriber_id] = subscribers.get(subscriber_id, [])
                new_subscription = Subscription(id=self.gen_subscrition_id(),
                                                subscriber_id=subscriber_id,
                                                topic=topic,
                                                callback=callback)
                subscriptions.append(new_subscription)
                logger.info("New subscription", subscription=new_subscription)



    async def unsubscribe(self, subscriber_id: SubscriberID, topics: Union[TopicList,None]):
        async with self.lock:
            #if no topics are given then unsubscribe from all topics
            if topics is None:
                topics = self._topics
            for topic in topics:
                subscribers = self._topics[topic] 
                del subscribers[subscriber_id]
                

    async def notify(self, topics:TopicList, data=None):
        #TODO improve with reader/writer lock pattern - so multiple notifications can happen at once
        async with self.lock:
            for topic in topics:
                subscribers = self._topics.get(topic, {})
                for subscriber_id, subscriptions in subscribers.items():
                    for subscription in subscriptions:
                        # call callback with subscritpion-info and provided data
                        await subscription.callback(subscription, data)



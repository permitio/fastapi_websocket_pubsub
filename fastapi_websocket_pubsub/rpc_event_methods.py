import asyncio
from fastapi_websocket_rpc import RpcMethodsBase
from .event_notifier import EventNotifier, Subscription, TopicList
from .logger import get_logger


class RpcEventServerMethods(RpcMethodsBase):

    def __init__(self, event_notifier: EventNotifier):
        super().__init__()
        self.event_notifier = event_notifier
        self.logger = get_logger('PubSubServer')

    async def subscribe(self, topics: TopicList = []) -> bool:
        """
        provided by the server so that the client can subscribe to topics.
        when new events are available on a topic, the server will call the
        client's `notify` method.
        """
        try:
            async def callback(subscription: Subscription, data):
                # remove the actual function
                sub = subscription.copy(exclude={"callback"})
                self.logger.debug("Notifying other side",
                                 {"subscription":subscription,
                                 "data":data, "channel_id": self.channel.id})
                await self.channel.other.notify(subscription=sub, data=data)

            # We'll use our channel id as our subscriber id
            sub_id = self.channel.id
            await self.event_notifier.subscribe(sub_id, topics, callback)
            return True
        except Exception as err:
            self.logger.exception("Failed to subscribe to RPC events notifier", topics)
            return False

    async def publish(self, topics: TopicList = [], data=None, sync=True, notifier_id=None) -> bool:
        """
        Publish an event through the server to subscribers

        Args:
            topics (TopicList): topics to publish
            data (Any, optional): data to pass with the event to the subscribers. Defaults to None.
            sync (bool, optional): Should the server finish publishing before returning to us
            notifier_id(str,optional): A unique identifier of the source of the event
                use a different id from the channel.id or the subscription id to receive own publications        

        Returns:
            bool: was the publish successful                
        """
        try:
            # use the given id or use our channel id
            notifier_id = notifier_id if notifier_id is not None else self.channel.id
            promise = self.event_notifier.notify(topics, data, notifier_id=notifier_id)
            if sync:
                await promise
            else:
                asyncio.create_task(promise)
            return True
        except Exception as err:
            self.logger.error("Failed to publish to events notifier",topics)
            return False

    async def ping(self) -> str:
        return "pong"


class RpcEventClientMethods(RpcMethodsBase):

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.logger = get_logger('PubSubClient')

    async def notify(self, subscription=None, data=None):
        self.logger.info("Received notification of event",
                         {'subscription':subscription, 'data':data})
        await self.client.trigger_topic(topic=subscription["topic"], data=data)

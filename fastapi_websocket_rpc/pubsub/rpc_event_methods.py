from .event_notifier import EventNotifier, Subscription, TopicList
from ..logger import get_logger
from ..websocket.rpc_methods import RpcMethodsBase


class RpcEventServerMethods(RpcMethodsBase):

    def __init__(self, event_notifier: EventNotifier):
        super().__init__()
        self.event_notifier = event_notifier
        self.logger = get_logger('RpcServer')

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
                self.logger.info("Notifying other side", subscription=subscription, data=data, channel_id=self.channel.id)
                await self.channel.other.notify(subscription=sub, data=data)

            # We'll use our channel id as our subscriber id
            sub_id = self.channel.id
            await self.event_notifier.subscribe(sub_id, topics, callback)
            return True
        except Exception as err:
            self.logger.error("Failed to subscribe to RPC events notifier",
                         err=err, topics=topics)
            return False

    async def ping(self) -> str:
        return "pong"


class RpcEventClientMethods(RpcMethodsBase):

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.logger = get_logger('RpcClient')

    async def notify(self, subscription=None, data=None):
        self.logger.info("Received notification of event",
                    subscription=subscription, data=data)
        await self.client.act_on_topic(topic=subscription["topic"], data=data)

from ..event_notifier import EventNotifier, Subscription, TopicList
from ..logger import logger
from ..websocket.rpc_methods import RpcMethodsBase


class RpcEventServerMethods(RpcMethodsBase):

    def __init__(self, event_notifier:EventNotifier):
        super().__init__()
        self.event_notifier = event_notifier


    async def subscribe(self, topics:TopicList=[])->bool:
        try:

            async def callback(subscription:Subscription, data):
                # remove the actual function
                sub = subscription.copy(exclude={"callback"})
                await self.channel.other.notify(subscription=sub, data=data)

            # We'll use our channel id as our subscriber id
            sub_id = self.channel.id
            await self.event_notifier.subscribe(sub_id,topics, callback)
            return True
        except Exception as err:
            logger.error("Failed to subscribe to RPC events notifier", err=err, topics=topics)
            return False


class RpcEventClientMethods(RpcMethodsBase):

    async def notify(self, subscription=None, data=None):
        logger.info("Received notification of event", subscription=subscription, data=data)


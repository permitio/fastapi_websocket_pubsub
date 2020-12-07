from lib.event_notifier import TopicList
from lib.websocket.websocket_rpc_endpoint import WebsocketRPCEndpoint

from .rpc_event_methods import RpcEventServerMethods
from .websocket_rpc_event_notifier import WebSocketRpcEventNotifier


class EventRpcEndpoint:

    def __init__(self):
        self.notifier = WebSocketRpcEventNotifier()
        self.methods = RpcEventServerMethods(self.notifier)
        self.endpoint = WebsocketRPCEndpoint(self.methods)

    async def notify(self, topics: TopicList, data=None):
        """
        Notify subscribres of given topics currently connected to the endpoint
        """
        await self.notifier.notify(topics, data)

    def register_routes(self, router):
        self.endpoint.register_routes(router)

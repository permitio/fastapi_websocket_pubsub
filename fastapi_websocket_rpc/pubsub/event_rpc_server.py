from typing import Union

from fastapi import WebSocket
from .event_notifier import Topic, TopicList
from ..websocket.websocket_rpc_endpoint import WebsocketRPCEndpoint
from .rpc_event_methods import RpcEventServerMethods
from .websocket_rpc_event_notifier import WebSocketRpcEventNotifier


class EventRpcEndpoint:
    """
    RPC pub/sub server endpoint
    """

    def __init__(self, methods_class=None, notifier=None):
        """

        Args:
            methods_class (optional): a class deriving from RpcEventServerMethods providing a 'subscribe' rpc method
                                      or None if RpcEventServerMethods should be used as is
            notifier (optional): Instance of WebSocketRpcEventNotifier or None to use WebSocketRpcEventNotifier() as is
        """
        self.notifier = notifier if notifier is not None else WebSocketRpcEventNotifier()
        self.methods = methods_class(self.notifier) if methods_class is not None else RpcEventServerMethods(self.notifier)
        self.endpoint = WebsocketRPCEndpoint(self.methods, on_disconnect=self.on_disconnect)

    async def notify(self, topics: Union[TopicList, Topic], data=None):
        """
        Notify subscribres of given topics currently connected to the endpoint
        """
        await self.notifier.notify(topics, data)

    async def on_disconnect(self, channel_id: str):
        await self.notifier.unsubscribe(channel_id)

    async def main_loop(self, websocket: WebSocket, client_id: str = None, **kwargs):
        await self.endpoint.main_loop(websocket, client_id=client_id, **kwargs)

    def register_routes(self, router):
        """
        Register websocket routes on the given router
        Args:
            router: FastAPI router to load route onto
        """
        self.endpoint.register_routes(router)

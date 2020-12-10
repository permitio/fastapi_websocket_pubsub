import asyncio

from ..websocket.websocket_rpc_client import WebSocketRpcClient
from .rpc_event_methods import RpcEventClientMethods


class EventRpcClient:
    """
    RPC pub/sub client

    Simple usage example (init class with subscription topics):
        client = EventRpcClient(["guns", "germs", "steel"])
        client.start_client("ws://localhost:8000/ws/test-client1")

    Advanced usage:
        override on_connect() to add more subscription / registartion logic
    """

    def __init__(self, topics=None, methods=None) -> None:
        """
        Args:
            topics client should subscribe to.
            methods ([type], optional): [description]. Defaults to None.
        """
        self.topics = topics
        self._methods = methods if methods is not None else RpcEventClientMethods()

    async def _client_loop(self, uri, wait_on_reader=True):
        async with  WebSocketRpcClient(uri, self._methods) as client:
            await self.on_connect(client)
            if wait_on_reader:
                await client.wait_on_reader()

    async def on_connect(self, client):
        """
        Method called upon first connection to server
        """
        if self.topics is not None:
            await client.channel.other.subscribe(topics=self.topics)

    def start_client(self, server_uri):
        """
        Start the client and wait on the sever-side
        """
        asyncio.get_event_loop().run_until_complete(self._client_loop(server_uri))

    def start_client_async(self, server_uri):
        """
        Start the client and return once finished subscribing to events
        RPC notifications will still be handeled in the background
        """
        asyncio.get_event_loop().run_until_complete(self._client_loop(server_uri, False))



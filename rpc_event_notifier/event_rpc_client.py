from lib.websocket.websocket_rpc_client import WebSocketRpcClient
from .rpc_event_methods import RpcEventClientMethods
import asyncio


class EventRpcClient:

    def __init__(self, topics=None) -> None:
        self.topics = topics

    async def _client_loop(self, uri, wait_on_reader=True):
        async with  WebSocketRpcClient(uri, RpcEventClientMethods()) as client:
            if self.topics is not None:
                await client.channel.other.subscribe(topics=self.topics)
            if wait_on_reader:
                await client.wait_on_reader()

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
                


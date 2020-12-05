import websockets
from .schemas import RpcRequest, RpcResponse
from lib.utils import gen_uid
from typing import Dict
import uuid
from pydantic import ValidationError
import asyncio
import logging
from .rpc_channel import RpcChannel


class WebSocketRpcClient:

    def __init__(self, uri, methods):
        self.methods = methods
        # Websocket connection
        self.conn = None
        # Websocket object
        self.ws = None
        # URI to connect on
        self.uri = uri
        # Pending requests - id mapped to async-event
        self.requests: Dict[str, asyncio.Event] = {}
        # Received responses
        self.responses = {}
           # Read worker
        self._read_task = None
        self.channel = None

    async def __aenter__(self):
        # Start connection
        self.conn = websockets.connect(self.uri)
        # Get socket
        self.ws = await self.conn.__aenter__()
        # Start reading
        self._read_task = asyncio.create_task(self.reader())
        self.channel = RpcChannel(self, self.ws)
        return self

    async def __aexit__(self, *args, **kwargs):
        # Stop reader
        self._read_task.cancel()
        # Stop socket
        await self.conn.__aexit__(*args, **kwargs)

    async def reader(self):
        """
        Read responses from socket worker
        """
        while True:
            raw_message = await self.ws.recv()
            await self.channel.on_message(raw_message)


    async def call(self, name, args={}):
        """
        Call a method and wait for a response to be received
        """
        return await self.channel.call(name, args)
  
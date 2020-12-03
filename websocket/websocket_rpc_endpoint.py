import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.endpoints import WebSocketEndpoint
from starlette.types import ASGIApp, Receive, Scope, Send
from typing import Dict
from .connection_manager import ConnectionManager
from .schemas import RpcRequest, RpcResponse
from .rpc_methods import RpcMethods
from .rpc_channel import RpcChannel


class WebsocketRPCEndpoint:

    def __init__(self, methods, manager = None):
        self.manager = manager if manager is not None else ConnectionManager()
        self.methods = methods

    def register_routes(self, router, prefix="/ws/"):

        @router.websocket(prefix + "{client_id}")
        async def websocket_endpoint(websocket: WebSocket, client_id: str):
            await self.manager.connect(websocket)
            channel = RpcChannel(self.methods, websocket)
            try:
                while True:
                    data = await websocket.receive()
                    await channel.on_message(data)
            except WebSocketDisconnect:
                self.manager.disconnect(websocket)

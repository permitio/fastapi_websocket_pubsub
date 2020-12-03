import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .connection_manager import ConnectionManager
from .schemas import RpcRequest, RpcResponse

# NULL default value - indicating no response was received
class NoResponse:
    pass



class RpcMethods:

    def __init__(self, endpoint):
        """
        endpoint (WebsocketRPCEndpoint): the endpoint these methods are loaded into
        """
        self.endpoint = endpoint
        self.manager: ConnectionManager = endpoint.manager

    async def echo(self, text: str) -> str:
        return text

    async def broadcast(self, text: str) -> str:
        tasks = []
        for client in self.manager.active_connections:
            tasks.append(asyncio.create_task(
                client.send_json(RpcResponse(result=text).dict())))
        await asyncio.gather(*tasks)
        return "performed broadcast"

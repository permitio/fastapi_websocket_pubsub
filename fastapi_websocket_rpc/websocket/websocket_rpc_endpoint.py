from fastapi import WebSocket, WebSocketDisconnect
from fastapi.param_functions import Depends
from fastapi import APIRouter, FastAPI, Depends, Header, HTTPException
import websockets

from .connection_manager import ConnectionManager
from .rpc_channel import RpcChannel
from .rpc_methods import RpcMethodsBase
from ..logger import get_logger

logger = get_logger("RPC_ENDPOINT") 

class WebSocketSimplifier:
    """
    Simple warpper over FastAPI WebSocket to ensure unified interface for send/recv
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    @property
    def send(self):
        return self.websocket.send_text

    @property
    def recv(self):
        return self.websocket.receive_text


class WebsocketRPCEndpoint:
    """
    A websocket RPC sever endpoint, exposing RPC methods
    """

    def __init__(self, methods: RpcMethodsBase, manager=None, on_disconnect=None):
        """[summary]

        Args:
            methods (RpcMethodsBase): RPC methods to expose
            manager ([ConnectionManager], optional): Connection tracking object. Defaults to None (i.e. new ConnectionManager()).
        """
        self.manager = manager if manager is not None else ConnectionManager()
        self.methods = methods
        self._on_disconnect = on_disconnect

    async def main_loop(self, websocket: WebSocket, client_id: str = None, **kwargs):
        try:
            await self.manager.connect(websocket)
            logger.info(f"Client connected", remote_address=websocket.client)
            channel = RpcChannel(self.methods, WebSocketSimplifier(websocket), **kwargs)
            channel.register_disconnect_handler(self._on_disconnect)
            try:
                while True:
                    data = await websocket.receive_text()
                    await channel.on_message(data)
            except WebSocketDisconnect:
                logger.error(f"Client disconnected - {websocket.client.port} :: {channel.id}")
                self.manager.disconnect(websocket)
                await channel.on_disconnect()
        except: 
            logger.exception(f"Failed to serve - {websocket.client.port}")
            self.manager.disconnect(websocket)
            

    def register_routes(self, router, prefix="/ws"):
        """
        Register websocket routes on the given router
        Args:
            router: FastAPI router to load route onto
            prefix (str, optional): the start of the route path - final route will add "{client_id}". Defaults to "/ws".
        """

        @router.websocket(prefix + "/{client_id}")
        async def websocket_endpoint(websocket: WebSocket, client_id: str):
            await self.main_loop(websocket, client_id)

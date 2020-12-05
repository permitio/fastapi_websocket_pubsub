import asyncio
import os
import sys
import typing
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .connection_manager import ConnectionManager
from .schemas import RpcRequest, RpcResponse


# NULL default value - indicating no response was received
class NoResponse:
    pass


class RpcMethodsBase:

    def __init__(self):
        """
        endpoint (WebsocketRPCEndpoint): the endpoint these methods are loaded into
        """
        self.channel = None

    def set_channel(self, channel):
        self.channel = channel


class ProcessDetails(BaseModel):
    pid: int = os.getpid()
    cmd: typing.List[str] = sys.argv
    workingdir: str = os.getcwd()


class RpcMethods(RpcMethodsBase):

    def __init__(self):
        """
        endpoint (WebsocketRPCEndpoint): the endpoint these methods are loaded into
        """
        super().__init__()

    async def get_proccess_details(self) -> ProcessDetails:
        return ProcessDetails()

    async def echo_method(self, method_name, args) -> bool:
        if self.channel is not None:
            asyncio.create_task(self.channel.call(method_name, args))
            return True
        else:
            return False

    async def echo(self, text: str) -> str:
        return text

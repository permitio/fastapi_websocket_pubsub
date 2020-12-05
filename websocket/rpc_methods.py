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


class ProcessDetails(BaseModel):
    pid: int = os.getpid()
    cmd: typing.List[str] = sys.argv
    workingdir: str = os.getcwd()



class RpcMethods:

    def __init__(self):
        """
        endpoint (WebsocketRPCEndpoint): the endpoint these methods are loaded into
        """

    async def get_proccess_details(self) -> ProcessDetails:
        return ProcessDetails()

    async def echo(self, text: str) -> str:
        return text

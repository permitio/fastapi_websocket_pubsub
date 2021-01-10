import asyncio
import os
import sys
import typing
import copy

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .connection_manager import ConnectionManager
from .schemas import RpcRequest, RpcResponse


# NULL default value - indicating no response was received
class NoResponse:
    pass


class RpcMethodsBase:
    """
    The basic interface RPC channels excpets method groups to implement.
     - create copy of the method object
     - set channel 
    """

    def __init__(self):
        self._channel = None

    def set_channel(self, channel):
        """
        Allows the channel to share access to its functions to the methods once nested under it
        """
        self._channel = channel

    @property
    def channel(self):
        return self._channel

    def copy(self):
        """ Simple copy ctor - overriding classes may need to override copy as well."""
        return copy.copy(self)


class ProcessDetails(BaseModel):
    pid: int = os.getpid()
    cmd: typing.List[str] = sys.argv
    workingdir: str = os.getcwd()


class RpcUtilityMethods(RpcMethodsBase):
    """
    A simple set of RPC functions useful for management and testing
    """

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

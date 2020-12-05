import asyncio

from typing import Dict
from .schemas import RpcRequest, RpcResponse, RpcMessage
from .rpc_methods import NoResponse
from lib.utils import gen_uid
from typing import Dict
import uuid
from pydantic import ValidationError
import asyncio
from lib.logger import logger
from inspect import signature, _empty


class RpcPromise:
    """
    Simple Event and id wrapper/proxy
    Holds the state of a pending request
    """

    def __init__(self, request: RpcRequest):
        self._request = request
        self._id = request.call_id
        self._event = asyncio.Event()

    @property
    def call_id(self):
        return self._id

    def set(self):
        self._event.set()

    def wait(self):
        return self._event.wait()


class RpcChannel:

    def __init__(self, methods, socket):
        self.methods = methods
        # Pending requests - id-mapped to async-event
        self.requests: Dict[str, asyncio.Event] = {}
        # Received responses
        self.responses = {}
        self.socket = socket

    def get_return_type(self, method):
        method_signature = signature(method)
        return method_signature.return_annotation if method_signature.return_annotation is not _empty else str

    async def send(self, data):
        await self.socket.send(data)

    async def receive(self, data):
        return await self.socket.recv()

    async def on_message(self, data):
        try:
            message = RpcMessage.parse_raw(data)
            if message.request is not None:
                await self.on_request(message.request)
            if message.response is not None:
                await self.on_response(message.response)
        except ValidationError as e:
            logger.error(f"Failed to parse message", message=data, error=e)

    async def on_request(self, message: RpcRequest):
        logger.info("Handling RPC request", request=message)
        method = getattr(self.methods, message.method)
        if callable(method):
            result = await method(**message.arguments)
        if result is not NoResponse:
            # get indicated type
            result_type = self.get_return_type(method)
            # if no type given - try to convert to string
            if result_type is str and type(result) is not str:
                result = str(result)
            response = RpcMessage(response=RpcResponse[result_type](
                call_id=message.call_id, result=result, result_type=result_type.__name__))
            await self.send(response.json())

    async def on_response(self, response: RpcResponse):
        logger.info("Handling RPC response", response=response)
        if response.call_id is not None and response.call_id in self.requests:
            self.responses[response.call_id] = response
            promise = self.requests[response.call_id]
            promise.set()

    async def wait_for_response(self, promise):
        """
        Wait on a previously made call
        """
        await promise.wait()
        response = self.responses[promise.call_id]
        del self.requests[promise.call_id]
        del self.responses[promise.call_id]
        return response

    async def async_call(self, name, args={}):
        """
        Call a method and return the event and the sent message (including the chosen call_id)
        use self.wait_for_response on the event and call_id to get the return value of the call
        """
        msg = RpcMessage(request=RpcRequest(
            method=name, arguments=args, call_id=gen_uid()))
        logger.info("Calling RPC method", message=msg)
        await self.send(msg.json())
        promise = self.requests[msg.request.call_id] = RpcPromise(msg.request)
        return promise

    async def call(self, name, args={}):
        """
        Call a method and wait for a response to be received
        """
        promise = await self.async_call(name, args)
        return await self.wait_for_response(promise)

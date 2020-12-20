import asyncio

from fastapi_websocket_rpc.websocket.rpc_methods import RpcUtilityMethods
from fastapi_websocket_rpc.websocket.websocket_rpc_client import WebSocketRpcClient


async def run_client(uri):
    async with WebSocketRpcClient(uri, RpcUtilityMethods(), extra_headers=[("X-TOKEN", "fake-super-secret-token")]) as client:
        response = await client.other.echo(text="Hello World!")
        print(response)
        response = await client.call("get_proccess_details")
        print(response)
        response = await client.call("echo_method", {"method_name": "get_proccess_details", "args": {}})
        print(response)
        # wait for server to call us and we reply
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(
        run_client("ws://localhost:8000/ws/a3"))

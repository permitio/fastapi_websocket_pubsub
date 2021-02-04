
# ⚡ FASTAPI Websocket Pub/Sub

<a href="https://github.com/authorizon/fastapi_websocket_pubsub/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/authorizon/fastapi_websocket_pubsub/workflows/Tests/badge.svg" alt="Tests">
</a>

<a href="https://pypi.org/project/fastapi-websocket-pub/" target="_blank">
    <img src="https://img.shields.io/pypi/v/fastapi-websocket-pubsub?color=%2331C654&label=PyPi%20package" alt="Package">
</a>


A fast and durable Pub/Sub channel over Websockets.
The easiest way to create a live publish / subscribe multi-cast over the web.

Supports and tested on Python >= 3.7 

## Intro
- The classic pub/sub pattern made easily accessible and scalable over the web and across your cloud in realtime.

- Subscribe
    - Clients subscribe to topics (arbitrary strings) and receive relevant events along with structured data (serialized with Pydantic).

- Publish 
    - Directly from server code to connected clients. 
        ```python
        app =  FastAPI() 
        endpoint = PubSubEndpoint()
        endpoint.register_route(app, "/pubsub")
        endpoint.publish(["my_event_topic"], data=["my", "data", 1])
        ```
    - From client to client through the servers
        ```python 
        client = PubSubClient()
        client.start_client(uri)
        endpoint.publish(["my_event_topic"], data=["my", "data", 1])
        ```    
    - Across server instances (using [broadcaster](https://pypi.org/project/broadcaster/) and a backend medium (e.g. Redis, Kafka, ...)
        - No matter which server a client connected to - it will get the its message



## Installation 🛠️
```
pip install fastapi_websocket_pubsub
```


## Simple Subscribe example:

Say the server exposes a "add" method, e.g. :
```python
class RpcCalculator(RpcMethodsBase):
    async def add(self, a, b):
        return a + b
```
Calling it is as easy as calling the method under the client's "other" property:
```python
response = await client.other.add(a=1,b=2)
print(response.result) # 3
```
getting the response with the return value.




## Usage example:

### Server:
```python
import uvicorn
from fastapi import FastAPI
from fastapi_websocket_rpc import RpcMethodsBase, WebsocketRPCEndpoint

# Methods to expose to the clients
class ConcatServer(RpcMethodsBase):
    async def concat(self, a="", b=""):
        return a + b
    
# Init the FAST-API app
app =  FastAPI()
# Create an endpoint and load it with the methods to expose
endpoint = WebsocketRPCEndpoint(ConcatServer())
# add the endpoint to the app
endpoint.register_route(app, "/ws")

# Start the server itself
uvicorn.run(app, host="0.0.0.0", port=9000)
```
### Client
```python
import asyncio
from fastapi_websocket_rpc import RpcMethodsBase, WebSocketRpcClient

async def run_client(uri):
    async with WebSocketRpcClient(uri, RpcMethodsBase()) as client:
        # call concat on the other side
        response = await client.other.concat(a="hello", b=" world")
        # print result
        print(response.result)  # will print "hello world"

# run the client until it completes interaction with server
asyncio.get_event_loop().run_until_complete(
    run_client("ws://localhost:9000/ws")
)
```

See the [examples](/examples) and [tests](/tests) folders for more server and client examples


## Server calling client example:
- Clients can call ```client.other.method()``` 
    - which is a shortcut for ```channel.other.method()```
- Servers also get the channel object and can call remote methods via ```channel.other.method()```
- See the [bidirectional call example](examples/bidirectional_server_example.py) for calling client from server and server events (e.g. ```on_connect```).


## What can I do with this?
Websockets are ideal to create bi-directional realtime connections over the web. 
 - Push updates 
 - Remote control mechanism 
 - Pub / Sub (see fastapi_websocket_pubsub)
 - Trigger events (see "tests/trigger_flow_test.py")
 - Node negotiations (see "tests/advanced_rpc_test.py :: test_recursive_rpc_calls")


## Concepts
- [RpcChannel](fastapi_websocket_rpc/rpc_channel.py) - implements the RPC-protocol over the websocket
    - Sending RpcRequests per method call 
    - Creating promises to track them (via unique call ids), and allow waiting for responses 
    - Executing methods on the remote side and serializing return values as    
    - Receiving RpcResponses and delivering them to waiting callers
- [RpcMethods](fastapi_websocket_rpc/rpc_methods.py) - classes passed to both client and server-endpoint inits to expose callable methods to the other side.
    - Simply derive from RpcMethodsBase and add your own async methods
    - Note currently only key-word arguments are supported
    - Checkout RpcUtilityMethods for example methods, which are also useful debugging utilities


- Foundations:

    - Based on [fastapi-websocket-rpc](https://github.com/acallasec/fastapi_websocket_rpc) for a robust realtime bidirectional channel

    - Based on [broadcaster](https://pypi.org/project/broadcaster/) for syncing server instances

    - Server Endpoint:

        - Based on [FAST-API](https://github.com/tiangolo/fastapi): enjoy all the benefits of a full ASGI platform, including Async-io and dependency injections (for example to authenticate connections)

        - Based on [Pydnatic](https://pydantic-docs.helpmanual.io/): easily serialize structured data as part of RPC requests and responses (see 'tests/basic_rpc_test.py :: test_structured_response' for an example)

    - Client :
        - Based on [Tenacity](https://tenacity.readthedocs.io/en/latest/index.html): allowing configurable retries to keep to connection alive
            - see WebSocketRpcClient.__init__'s retry_config 
            
        - Based on python [websockets](https://websockets.readthedocs.io/en/stable/intro.html) - a more comprehensive client than the one offered by Fast-api



## Pull requests - welcome!
- Please include tests for new features 




# ⚡ FASTAPI Websocket Pub/Sub 🗞️

<a href="https://github.com/authorizon/fastapi_websocket_pubsub/actions?query=workflow%3ATests" target="_blank">
    <img src="https://github.com/authorizon/fastapi_websocket_pubsub/workflows/Tests/badge.svg" alt="Tests">
</a>

<a href="https://pypi.org/project/fastapi-websocket-pubsub/" target="_blank">
    <img src="https://img.shields.io/pypi/v/fastapi-websocket-pubsub?color=%2331C654&label=PyPi%20package" alt="Package">
</a>


A fast and durable Pub/Sub channel over Websockets.
The easiest way to create a live publish / subscribe multi-cast over the web.

Supports and tested on Python >= 3.7 


## Installation 🛠️
```
pip install fastapi_websocket_pubsub
```


## Intro
The classic pub/sub pattern made easily accessible and scalable over the web and across your cloud in realtime; while enjoying the benefits of FastAPI (e.g. dependency injection).

FastAPI + WebSockets + PubSub ==  ⚡💪 ❤️


- Subscribe
    - Clients subscribe to topics (arbitrary strings) and receive relevant events along with structured data (serialized with Pydantic).
        ```python
        # Callback to be called upon event being published on server
        async def on_event(data):
            print("We got an event! with data- ", data)
        # Subscribe for the event 
        client.subscribe("my event", on_event)
        ```

- Publish 
    - Directly from server code to connected clients. 
        ```python
        app = FastAPI() 
        endpoint = PubSubEndpoint()
        endpoint.register_route(app, "/pubsub")
        endpoint.publish(["my_event_topic"], data=["my", "data", 1])
        ```
    - From client to client (through the servers)
        ```python 
        async with PubSubClient(server_uri="ws://localhost/pubsub") as client:
            endpoint.publish(["my_event_topic"], data=["my", "data", 1])
        ```    
    - Across server instances (using [broadcaster](https://pypi.org/project/broadcaster/) and a backend medium (e.g. Redis, Kafka, ...))
        - No matter which server a client connects to - it will get the messages it subscribes to
        ```python
        app = FastAPI() 
        endpoint = PubSubEndpoint(broadcaster="postgres://localhost:5432/")
        
        @app.websocket("/pubsub")
        async def websocket_rpc_endpoint(websocket: WebSocket):
            async with endpoint.broadcaster:
                await endpoint.main_loop(websocket)
        ```
        see [examples/pubsub_broadcaster_server_example.py](examples/pubsub_broadcaster_server_example.py) for full usage example 



## Usage example (server publishing following HTTP trigger):
In the code below, a client connects to the server and subscribes to a topic named "triggered".
Aside from PubSub websocket, the server also exposes a regular http route, which triggers publication of the event. 

### Server:
```python
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from fastapi_websocket_pubsub import PubSubEndpoint
app =  FastAPI()
# Init endpoint
endpoint = PubSubEndpoint()
# register the endpoint on the app
endpoint.register_route(app, "/pubsub")
# Register a regular HTTP route
@app.get("/trigger")
async def trigger_events():
    # Upon request trigger an event
    endpoint.publish(["triggered"])
```
### Client:
```python
from fastapi_websocket_pubsub import PubSubClient
# Callback to be called upon event being published on server
async def on_trigger(data):
    print("Trigger URL was accessed")

async with PubSubClient(server_uri="ws://localhost/pubsub") as client:
    # Subscribe for the event 
    client.subscribe("triggered", on_event)

```

## More Examples
- See the [examples](/examples) and [tests](/tests) folders for more server and client examples.
- See [fastapi-websocket-rpc depends example](https://github.com/authorizon/fastapi_websocket_rpc/blob/master/tests/fast_api_depends_test.py) to see how to combine with FASTAPI dependency injections 

## What can I do with this?
The combination of Websockets, and bi-directional Pub/Sub is  ideal to create realtime data propagation solution at scale over the web. 
 - Update mechanism
 - Remote control mechanism
 - Data processing
 - Distributed computing
 - Realtime communications over the web   


## Foundations:

- Based on [fastapi-websocket-rpc](https://github.com/authorizon/fastapi_websocket_rpc) for a robust realtime bidirectional channel

- Based on [broadcaster](https://pypi.org/project/broadcaster/) for syncing server instances

- Server Endpoint:

    - Based on [FAST-API](https://github.com/tiangolo/fastapi): enjoy all the benefits of a full ASGI platform, including Async-io and dependency injections (for example to authenticate connections)

    - Based on [Pydnatic](https://pydantic-docs.helpmanual.io/): easily serialize structured data as part of RPC requests and responses. Simply Pass Pydantic data models as PubSub published data to have it available as part of an event. 

- Client :
    - Based on [Tenacity](https://tenacity.readthedocs.io/en/latest/index.html): allowing configurable retries to keep to connection alive
        - see WebSocketRpcClient.__init__'s retry_config 

    - Based on python [websockets](https://websockets.readthedocs.io/en/stable/intro.html) - a more comprehensive client than the one offered by Fast-api

## Logging 
fastapi-websocket-pubsub uses fastapi-websocket-rpc for logging config.
It provides a helper logging module to control how it produces logs for you.
See [fastapi_websocket_rpc/logger.py](fastapi_websocket_rpc/logger.py).
Use ```logging_config.set_mode``` or the 'WS_RPC_LOGGING' environment variable to choose the logging method you prefer.
Or override completely via default logging config (e.g. 'logging.config.dictConfig'), all logger name start with: 'fastapi.ws_rpc.pubsub'

example:
```python
# set RPC to log like UVICORN
from fastapi_websocket_rpc.logger import logging_config, LoggingModes
logging_config.set_mode(LoggingModes.UVICORN)
```

## Pull requests - welcome!
- Please include tests for new features 



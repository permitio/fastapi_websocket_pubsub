import os
import sys
import pytest
import asyncio
import uvicorn
import requests
from fastapi import FastAPI
from multiprocessing import Process

from fastapi_websocket_rpc.utils import gen_uid
from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_rpc import WebsocketRPCEndpoint, RpcMethodsBase

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient
from fastapi_websocket_pubsub.rpc_event_methods import RpcEventServerMethods
from fastapi_websocket_pubsub.websocket_rpc_event_notifier import (
    WebSocketRpcEventNotifier,
)

logger = get_logger("Test")

PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"
trigger_url = f"http://localhost:{PORT}/trigger"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"


class CustomPubSubMethods(RpcEventServerMethods):
    async def custom_method(self) -> str:
        return "custom_response"


class InvalidMethods(RpcMethodsBase):
    async def some_method(self) -> str:
        return "hello"


def setup_server_rest_route(app, endpoint: PubSubEndpoint):
    @app.get("/trigger")
    async def trigger_events():
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"


def setup_server_with_premade_endpoint():
    app = FastAPI()
    premade_endpoint = WebsocketRPCEndpoint()
    endpoint = PubSubEndpoint(endpoint=premade_endpoint)
    endpoint.register_route(app, path="/pubsub")
    setup_server_rest_route(app, endpoint)
    uvicorn.run(app, port=PORT)


def setup_server_with_no_methods_endpoint():
    app = FastAPI()
    premade_endpoint = WebsocketRPCEndpoint()
    endpoint = PubSubEndpoint(endpoint=premade_endpoint)
    endpoint.register_route(app, path="/pubsub")
    setup_server_rest_route(app, endpoint)
    uvicorn.run(app, port=PORT)


def setup_server_with_custom_methods():
    app = FastAPI()
    endpoint = PubSubEndpoint(methods_class=CustomPubSubMethods)
    endpoint.register_route(app, path="/pubsub")
    setup_server_rest_route(app, endpoint)
    uvicorn.run(app, port=PORT)


def setup_server_with_premade_methods_and_notifier():
    app = FastAPI()
    custom_notifier = WebSocketRpcEventNotifier()
    custom_methods = RpcEventServerMethods(custom_notifier)
    premade_endpoint = WebsocketRPCEndpoint(custom_methods)
    endpoint = PubSubEndpoint(endpoint=premade_endpoint)
    endpoint.register_route(app, path="/pubsub")
    setup_server_rest_route(app, endpoint)
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    proc = Process(target=setup_server_with_premade_endpoint, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()


@pytest.fixture()
def server_no_methods():
    proc = Process(target=setup_server_with_no_methods_endpoint, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()


@pytest.fixture()
def server_custom_methods():
    proc = Process(target=setup_server_with_custom_methods, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()


@pytest.fixture()
def server_premade_methods_notifier():
    proc = Process(
        target=setup_server_with_premade_methods_and_notifier, args=(), daemon=True
    )
    proc.start()
    yield proc
    proc.kill()


@pytest.mark.asyncio
async def test_premade_endpoint_subscribe_http_trigger(server):
    # finish trigger
    finish = asyncio.Event()
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listening
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_premade_endpoint_pub_sub(server):
    # finish trigger
    finish = asyncio.Event()
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listening
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # publish events (with sync=False to avoid deadlocks waiting on the publish to ourselves)
        published = await client.publish(
            [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
        )
        assert published.result
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_premade_endpoint_no_methods(server_no_methods):
    # finish trigger
    finish = asyncio.Event()
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listening
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_premade_endpoint_custom_methods_preserved(server_custom_methods):
    # finish trigger
    finish = asyncio.Event()
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listening
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_premade_endpoint_with_methods_and_notifier(
    server_premade_methods_notifier,
):
    # finish trigger
    finish = asyncio.Event()
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listening
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


def test_premade_endpoint_invalid_methods_raises_error():
    invalid_methods = InvalidMethods()
    premade_endpoint = WebsocketRPCEndpoint(invalid_methods)

    with pytest.raises(ValueError) as exc_info:
        PubSubEndpoint(endpoint=premade_endpoint)

    assert "RpcEventServerMethods" in str(exc_info.value)
    assert "InvalidMethods" in str(exc_info.value)


def test_premade_endpoint_with_methods_and_methods_class_raises_error():
    custom_notifier = WebSocketRpcEventNotifier()
    custom_methods = RpcEventServerMethods(custom_notifier)
    premade_endpoint = WebsocketRPCEndpoint(custom_methods)

    with pytest.raises(ValueError) as exc_info:
        PubSubEndpoint(methods_class=RpcEventServerMethods, endpoint=premade_endpoint)

    assert "methods_class" in str(exc_info.value)

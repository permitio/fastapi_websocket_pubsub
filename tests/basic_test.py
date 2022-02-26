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

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient
from fastapi_websocket_pubsub.event_notifier import ALL_TOPICS

logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"
trigger_url = f"http://localhost:{PORT}/trigger"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"


def setup_server_rest_route(app, endpoint: PubSubEndpoint):
    @app.get("/trigger")
    async def trigger_events():
        logger.info("Triggered via HTTP route - publishing event")
        # Publish an event named 'steel'
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"


def setup_server():
    app = FastAPI()
    # PubSub websocket endpoint
    endpoint = PubSubEndpoint()
    endpoint.register_route(app, path="/pubsub")
    # Regular REST endpoint - that publishes to PubSub
    setup_server_rest_route(app, endpoint)
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_subscribe_http_trigger(server):
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_pub_sub(server):
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # publish events (with sync=False toa void deadlocks waiting on the publish to ourselves)
        published = await client.publish(
            [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
        )
        assert published.result
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_pub_sub_with_all_topics(server):
    """
    Check client gets event when subscribing via ALL_TOPICS
    """
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(ALL_TOPICS, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # publish events (with sync=False toa void deadlocks waiting on the publish to ourselves)
        published = await client.publish(
            [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
        )
        assert published.result
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)

import os
import sys
import pytest
import asyncio
import uvicorn
import requests
from multiprocessing import Process

from fastapi import FastAPI
from fastapi_websocket_rpc import logger
from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_rpc.utils import gen_uid
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient, Subscription, Topic

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)

logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"
trigger_url = f"http://localhost:{PORT}/trigger"

DATA = "MAGIC"
SERVER_TOPIC = "event/has-happened"
CLIENT_TOPIC = "event/has-been-processed"


def setup_server_rest_route(app, endpoint: PubSubEndpoint):
    @app.get("/trigger")
    async def trigger_events():
        logger.info("Triggered via HTTP route - publishing event")
        # Publish an event - to the our own server callback / which will trigger another event for the client
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([SERVER_TOPIC], data=DATA))
        return "triggered"


def setup_server():
    app = FastAPI()
    # PubSub websocket endpoint
    endpoint = PubSubEndpoint()
    endpoint.register_route(app, "/pubsub")

    # receive an event and publish another (this time for the client)
    async def event_callback(subscription: Subscription, data):
        logger.info(f"Got topic {subscription.topic} - re-publishing as {CLIENT_TOPIC}")
        asyncio.create_task(endpoint.publish([CLIENT_TOPIC], data))

    @app.on_event("startup")
    async def startup():
        # subscribe to our own events
        await endpoint.subscribe([SERVER_TOPIC], event_callback)

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
async def test_server_subscribe_http_trigger(server):
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(CLIENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)

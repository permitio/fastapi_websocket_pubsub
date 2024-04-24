"""
Pattern:
        Publishing-Client -> PubSubServer -> Subscribing->Client

"""

import os
import sys
import pytest
import uvicorn
import asyncio
from multiprocessing import Process, Event as ProcEvent

from fastapi import FastAPI

from fastapi_websocket_rpc.logger import get_logger

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient

logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"


DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"

CLIENT_START_SYNC = ProcEvent()


def setup_server():
    app = FastAPI()
    # PubSub websocket endpoint
    endpoint = PubSubEndpoint()
    endpoint.register_route(app, path="/pubsub")
    uvicorn.run(app, port=PORT)


def setup_publishing_client():
    """
    this client will publish an event to the main-test client
    """

    async def actual():
        # Wait for other client to wake up before publishing to it
        CLIENT_START_SYNC.wait(5)
        logger.info("Client start sync done")
        # Create a client and subscribe to topics
        client = PubSubClient()
        client.start_client(uri)
        # wait for the client to be ready
        await client.wait_until_ready()
        # publish event
        logger.info("Publishing event")
        published = await client.publish([EVENT_TOPIC], data=DATA)
        assert published.result

    logger.info("Starting async publishing client")
    asyncio.run(actual())


@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.fixture(scope="module")
def pub_client():
    # Run the server as a separate process
    proc = Process(target=setup_publishing_client, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_pub_sub_multi_client(server, pub_client):
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            assert topic == EVENT_TOPIC
            finish.set()

        # subscribe for the event
        logger.info("Subscribing for events")
        client.subscribe(EVENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        await client.wait_until_ready()
        # Let the other client know we're ready
        logger.info("First client is ready")
        CLIENT_START_SYNC.set()
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 10)

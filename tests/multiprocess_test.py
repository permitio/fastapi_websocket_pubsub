import os
import sys

from fastapi_websocket_rpc import logger

# Add parent path to use local src as package for tests
sys.path.append(os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir)))

import asyncio
from multiprocessing import Process, Event as ProcEvent

import pytest
import uvicorn
from fastapi import APIRouter, FastAPI


from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_rpc.utils import gen_uid
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient

logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"


DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"

CLIENT_START_SYNC = ProcEvent()

def setup_server():
    app =  FastAPI()
    router = APIRouter()
    # PubSub websocket endpoint
    endpoint = PubSubEndpoint()
    endpoint.register_route(router, "/pubsub")
    app.include_router(router)
    uvicorn.run(app, port=PORT)

def setup_publishing_client():
    """
    this client will publish an event to the main-test client 
    """
    async def actual():
        # # Give the other client a chance to subscribe (TODO: sync start between the processes)
        CLIENT_START_SYNC.wait(5)
        # Create a client and subscribe to topics
        client = PubSubClient()
        client.start_client(uri)
        # wait for the client to be ready 
        await client.wait_until_ready()
        # publish event
        logger.info("Publishing event")
        published = await client.publish([EVENT_TOPIC], data=DATA)
        assert published.result == True
    logger.info("Starting async publishing client")
    asyncio.get_event_loop().run_until_complete(actual())


@pytest.fixture(scope="module")
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill() # Cleanup after test

@pytest.fixture(scope="module")
def pub_client():
    # Run the server as a separate process
    proc = Process(target=setup_publishing_client, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill() # Cleanup after test


@pytest.mark.asyncio
async def test_pub_sub_multi_client(server, pub_client):
    # finish trigger
    finish = asyncio.Event()
    # Create a client and subscribe to topics
    client = PubSubClient()
    async def on_event(data):
        assert data == DATA
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
    await asyncio.wait_for(finish.wait(),10)

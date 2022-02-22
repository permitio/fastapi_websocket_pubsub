import os
import sys
import pytest
import asyncio
import uvicorn
import requests
from multiprocessing import Process

from fastapi import FastAPI, HTTPException, WebSocket, Header
from fastapi_websocket_rpc import logger
from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient

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
CLIENT_TOPIC = "event/has-been-processed"


async def verify_permitted_topics(topics, channel):
    if "permitted_topics" not in channel.context.get("claims", {}):
        return
    unauthorized_topics = set(topics).difference(
        channel.context["claims"]["permitted_topics"]
    )
    if unauthorized_topics:
        raise HTTPException(
            description=f"Invalid 'topics' to subscribe {unauthorized_topics}"
        )


async def check_claims(websocket: WebSocket, x_token: str = Header(...)):
    if x_token != "secret":
        await websocket.close(403)
    return x_token


def setup_server():
    app = FastAPI()
    # PubSub websocket endpoint
    endpoint = PubSubEndpoint()
    endpoint.notifier.add_channel_restriction(verify_permitted_topics)

    @app.websocket("/pubsub")
    async def websocket_endpoint(websocket: WebSocket):
        headers = eval(websocket.headers["headers"])
        await endpoint.main_loop(websocket, **headers)

    @app.get("/trigger")
    async def trigger_events():
        logger.info("Triggered via HTTP route - publishing event")
        # Publish an event - to our own server callback / which will trigger another event for the client
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([CLIENT_TOPIC], data=DATA))
        return "triggered"

    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


async def server_subscribe_to_topic(server, is_topic_permitted):
    # finish trigger
    finish = asyncio.Event()

    permitted_topics = ["t1", "t2"]
    if is_topic_permitted:
        permitted_topics.append(CLIENT_TOPIC)

    # Create a client and subscribe to topics
    async with PubSubClient(
        extra_headers={"headers": {"claims": {"permitted_topics": permitted_topics}}}
    ) as client:

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
        if is_topic_permitted:
            await asyncio.wait_for(finish.wait(), 5)
        else:
            await asyncio.sleep(5)
            assert not finish.is_set()


@pytest.mark.asyncio
async def test_server_subscribe_to_restricted_topic(server):
    await server_subscribe_to_topic(server, False)


@pytest.mark.asyncio
async def test_server_subscribe_to_permitted_topic(server):
    await server_subscribe_to_topic(server, True)


async def server_publish_to_topic(server, is_topic_permitted):
    # Create a client and subscribe to topics
    async with PubSubClient(
        extra_headers={"headers": {"claims": {"permitted_topics": ["t1", "t2"]}}}
    ) as client:
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()

        result = await client.publish(
            ["t1" if is_topic_permitted else "t3"], data=DATA, sync=True
        )
        assert result.result == is_topic_permitted


@pytest.mark.asyncio
async def test_server_publish_to_restricted_topic(server):
    await server_publish_to_topic(server, False)


@pytest.mark.asyncio
async def test_server_publish_to_permitted_topic(server):
    await server_publish_to_topic(server, True)

import os
import sys

from fastapi_websocket_rpc import logger
from fastapi_websocket_rpc.rpc_channel import RpcChannel

import asyncio
from multiprocessing import Process
import requests

import pytest
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_rpc.utils import gen_uid
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient, Subscription
from fastapi_websocket_pubsub.event_notifier import ALL_TOPICS

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"
trigger_url = f"http://localhost:{PORT}/trigger"
ask_remote_id_url = f"http://localhost:{PORT}/ask-remote-id"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"

REMOTE_ID_ANSWER_TOPIC = "client/my-remote-id"


def setup_server_rest_routes(
    app, endpoint: PubSubEndpoint, remote_id_event: asyncio.Event
):
    @app.get("/trigger")
    async def trigger_events():
        logger.info("Triggered via HTTP route - publishing event")
        # Publish an event named 'steel'
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"

    @app.get("/ask-remote-id")
    async def trigger_events():
        logger.info("Got asked if i have the remote id")
        answer = "yes" if remote_id_event.is_set() else "no"
        asyncio.create_task(
            endpoint.publish([REMOTE_ID_ANSWER_TOPIC], {"answer": answer})
        )
        return {"answer": answer}


def setup_server():
    app = FastAPI()
    remote_id_ok = asyncio.Event()

    async def try_to_get_remote_id(channel: RpcChannel):
        logger.info(f"trying to get remote channel id")
        channel_other_channel_id = await channel.get_other_channel_id()
        logger.info(f"finished getting remote channel id")
        if channel_other_channel_id is not None:
            remote_id_ok.set()
            logger.info(f"remote channel id: {channel_other_channel_id}")
        logger.info(f"local channel id: {channel_other_channel_id}")

    async def on_connect(channel: RpcChannel):
        logger.info(f"Connected to remote channel")
        asyncio.create_task(try_to_get_remote_id(channel))

    # PubSub websocket endpoint - setting up the server with remote id
    endpoint = PubSubEndpoint(rpc_channel_get_remote_id=True, on_connect=[on_connect])
    endpoint.register_route(app, "/pubsub")

    # Regular REST endpoint - that publishes to PubSub
    setup_server_rest_routes(app, endpoint, remote_id_ok)
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_subscribe_http_trigger_with_remote_id_on(server):
    """
    same as the basic_test::test_subscribe_http_trigger, but this time makes sure that
    the rpc_channel_get_remote_id doesn't break anything.
    """
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
async def test_pub_sub_with_remote_id_on(server):
    """
    same as the basic_test::test_pubsub, but this time makes sure that
    the rpc_channel_get_remote_id doesn't break anything.
    """
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
async def test_pub_sub_with_all_topics_with_remote_id_on(server):
    """
    same as the basic_test::test_pub_sub_with_all_topics, but this time makes sure that
    the rpc_channel_get_remote_id doesn't break anything.
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


@pytest.mark.asyncio
async def test_getting_remote_id(server):
    """
    tests that the server managed to get the client's channel id successfully.
    """
    # finish trigger
    finish = asyncio.Event()
    remote_id_yes = asyncio.Event()

    # Create a client and subscribe to topics
    async with PubSubClient() as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        async def on_answer(data, topic):
            assert data.get("answer", None) == "yes"
            remote_id_yes.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        client.subscribe(REMOTE_ID_ANSWER_TOPIC, on_answer)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # trigger the server via an HTTP route
        requests.get(trigger_url)
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)
        # sleep so that the server can finish getting the remote id
        await asyncio.sleep(1)
        # ask the server if he got the remote id
        # will trigger the REMOTE_ID_ANSWER_TOPIC topic and the on_answer() callback
        requests.get(ask_remote_id_url)
        await asyncio.wait_for(remote_id_yes.wait(), 5)
        # the client can also try to get it's remote id
        # super ugly but it's working:
        my_remote_id = await client._rpc_channel._get_other_channel_id()
        assert my_remote_id is not None

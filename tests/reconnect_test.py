import os
import sys
import pytest
import uvicorn
import asyncio
from fastapi import FastAPI
from multiprocessing import Process, Value

from fastapi_websocket_rpc import RpcChannel, logger
from fastapi_websocket_rpc.utils import gen_uid
from fastapi_websocket_rpc.logger import get_logger
from fastapi_websocket_rpc.rpc_channel import RpcChannelClosedException

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient


logger.logging_config.set_mode(logger.LoggingModes.UVICORN)

logger = get_logger("Test")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
uri = f"ws://localhost:{PORT}/pubsub"
trigger_url = f"http://localhost:{PORT}/trigger"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"


def setup_server(disconnect_delay=0):
    app = FastAPI()
    # Multiprocess shared value
    counter = Value("i", 0)

    async def on_connect(channel: RpcChannel):
        if counter.value == 0:
            # Immediate death
            if disconnect_delay == 0:
                logger.info("Disconnect once")
                await channel.socket.close()
            # Delayed death
            else:

                async def disconn():
                    await asyncio.sleep(disconnect_delay)
                    logger.info("Disconnect once")
                    await channel.socket.close()

                asyncio.create_task(disconn())
            counter.value = 1

    # PubSub websocket endpoint
    endpoint = PubSubEndpoint(on_connect=[on_connect])
    endpoint.register_route(app, "/pubsub")
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.fixture(params=[0.001, 0.01, 0.1, 0.2])
def delayed_death_server(request):
    disconnect_delay = request.param
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(disconnect_delay,), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_immediate_server_disconnect(server):
    """
    Test reconnecting when a server hangups on connect
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
async def test_delayed_server_disconnect(delayed_death_server):
    """
    Test reconnecting when a server hangups AFTER connect
    """
    # finish trigger
    finish = asyncio.Event()

    async def on_connect(client, channel):
        try:
            print("Connected")
            # publish events (with sync=False to avoid deadlocks waiting on the publish to ourselves)
            published = await client.publish(
                [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
            )
            assert published.result
        except RpcChannelClosedException:
            # expected
            pass

    # Create a client and subscribe to topics
    async with PubSubClient(on_connect=[on_connect]) as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)


@pytest.mark.asyncio
async def test_disconnect_callback(delayed_death_server):
    """
    Test reconnecting when a server hangups AFTER connect and that the disconnect callback work
    """
    # finish trigger
    finish = asyncio.Event()
    disconnected = asyncio.Event()

    async def on_disconnect(channel):
        print("-------- Disconnected")
        disconnected.set()

    async def on_connect(client, channel):
        try:
            print("Connected")
            # publish events (with sync=False to avoid deadlocks waiting on the publish to ourselves)
            published = await client.publish(
                [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
            )
            assert published.result
        except RpcChannelClosedException:
            # expected
            pass

    # Create a client and subscribe to topics
    async with PubSubClient(
        on_disconnect=[on_disconnect], on_connect=[on_connect]
    ) as client:

        async def on_event(data, topic):
            assert data == DATA
            finish.set()

        # subscribe for the event
        client.subscribe(EVENT_TOPIC, on_event)
        # start listentining
        client.start_client(uri)
        # wait for the client to be ready to receive events
        await client.wait_until_ready()
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(), 5)

    await asyncio.wait_for(disconnected.wait(), 1)
    assert disconnected.is_set()


@pytest.mark.asyncio
async def test_disconnect_callback_without_context(delayed_death_server):
    """
    Test reconnecting when a server hangups AFTER connect and that the disconnect callback work
    """
    # finish trigger
    finish = asyncio.Event()
    disconnected = asyncio.Event()

    async def on_disconnect(channel):
        disconnected.set()

    async def on_connect(client, channel):
        try:
            print("Connected")
            # publish events (with sync=False to avoid deadlocks waiting on the publish to ourselves)
            published = await client.publish(
                [EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid()
            )
            assert published.result
        except RpcChannelClosedException:
            # expected
            pass

    # Create a client and subscribe to topics
    client = PubSubClient(on_disconnect=[on_disconnect], on_connect=[on_connect])

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
    await client.disconnect()
    await asyncio.wait_for(disconnected.wait(), 1)
    assert disconnected.is_set()

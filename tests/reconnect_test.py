import logging
import os
import sys

from fastapi_websocket_rpc import logger, RpcChannel
logger.logging_config.set_mode(logger.LoggingModes.UVICORN)

# Add parent path to use local src as package for tests
sys.path.append(os.path.abspath(os.path.join(os.path.basename(__file__), os.path.pardir)))

import asyncio
from multiprocessing import Process, Value

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
trigger_url = f"http://localhost:{PORT}/trigger"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"


def setup_server(disconnect_delay=0):
    app =  FastAPI()
    # Multiprocess shared value
    counter = Value("i", 0) 
    
    async def on_connect(channel:RpcChannel):
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
    proc.kill() # Cleanup after test

@pytest.fixture()
def delayed_death_server():
    disconnect_delay = 0.001
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(disconnect_delay,), daemon=True)
    proc.start()
    yield proc
    proc.kill() # Cleanup after test


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
        published = await client.publish([EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid())
        assert published.result == True
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(),5)

@pytest.mark.asyncio
async def test_delayed_server_disconnect(delayed_death_server):
    """
    Test reconnecting when a server hangups AFTER connect
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
        published = await client.publish([EVENT_TOPIC], data=DATA, sync=False, notifier_id=gen_uid())
        assert published.result == True
        # wait for finish trigger
        await asyncio.wait_for(finish.wait(),5)

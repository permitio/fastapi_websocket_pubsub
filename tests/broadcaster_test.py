import os
import sys
import pytest
import asyncio
import uvicorn
import requests

from typing import Optional
from fastapi import FastAPI
from starlette.websockets import WebSocket
from multiprocessing import Process

from fastapi_websocket_rpc.logger import get_logger, logging_config, LoggingModes
logging_config.set_mode(LoggingModes.LOGURU)

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient


logger = get_logger("Test")
logger.add(sys.stderr, format="<green>{time}</green> | {process} | <blue>{name: <40}</blue>|<level>{level:^6} | {message}</level>", level="INFO")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
first_server_trigger_url = f"http://localhost:{PORT}/ws1/trigger"
first_endpoint_uri = f"ws://localhost:{PORT}/ws1"
second_endpoint_uri = f"ws://localhost:{PORT}/ws2"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"


def setup_pubsub_endpoint(app, endpoint: PubSubEndpoint, path: str):
    @app.websocket(path)
    async def websocket_rpc_endpoint(websocket: WebSocket):
        await endpoint.main_loop(websocket)


def setup_trigger_endpoint_for(app, endpoint: PubSubEndpoint, path: str):
    @app.get(f"{path}/trigger")
    async def trigger_events():
        trigger_logger = logger.bind(name="trigger endpoint")
        trigger_logger.info(f"Triggered via HTTP route - publishing event to {path}")
        # Publish an event named 'steel'
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"


def setup_server():
    """
    sets up 2 pubsub server endpoints on the server, both connected via broadcaster
    """
    app = FastAPI()
    first_endpoint = PubSubEndpoint(broadcaster="postgres://localhost:5432/")
    setup_pubsub_endpoint(app, first_endpoint, path="/ws1")
    setup_trigger_endpoint_for(app, first_endpoint, path="/ws1")

    second_endpoint = PubSubEndpoint(broadcaster="postgres://localhost:5432/")
    setup_pubsub_endpoint(app, second_endpoint, path="/ws2")
    setup_trigger_endpoint_for(app, second_endpoint, path="/ws2")

    uvicorn.run(app, port=PORT)


@pytest.fixture()
def server():
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_all_clients_get_a_topic_via_broadcast(server):
    """
    if:
    - 2 clients are subscribed to 2 servers (on the same topic)
    - the 2 servers are connected via broadcast
    - one server receives a message on this topic

    then:
    - all servers (and clients) will get the message
    - the server that did not originally get the message will receive it via broadcast
    """
    # finish trigger
    client_one_got_the_message = asyncio.Event()
    client_two_got_the_message = asyncio.Event()

    async def subscribe_to_server(server_uri: str, on_received_event: asyncio.Event, *, client_name: str, trigger_url: Optional[str] = None):
        async with PubSubClient() as client:
            async def on_event(data, topic):
                assert data == DATA

                logger.info(f"client '{client_name}' received data '{data}' on topic '{topic}'")
                on_received_event.set()

            # subscribe for the event
            client.subscribe(EVENT_TOPIC, on_event)
            # start listentining
            client.start_client(server_uri)
            # wait for the client to be ready to receive events
            await client.wait_until_ready()

            logger.info("client ready")

            if trigger_url:
                requests.get(trigger_url)

            # keeps the client alive for 5 seconds
            # otherwise the __aexit__ will close the connection
            await asyncio.sleep(10)

    await asyncio.gather(*[
        asyncio.create_task(subscribe_to_server(first_endpoint_uri, client_one_got_the_message, client_name="client1", trigger_url=first_server_trigger_url)),
        asyncio.create_task(subscribe_to_server(second_endpoint_uri, client_two_got_the_message, client_name="client2")),
    ])



    # wait for finish trigger
    await asyncio.wait_for(client_one_got_the_message.wait(), 5)
    await asyncio.wait_for(client_two_got_the_message.wait(), 5)

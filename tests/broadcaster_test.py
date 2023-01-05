import os
import time
import sys
import pytest
import asyncio
import uvicorn
import requests
import random
import string

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
logger.remove()
logger.add(sys.stderr, format="<green>{time}</green> | {process} | <blue>{name: <50}</blue>|<level>{level:^6} | {message}</level>", level="INFO")

# Configurable
PORT = int(os.environ.get("PORT") or "7990")
first_server_trigger_url = f"http://localhost:{PORT}/ws1/trigger"
first_endpoint_uri = f"ws://localhost:{PORT}/ws1"
second_endpoint_uri = f"ws://localhost:{PORT}/ws2"

DATA = "MAGIC"
EVENT_TOPIC = "event/has-happened"
PG_HOST_PORT = 25432
PG_SLEEP_TIME = 10

@pytest.fixture()
def postgres(request):
    CONTAINER_NAME = "broadcastdb" + "".join(
        [random.choice(string.ascii_letters) for _ in range(8)]
    )

    def rm_container():
        os.system(f'docker rm -f {CONTAINER_NAME} > /dev/null 2>&1')

    rm_container() # Make sure no previous container exists

    postgres_args = ''
    timeout_marker = request.node.get_closest_marker("postgres_idle_timeout")
    if timeout_marker is not None:
        timeout = timeout_marker.args[0]
        postgres_args = f'-c idle_session_timeout={timeout} -c idle_in_transaction_session_timeout={timeout}'


    logger.info(f"running postgres on host port {PG_HOST_PORT}...")
    os.system(f'docker run -d -p {PG_HOST_PORT}:5432 --name {CONTAINER_NAME} -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:alpine {postgres_args} > /dev/null 2>&1')
    logger.info(f"Sleeping for {PG_SLEEP_TIME} seconds so postgres could stabilize")
    time.sleep(PG_SLEEP_TIME)

    try:
        yield f"postgres://postgres:postgres@localhost:{PG_HOST_PORT}/"
    finally:
        rm_container()

def setup_pubsub_endpoint(app: FastAPI, broadcast_url: str, path: str):
    """
    sets up endpoints on the fastapi app:
    - a pub/sub websocket endpoint for clients to connect to
    - a trigger endpoint that causes the pub/sub server to publish a message on a predefined topic
    """
    logger.info(f"[{path} endpoint] connecting to broadcast backbone service on '{broadcast_url}'")
    endpoint = PubSubEndpoint(broadcaster=broadcast_url, ignore_broadcaster_disconnected=False)

    @app.websocket(path)
    async def websocket_rpc_endpoint(websocket: WebSocket):
        await endpoint.main_loop(websocket)

    @app.get(f"{path}/trigger")
    async def trigger_events():
        trigger_logger = logger.bind(name="trigger endpoint")
        trigger_logger.info(f"Triggered via HTTP route - publishing event to {path}")
        # Publish an event named 'steel'
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"

    return endpoint


def setup_server(broadcast_url):
    """
    sets up 2 pubsub server endpoints on the server, both connected via broadcaster
    """
    app = FastAPI()
    setup_pubsub_endpoint(app, broadcast_url, path="/ws1")
    setup_pubsub_endpoint(app, broadcast_url, path="/ws2")
    logger.info("Running server app")
    uvicorn.run(app, port=PORT)

@pytest.fixture()
def server(postgres):
    # Run the server as a separate process
    proc = Process(target=setup_server, args=(postgres, ), daemon=True)
    proc.start()
    logger.info("Server started on a daemon process")
    yield proc
    proc.kill()  # Cleanup after test


@pytest.mark.asyncio
async def test_all_clients_get_a_topic_via_broadcast(server, repeats=1, interval=0):
    """
    if:
    - 2 clients are subscribed to 2 servers (on the same topic)
    - the 2 servers are connected via broadcast
    - one server receives a message on this topic

    then:
    - all servers (and clients) will get the message
    - the server that did not originally get the message will receive it via broadcast
    """
    # When both clients would receive event, semaphore would get locked
    sem = asyncio.Semaphore(2)

    async def on_event(data, topic):
        logger.info(f"client received data '{data}' on topic '{topic}'")
        assert data == DATA
        await sem.acquire()

    async with PubSubClient() as client1:
        async with PubSubClient() as client2:
            for c, uri in [(client1,first_endpoint_uri), (client2,second_endpoint_uri)]:
                c.subscribe(EVENT_TOPIC, on_event)
                c.start_client(uri)
                await c.wait_until_ready()

            for repeat in range(repeats):
                logger.info("Triggering event")
                requests.get(first_server_trigger_url)

                async def wait_for_sem():
                    while not sem.locked():
                        await asyncio.sleep(0.1)

                logger.info("Wait for events to be set")
                await asyncio.wait_for(wait_for_sem(), 5)

                for _ in range(2):
                    # Clean semaphore before next round
                    sem.release()

                if repeat + 1 < repeats:
                    await asyncio.sleep(interval)

@pytest.mark.postgres_idle_timeout(3000)
@pytest.mark.asyncio
async def test_idle_pg_broadcaster_disconnect(server):
    """
    if:
    - 2 clients are subscribed to 2 servers (on the same topic)
    - the 2 servers are connected via broadcast (backed by a postgres DB)
    - one server receives a message on this topic
    - the servers are disconnected from the broadcaster due to idle timeout
    - one server receives another message on this topic

    then:
    - all servers (and clients) will get both of the messages
    """
    await test_all_clients_get_a_topic_via_broadcast(server, repeats=3, interval=4)


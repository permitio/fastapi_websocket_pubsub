import os
import time
import sys
import pytest
import asyncio
import uvicorn
import requests

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


@pytest.fixture()
def postgres():
    """
    runs a postgres container so that we can test the broadcaster functionality with postgres
    """
    logger.info(f"running the postgres container")
    os.system('docker run -d -p 5433:5432 --name broadcastdb -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:alpine')

    time.sleep(5) # wait for postgres to go up and stabilize

    # exposing postgres url to the test
    yield "postgres://postgres:postgres@localhost:5433/"

    logger.info("stopping the container and cleaning up")
    os.system("docker stop broadcastdb")
    os.system("docker rm -f broadcastdb")


# @pytest.fixture()
# def postgres_with_idle_session_timeout():
#     os.system("docker rm -f broadcastdb")
#     os.system('docker run -i --rm postgres:alpine cat /usr/local/share/postgresql/postgresql.conf.sample > postgres.conf')

#     # Set idle timeout of 5s in order to test completion of reader task
#     with open("postgres.conf", "a") as conf:
#         conf.writelines(["idle_session_timeout=5000",
#                          "idle_in_transaction_session_timeout=5000"])

#     os.system('docker run -d -p 5433:5432 --name broadcastdb -v "$PWD/postgres.conf":/etc/postgresql/postgresql.conf -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:alpine')

#     yield "postgres://postgres:postgres@localhost:5433/"

#     os.system("docker rm -f broadcastdb")


def setup_pubsub_endpoint(app: FastAPI, broadcast_url: str, path: str):
    """
    sets up endpoints on the fastapi app:
    - a pub/sub websocket endpoint for clients to connect to
    - a trigger endpoint that causes the pub/sub server to publish a message on a predefined topic
    """
    logger.info(f"[{path} endpoint] connecting to broadcast backbone service on '{broadcast_url}'")
    endpoint = PubSubEndpoint(broadcaster=broadcast_url)

    @app.websocket(path)
    async def websocket_rpc_endpoint(websocket: WebSocket):
        await endpoint.main_loop(websocket)

    @app.get(f"{path}/trigger")
    async def trigger_events():
        logger.info(f"[{path}/trigger endpoint] Triggered via HTTP route - publishing event to {path}")
        # Publish an event named 'steel'
        # Since we are calling back (RPC) to the client- this would deadlock if we wait on it
        asyncio.create_task(endpoint.publish([EVENT_TOPIC], data=DATA))
        return "triggered"

    return endpoint


def setup_server(broadcast_url):
    """
    sets up 2 pubsub server endpoints on the server, both connected via broadcaster
    """
    print("Running server app")
    app = FastAPI()
    setup_pubsub_endpoint(app, broadcast_url, path="/ws1")
    setup_pubsub_endpoint(app, broadcast_url, path="/ws2")
    uvicorn.run(app, port=PORT)




@pytest.fixture()
def server(postgres):
    # Run the server as a separate process
    print("Server fixture")
    proc = Process(target=setup_server, args=(postgres, ), daemon=True)
    proc.start()
    print("Server started on a deamon process")
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
    # When both clients would recieve event, semaphore would get locked
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

            print("Triggering event")
            requests.get(first_server_trigger_url)

            async def wait_for_sem():
                while not sem.locked():
                    await asyncio.sleep(0.1)

            print("Wait for events to be set")
            await asyncio.wait_for(wait_for_sem(), 5)

# @pytest.mark.asyncio
# async def test_ws_closes_on_pg_broadcaster_disconnect(server):
#     """
#     if:
#     - A client is connected via websocket to a server
#     - The server is connected to a broadcaster backed by postgresql DB
#     - The server <-> DB connection gets disconnected

#     then:
#     - Websocket connection between client and server should close
#     """
#     # TODO: This should use a different postgres DB that has 3s idle timeout

#     async def on_event(data, topic):
#         logger.info(f"client received data '{data}' on topic '{topic}'")

#     async with PubSubClient(topics=[EVENT_TOPIC], callback=on_event, server_uri=first_endpoint_uri) as c:
#         done, pending = await asyncio.wait([c._run_task], timeout=10)
#         # assert c._run_task in done
#         assert c._run_task in pending # This is without the fix



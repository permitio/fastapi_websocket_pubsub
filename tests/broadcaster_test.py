import os
import sys
import pytest
import asyncio
import uvicorn
import requests
import asyncpg
import contextlib

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
PG_URI = "postgres://postgres:postgres@localhost:5432"

def setup_pubsub_endpoint(app, path: str):
    endpoint = PubSubEndpoint(broadcaster=PG_URI)

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


def setup_server():
    """
    sets up 2 pubsub server endpoints on the server, both connected via broadcaster
    """
    app = FastAPI()
    first_endpoint = setup_pubsub_endpoint(app, path="/ws1")
    second_endpoint = setup_pubsub_endpoint(app, path="/ws2")
    print("Running server app")
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def postgres():
    os.system("docker rm -f broadcastdb")
    os.system('docker run -i --rm postgres:alpine cat /usr/local/share/postgresql/postgresql.conf.sample > postgres.conf')
    
    # Set idle timeout of 5s in order to test completion of reader task
    with open("postgres.conf", "a") as conf:
        conf.writelines(["idle_session_timeout=5000", 
                         "idle_in_transaction_session_timeout=5000"])
                         
    os.system('docker run -d -p 5433:5432 --name broadcastdb -v "$PWD/postgres.conf":/etc/postgresql/postgresql.conf -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:alpine')
    
    yield "postgres://postgres:postgres@localhost:5433/"
    os.system("docker rm -f broadcastdb")

@pytest.fixture()
def server():
    # Run the server as a separate process
    print("Server fixture")
    proc = Process(target=setup_server, args=(), daemon=True)
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

@pytest.mark.asyncio
async def test_ws_closes_on_pg_broadcaster_disconnect(server):
    """
    if:
    - A client is connected via websocket to a server
    - The server is connected to a broadcaster backed by postgresql DB
    - The server <-> DB connection gets disconnected 

    then:
    - Websocket connection between client and server should close
    """
    # TODO: This should use a different postgres DB that has 3s idle timeout

    async def on_event(data, topic):
        logger.info(f"client received data '{data}' on topic '{topic}'")

    async with PubSubClient(topics=[EVENT_TOPIC], callback=on_event, server_uri=first_endpoint_uri) as c:
        done, pending = await asyncio.wait([c._run_task], timeout=10)
        # assert c._run_task in done
        assert c._run_task in pending # This is without the fix

    

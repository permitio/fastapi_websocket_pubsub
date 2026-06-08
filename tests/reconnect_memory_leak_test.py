import asyncio
import os
import sys

import pytest
import uvicorn
from fastapi import FastAPI
from multiprocessing import Process

from fastapi_websocket_rpc import RpcChannel

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)
from fastapi_websocket_pubsub import PubSubEndpoint, PubSubClient

# Use a dedicated port so this test can run alongside the others.
PORT = int(os.environ.get("PORT") or "7991")
uri = f"ws://localhost:{PORT}/pubsub"


def setup_always_disconnect_server():
    """A server that closes the socket shortly after every connect, forcing the
    client into a continual reconnect loop."""
    app = FastAPI()

    async def on_connect(channel: RpcChannel):
        async def disconnect_soon():
            await asyncio.sleep(0.05)
            await channel.socket.close()

        asyncio.create_task(disconnect_soon())

    endpoint = PubSubEndpoint(on_connect=[on_connect])
    endpoint.register_route(app, path="/pubsub")
    uvicorn.run(app, port=PORT)


@pytest.fixture()
def repeating_death_server():
    proc = Process(target=setup_always_disconnect_server, args=(), daemon=True)
    proc.start()
    yield proc
    proc.kill()


@pytest.mark.asyncio
async def test_reconnect_loop_does_not_leak_disconnect_waiters(repeating_death_server):
    """Each reconnect iteration races the reader task against
    ``self._disconnect_signal.wait()``. The loser of that race must be cancelled,
    otherwise a pending waiter accumulates on the disconnect signal on every
    reconnect (unbounded). This asserts the waiter count stays bounded across
    many reconnects; it fails if the cancellation is removed.
    """
    reconnects = 0

    async def on_disconnect(channel):
        nonlocal reconnects
        reconnects += 1

    client = PubSubClient(on_disconnect=[on_disconnect])
    client.start_client(uri)
    try:
        # Wait until several reconnect cycles have actually happened.
        async def wait_for_reconnects():
            while reconnects < 5:
                await asyncio.sleep(0.05)

        await asyncio.wait_for(wait_for_reconnects(), 20)

        # `_disconnect_signal.wait()` registers a future on the Event's internal
        # waiter list; cancelling the losing task removes it again. Without that
        # cancellation the list grows by one per reconnect.
        waiters = len(client._disconnect_signal._waiters)
        assert waiters <= 2, (
            f"leaked {waiters} disconnect-signal waiters over {reconnects} "
            f"reconnects (expected the per-reconnect waiter to be cancelled)"
        )
    finally:
        await client.disconnect()

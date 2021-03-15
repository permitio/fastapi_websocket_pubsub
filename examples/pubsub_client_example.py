"""
See pubsub_sever_example.py for running instructions

A very simple client
"""
import asyncio
import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.basename(__file__), "..")))
from fastapi_websocket_pubsub import PubSubClient


PORT = int(os.environ.get("PORT") or "8000")


async def on_events(data, topic):
    print(f"running callback for {topic}!")


async def main():
    # Create a client and subscribe to topics
    client = PubSubClient(["guns", "germs"], callback=on_events)

    async def on_steel(data, topic):
        print("running callback steel!")
        print("Got data", data)
        asyncio.create_task(client.disconnect())

    client.subscribe("steel", on_steel)
    client.start_client(f"ws://localhost:{PORT}/pubsub")
    await client.wait_until_done()


asyncio.run(main())

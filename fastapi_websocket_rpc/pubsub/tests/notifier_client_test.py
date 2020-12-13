"""
See notifier_sever_test.py for test instructions
"""
import logging

from fastapi_websocket_rpc.pubsub import EventRpcClient

async def on_steel(data):
    logging.info("running callback on_steel!")

# Create a client and subscribe to topics
client = EventRpcClient(["guns", "germs"])
client.subscribe("steel", on_steel)
client.start_client("ws://localhost:8000/ws/test-client1")
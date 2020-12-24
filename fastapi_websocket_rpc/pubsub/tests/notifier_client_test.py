"""
See notifier_sever_test.py for test instructions
"""
import logging

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.basename(__file__), "..")))

PORT = int(os.environ.get("PORT") or "8000")

from fastapi_websocket_rpc.pubsub import EventRpcClient

async def on_steel(data):
    logging.info("running callback on_steel!")

# Create a client and subscribe to topics
client = EventRpcClient(["guns", "germs"])
client.subscribe("steel", on_steel)
client.start_client(f"ws://localhost:{PORT}/ws/test-client1")
"""
See notifier_sever_test.py for test instructions
"""
from libws.rpc_event_notifier import EventRpcClient

# Create a client and subscribe to topics
client = EventRpcClient(["guns", "germs", "steel"])
client.start_client("ws://localhost:8000/ws/test-client1")
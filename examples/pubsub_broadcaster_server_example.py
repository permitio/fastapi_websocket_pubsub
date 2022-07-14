"""
Multiple Servers linked via broadcaster example.

To run this example. 
-  0. Setup a broadcast medium and pass its configuration to the endpoint (e.g. postgres on 'postgres://localhost:5432/' )
 - 1. run this script for the servers (as many instances as you'd like) - use the PORT env-variable to run them on different ports 
 - 2. once the servers are up, run notifier_client_test.py and connect to one of them
 - 3. send get request to one server on: '/trigger'
 - 4. See that the client recives the event -no matter which server you connected it to, or which server got the initial trigger to publish
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.basename(__file__), "..")))


from fastapi_websocket_pubsub import PubSubEndpoint
import asyncio
import os
from starlette.websockets import WebSocket
import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

PORT = int(os.environ.get("PORT") or "8000")


app = FastAPI()
router = APIRouter()
endpoint = PubSubEndpoint(broadcaster="postgres://localhost:5432/")

@router.websocket("/pubsub")
async def websocket_rpc_endpoint(websocket: WebSocket):
    await endpoint.main_loop(websocket)

app.include_router(router)


async def events():
    await asyncio.sleep(1)
    await endpoint.publish(["guns", "germs"])
    await asyncio.sleep(1)
    await endpoint.publish(["germs"])
    await asyncio.sleep(1)
    await endpoint.publish(["steel"])


@app.get("/trigger")
async def trigger_events():
    asyncio.create_task(events())


uvicorn.run(app, host="0.0.0.0", port=PORT)

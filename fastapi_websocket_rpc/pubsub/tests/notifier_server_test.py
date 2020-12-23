"""
To run this test.
 - 1. run this script for the server
 - 2. once the server is up, run notifier_client_test.py
 - 3. send get request to server on: 'http://localhost:8000/trigger'
"""

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from fastapi_websocket_rpc.pubsub import EventRpcEndpoint

app =  FastAPI()
router = APIRouter()
endpoint = EventRpcEndpoint()
endpoint.register_routes(router)
app.include_router(router)

async def events():
    await asyncio.sleep(1)
    await endpoint.notify(["guns", "germs"])
    await asyncio.sleep(1)
    await endpoint.notify(["germs"])
    await asyncio.sleep(1)
    await endpoint.notify(["steel"])

@app.get("/trigger")
async def trigger_events():
    asyncio.create_task(events())

uvicorn.run(app, host="0.0.0.0", port=8000)

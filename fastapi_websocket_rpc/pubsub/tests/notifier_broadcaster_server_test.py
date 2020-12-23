"""
To run this test.
 - 1. run this script for the server
 - 2. once the server is up, run notifier_client_test.py
 - 3. send get request to server on: 'http://localhost:8000/trigger'
"""

import asyncio
import os
from starlette.websockets import WebSocket
import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from fastapi_websocket_rpc.pubsub import EventRpcEndpoint

PORT = int(os.environ.get("PORT") or "8000")


app =  FastAPI()
router = APIRouter()
endpoint = EventRpcEndpoint(broadcaster="postgres://localhost:5432/acalladb")

@router.websocket("/ws/{client_id}")
async def websocket_rpc_endpoint(websocket: WebSocket, client_id: str):
    async with endpoint.broadcaster:
        endpoint.broadcaster.start_reader_task() 
        await endpoint.main_loop(websocket)
        
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

uvicorn.run(app, host="0.0.0.0", port=PORT)

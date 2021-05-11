"""
To run this test.
 - 1. run this script for the server
 - 2. once the server is up, run pubsub_client_example.py
 - 3. send get request to server on: 'http://localhost:8000/trigger'
"""

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from fastapi_websocket_pubsub import PubSubEndpoint

app =  FastAPI()
router = APIRouter()
endpoint = PubSubEndpoint()
endpoint.register_route(router)
app.include_router(router)

async def events():
    await asyncio.sleep(1)
    # Publish multiple topics (without data)
    await endpoint.publish(["guns", "germs"])
    await asyncio.sleep(1)
    # Publish single topic (without data)
    await endpoint.publish(["germs"])
    await asyncio.sleep(1)
    # Publish single topic (with data)
    await endpoint.publish(["steel"], data={"author": "Jared Diamond"})

@app.get("/trigger")
async def trigger_events():
    asyncio.create_task(events())

uvicorn.run(app, host="0.0.0.0", port=8000)

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from libws.websocket.rpc_methods import RpcUtilityMethods
from libws.websocket.websocket_rpc_endpoint import WebsocketRPCEndpoint

app =  FastAPI()
router = APIRouter()
endpoint = WebsocketRPCEndpoint(RpcUtilityMethods())
endpoint.register_routes(router)
app.include_router(router)
uvicorn.run(app, host="0.0.0.0", port=8000)


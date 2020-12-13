import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRouter

from fastapi_websocket_rpc.websocket.rpc_methods import RpcUtilityMethods
from fastapi_websocket_rpc.websocket.websocket_rpc_endpoint import WebsocketRPCEndpoint

app =  FastAPI()
router = APIRouter()
endpoint = WebsocketRPCEndpoint(RpcUtilityMethods())
endpoint.register_routes(router)
app.include_router(router)
uvicorn.run(app, host="0.0.0.0", port=8000)


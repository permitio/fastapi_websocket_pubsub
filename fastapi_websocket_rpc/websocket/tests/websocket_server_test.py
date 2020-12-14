from starlette import responses
import uvicorn
from fastapi import APIRouter, FastAPI, Depends, Header, HTTPException, WebSocket

from fastapi_websocket_rpc.websocket.rpc_methods import RpcUtilityMethods
from fastapi_websocket_rpc.websocket.websocket_rpc_endpoint import WebsocketRPCEndpoint

async def get_token_header(x_token: str = Header(...)):
    print(x_token)
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")

app =  FastAPI()
router = APIRouter()
endpoint = WebsocketRPCEndpoint(RpcUtilityMethods())

@router.websocket("/ws/{client_id}")
async def websocket_rpc_endpoint(websocket: WebSocket, client_id: str, token=Depends(get_token_header)):
    await endpoint.main_loop(websocket)


app.include_router(router, dependencies=[Depends(get_token_header)])
uvicorn.run(app, host="0.0.0.0", port=8000)


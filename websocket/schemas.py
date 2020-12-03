from pydantic import BaseModel
from typing import List, Optional, Dict

UUID = str


class RpcRequest(BaseModel):
    method: str
    arguments: Optional[Dict] = {}
    call_id: Optional[UUID] = None


class RpcResponse(BaseModel):
    result: str
    call_id: Optional[UUID] = None


class RpcMessage(BaseModel):
    request: Optional[RpcRequest] = None
    response: Optional[RpcResponse] = None
 

from fastapi_websocket_rpc.logger import get_logger as rpc_get_logger

def get_logger(name):
    return rpc_get_logger(f"pubsub.{name}")

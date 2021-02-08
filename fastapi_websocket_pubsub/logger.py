import logging
import sys
import os


def get_logger(name):
    if os.environ.get("WS_RPC_LOGGING") == "loguru":
        from loguru import logger
    else:    
        logger = logging.getLogger("fastapi.ws_rpc")
    return logger




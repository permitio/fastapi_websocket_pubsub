import os
import sys

from fastapi_websocket_rpc import logger

from fastapi_websocket_pubsub.event_notifier import EventNotifier

import asyncio
from multiprocessing import Process

import pytest

from fastapi_websocket_pubsub import Subscription

# Add parent path to use local src as package for tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
)

TOPIC = "event/has-been-processed"
SUB_ID = "test"


@pytest.mark.asyncio
async def test_subscribe_callbacks_unit():

    notifier = EventNotifier()

    async def event_callback(subscription: Subscription, data):
        logger.info(f"Got topic {subscription.topic}")

    subscribed = asyncio.Event()
    unsubscribed = asyncio.Event()

    async def server_subscribe(*args):
        subscribed.set()

    async def server_unsubscribe(*args):
        unsubscribed.set()

    notifier.register_subscribe_event(server_subscribe)
    notifier.register_unsubscribe_event(server_unsubscribe)

    await notifier.subscribe(SUB_ID, [TOPIC], event_callback)
    await asyncio.wait_for(subscribed.wait(), 5)
    await notifier.unsubscribe(SUB_ID)
    await asyncio.wait_for(unsubscribed.wait(), 5)

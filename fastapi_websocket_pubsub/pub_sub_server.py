import asyncio
from typing import Coroutine, List, Union

from fastapi import WebSocket
from fastapi_websocket_rpc import WebsocketRPCEndpoint
from fastapi_websocket_rpc.rpc_channel import RpcChannel

from .logger import get_logger
from .event_broadcaster import EventBroadcaster
from .event_notifier import (
    ALL_TOPICS,
    EventCallback,
    EventNotifier,
    Subscription,
    Topic,
    TopicList,
)
from .rpc_event_methods import RpcEventServerMethods
from .websocket_rpc_event_notifier import WebSocketRpcEventNotifier

logger = get_logger("PubSubEndpoint")


class PubSubEndpoint:
    """
    RPC pub/sub server endpoint
    """

    def __init__(
        self,
        methods_class=None,
        notifier: EventNotifier = None,
        broadcaster: Union[EventBroadcaster, str] = None,
        on_connect: List[Coroutine] = None,
        on_disconnect: List[Coroutine] = None,
        rpc_channel_get_remote_id: bool = False,
        ignore_broadcaster_disconnected = True,
    ):
        """
        The PubSub endpoint recives subscriptions from clients and publishes data back to them upon receiving relevant publications.
            Publications (aka event notifications) can come from:
                - Code in the same server calling this instance's '.publish()'
                - Connected PubSubClients calling their own publish method (and piping into the servers via RPC)
                - Other servers linked through a broadcaster channel such as Redis Pub/Sub, Kafka, or postgres listen/notify
                    (@see EventBroadcaster and of course https://pypi.org/project/broadcaster/)

        Args:
            methods_class (optional): a class deriving from RpcEventServerMethods providing a 'subscribe' rpc method
                                      or None if RpcEventServerMethods should be used as is

            notifier (optional): Instance of WebSocketRpcEventNotifier or None to use WebSocketRpcEventNotifier() as is
                                 Handles to internal event pub/sub logic

            broadcaster (optional): Instance of EventBroadcaster, a URL string to init EventBroadcaster, or None to not use
                                    The broadcaster allows several EventRpcEndpoints across multiple processes / services to share incoming notifications

            on_connect (List[Coroutine]): callbacks on connection being established (each callback is called with the channel)
            on_disconnect (List[Coroutine]): callbacks on connection termination (each callback is called with the channel)
            ignore_broadcaster_disconnected: Don't end main loop if broadcaster's reader task ends (due to underlying disconnection)
        """
        self.notifier = (
            notifier if notifier is not None else WebSocketRpcEventNotifier()
        )
        self.broadcaster = (
            broadcaster
            if isinstance(broadcaster, EventBroadcaster) or broadcaster is None
            else EventBroadcaster(broadcaster, self.notifier)
        )
        self.methods = (
            methods_class(self.notifier)
            if methods_class is not None
            else RpcEventServerMethods(self.notifier)
        )
        if on_disconnect is None:
            on_disconnect = []
        self.endpoint = WebsocketRPCEndpoint(
            self.methods,
            on_disconnect=[self.on_disconnect, *on_disconnect],
            on_connect=on_connect,
            rpc_channel_get_remote_id=rpc_channel_get_remote_id,
        )
        self._rpc_channel_get_remote_id = rpc_channel_get_remote_id
        # server id used to publish events for clients
        self._id = self.notifier.gen_subscriber_id()
        # Separate if for the server to subscribe to its own events
        self._subscriber_id: str = self.notifier.gen_subscriber_id()
        self._ignore_broadcaster_disconnected = ignore_broadcaster_disconnected

    async def subscribe(
        self, topics: Union[TopicList, ALL_TOPICS], callback: EventCallback
    ) -> List[Subscription]:
        return await self.notifier.subscribe(self._subscriber_id, topics, callback)

    async def publish(self, topics: Union[TopicList, Topic], data=None):
        """
        Publish events to subscribres of given topics currently connected to the endpoint

        Args:
            topics (Union[TopicList, Topic]): topics to publish to relevant subscribers
            data (Any, optional): Event data to be passed to each subscriber. Defaults to None.
        """
        # if we have a broadcaster make sure we share with it (no matter where this call comes from)
        # sharing here means - the broadcaster listens in to the notifier as well
        logger.debug(f"Publishing message to topics: {topics}")
        if self.broadcaster is not None:
            logger.debug(f"Acquiring broadcaster sharing context")
            async with self.broadcaster.get_context(listen=False, share=True):
                await self.notifier.notify(topics, data, notifier_id=self._id)
        # otherwise just notify
        else:
            await self.notifier.notify(topics, data, notifier_id=self._id)

    # canonical name (backward compatability)
    notify = publish

    async def on_disconnect(self, channel: RpcChannel):
        if self._rpc_channel_get_remote_id:
            channel_other_channel_id = await channel.get_other_channel_id()
            if channel_other_channel_id is None:
                logger.warning(
                    "could not fetch remote channel id, using local channel id to unsubscribe"
                )
                subscriber_id = channel.id
            else:
                subscriber_id = channel_other_channel_id
        else:
            subscriber_id = channel.id
        await self.notifier.unsubscribe(subscriber_id)

    async def main_loop(self, websocket: WebSocket, client_id: str = None, **kwargs):
        if self.broadcaster is not None:
            async with self.broadcaster:
                logger.debug("Entering endpoint's main loop with broadcaster")
                if self._ignore_broadcaster_disconnected:
                    await self.endpoint.main_loop(websocket, client_id=client_id, **kwargs)
                else:        
                    done, pending = await asyncio.wait([self.endpoint.main_loop(websocket, client_id=client_id, **kwargs),
                                                        self.broadcaster.get_reader_task()],
                                                        return_when=asyncio.FIRST_COMPLETED)
                    logger.debug(f"task is done: {done}")
                    for t in pending:
                        t.cancel()
        else:
            logger.debug("Entering endpoint's main loop without broadcaster")
            await self.endpoint.main_loop(websocket, client_id=client_id, **kwargs)

        logger.debug("Leaving endpoint's main loop")

    def register_route(self, router, path="/pubsub"):
        """
        Register websocket routes on the given router
        Args:
            router: FastAPI router to load route onto
        """
        self.endpoint.register_route(router, path)

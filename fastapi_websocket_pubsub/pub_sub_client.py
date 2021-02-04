from fastapi_websocket_rpc.rpc_channel import RpcChannel
from fastapi_websocket_pubsub.exceptions import PubSubClientInvalidStateException
import functools
import asyncio
from typing import Coroutine, List
from tenacity import retry, wait
from websockets.exceptions import WebSocketException, ConnectionClosed

from .logger import get_logger
from .event_notifier import Topic, TopicList
from fastapi_websocket_rpc import RpcMethodsBase
from fastapi_websocket_rpc import WebSocketRpcClient
from .event_notifier import Topic
from .rpc_event_methods import RpcEventClientMethods

logger = get_logger('PubSubClient')

class PubSubClient:
    """
    pub/sub client (RPC based)

    Simple usage example (init class with subscription topics):
        client = PubSubClient(["guns", "germs", "steel"])
        client.start_client("ws://localhost:8000/ws/test-client1")

    If you want to run callbacks on topic events:
        client = PubSubClient()
        # guns_coroutine will be awaited on when event arrives on "guns" topic
        client.subscribe("guns", guns_coroutine)
        client.subscribe("germs", germs_coroutine)

    you can also run callback on successful connection
        client.on_connect(on_connect_coroutine)

    when you are done registering callbacks, call (once you do, you cannot subscribe to more topics)
    client.start_client("ws://localhost:8000/ws/test-client1")

    Advanced usage:
        override on_connect() to add more subscription / registartion logic
    """

    def __init__(self, topics: List[Topic] = [], 
                callback=None, 
                methods_class:RpcMethodsBase=None, 
                retry_config=None, 
                keep_alive:float=0, 
                on_connect:List[Coroutine]=None, 
                on_disconnect:List[Coroutine]=None, 
                **kwargs) -> None:
        """
        Args:
            topics (List[Topic]): topics client should subscribe to.
            methods_class ([RpcMethodsBase], optional): RPC Methods exposed by client. Defaults to RpcEventClientMethods.
            retry_config (Dict, optional): Tenacity (https://tenacity.readthedocs.io/) retry kwargs. Defaults to  {'wait': wait.wait_random_exponential(max=45)}
                                           retry_config is used both for initial connection failures and reconnects upon connection loss
            keep_alive(float): interval in seconds to send a keep-alive ping over the underlying RPC channel, Defaults to 0, which means keep alive is disabled.
            on_connect (List[Coroutine]): callbacks on connection being established (each callback is called with the PubSub-client and the rpc-channel)
                                          @note exceptions thrown in on_connect callbacks propagate to the client and will cause connection restart!
            on_disconnect (List[Coroutine]): callbacks on connection termination (each callback is called with the rpc-channel)
        """
        # init our methods with access to the client object (i.e. self) so they can trigger our callbacks
        self._methods = methods_class(self) if methods_class is not None else RpcEventClientMethods(self)
        # Subscription topics
        self._topics = []  
        # Subscription callbacks
        self._callbacks = {}
        self._ready_event = asyncio.Event()
        self._connect_kwargs = kwargs
        # Tenacity retry configuration
        self._retry_config = retry_config
        # Keep alive config
        self._keep_alive = keep_alive
        # Core event handlers
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        # The RpcChannel initialized - used to access the client from other asyncio tasks
        self._rpc_channel = None
        # register given topics
        for topic in topics:
            self.subscribe(topic, callback)

    def is_ready(self) -> bool:
        return self._ready_event.is_set()

    def wait_until_ready(self) -> Coroutine:
        return self._ready_event.wait()

    async def run(self, uri, wait_on_reader=True):
        """
        runs the rpc client (async api).
        if you want to call from a synchronous program, use start_client().
        """
        logger.info("trying to connect", server_uri=uri)
        async with WebSocketRpcClient(uri, self._methods,
                                      retry_config=self._retry_config, 
                                      keep_alive=self._keep_alive,
                                      # Register core event callbacks
                                      on_connect=[self._primary_on_connect],
                                      on_disconnect=self._on_disconnect, 
                                      **self._connect_kwargs) as client:
            try:
                logger.info(f"connected to PubSub server", server_uri=client.uri)
                # if we managed to connect
                if client is not None:
                    if wait_on_reader:
                        # Wait on the internal RPC task - keeping the client alive
                        await client.wait_on_reader()

            except ConnectionClosed:
                logger.error("RPC connection lost")
                raise
            except WebSocketException as err:
                logger.info("RPC connection failed", error=err)
                raise
            except Exception as err:
                logger.critical("RPC Uncaught Error", error=err)
                raise

    async def _primary_on_connect(self, channel: RpcChannel):
        # Store current channel for additional use by other methods
        self._rpc_channel = channel
        # subscribe to all the topics we have registered
        await self._subscribe_stored_topics(channel)
        self._ready_event.set()
        # Now that PubSub us alive trigger sub subscribers
        if isinstance(self._on_connect, list):
            await asyncio.gather(*(callback(self, channel) for callback in self._on_connect))
        

    def subscribe(self, topic: Topic, callback: Coroutine):
        """
        Subscribe for events (prior to starting the client)
        @see fastapi_websocket_pubsub/rpc_event_methods.py :: RpcEventServerMethods.subscribe

        Args:
            topic (Topic): the identifier of the event topic with wish to be called 
                           upon events being published - can be a simple string e.g. 
                           'hello' or a complex path 'a/b/c/d' 
            callback (Coroutine): the function to call upon relevant event publishing
        """
        if not self.is_ready():
            self._topics.append(topic)
            self._callbacks[topic] = callback
        else:
            raise PubSubClientInvalidStateException("Client already connected and subscribed")

    async def publish(self, topics: TopicList, data=None, sync=True, notifier_id=None) -> bool:
        """
        Publish an event through the server to subscribers.
        @see fastapi_websocket_pubsub/rpc_event_methods.py :: RpcEventServerMethods.publish

        Args:
            topics (TopicList): topics to publish
            data (Any, optional): data to pass with the event to the subscribers. Defaults to None.
            sync (bool, optional): Should the server finish publishing before returning to us
            notifier_id(str,optional): A unique identifier of the source of the event
                use a different id from the channel.id or the subscription id to receive own publications

        Raises:
            PubSubClientInvalidStateException

        Returns:
            bool: was the publish successful
        """
        if self.is_ready() and self._rpc_channel is not None:
            return await self._rpc_channel.other.publish(topics=topics, data=data, sync=sync, notifier_id=notifier_id)
        else:
            raise PubSubClientInvalidStateException("Client not connected")

    async def _subscribe_stored_topics(self, channel):
        """
        Communicate topics stored at self._topics to the PubSub Server
        """
        if self._topics:
            await channel.other.subscribe(topics=self._topics)

    async def trigger_topic(self, topic: Topic, data=None):
        """
        Called by RpcEventClientMethods.notify (from RPC) to handle the published event

        Args:
            topic (Topic)
            data ([Any], optional)
        """
        if topic in self._callbacks:
            await self._callbacks[topic](data=data)

    def start_client(self, server_uri, loop: asyncio.AbstractEventLoop = None, wait_on_reader=True):
        """
        Start the client and wait [if wait_on_reader=True] on the RPC-reader task

        Args:
            server_uri (str): uri to server pubsub-endpoint (e.g. 'http://localhost/pubsub')
            loop (asyncio.AbstractEventLoop, optional): event loop to run on. Defaults to asyncio.get_event_loop().
            wait_on_reader (bool, optional): Wait on task reading from server. Defaults to True.
        """
        loop = loop or asyncio.get_event_loop()
        # If the loop hasn't started yet - take over
        if not loop.is_running:
            loop.run_until_complete(self.run(server_uri, wait_on_reader))
        # Otherwise
        else:
            asyncio.create_task(self.run(server_uri, wait_on_reader))

    def start_client_async(self, server_uri, loop: asyncio.AbstractEventLoop = None):
        """
        Start the client and return once finished subscribing to events
        RPC notifications will still be handeled in the background
        """
        self.start_client(server_uri, loop, False)

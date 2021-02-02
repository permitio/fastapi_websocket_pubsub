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


def apply_retry(func):
    @functools.wraps(func)
    async def wrapped_with_retries(self, *args, **kwargs):
        if self._retry_config is False:
            new_func = func
        else:
            retry_decorator = retry(**self._retry_config)
            new_func = retry_decorator(func)
        return await new_func(self, *args, **kwargs)
    return wrapped_with_retries


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

    def __init__(self, topics: List[Topic] = [], callback=None, methods_class=None, retry_config=None, keep_alive_interval=0, **kwargs) -> None:
        """
        Args:
            topics (List[Topic]): topics client should subscribe to.
            methods_class ([RpcMethodsBase], optional): RPC Methods exposed by client. Defaults to RpcEventClientMethods.
            retry_config (Dict, optional): Tenacity (https://tenacity.readthedocs.io/) retry kwargs. Defaults to  {'wait': wait.wait_random_exponential(max=45)}
                                           retry_config is used both for initial connection failures and reconnects upon connection loss
        """
        # init our methods with access to the client object (i.e. self) so they can trigger our callbacks
        self._methods = methods_class(self) if methods_class is not None else RpcEventClientMethods(self)
        self._topics = []  # these topics will not have an attached callback
        self._callbacks = {}
        self._on_connect_callbacks = []
        self._ready_event = asyncio.Event()
        self._connect_kwargs = kwargs
        # Tenacity retry configuration
        self._retry_config = retry_config if retry_config is not None else {
            'wait': wait.wait_random_exponential(max=45)}
        self._keep_alive_interval = keep_alive_interval
        self._keep_alive_task = None
        # The WebSocketRpcClient initialized in run - used to access the client from other asyncio tasks
        self._rpc_client = None
        # register given topics
        for topic in topics:
            self.subscribe(topic, callback)

    def is_ready(self) -> bool:
        return self._ready_event.is_set()

    def wait_until_ready(self) -> Coroutine:
        return self._ready_event.wait()

    @apply_retry
    async def run(self, uri, wait_on_reader=True):
        """
        runs the rpc client (async api).
        if you want to call from a synchronous program, use start_client().
        """
        logger.info("trying to connect", server_uri=uri)
        async with WebSocketRpcClient(uri, self._methods, retry_config=self._retry_config, **self._connect_kwargs) as client:
            try:
                # if we managed to connect
                if client is not None:
                    await self._on_connection(client)
                    self._start_keep_alive(client)
                    self._rpc_client = client
                    self._ready_event.set()
                    if wait_on_reader:
                        await client.wait_on_reader()
            except ConnectionClosed:
                logger.error("RPC connection lost")
                # re-Raise so retry can reconnect us
                raise
            except WebSocketException as err:
                logger.info("RPC connection failed", error=err)
                # re-Raise so retry can reconnect us
                raise
            except Exception as err:
                logger.critical("RPC Uncaught Error", error=err)
                # re-Raise so retry can reconnect us
                raise
            finally:
                client._read_task.cancel()
                self._cancel_keep_alive()

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
        if self.is_ready() and self._rpc_client is not None:
            return await self._rpc_client.channel.other.publish(topics=topics, data=data, sync=sync, notifier_id=notifier_id)
        else:
            raise PubSubClientInvalidStateException("Client not connected")

    def on_connect(self, callback: Coroutine):
        self._on_connect_callbacks.append(callback)

    async def _on_connection(self, client):
        """
        Method called upon first connection to server
        """
        logger.info(f"connected to server", server_uri=client.uri)
        if self._topics:
            await client.channel.other.subscribe(topics=self._topics)
        if self._on_connect_callbacks:
            await asyncio.gather(*(callback() for callback in self._on_connect_callbacks))

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

    async def _keep_alive(self, client):
        while True:
            await asyncio.sleep(self._keep_alive_interval)
            logger.info("Pinging server")
            await client.channel.other.ping()

    def _cancel_keep_alive(self):
        if self._keep_alive_task:
            logger.info("Cancelling keep alive task")
            self._keep_alive_task.cancel()
            self._keep_alive_task = None

    def _start_keep_alive(self, client):
        self._cancel_keep_alive()
        if self._keep_alive_interval <= 0:
            return

        logger.info("Starting keep alive task", interval=f"{self._keep_alive_interval} seconds")
        self._keep_alive_task = asyncio.create_task(self._keep_alive(client))

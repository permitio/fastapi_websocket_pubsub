from fastapi_websocket_rpc.rpc_channel import RpcChannel, OnDisconnectCallback, OnConnectCallback
from fastapi_websocket_pubsub.exceptions import PubSubClientInvalidStateException

import websockets
import asyncio
from typing import Coroutine, List

from .logger import get_logger
from .event_notifier import Topic, TopicList
from fastapi_websocket_rpc import RpcMethodsBase
from fastapi_websocket_rpc import WebSocketRpcClient
from .event_notifier import Topic
from .rpc_event_methods import RpcEventClientMethods

logger = get_logger('PubSubClient')

# Callback signature 
async def PubSubOnConnectCallback(pubsub_client, channel:RpcChannel):
    pass

class PubSubClient:
    """
    pub/sub client (RPC based)

    Usage as subscriber:
        Simple usage example (init class with subscription topics):
            client = PubSubClient(["guns", "germs", "steel"], callback_coroutine)
            client.start_client("ws://localhost:8000/pubsub")

        If you want to register separate callbacks per topic:
            client = PubSubClient()
            # guns_coroutine will be awaited on when event arrives on "guns" topic
            client.subscribe("guns", guns_coroutine)
            client.subscribe("germs", germs_coroutine)

        When you are done registering callbacks (once you do, you cannot subscribe to more topics) call:
            client.start_client("ws://localhost:8000/pubsub")

        Another more compact option - using async with -
            async with PubSubClient(["guns","germs"], both_events_coroutine, server_uri="ws://localhost:8000/pubsub") as client:
                # will not end until client.disconnect() is called (by another task / callback)
                await client.wait_until_done()


    Usage as publisher:
            client = PubSubClient()
            client.start_client("ws://localhost:8000/pubsub")
            # Channel must be ready before we can publish on it
            await client.wait_until_ready()
            await client.publish(["Breakfast Options"], data=["spam", "eggs and spam", {"no spam": "egg bacon spam and sausage"} ])

    """

    def __init__(self, topics: List[Topic] = None,
                 callback=None,
                 methods_class: RpcMethodsBase = None,
                 retry_config=None,
                 keep_alive: float = 0,
                 on_connect: List[PubSubOnConnectCallback] = None,
                 on_disconnect: List[OnDisconnectCallback] = None,
                 server_uri = None,
                 **kwargs) -> None:
        """
        Args:
            topics (List[Topic]): topics client should subscribe to, Defaults to None.
            methods_class ([RpcMethodsBase], optional): RPC Methods exposed by client. Defaults to RpcEventClientMethods.
            retry_config (Dict, optional): Tenacity (https://tenacity.readthedocs.io/) retry kwargs. Defaults to  {'wait': wait.wait_random_exponential(max=45)}
                                           retry_config is used both for initial connection failures and reconnects upon connection loss
            keep_alive(float): interval in seconds to send a keep-alive ping over the underlying RPC channel, Defaults to 0, which means keep alive is disabled.
            on_connect (List[Coroutine]): callbacks on connection being established (each callback is called with the PubSub-client and the rpc-channel)
                                          @note exceptions thrown in on_connect callbacks propagate to the client and will cause connection restart!
            on_disconnect (List[Coroutine]): callbacks on connection termination (each callback is called with the rpc-channel)
        """
        # Should async with start the client and connect to the server, and on which address
        self._server_uri = server_uri
        # init our methods with access to the client object (i.e. self) so they can trigger our callbacks
        self._methods = methods_class(self) if methods_class is not None else RpcEventClientMethods(self)
        # Subscription topics
        self._topics = []
        # Subscription callbacks
        self._callbacks = {}
        self._connect_kwargs = kwargs
        # Tenacity retry configuration
        self._retry_config = retry_config
        # Keep alive config
        self._keep_alive = keep_alive
        # Core event handlers
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect if on_disconnect is not None else []
        # internal asyncio tasks
        self._run_task: asyncio.Task = None
        # event to force termination
        self._disconnect_signal:asyncio.Event = None
        # event to indicate the connection is ready for use 
        self._ready_event:asyncio.Event = None
        # The RpcChannel initialized - used to access the client from other asyncio tasks
        self._rpc_channel = None
        # register given topics (if we got any)
        if isinstance(topics,list):
            for topic in topics:
                self.subscribe(topic, callback)

    def is_ready(self) -> bool:
        if self._ready_event is not None:
            return self._ready_event.is_set()
        else:
            return False

    async def wait_until_done(self):
        if self._run_task is not None:
            return await self._run_task

    def wait_until_ready(self, create_event=True) -> Coroutine:
        """Return a wait coroutine for the internal readiness event
        Args:
            create_event (bool, optional): Should an event be created if missing 
            (@Note- avoid creating an event from another loop). Defaults to True.

        Raises:
            PubSubClientInvalidStateException: if has no event to wait on

        Returns:
            Coroutine: waiting function on internal event
        """
        if self._ready_event is None:
            if create_event:
                self._ready_event = asyncio.Event()
                return self._ready_event.wait()
            else:
                raise PubSubClientInvalidStateException("Cannot wait on readiness prior to client starting or without creating an event")
        else:    
            return self._ready_event.wait()

    def _init_event_objects(self):
        """
        Init asyncio events. This should be done in the correct event loop (And so better avoided at __init__)
        """
        if self._ready_event is None:
            self._ready_event = asyncio.Event()
        if self._disconnect_signal is None:
            self._disconnect_signal = asyncio.Event()

    async def __aenter__(self):
        if self._server_uri is not None:
            self.start_client(self._server_uri)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()

    async def disconnect(self):
        """
        Force the internal client to disconnect, and wait for it to do so
        """
        if self._disconnect_signal is None:
            self._disconnect_signal = asyncio.Event()
        self._disconnect_signal.set()
        if self._run_task is not None:
            await self._run_task
        self._run_task = None
        
    async def run(self, uri, wait_on_reader=True):
        """
        runs the rpc client (async api).
        if you want to call from a synchronous program, use start_client().
        """
        # init internal events 
        self._init_event_objects()
        while not self._disconnect_signal.is_set():
            try:
                logger.info(f"Trying to connect to Pub/Sub server - {uri}")
                client = WebSocketRpcClient(uri, self._methods,
                                            retry_config=self._retry_config,
                                            keep_alive=self._keep_alive,
                                            # Register core event callbacks
                                            on_connect=[self._primary_on_connect],
                                            on_disconnect=self._on_disconnect,
                                            **self._connect_kwargs)
                async with client:
                    try:
                        logger.info(f"Connected to PubSub server {uri}")
                        if wait_on_reader:
                            # Wait on the internal RPC task or until we ar asked to terminate - keeping the client alive meanwhile
                            # Waiting on the reader tasks allows us to receive exceptions raised on the websocket layer- indicating a need to reset the connection 
                            wait_on_reader_task = client.wait_on_reader()
                            for task in asyncio.as_completed([wait_on_reader_task, self._disconnect_signal.wait()]):
                                await task
                                break
                    except websockets.exceptions.WebSocketException as err:
                        logger.info(f"Connection failed with - {err}. -- Trying to reconnect.")
                    except asyncio.exceptions.CancelledError:
                        logger.info(f"Connection was actively canceled -- won't try to reconnect.")
                        # clean exit (no retrying)
                        # better support for keyboard interrupt 
                        return                         
                    except:
                        # log unhandled exceptions (which will be swallowed by the with statement otherwise )
                        logger.exception(f"Unknown PubSub error -- Trying to reconnect.")
            except:
                logger.exception(f"Unknown PubSub init error -- Trying to reconnect.")
                

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
        # TODO: add support for post connection subscriptions
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
        callback = None
        if topic in self._callbacks:
            try:
                callback = self._callbacks.get(topic,None)
                if callback is not None:
                    await callback(data=data, topic=topic)
            except:
                logger.exception("Failed to trigger a pub/sub callback", {'data':data, 'topic': topic})

    def start_client(self, server_uri, loop: asyncio.AbstractEventLoop = None, wait_on_reader=True):
        """
        Start the client (spinning out self.run as an asyncio task)

        Args:
            server_uri (str): uri to server pubsub-endpoint (e.g. 'http://localhost/pubsub')
            loop (asyncio.AbstractEventLoop, optional): event loop to run on. Defaults to asyncio.get_event_loop().
            wait_on_reader (bool, optional): Wait on task reading from server. Defaults to True.
        """
        loop = loop or asyncio.get_event_loop()
        # If the loop hasn't started yet - take over
        if not loop.is_running():
           loop.run_until_complete(self.run(server_uri, wait_on_reader))
        # Otherwise
        else:
            self._run_task = asyncio.create_task(self.run(server_uri, wait_on_reader))

    def start_client_async(self, server_uri, loop: asyncio.AbstractEventLoop = None):
        """
        Start the client and return once finished subscribing to events
        RPC notifications will still be handeled in the background
        Useful only in cases the async-loop is created by the client (i.e. start_client doesn't create a new task on an exiting loop)
        """
        self.start_client(server_uri, loop, False)

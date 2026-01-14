"""Tests for Redis DriverInfo support in EventBroadcaster."""

import sys
from unittest.mock import MagicMock, patch
import pytest

from fastapi_websocket_pubsub import EventBroadcaster
from fastapi_websocket_pubsub.event_notifier import EventNotifier
from broadcaster import Broadcast


class MockRedisBackend:
    """Mock backend with 'Redis' in class name for type checking."""
    pass


class MockPostgresBackend:
    """Mock backend without 'Redis' in class name."""
    pass


class TestDriverInfo:
    """Test suite for Redis driver info functionality."""

    @pytest.mark.asyncio
    async def test_add_driver_info_with_driver_info_class(self):
        """Test _add_driver_info_to_broadcast with modern redis-py (DriverInfo class available)."""
        # Create a mock notifier
        mock_notifier = MagicMock(spec=EventNotifier)

        # Create EventBroadcaster instance
        broadcaster = EventBroadcaster("redis://localhost:6379", mock_notifier)

        # Create a mock Broadcast instance
        mock_broadcast = MagicMock(spec=Broadcast)

        # Mock the backend and Redis client
        mock_redis_client = MagicMock()
        mock_pool = MagicMock()
        mock_pool.connection_kwargs = {}
        mock_redis_client.connection_pool = mock_pool

        # Use MockRedisBackend so type(backend).__name__ contains "Redis"
        mock_backend = MockRedisBackend()
        mock_backend._conn = mock_redis_client
        mock_broadcast._backend = mock_backend

        # Create a mock DriverInfo instance with add_upstream_driver method
        mock_driver_info_instance = MagicMock()
        mock_driver_info_instance.add_upstream_driver = MagicMock(
            return_value=mock_driver_info_instance
        )

        # Create a mock DriverInfo class
        mock_driver_info_class = MagicMock(return_value=mock_driver_info_instance)

        # Create a mock redis module with DriverInfo
        mock_redis_module = MagicMock()
        mock_redis_module.DriverInfo = mock_driver_info_class

        with patch(
            "fastapi_websocket_pubsub.event_broadcaster.get_version",
            return_value="0.3.9",
        ):
            # Temporarily add our mock redis module
            original_redis = sys.modules.get("redis")
            sys.modules["redis"] = mock_redis_module

            try:
                broadcaster._add_driver_info_to_broadcast(mock_broadcast)

                # Verify driver_info was set in connection_kwargs
                assert "driver_info" in mock_pool.connection_kwargs

                # Verify add_upstream_driver was called with correct arguments
                mock_driver_info_instance.add_upstream_driver.assert_called_once_with(
                    "fastapi-websocket-pubsub", "0.3.9"
                )
            finally:
                # Restore original redis module
                if original_redis:
                    sys.modules["redis"] = original_redis
                else:
                    sys.modules.pop("redis", None)

    @pytest.mark.asyncio
    async def test_add_driver_info_fallback_old_redis(self):
        """Test _add_driver_info_to_broadcast fallback for older redis-py versions (no DriverInfo)."""
        mock_notifier = MagicMock(spec=EventNotifier)
        broadcaster = EventBroadcaster("redis://localhost:6379", mock_notifier)

        mock_broadcast = MagicMock(spec=Broadcast)
        mock_redis_client = MagicMock()
        mock_pool = MagicMock()
        mock_pool.connection_kwargs = {}
        mock_redis_client.connection_pool = mock_pool

        # Use MockRedisBackend so type(backend).__name__ contains "Redis"
        mock_backend = MockRedisBackend()
        mock_backend._conn = mock_redis_client
        mock_broadcast._backend = mock_backend

        # Create a mock redis module WITHOUT DriverInfo but WITH __version__
        mock_redis_module = MagicMock(spec=["__version__"])
        mock_redis_module.__version__ = "3.5.3"

        with patch(
            "fastapi_websocket_pubsub.event_broadcaster.get_version",
            return_value="0.3.9",
        ):
            # Temporarily replace redis module
            original_redis = sys.modules.get("redis")
            sys.modules["redis"] = mock_redis_module

            try:
                broadcaster._add_driver_info_to_broadcast(mock_broadcast)

                # For older redis-py versions without DriverInfo, should fall back to lib_name and lib_version
                assert "driver_info" not in mock_pool.connection_kwargs
                assert (
                    mock_pool.connection_kwargs["lib_name"]
                    == "redis-py(fastapi-websocket-pubsub_v0.3.9)"
                )
                assert mock_pool.connection_kwargs["lib_version"] == "3.5.3"
            finally:
                # Restore original redis module
                if original_redis:
                    sys.modules["redis"] = original_redis
                else:
                    sys.modules.pop("redis", None)

    @pytest.mark.asyncio
    async def test_add_driver_info_no_backend(self):
        """Test _add_driver_info_to_broadcast when backend is not available."""
        mock_notifier = MagicMock(spec=EventNotifier)
        broadcaster = EventBroadcaster("redis://localhost:6379", mock_notifier)
        
        mock_broadcast = MagicMock(spec=Broadcast)
        mock_broadcast._backend = None

        # Should not raise an exception
        broadcaster._add_driver_info_to_broadcast(mock_broadcast)

    @pytest.mark.asyncio
    async def test_add_driver_info_no_connection_pool(self):
        """Test _add_driver_info_to_broadcast when redis client has no connection_pool."""
        mock_notifier = MagicMock(spec=EventNotifier)
        broadcaster = EventBroadcaster("redis://localhost:6379", mock_notifier)

        mock_broadcast = MagicMock(spec=Broadcast)
        mock_redis_client = MagicMock()
        mock_redis_client.connection_pool = None

        # Use MockRedisBackend so type(backend).__name__ contains "Redis"
        mock_backend = MockRedisBackend()
        mock_backend._conn = mock_redis_client
        mock_broadcast._backend = mock_backend

        # Should not raise an exception
        broadcaster._add_driver_info_to_broadcast(mock_broadcast)

    @pytest.mark.asyncio
    async def test_add_driver_info_skips_non_redis(self):
        """Test that _add_driver_info_to_broadcast skips non-Redis backend types."""
        mock_notifier = MagicMock(spec=EventNotifier)
        broadcaster = EventBroadcaster("postgres://localhost:5432/db", mock_notifier)

        mock_broadcast = MagicMock(spec=Broadcast)
        mock_redis_client = MagicMock()
        mock_pool = MagicMock()
        mock_pool.connection_kwargs = {}
        mock_redis_client.connection_pool = mock_pool

        # Use MockPostgresBackend so type(backend).__name__ does NOT contain "Redis"
        mock_backend = MockPostgresBackend()
        mock_backend._conn = mock_redis_client
        mock_broadcast._backend = mock_backend

        # Should not add driver info for non-Redis backend types
        broadcaster._add_driver_info_to_broadcast(mock_broadcast)

        # Verify no driver info was added
        assert "driver_info" not in mock_pool.connection_kwargs
        assert "lib_name" not in mock_pool.connection_kwargs

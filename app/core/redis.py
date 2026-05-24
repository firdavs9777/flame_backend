import redis.asyncio as redis
import json
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisPubSub:
    """Redis pub/sub manager for cross-worker WebSocket communication.

    Without a healthy pub/sub connection, cross-worker WebSocket delivery is
    broken (one user's message won't reach the other if they're on different
    workers). We fail loudly at startup instead of silently degrading.
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable] = None
        self.healthy: bool = False

    async def connect(self):
        """Connect to Redis. Raises on failure — pub/sub is required."""
        logger.info(f"Connecting to Redis at {settings.REDIS_URL}...")
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await self.redis.ping()
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe("websocket_events")
        self.healthy = True
        logger.info("Redis connected and subscribed to websocket_events")

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self.pubsub:
            await self.pubsub.unsubscribe("websocket_events")
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()

    def set_message_handler(self, handler: Callable):
        """Set the handler for incoming messages."""
        self._message_handler = handler

    async def start_listener(self):
        """Start listening for Redis pub/sub messages."""
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        """Listen for messages from Redis. Auto-reconnects on transient errors."""
        backoff = 1
        while True:
            try:
                if not self.pubsub:
                    break
                async for message in self.pubsub.listen():
                    if message["type"] == "message" and self._message_handler:
                        try:
                            data = json.loads(message["data"])
                            await self._message_handler(data)
                        except json.JSONDecodeError:
                            logger.warning("Bad JSON on websocket_events")
                        except Exception as e:
                            logger.exception(f"Error handling pubsub message: {e}")
                backoff = 1
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"Pubsub listener error, reconnecting in {backoff}s: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                try:
                    if self.pubsub:
                        await self.pubsub.subscribe("websocket_events")
                except Exception:
                    pass

    async def publish(self, event_type: str, data: Dict[str, Any]):
        """Publish a message to all workers."""
        if not self.redis:
            logger.warning("publish called but Redis is not connected")
            return
        message = json.dumps({"type": event_type, "data": data})
        try:
            await self.redis.publish("websocket_events", message)
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")


# Global instance
redis_pubsub = RedisPubSub()

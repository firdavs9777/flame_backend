import redis.asyncio as redis
import json
import asyncio
from typing import Optional, Callable, Dict, Any
from app.core.config import settings


class RedisPubSub:
    """Redis pub/sub manager for cross-worker WebSocket communication."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable] = None

    async def connect(self):
        """Connect to Redis."""
        print(f"[Redis] Connecting to {settings.REDIS_URL}...")
        try:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe("websocket_events")
            print("[Redis] Connected and subscribed to websocket_events channel")
        except Exception as e:
            print(f"[Redis] Failed to connect: {e}")

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
        """Listen for messages from Redis."""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message" and self._message_handler:
                    try:
                        data = json.loads(message["data"])
                        await self._message_handler(data)
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        print(f"[Redis] Error handling message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Redis] Listener error: {e}")

    async def publish(self, event_type: str, data: Dict[str, Any]):
        """Publish a message to all workers."""
        if self.redis:
            message = json.dumps({"type": event_type, "data": data})
            await self.redis.publish("websocket_events", message)


# Global instance
redis_pubsub = RedisPubSub()

"""
Redis caching infrastructure for Flame backend.

Provides:
- Async Redis connection management
- Key-value caching with TTL
- JSON serialization support
- Cache decorators for methods
- User online status tracking
- Conversation cache management
"""

import json
import hashlib
from typing import Optional, Any, TypeVar, Callable, List, Dict, Union
from datetime import timedelta
from functools import wraps
from redis import asyncio as aioredis
from app.core.config import settings

T = TypeVar('T')


class CacheService:
    """
    Async Redis caching service.

    Usage:
        from app.core.cache import cache

        # Get/Set
        await cache.set("key", "value", ttl=300)
        value = await cache.get("key")

        # JSON
        await cache.set_json("user:123", {"name": "John"}, ttl=300)
        data = await cache.get_json("user:123")

        # Delete
        await cache.delete("key")
        await cache.delete_pattern("user:*")
    """

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self):
        """Initialize Redis connection."""
        if self._connected:
            return

        try:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
            # Test connection
            await self.redis.ping()
            self._connected = True
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self._connected = False

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self._connected = False

    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._connected

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        if not self._connected:
            return None
        try:
            return await self.redis.get(key)
        except Exception:
            return None

    async def set(
        self,
        key: str,
        value: Union[str, int, float],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a value with optional TTL.

        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live in seconds
        """
        if not self._connected:
            return False
        try:
            if ttl:
                await self.redis.setex(key, ttl, value)
            else:
                await self.redis.set(key, value)
            return True
        except Exception:
            return False

    async def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON value."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Serialize and set JSON value."""
        try:
            json_str = json.dumps(value, default=str)
            return await self.set(key, json_str, ttl)
        except (TypeError, json.JSONDecodeError):
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key."""
        if not self._connected:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception:
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Redis pattern (e.g., "user:*")

        Returns:
            Number of keys deleted
        """
        if not self._connected:
            return 0
        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await self.redis.delete(*keys)
            return 0
        except Exception:
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self._connected:
            return False
        try:
            return await self.redis.exists(key) > 0
        except Exception:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        if not self._connected:
            return False
        try:
            return await self.redis.expire(key, ttl)
        except Exception:
            return False

    async def incr(self, key: str) -> int:
        """Increment a counter."""
        if not self._connected:
            return 0
        try:
            return await self.redis.incr(key)
        except Exception:
            return 0

    async def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Get multiple values at once."""
        if not self._connected or not keys:
            return {}
        try:
            values = await self.redis.mget(keys)
            return dict(zip(keys, values))
        except Exception:
            return {}

    async def set_many(
        self,
        mapping: Dict[str, str],
        ttl: Optional[int] = None
    ) -> bool:
        """Set multiple values at once."""
        if not self._connected or not mapping:
            return False
        try:
            await self.redis.mset(mapping)
            if ttl:
                for key in mapping:
                    await self.redis.expire(key, ttl)
            return True
        except Exception:
            return False


class OnlineStatusTracker:
    """
    Track user online status using Redis.

    More efficient than database queries for frequent online checks.
    """

    def __init__(self, cache: CacheService):
        self.cache = cache
        self.ttl = 120  # Consider offline after 2 minutes without heartbeat

    async def set_online(self, user_id: str) -> bool:
        """Mark user as online."""
        return await self.cache.set(f"online:{user_id}", "1", ttl=self.ttl)

    async def set_offline(self, user_id: str) -> bool:
        """Mark user as offline."""
        return await self.cache.delete(f"online:{user_id}")

    async def is_online(self, user_id: str) -> bool:
        """Check if user is online."""
        return await self.cache.exists(f"online:{user_id}")

    async def refresh(self, user_id: str) -> bool:
        """Refresh online status (call on heartbeat)."""
        return await self.cache.expire(f"online:{user_id}", self.ttl)

    async def get_online_status(self, user_ids: List[str]) -> Dict[str, bool]:
        """Batch check online status for multiple users."""
        if not user_ids:
            return {}

        keys = [f"online:{uid}" for uid in user_ids]
        results = await self.cache.get_many(keys)

        return {
            uid: results.get(f"online:{uid}") is not None
            for uid in user_ids
        }


class ConversationCache:
    """
    Cache conversation data for quick access.
    """

    def __init__(self, cache: CacheService):
        self.cache = cache
        self.ttl = 60  # 1 minute cache for conversation list

    async def get_conversation_list(self, user_id: str) -> Optional[dict]:
        """Get cached conversation list for user."""
        return await self.cache.get_json(f"convlist:{user_id}")

    async def set_conversation_list(
        self,
        user_id: str,
        data: dict
    ) -> bool:
        """Cache conversation list for user."""
        return await self.cache.set_json(f"convlist:{user_id}", data, ttl=self.ttl)

    async def invalidate_conversation_list(self, user_id: str) -> bool:
        """Invalidate conversation list cache."""
        return await self.cache.delete(f"convlist:{user_id}")

    async def invalidate_for_users(self, user_ids: List[str]) -> int:
        """Invalidate conversation list for multiple users."""
        count = 0
        for uid in user_ids:
            if await self.invalidate_conversation_list(uid):
                count += 1
        return count


class UserCache:
    """
    Cache user profile data.
    """

    def __init__(self, cache: CacheService):
        self.cache = cache
        self.ttl = 300  # 5 minutes cache

    async def get_user(self, user_id: str) -> Optional[dict]:
        """Get cached user data."""
        return await self.cache.get_json(f"user:{user_id}")

    async def set_user(self, user_id: str, data: dict) -> bool:
        """Cache user data."""
        return await self.cache.set_json(f"user:{user_id}", data, ttl=self.ttl)

    async def invalidate_user(self, user_id: str) -> bool:
        """Invalidate user cache."""
        return await self.cache.delete(f"user:{user_id}")

    async def get_users_batch(self, user_ids: List[str]) -> Dict[str, Optional[dict]]:
        """Get multiple users from cache."""
        if not user_ids:
            return {}

        result = {}
        for uid in user_ids:
            data = await self.get_user(uid)
            result[uid] = data
        return result


class RateLimiter:
    """
    Rate limiting using Redis.
    """

    def __init__(self, cache: CacheService):
        self.cache = cache

    async def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """
        Check if request should be rate limited.

        Args:
            key: Unique key (e.g., "ratelimit:user:123:messages")
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            True if rate limited, False if allowed
        """
        if not self.cache.is_connected():
            return False  # Allow if Redis is down

        try:
            count = await self.cache.incr(key)

            # Set expiry on first request
            if count == 1:
                await self.cache.expire(key, window_seconds)

            return count > max_requests
        except Exception:
            return False

    async def get_remaining(
        self,
        key: str,
        max_requests: int
    ) -> int:
        """Get remaining requests in current window."""
        if not self.cache.is_connected():
            return max_requests

        try:
            current = await self.cache.get(key)
            if current:
                return max(0, max_requests - int(current))
            return max_requests
        except Exception:
            return max_requests


# Global instances
cache = CacheService()
online_tracker = OnlineStatusTracker(cache)
conversation_cache = ConversationCache(cache)
user_cache = UserCache(cache)
rate_limiter = RateLimiter(cache)


# Decorator for caching function results
def cached(
    key_prefix: str,
    ttl: int = 300,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Decorator to cache async function results.

    Usage:
        @cached("user_profile", ttl=300)
        async def get_user_profile(user_id: str):
            ...

        @cached("search", ttl=60, key_builder=lambda q, page: f"{q}:{page}")
        async def search(query: str, page: int):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Skip cache if not connected
            if not cache.is_connected():
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                # Create hash from args/kwargs
                key_data = f"{args}:{kwargs}"
                key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
                cache_key = f"{key_prefix}:{key_hash}"

            # Try cache first
            cached_value = await cache.get_json(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            await cache.set_json(cache_key, result, ttl)

            return result
        return wrapper
    return decorator

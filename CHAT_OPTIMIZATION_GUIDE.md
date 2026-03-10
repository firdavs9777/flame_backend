# Flame Backend - Chat System Optimization Guide

This document provides a comprehensive analysis of the current chat implementation and detailed recommendations for optimizations, especially for real-time messaging performance and scalability.

---

## Table of Contents

1. [Current Implementation Analysis](#current-implementation-analysis)
2. [Database Optimizations](#database-optimizations)
3. [WebSocket Optimizations](#websocket-optimizations)
4. [Caching Strategy](#caching-strategy)
5. [Message Delivery Improvements](#message-delivery-improvements)
6. [Media Handling Optimizations](#media-handling-optimizations)
7. [Scalability Considerations](#scalability-considerations)
8. [Push Notifications](#push-notifications)
9. [Performance Monitoring](#performance-monitoring)
10. [Implementation Priority](#implementation-priority)

---

## Current Implementation Analysis

### Strengths of Current Implementation

1. **Async-first design** - Uses Motor (async MongoDB driver) and httpx (async HTTP)
2. **Clean architecture** - Clear separation between routes, services, and models
3. **Rich message types** - Supports text, images, videos, voice, stickers
4. **Real-time features** - WebSocket for typing indicators, read receipts, reactions
5. **Conversation caching** - Last message info cached in Conversation document

### Identified Bottlenecks

#### 1. N+1 Query Problem in `get_conversations()`

**Location:** `app/chat/service.py:14-70`

```python
# Current implementation fetches users one by one
for conv in conversations:
    other_user_id = conv.get_other_user_id(str(user.id))
    other_user = await User.get(other_user_id)  # N queries!
```

**Impact:** For a user with 20 conversations, this makes 21 database calls (1 for conversations + 20 for users).

#### 2. In-Memory Pagination

**Location:** `app/chat/service.py:67-68`

```python
total = len(results)
paginated = results[offset : offset + limit]
```

**Impact:** Fetches ALL conversations, then slices in Python. Wastes memory and bandwidth.

#### 3. Single-Server WebSocket Manager

**Location:** `app/chat/websocket.py:12-71`

```python
class ConnectionManager:
    active_connections: Dict[str, WebSocket] = {}  # In-memory only
```

**Impact:** Cannot scale horizontally. Users connected to different servers can't communicate.

#### 4. No Connection Pooling for Storage

**Location:** `app/core/storage.py:15-26`

```python
def __init__(self):
    self.client = boto3.client("s3", ...)  # Synchronous client
```

**Impact:** Creates new S3 connections for each upload. Missing async support.

#### 5. Missing Database Indexes

Several queries lack optimal indexes for common access patterns.

#### 6. No Message Delivery Confirmation

Messages are marked as "sent" but no reliable delivery/receipt confirmation system.

---

## Database Optimizations

### 1. Add Missing Indexes

Create these indexes for optimal query performance:

```python
# In app/models/message.py - Add to Settings.indexes
class Message(Document):
    class Settings:
        name = "messages"
        indexes = [
            "conversation_id",
            "sender_id",
            [("conversation_id", 1), ("timestamp", -1)],
            [("conversation_id", 1), ("is_deleted", 1)],
            # ADD THESE:
            [("conversation_id", 1), ("status", 1)],  # For unread queries
            [("conversation_id", 1), ("_id", -1)],    # For cursor pagination
            {"key": [("timestamp", 1)], "expireAfterSeconds": 31536000}  # Optional: TTL for old messages
        ]
```

```python
# In app/models/conversation.py - Add compound index
class Conversation(Document):
    class Settings:
        indexes = [
            # Existing...
            # ADD: For listing user's conversations sorted by activity
            [("user1_id", 1), ("user2_id", 1), ("updated_at", -1)],
        ]
```

```python
# Create indexes via MongoDB shell or migration script:
db.messages.createIndex({"conversation_id": 1, "timestamp": -1})
db.messages.createIndex({"conversation_id": 1, "status": 1})
db.conversations.createIndex({"user1_id": 1, "updated_at": -1})
db.conversations.createIndex({"user2_id": 1, "updated_at": -1})
```

### 2. Fix N+1 Query Problem

**Replace individual user fetches with batch query:**

```python
# app/chat/service.py - Optimized get_conversations()

@staticmethod
async def get_conversations(
    user: User,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[dict], int]:
    """Get user's conversations - OPTIMIZED."""
    user_id = str(user.id)

    # Use aggregation pipeline for efficient query
    pipeline = [
        # Match user's conversations
        {
            "$match": {
                "$or": [
                    {"user1_id": user_id},
                    {"user2_id": user_id}
                ]
            }
        },
        # Sort by recent activity
        {"$sort": {"updated_at": -1}},
        # Facet for count and pagination
        {
            "$facet": {
                "total": [{"$count": "count"}],
                "data": [
                    {"$skip": offset},
                    {"$limit": limit}
                ]
            }
        }
    ]

    result = await Conversation.aggregate(pipeline).to_list()

    conversations = result[0]["data"] if result else []
    total = result[0]["total"][0]["count"] if result and result[0]["total"] else 0

    # Batch fetch all other users in ONE query
    other_user_ids = []
    for conv in conversations:
        other_id = conv["user2_id"] if conv["user1_id"] == user_id else conv["user1_id"]
        other_user_ids.append(other_id)

    # Single query for all users
    users = await User.find({"_id": {"$in": [ObjectId(uid) for uid in other_user_ids]}}).to_list()
    user_map = {str(u.id): u for u in users}

    # Build results
    results = []
    for conv in conversations:
        other_id = conv["user2_id"] if conv["user1_id"] == user_id else conv["user1_id"]
        other_user = user_map.get(other_id)
        if not other_user:
            continue

        # Check mute status
        is_muted = False
        muted_until = None
        if user_id == conv["user1_id"] and conv.get("user1_muted_until"):
            if conv["user1_muted_until"] > datetime.now(timezone.utc):
                is_muted = True
                muted_until = conv["user1_muted_until"].isoformat()
        elif user_id == conv["user2_id"] and conv.get("user2_muted_until"):
            if conv["user2_muted_until"] > datetime.now(timezone.utc):
                is_muted = True
                muted_until = conv["user2_muted_until"].isoformat()

        # Get unread count
        unread_count = conv.get("user1_unread_count", 0) if user_id == conv["user1_id"] else conv.get("user2_unread_count", 0)

        results.append({
            "conversation": conv,
            "other_user": other_user,
            "unread_count": unread_count,
            "last_message": {
                "id": conv.get("last_message_id"),
                "content": conv.get("last_message_content"),
                "sender_id": conv.get("last_message_sender_id"),
                "timestamp": conv.get("last_message_at").isoformat() if conv.get("last_message_at") else None,
            } if conv.get("last_message_id") else None,
            "is_muted": is_muted,
            "muted_until": muted_until,
        })

    return results, total
```

**Result:** Reduces from N+1 queries to 2 queries (1 aggregation + 1 batch user fetch).

### 3. Use Cursor-Based Pagination for Messages

**Current:** Uses `before` message ID then filters by timestamp.

**Recommended:** Use `_id` directly (more efficient):

```python
# app/chat/service.py - Optimized get_messages()

@staticmethod
async def get_messages(
    conversation_id: str,
    user: User,
    limit: int = 50,
    cursor: Optional[str] = None,  # Last message _id
) -> Tuple[List[Message], Optional[str]]:
    """Get messages with cursor-based pagination."""
    conv = await ChatService.get_conversation(conversation_id, user)

    query = {
        "conversation_id": str(conv.id),
        "is_deleted": {"$ne": True}
    }

    if cursor:
        # Fetch messages before cursor (older)
        query["_id"] = {"$lt": ObjectId(cursor)}

    messages = (
        await Message.find(query)
        .sort([("_id", -1)])  # Sort by _id (contains timestamp)
        .limit(limit + 1)
        .to_list()
    )

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Return next cursor
    next_cursor = str(messages[-1].id) if messages and has_more else None

    # Reverse for chronological order
    messages.reverse()

    return messages, next_cursor
```

### 4. Optimize Message Status Updates

**Current:** Updates message status one by one or with multiple finds.

**Recommended:** Use bulk write operations:

```python
# app/chat/service.py - Optimized mark_messages_read()

@staticmethod
async def mark_messages_read(
    conversation_id: str,
    user: User,
    up_to_message_id: Optional[str] = None,  # Mark all up to this message
):
    """Mark messages as read efficiently."""
    conv = await ChatService.get_conversation(conversation_id, user)

    # Build query for unread messages from other user
    query = {
        "conversation_id": str(conv.id),
        "sender_id": {"$ne": str(user.id)},
        "status": {"$ne": MessageStatus.READ.value}
    }

    if up_to_message_id:
        query["_id"] = {"$lte": ObjectId(up_to_message_id)}

    # Bulk update with single query
    await Message.find(query).update_many({
        "$set": {"status": MessageStatus.READ.value}
    })

    # Reset unread count
    conv.reset_unread(str(user.id))
    await conv.save()
```

### 5. Add Read Concern for Consistency

For critical operations, use appropriate read/write concerns:

```python
# For important reads (like checking if match exists)
from pymongo import ReadPreference, WriteConcern

# In critical operations:
async def check_match_exists(user1_id: str, user2_id: str) -> bool:
    # Use majority read concern for consistency
    match = await Match.find_one(
        {
            "$or": [
                {"user1_id": user1_id, "user2_id": user2_id},
                {"user1_id": user2_id, "user2_id": user1_id}
            ],
            "is_active": True
        },
        # Note: Beanie/Motor handles this differently - configure at collection level
    )
    return match is not None
```

---

## WebSocket Optimizations

### 1. Add Redis Pub/Sub for Horizontal Scaling

The current implementation uses in-memory dictionaries, which don't work across multiple server instances.

**New file: `app/core/redis_pubsub.py`**

```python
import aioredis
import json
from typing import Optional, Callable, Awaitable
from app.core.config import settings

class RedisPubSub:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.handlers: dict[str, Callable[[dict], Awaitable[None]]] = {}

    async def connect(self):
        self.redis = await aioredis.from_url(settings.REDIS_URL)
        self.pubsub = self.redis.pubsub()

    async def disconnect(self):
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()

    async def subscribe(self, channel: str, handler: Callable[[dict], Awaitable[None]]):
        """Subscribe to a channel with a handler."""
        self.handlers[channel] = handler
        await self.pubsub.subscribe(channel)

    async def publish(self, channel: str, message: dict):
        """Publish message to channel."""
        await self.redis.publish(channel, json.dumps(message))

    async def listen(self):
        """Listen for messages and dispatch to handlers."""
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"].decode()
                data = json.loads(message["data"])
                if channel in self.handlers:
                    await self.handlers[channel](data)

# Global instance
redis_pubsub = RedisPubSub()
```

**Updated `app/chat/websocket.py`:**

```python
from app.core.redis_pubsub import redis_pubsub
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_conversations: Dict[str, Set[str]] = {}
        self.server_id = str(uuid.uuid4())[:8]  # Unique server identifier

    async def initialize(self):
        """Initialize Redis pub/sub."""
        await redis_pubsub.connect()
        # Subscribe to broadcast channel
        await redis_pubsub.subscribe(
            "chat_broadcast",
            self._handle_redis_message
        )
        # Start listener in background
        asyncio.create_task(redis_pubsub.listen())

    async def _handle_redis_message(self, data: dict):
        """Handle messages from Redis."""
        if data.get("server_id") == self.server_id:
            return  # Ignore our own messages

        target_type = data.get("target_type")
        target_id = data.get("target_id")
        message = data.get("message")
        exclude_user = data.get("exclude_user")

        if target_type == "user":
            await self._send_to_local_user(target_id, message)
        elif target_type == "conversation":
            await self._broadcast_to_local_conversation(target_id, message, exclude_user)

    async def send_personal_message(self, message: dict, user_id: str):
        """Send to user - try local first, then broadcast via Redis."""
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)
        else:
            # User might be on another server
            await redis_pubsub.publish("chat_broadcast", {
                "server_id": self.server_id,
                "target_type": "user",
                "target_id": user_id,
                "message": message
            })

    async def broadcast_to_conversation(
        self, message: dict, conversation_id: str, exclude_user: Optional[str] = None
    ):
        """Broadcast to conversation - local + Redis."""
        # Send to local users
        await self._broadcast_to_local_conversation(conversation_id, message, exclude_user)

        # Broadcast via Redis for other servers
        await redis_pubsub.publish("chat_broadcast", {
            "server_id": self.server_id,
            "target_type": "conversation",
            "target_id": conversation_id,
            "message": message,
            "exclude_user": exclude_user
        })

    async def _send_to_local_user(self, user_id: str, message: dict):
        """Send to local user if connected."""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except:
                pass  # Connection might be closed

    async def _broadcast_to_local_conversation(
        self, conversation_id: str, message: dict, exclude_user: Optional[str]
    ):
        """Broadcast to local users in conversation."""
        for user_id, conversations in self.user_conversations.items():
            if conversation_id in conversations and user_id != exclude_user:
                await self._send_to_local_user(user_id, message)
```

### 2. Add Connection Heartbeat/Ping-Pong

Detect stale connections and clean them up:

```python
# app/chat/websocket.py

import asyncio
from datetime import datetime, timezone, timedelta

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.last_heartbeat: Dict[str, datetime] = {}
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_timeout = 90  # seconds

    async def start_heartbeat_checker(self):
        """Background task to check for dead connections."""
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await self._check_dead_connections()

    async def _check_dead_connections(self):
        """Remove connections that haven't responded to heartbeat."""
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=self.heartbeat_timeout)

        dead_users = []
        for user_id, last_beat in self.last_heartbeat.items():
            if now - last_beat > timeout:
                dead_users.append(user_id)

        for user_id in dead_users:
            await self._cleanup_dead_connection(user_id)

    async def _cleanup_dead_connection(self, user_id: str):
        """Clean up a dead connection."""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].close()
            except:
                pass
            self.disconnect(user_id)

            # Update user offline status
            user = await User.get(user_id)
            if user:
                user.is_online = False
                user.last_active = datetime.now(timezone.utc)
                await user.save()

    def update_heartbeat(self, user_id: str):
        """Update last heartbeat time for user."""
        self.last_heartbeat[user_id] = datetime.now(timezone.utc)
```

**In WebSocket handler:**

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    # ... authentication ...

    await manager.connect(websocket, user_id)
    manager.update_heartbeat(user_id)

    try:
        while True:
            data = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=60  # Expect at least ping every 60s
            )

            message = json.loads(data)
            event = message.get("event")

            if event == "ping":
                manager.update_heartbeat(user_id)
                await websocket.send_json({"event": "pong"})
            # ... other events ...

    except asyncio.TimeoutError:
        # No message received, send ping
        try:
            await websocket.send_json({"event": "ping"})
        except:
            manager.disconnect(user_id)
    except WebSocketDisconnect:
        manager.disconnect(user_id)
```

### 3. Add Message Queuing for Reliability

For important messages, queue them if user is offline:

```python
# app/core/message_queue.py

from datetime import datetime, timezone, timedelta
from typing import List, Dict

class OfflineMessageQueue:
    """Queue messages for offline users - stored in Redis."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.queue_ttl = 86400 * 7  # 7 days

    async def queue_message(self, user_id: str, message: dict):
        """Add message to user's offline queue."""
        key = f"offline_queue:{user_id}"
        message["queued_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.rpush(key, json.dumps(message))
        await self.redis.expire(key, self.queue_ttl)

    async def get_pending_messages(self, user_id: str) -> List[dict]:
        """Get and clear user's pending messages."""
        key = f"offline_queue:{user_id}"
        messages = await self.redis.lrange(key, 0, -1)
        if messages:
            await self.redis.delete(key)
        return [json.loads(m) for m in messages]

    async def get_queue_size(self, user_id: str) -> int:
        """Get number of pending messages."""
        key = f"offline_queue:{user_id}"
        return await self.redis.llen(key)
```

**Usage in ConnectionManager:**

```python
async def send_personal_message(self, message: dict, user_id: str):
    """Send to user - queue if offline."""
    if user_id in self.active_connections:
        try:
            await self.active_connections[user_id].send_json(message)
            return True
        except:
            self.disconnect(user_id)

    # User offline - queue important messages
    if message.get("event") in ["new_message", "new_match"]:
        await self.offline_queue.queue_message(user_id, message)

    return False

async def connect(self, websocket: WebSocket, user_id: str):
    """Accept connection and deliver queued messages."""
    await websocket.accept()
    self.active_connections[user_id] = websocket

    # Deliver queued messages
    pending = await self.offline_queue.get_pending_messages(user_id)
    for message in pending:
        try:
            await websocket.send_json(message)
        except:
            break
```

### 4. Implement Connection Throttling

Prevent abuse and resource exhaustion:

```python
# app/chat/websocket.py

from collections import defaultdict
from datetime import datetime, timezone, timedelta

class RateLimiter:
    def __init__(self):
        self.message_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.max_messages_per_minute = 60
        self.max_messages_per_second = 10

    def is_rate_limited(self, user_id: str) -> bool:
        """Check if user is rate limited."""
        now = datetime.now(timezone.utc)
        minute_ago = now - timedelta(minutes=1)
        second_ago = now - timedelta(seconds=1)

        # Clean old entries
        self.message_counts[user_id] = [
            t for t in self.message_counts[user_id]
            if t > minute_ago
        ]

        times = self.message_counts[user_id]

        # Check per-minute limit
        if len(times) >= self.max_messages_per_minute:
            return True

        # Check per-second limit
        recent = [t for t in times if t > second_ago]
        if len(recent) >= self.max_messages_per_second:
            return True

        return False

    def record_message(self, user_id: str):
        """Record a message from user."""
        self.message_counts[user_id].append(datetime.now(timezone.utc))

rate_limiter = RateLimiter()
```

---

## Caching Strategy

### 1. Implement Redis Caching Layer

**New file: `app/core/cache.py`**

```python
import aioredis
import json
from typing import Optional, Any, TypeVar, Callable
from datetime import timedelta
from functools import wraps
from app.core.config import settings

T = TypeVar('T')

class CacheService:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self):
        self.redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )

    async def get(self, key: str) -> Optional[str]:
        return await self.redis.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None  # seconds
    ):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        if ttl:
            await self.redis.setex(key, ttl, value)
        else:
            await self.redis.set(key, value)

    async def delete(self, key: str):
        await self.redis.delete(key)

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

    async def get_json(self, key: str) -> Optional[dict]:
        value = await self.get(key)
        return json.loads(value) if value else None

    # Cache decorator
    def cached(
        self,
        key_prefix: str,
        ttl: int = 300,  # 5 minutes default
        key_builder: Optional[Callable[..., str]] = None
    ):
        """Decorator for caching function results."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Build cache key
                if key_builder:
                    cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
                else:
                    cache_key = f"{key_prefix}:{hash(str(args) + str(kwargs))}"

                # Try cache first
                cached = await self.get_json(cache_key)
                if cached is not None:
                    return cached

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                await self.set(cache_key, result, ttl)

                return result
            return wrapper
        return decorator

cache = CacheService()
```

### 2. Cache User Profiles

Users are fetched frequently - cache them:

```python
# app/community/service.py

from app.core.cache import cache

class UserService:
    CACHE_TTL = 300  # 5 minutes

    @staticmethod
    async def get_user_by_id_cached(user_id: str) -> Optional[User]:
        """Get user with caching."""
        cache_key = f"user:{user_id}"

        # Try cache
        cached = await cache.get_json(cache_key)
        if cached:
            return User(**cached)

        # Fetch from DB
        user = await User.get(user_id)
        if user:
            # Cache user data (without sensitive fields)
            user_data = {
                "id": str(user.id),
                "name": user.name,
                "age": user.age,
                "bio": user.bio,
                "photos": [p.dict() for p in user.photos],
                "is_online": user.is_online,
                "last_active": user.last_active.isoformat(),
            }
            await cache.set(cache_key, user_data, UserService.CACHE_TTL)

        return user

    @staticmethod
    async def invalidate_user_cache(user_id: str):
        """Invalidate user cache after updates."""
        await cache.delete(f"user:{user_id}")
```

### 3. Cache Conversation List

```python
# app/chat/service.py

class ChatService:
    @staticmethod
    async def get_conversations_cached(
        user: User,
        limit: int = 20,
        offset: int = 0,
    ):
        """Get conversations with caching for first page."""
        user_id = str(user.id)

        # Only cache first page
        if offset == 0 and limit == 20:
            cache_key = f"conversations:{user_id}"
            cached = await cache.get_json(cache_key)
            if cached:
                return cached["results"], cached["total"]

        # Fetch from DB
        results, total = await ChatService.get_conversations(user, limit, offset)

        # Cache first page
        if offset == 0 and limit == 20:
            # Don't cache full User objects - just essential data
            cache_data = {
                "results": [
                    {
                        "conversation_id": str(r["conversation"].id),
                        "other_user_id": str(r["other_user"].id),
                        "other_user_name": r["other_user"].name,
                        "other_user_photo": r["other_user"].photos[0].url if r["other_user"].photos else None,
                        "other_user_online": r["other_user"].is_online,
                        "unread_count": r["unread_count"],
                        "last_message": r["last_message"],
                        "is_muted": r["is_muted"],
                    }
                    for r in results
                ],
                "total": total
            }
            await cache.set(cache_key, cache_data, 60)  # 1 minute cache

        return results, total

    @staticmethod
    async def invalidate_conversation_cache(user1_id: str, user2_id: str):
        """Invalidate conversation cache for both users."""
        await cache.delete(f"conversations:{user1_id}")
        await cache.delete(f"conversations:{user2_id}")
```

### 4. Cache Sticker Packs

Sticker packs rarely change - cache aggressively:

```python
# app/chat/service.py

class StickerService:
    @staticmethod
    async def get_sticker_packs_cached() -> List[StickerPack]:
        """Get all sticker packs with caching."""
        cache_key = "sticker_packs:all"

        cached = await cache.get_json(cache_key)
        if cached:
            return [StickerPack(**p) for p in cached]

        packs = await StickerPack.find_all().to_list()

        # Cache for 1 hour
        await cache.set(
            cache_key,
            [p.dict() for p in packs],
            3600
        )

        return packs

    @staticmethod
    async def get_sticker_pack_cached(pack_id: str) -> Tuple[StickerPack, List[Sticker]]:
        """Get sticker pack with stickers, cached."""
        cache_key = f"sticker_pack:{pack_id}"

        cached = await cache.get_json(cache_key)
        if cached:
            return (
                StickerPack(**cached["pack"]),
                [Sticker(**s) for s in cached["stickers"]]
            )

        pack, stickers = await StickerService.get_sticker_pack(pack_id)

        # Cache for 1 hour
        await cache.set(cache_key, {
            "pack": pack.dict(),
            "stickers": [s.dict() for s in stickers]
        }, 3600)

        return pack, stickers
```

### 5. Online Status Cache

Track online users in Redis for quick lookups:

```python
# app/core/online_tracker.py

class OnlineTracker:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ttl = 120  # Consider offline after 2 minutes without heartbeat

    async def set_online(self, user_id: str):
        """Mark user as online."""
        await self.redis.setex(f"online:{user_id}", self.ttl, "1")

    async def set_offline(self, user_id: str):
        """Mark user as offline."""
        await self.redis.delete(f"online:{user_id}")

    async def is_online(self, user_id: str) -> bool:
        """Check if user is online."""
        return await self.redis.exists(f"online:{user_id}")

    async def get_online_users(self, user_ids: List[str]) -> Dict[str, bool]:
        """Batch check online status."""
        if not user_ids:
            return {}

        pipeline = self.redis.pipeline()
        for uid in user_ids:
            pipeline.exists(f"online:{uid}")

        results = await pipeline.execute()
        return {uid: bool(r) for uid, r in zip(user_ids, results)}

    async def refresh_online(self, user_id: str):
        """Refresh online TTL (call on heartbeat)."""
        await self.redis.expire(f"online:{user_id}", self.ttl)
```

---

## Message Delivery Improvements

### 1. Implement Message Acknowledgment

Track delivery status reliably:

```python
# app/chat/service.py

class MessageDeliveryService:
    @staticmethod
    async def send_with_ack(
        conversation_id: str,
        sender: User,
        content: str,
        message_type: MessageType,
        **kwargs
    ) -> Message:
        """Send message with delivery tracking."""
        # Create message with SENDING status
        message = Message(
            conversation_id=conversation_id,
            sender_id=str(sender.id),
            content=content,
            type=message_type,
            status=MessageStatus.SENDING,  # Initial status
            **kwargs
        )
        await message.insert()

        # Try to deliver via WebSocket
        message_data = format_message(message)
        delivered = await manager.broadcast_to_conversation(
            {
                "event": "new_message",
                "data": {
                    "conversation_id": conversation_id,
                    "message": message_data,
                    "ack_required": True,  # Request acknowledgment
                }
            },
            conversation_id,
            exclude_user=str(sender.id)
        )

        # Update status based on delivery
        if delivered:
            message.status = MessageStatus.DELIVERED
        else:
            message.status = MessageStatus.SENT
        await message.save()

        return message
```

**WebSocket acknowledgment handler:**

```python
# In websocket_endpoint

elif event == "message_ack":
    # Client acknowledges receiving message
    message_id = payload.get("message_id")
    if message_id:
        message = await Message.get(message_id)
        if message and message.status == MessageStatus.SENT:
            message.status = MessageStatus.DELIVERED
            await message.save()

            # Notify sender
            await manager.send_personal_message({
                "event": "message_delivered",
                "data": {
                    "message_id": message_id,
                    "conversation_id": message.conversation_id
                }
            }, message.sender_id)
```

### 2. Implement Read Receipts

```python
# app/chat/service.py

@staticmethod
async def mark_read_with_notification(
    conversation_id: str,
    user: User,
    message_ids: List[str],
):
    """Mark messages as read and notify sender."""
    conv = await ChatService.get_conversation(conversation_id, user)

    # Get messages that need to be marked read
    messages = await Message.find({
        "_id": {"$in": [ObjectId(mid) for mid in message_ids]},
        "conversation_id": str(conv.id),
        "sender_id": {"$ne": str(user.id)},
        "status": {"$ne": MessageStatus.READ.value}
    }).to_list()

    if not messages:
        return

    # Update all to READ
    await Message.find({
        "_id": {"$in": [m.id for m in messages]}
    }).update_many({"$set": {"status": MessageStatus.READ.value}})

    # Reset unread count
    conv.reset_unread(str(user.id))
    await conv.save()

    # Group by sender for notifications
    sender_ids = set(m.sender_id for m in messages)
    for sender_id in sender_ids:
        sender_message_ids = [str(m.id) for m in messages if m.sender_id == sender_id]
        await manager.send_personal_message({
            "event": "messages_read",
            "data": {
                "conversation_id": conversation_id,
                "message_ids": sender_message_ids,
                "read_by": str(user.id),
                "read_at": datetime.now(timezone.utc).isoformat()
            }
        }, sender_id)
```

### 3. Batch Message Sending

For high-volume scenarios:

```python
# app/chat/service.py

class BatchMessageService:
    @staticmethod
    async def send_batch(
        conversation_id: str,
        sender: User,
        messages: List[dict]  # [{content, type, ...}]
    ) -> List[Message]:
        """Send multiple messages efficiently."""
        conv = await ChatService.get_conversation(conversation_id, sender)

        # Create all messages
        message_docs = []
        for msg_data in messages:
            message = Message(
                conversation_id=str(conv.id),
                sender_id=str(sender.id),
                content=msg_data["content"],
                type=msg_data.get("type", MessageType.TEXT),
                status=MessageStatus.SENT,
            )
            message_docs.append(message)

        # Bulk insert
        await Message.insert_many(message_docs)

        # Update conversation with last message
        last_msg = message_docs[-1]
        conv.last_message_id = str(last_msg.id)
        conv.last_message_content = last_msg.content[:100]
        conv.last_message_sender_id = str(sender.id)
        conv.last_message_at = last_msg.timestamp
        conv.updated_at = datetime.now(timezone.utc)

        other_user_id = conv.get_other_user_id(str(sender.id))
        conv.increment_unread(other_user_id)
        # Increment by number of messages
        if str(sender.id) == conv.user1_id:
            conv.user2_unread_count += len(message_docs) - 1
        else:
            conv.user1_unread_count += len(message_docs) - 1

        await conv.save()

        return message_docs
```

---

## Media Handling Optimizations

### 1. Use Async S3 Client

Replace synchronous boto3 with aioboto3:

```python
# app/core/storage.py - Updated

import aioboto3
from contextlib import asynccontextmanager

class AsyncStorageService:
    def __init__(self):
        self.session = aioboto3.Session()
        self.bucket = settings.SPACES_BUCKET
        self.cdn_url = settings.SPACES_CDN_URL
        self.project_folder = settings.SPACES_PROJECT_FOLDER

    @asynccontextmanager
    async def get_client(self):
        async with self.session.client(
            "s3",
            endpoint_url=f"https://{settings.SPACES_ENDPOINT}",
            aws_access_key_id=settings.DO_SPACES_KEY,
            aws_secret_access_key=settings.DO_SPACES_SECRET,
        ) as client:
            yield client

    async def upload_file(
        self,
        file: UploadFile,
        folder: str = "uploads",
        filename: Optional[str] = None,
    ) -> str:
        """Upload file asynchronously."""
        if not filename:
            ext = file.filename.split(".")[-1] if file.filename else "jpg"
            filename = f"{uuid.uuid4()}.{ext}"

        key = self._build_key(folder, filename)
        content = await file.read()

        async with self.get_client() as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
                ACL="public-read",
            )

        await file.seek(0)
        return self._fix_url(key)
```

### 2. Implement Image Resizing

Resize images before upload to save bandwidth:

```python
# app/core/image_processor.py

from PIL import Image
import io
from typing import Tuple

class ImageProcessor:
    MAX_DIMENSION = 1920
    THUMBNAIL_SIZE = (200, 200)
    QUALITY = 85

    @staticmethod
    async def process_image(file: UploadFile) -> Tuple[bytes, bytes]:
        """Process image: resize and create thumbnail."""
        content = await file.read()
        await file.seek(0)

        # Open image
        img = Image.open(io.BytesIO(content))

        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Resize if too large
        if max(img.size) > ImageProcessor.MAX_DIMENSION:
            img.thumbnail(
                (ImageProcessor.MAX_DIMENSION, ImageProcessor.MAX_DIMENSION),
                Image.Resampling.LANCZOS
            )

        # Save main image
        main_buffer = io.BytesIO()
        img.save(main_buffer, format='JPEG', quality=ImageProcessor.QUALITY, optimize=True)
        main_bytes = main_buffer.getvalue()

        # Create thumbnail
        thumb = img.copy()
        thumb.thumbnail(ImageProcessor.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        thumb_buffer = io.BytesIO()
        thumb.save(thumb_buffer, format='JPEG', quality=80)
        thumb_bytes = thumb_buffer.getvalue()

        return main_bytes, thumb_bytes

    @staticmethod
    def get_image_dimensions(content: bytes) -> Tuple[int, int]:
        """Get image dimensions."""
        img = Image.open(io.BytesIO(content))
        return img.size
```

### 3. Implement Video Thumbnail Generation

```python
# app/core/video_processor.py

import subprocess
import tempfile
import os

class VideoProcessor:
    @staticmethod
    async def generate_thumbnail(video_content: bytes) -> bytes:
        """Generate thumbnail from video."""
        # Write video to temp file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
            video_file.write(video_content)
            video_path = video_file.name

        # Generate thumbnail using ffmpeg
        thumb_path = video_path + '_thumb.jpg'
        try:
            subprocess.run([
                'ffmpeg', '-i', video_path,
                '-ss', '00:00:01',  # Take frame at 1 second
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                '-y', thumb_path
            ], capture_output=True, check=True)

            with open(thumb_path, 'rb') as f:
                return f.read()
        finally:
            # Cleanup
            os.unlink(video_path)
            if os.path.exists(thumb_path):
                os.unlink(thumb_path)

    @staticmethod
    async def get_video_duration(video_content: bytes) -> int:
        """Get video duration in seconds."""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(video_content)
            video_path = f.name

        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ], capture_output=True, text=True)

            return int(float(result.stdout.strip()))
        finally:
            os.unlink(video_path)
```

### 4. Implement Upload Progress Tracking

For large files, track upload progress via WebSocket:

```python
# app/chat/routes.py

@router.post("/{conversation_id}/messages/video")
async def send_video_message(
    conversation_id: str,
    video: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Send video with progress tracking."""
    # Generate upload ID
    upload_id = str(uuid.uuid4())

    # Notify start
    await manager.send_personal_message({
        "event": "upload_started",
        "data": {
            "upload_id": upload_id,
            "conversation_id": conversation_id,
            "file_name": video.filename,
            "file_size": video.size
        }
    }, str(current_user.id))

    try:
        # Process and upload
        video_url = await storage.upload_message_video(conversation_id, video)

        # Notify complete
        await manager.send_personal_message({
            "event": "upload_complete",
            "data": {"upload_id": upload_id, "url": video_url}
        }, str(current_user.id))

        # Create message...

    except Exception as e:
        await manager.send_personal_message({
            "event": "upload_failed",
            "data": {"upload_id": upload_id, "error": str(e)}
        }, str(current_user.id))
        raise
```

---

## Scalability Considerations

### 1. Database Sharding Strategy

For high-scale deployment, shard MongoDB by conversation:

```javascript
// MongoDB sharding setup
sh.enableSharding("flame_db")

// Shard messages by conversation_id (range-based)
sh.shardCollection("flame_db.messages", { "conversation_id": 1 })

// Shard conversations by user (hashed for even distribution)
sh.shardCollection("flame_db.conversations", { "user1_id": "hashed" })
```

### 2. Read Replicas for Heavy Reads

Configure Motor to use read replicas:

```python
# app/core/database.py

from pymongo import ReadPreference

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        readPreference=ReadPreference.SECONDARY_PREFERRED  # Read from replicas
    )
```

### 3. Connection Pooling

Configure appropriate pool sizes:

```python
# app/core/database.py

db.client = AsyncIOMotorClient(
    settings.MONGODB_URL,
    maxPoolSize=100,
    minPoolSize=10,
    maxIdleTimeMS=30000,
    waitQueueTimeoutMS=5000,
)
```

### 4. Load Balancer Sticky Sessions

For WebSocket connections, use sticky sessions:

```nginx
# nginx.conf
upstream websocket_backend {
    ip_hash;  # Sticky sessions based on IP
    server backend1:8000;
    server backend2:8000;
}

server {
    location /ws {
        proxy_pass http://websocket_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### 5. Auto-Scaling Considerations

```yaml
# Kubernetes HPA example
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: flame-backend
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: flame-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## Push Notifications

### 1. Implement Push Notification Service

```python
# app/core/push_notifications.py

import httpx
from typing import List, Optional
from app.models.device import Device
from app.core.config import settings

class PushNotificationService:
    def __init__(self):
        self.fcm_url = "https://fcm.googleapis.com/v1/projects/{}/messages:send".format(
            settings.FIREBASE_PROJECT_ID
        )

    async def send_to_user(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[dict] = None
    ):
        """Send push notification to all user's devices."""
        devices = await Device.find(Device.user_id == user_id).to_list()

        for device in devices:
            await self._send_fcm(device.token, title, body, data)

    async def _send_fcm(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None
    ):
        """Send via Firebase Cloud Messaging."""
        # Get access token (implement OAuth2 for Firebase)
        access_token = await self._get_fcm_token()

        payload = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body
                },
                "data": data or {}
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    self.fcm_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                )
            except Exception as e:
                # Log error, possibly remove invalid token
                pass

    async def send_new_message_notification(
        self,
        recipient_id: str,
        sender_name: str,
        message_preview: str,
        conversation_id: str
    ):
        """Send notification for new message."""
        # Check if user has notifications enabled and conversation not muted
        # (implement this check)

        await self.send_to_user(
            recipient_id,
            title=sender_name,
            body=message_preview[:100],
            data={
                "type": "new_message",
                "conversation_id": conversation_id
            }
        )

    async def send_new_match_notification(
        self,
        user_id: str,
        match_name: str,
        match_id: str
    ):
        """Send notification for new match."""
        await self.send_to_user(
            user_id,
            title="New Match!",
            body=f"You and {match_name} liked each other!",
            data={
                "type": "new_match",
                "match_id": match_id
            }
        )

push_service = PushNotificationService()
```

### 2. Integrate with Message Sending

```python
# app/chat/service.py

async def send_message(...):
    # ... existing code ...

    # Send push notification if recipient is offline
    other_user_id = conv.get_other_user_id(str(sender.id))
    if not manager.is_user_online(other_user_id):
        # Check mute status
        is_muted = ChatService._is_conversation_muted(conv, other_user_id)
        if not is_muted:
            await push_service.send_new_message_notification(
                recipient_id=other_user_id,
                sender_name=sender.name,
                message_preview=preview_content,
                conversation_id=str(conv.id)
            )
```

---

## Performance Monitoring

### 1. Add Request Timing Middleware

```python
# app/core/middleware.py

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        response = await call_next(request)

        process_time = time.perf_counter() - start_time

        # Log slow requests
        if process_time > 1.0:  # > 1 second
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {process_time:.2f}s"
            )

        # Add timing header
        response.headers["X-Process-Time"] = str(process_time)

        return response
```

### 2. Add Database Query Monitoring

```python
# app/core/monitoring.py

import time
from functools import wraps
from typing import Callable
import logging

logger = logging.getLogger("db_queries")

def monitor_db_query(operation: str):
    """Decorator to monitor database query performance."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start

                # Log slow queries
                if elapsed > 0.1:  # > 100ms
                    logger.warning(
                        f"Slow query: {operation} took {elapsed:.3f}s"
                    )

                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(
                    f"Query failed: {operation} after {elapsed:.3f}s - {e}"
                )
                raise
        return wrapper
    return decorator

# Usage:
@monitor_db_query("get_conversations")
async def get_conversations(user: User, limit: int, offset: int):
    # ... implementation
```

### 3. Add Metrics Collection

```python
# app/core/metrics.py

from prometheus_client import Counter, Histogram, Gauge
import time

# Define metrics
MESSAGES_SENT = Counter(
    'messages_sent_total',
    'Total messages sent',
    ['type']  # text, image, video, etc.
)

MESSAGE_LATENCY = Histogram(
    'message_send_latency_seconds',
    'Time to send a message',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

ACTIVE_WEBSOCKETS = Gauge(
    'active_websocket_connections',
    'Number of active WebSocket connections'
)

ONLINE_USERS = Gauge(
    'online_users',
    'Number of online users'
)

# Usage in code:
async def send_message(...):
    with MESSAGE_LATENCY.time():
        message = await ChatService.send_message(...)
    MESSAGES_SENT.labels(type=message.type.value).inc()
```

### 4. Add Health Check Endpoints

```python
# app/main.py

@app.get("/health/detailed")
async def detailed_health():
    """Detailed health check with component status."""
    health = {
        "status": "healthy",
        "components": {}
    }

    # Check MongoDB
    try:
        await db.client.admin.command('ping')
        health["components"]["mongodb"] = {"status": "healthy"}
    except Exception as e:
        health["status"] = "unhealthy"
        health["components"]["mongodb"] = {"status": "unhealthy", "error": str(e)}

    # Check Redis
    try:
        await cache.redis.ping()
        health["components"]["redis"] = {"status": "healthy"}
    except Exception as e:
        health["status"] = "unhealthy"
        health["components"]["redis"] = {"status": "unhealthy", "error": str(e)}

    # WebSocket connections count
    health["components"]["websocket"] = {
        "status": "healthy",
        "active_connections": len(manager.active_connections)
    }

    return health
```

---

## Implementation Priority

### Phase 1: Critical (Immediate Impact)

1. **Fix N+1 query in get_conversations()** - Biggest performance win
2. **Add database indexes** - Essential for query performance
3. **Implement Redis caching** - Reduce database load
4. **Fix in-memory pagination** - Use database-level pagination

### Phase 2: Important (Significant Impact)

5. **Add Redis Pub/Sub for WebSocket** - Enable horizontal scaling
6. **Implement async S3 client** - Remove blocking I/O
7. **Add connection heartbeat** - Detect dead connections
8. **Implement push notifications** - Ensure message delivery

### Phase 3: Optimization (Polish)

9. **Add image resizing** - Save bandwidth
10. **Implement message queuing** - Improve reliability
11. **Add metrics and monitoring** - Visibility
12. **Implement cursor-based pagination** - Better performance for large datasets

### Phase 4: Scale (When Needed)

13. **Database sharding strategy** - For millions of users
14. **Read replicas** - Distribute read load
15. **Auto-scaling configuration** - Handle traffic spikes

---

## Summary

The current implementation is functional but has several opportunities for optimization:

| Area | Current Issue | Recommended Fix | Impact |
|------|--------------|-----------------|--------|
| Database | N+1 queries | Batch fetching, aggregation | High |
| Database | Missing indexes | Add compound indexes | High |
| WebSocket | Single-server only | Redis Pub/Sub | High |
| Caching | None | Redis caching layer | High |
| Storage | Sync client | Async aioboto3 | Medium |
| Pagination | In-memory | Database-level | Medium |
| Monitoring | Minimal | Prometheus metrics | Medium |
| Push | Not implemented | FCM integration | Medium |

Implementing these optimizations in order of priority will significantly improve the chat system's performance, reliability, and scalability.

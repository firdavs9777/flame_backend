# Flame Backend - Optimization Implementation Plan

This document outlines the implemented optimizations and the plan for remaining optimizations.

---

## Implemented Optimizations (Done)

### 1. Fixed N+1 Query Problem in `get_conversations()`
**File:** `app/chat/service.py:14-107`

**Before:** For each conversation, made individual database query to fetch user (N+1 queries)
```python
for conv in conversations:
    other_user = await User.get(other_user_id)  # N queries!
```

**After:** Batch fetch all users in single query
```python
# Collect all user IDs first
other_user_ids = [conv.get_other_user_id(...) for conv in conversations]

# Single batch query
other_users = await User.find({"_id": {"$in": [ObjectId(uid) for uid in other_user_ids]}}).to_list()

# O(1) lookup map
user_map = {str(u.id): u for u in other_users}
```

**Impact:** Reduced from N+1 to 2 queries (50-100x improvement for users with many conversations)

---

### 2. Fixed In-Memory Pagination
**File:** `app/chat/service.py:39-45`

**Before:** Fetched ALL conversations, then sliced in Python
```python
conversations = await Conversation.find(query).to_list()  # Fetch all!
paginated = results[offset:offset + limit]  # Slice in memory
```

**After:** Database-level pagination
```python
total = await Conversation.find(query).count()
conversations = await Conversation.find(query).skip(offset).limit(limit).to_list()
```

**Impact:** Memory usage reduced proportionally to page size, faster response times

---

### 3. Cursor-Based Pagination for Messages
**File:** `app/chat/service.py:121-163`

**Before:** Fetched "before" message first, then filtered by timestamp
```python
before_msg = await Message.get(before)  # Extra query
query["timestamp"] = {"$lt": before_msg.timestamp}
```

**After:** Direct _id comparison (more efficient)
```python
if ObjectId.is_valid(before):
    query["_id"] = {"$lt": ObjectId(before)}  # No extra query needed
```

**Impact:** Eliminated 1 query per pagination request, better index utilization

---

### 4. Enhanced `mark_messages_read()` with Bulk Operations
**File:** `app/chat/service.py:416-468`

**Before:** Updated messages one by one or with multiple conditions

**After:**
- Single bulk update operation
- Support for "mark all" functionality
- Added `read_at` timestamp tracking
- Returns count of updated messages

```python
result = await Message.find(query).update_many({
    "$set": {
        "status": MessageStatus.READ.value,
        "read_at": datetime.now(timezone.utc)
    }
})
```

---

### 5. Added Database Indexes
**File:** `app/models/message.py:88-100`

Added optimized compound indexes:
```python
indexes = [
    "conversation_id",
    "sender_id",
    [("conversation_id", 1), ("timestamp", -1)],  # Time-sorted messages
    [("conversation_id", 1), ("is_deleted", 1)],  # Filter deleted
    [("conversation_id", 1), ("_id", -1)],        # Cursor pagination
    [("conversation_id", 1), ("status", 1)],      # Unread queries
    [("conversation_id", 1), ("sender_id", 1), ("status", 1)],  # Mark read
]
```

---

### 6. Redis Caching Infrastructure
**File:** `app/core/cache.py` (NEW)

Created comprehensive caching layer:
- `CacheService` - Core Redis operations
- `OnlineStatusTracker` - Track user online status
- `ConversationCache` - Cache conversation lists
- `UserCache` - Cache user profiles
- `RateLimiter` - Redis-based rate limiting
- `@cached` decorator - Function result caching

**File:** `app/main.py` - Integrated cache lifecycle

---

### 7. Enhanced Health Check
**File:** `app/main.py:116-146`

Added `/health/detailed` endpoint showing component status for MongoDB and Redis.

---

## Remaining Optimizations (To Do)

### Phase 1: High Priority (Next Sprint)

#### 1.1 Integrate Cache into Services
**Effort:** Medium | **Impact:** High

Integrate the caching infrastructure into actual services:

```python
# app/chat/service.py
from app.core.cache import cache, conversation_cache, user_cache

class ChatService:
    @staticmethod
    async def get_conversations_cached(user: User, limit: int, offset: int):
        """Get conversations with caching."""
        user_id = str(user.id)

        # Check cache for first page
        if offset == 0 and limit == 20:
            cached = await conversation_cache.get_conversation_list(user_id)
            if cached:
                return cached["results"], cached["total"]

        # Fetch from DB
        results, total = await ChatService.get_conversations(user, limit, offset)

        # Cache first page
        if offset == 0 and limit == 20:
            await conversation_cache.set_conversation_list(user_id, {
                "results": results,
                "total": total
            })

        return results, total
```

**Tasks:**
- [ ] Integrate conversation list caching
- [ ] Integrate user profile caching
- [ ] Add cache invalidation on updates
- [ ] Add cache warming on login

---

#### 1.2 Redis Pub/Sub for WebSocket Scaling
**Effort:** High | **Impact:** High

Enable horizontal scaling of WebSocket servers:

```python
# app/core/pubsub.py
class RedisPubSub:
    async def publish(self, channel: str, message: dict):
        """Publish to all servers."""
        await self.redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str):
        """Subscribe to channel."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

# app/chat/websocket.py
class ConnectionManager:
    async def broadcast_to_conversation(self, message, conversation_id, exclude_user=None):
        # Local broadcast
        await self._local_broadcast(message, conversation_id, exclude_user)

        # Redis broadcast for other servers
        await pubsub.publish("chat_broadcast", {
            "type": "conversation",
            "conversation_id": conversation_id,
            "message": message,
            "exclude_user": exclude_user
        })
```

**Tasks:**
- [ ] Create `app/core/pubsub.py`
- [ ] Update ConnectionManager to use Redis pub/sub
- [ ] Add server identification for deduplication
- [ ] Test with multiple server instances

---

#### 1.3 WebSocket Connection Heartbeat
**Effort:** Low | **Impact:** Medium

Detect and clean up stale connections:

```python
# app/chat/websocket.py
class ConnectionManager:
    def __init__(self):
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_timeout = 90   # seconds
        self.last_heartbeat: Dict[str, datetime] = {}

    async def start_heartbeat_checker(self):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await self._cleanup_stale_connections()

    async def _cleanup_stale_connections(self):
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=self.heartbeat_timeout)

        stale = [uid for uid, last in self.last_heartbeat.items()
                 if now - last > timeout]

        for user_id in stale:
            await self._disconnect_user(user_id)
```

**Tasks:**
- [ ] Add heartbeat tracking
- [ ] Implement cleanup coroutine
- [ ] Start checker on app startup
- [ ] Update online status on heartbeat

---

### Phase 2: Medium Priority (Following Sprint)

#### 2.1 Push Notification Service
**Effort:** High | **Impact:** High

Implement FCM push notifications for offline users:

```python
# app/core/push_notifications.py
class PushService:
    async def send_message_notification(
        self,
        recipient_id: str,
        sender_name: str,
        message_preview: str,
        conversation_id: str
    ):
        # Check if user is offline
        if await online_tracker.is_online(recipient_id):
            return  # User will get WebSocket message

        # Check notification settings and mute status
        # Send via FCM
        await self._send_fcm(recipient_id, ...)
```

**Tasks:**
- [ ] Create `app/core/push_notifications.py`
- [ ] Integrate with chat message sending
- [ ] Add notification preferences check
- [ ] Add mute status check
- [ ] Handle FCM token refresh

---

#### 2.2 Message Queue for Offline Delivery
**Effort:** Medium | **Impact:** Medium

Queue messages for offline users:

```python
# app/core/message_queue.py
class OfflineMessageQueue:
    async def queue_message(self, user_id: str, message: dict):
        key = f"offline_queue:{user_id}"
        await self.redis.rpush(key, json.dumps(message))
        await self.redis.expire(key, 86400 * 7)  # 7 days

    async def get_pending_messages(self, user_id: str) -> List[dict]:
        key = f"offline_queue:{user_id}"
        messages = await self.redis.lrange(key, 0, -1)
        if messages:
            await self.redis.delete(key)
        return [json.loads(m) for m in messages]
```

**Tasks:**
- [ ] Create message queue service
- [ ] Queue important messages when user offline
- [ ] Deliver queued messages on connection
- [ ] Add queue size limits

---

#### 2.3 Async S3 Client
**Effort:** Medium | **Impact:** Medium

Replace synchronous boto3 with aioboto3:

```python
# app/core/storage.py
import aioboto3

class AsyncStorageService:
    async def upload_file(self, file: UploadFile, folder: str) -> str:
        async with self.session.client("s3", ...) as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=file.content_type,
                ACL="public-read"
            )
```

**Tasks:**
- [ ] Add aioboto3 to requirements
- [ ] Create async storage service
- [ ] Migrate existing code
- [ ] Add connection pooling

---

#### 2.4 Image Resizing Before Upload
**Effort:** Medium | **Impact:** Medium

Resize images to save bandwidth:

```python
# app/core/image_processor.py
from PIL import Image

class ImageProcessor:
    MAX_DIMENSION = 1920
    THUMBNAIL_SIZE = (200, 200)

    @staticmethod
    async def process_image(content: bytes) -> Tuple[bytes, bytes]:
        """Returns (resized_image, thumbnail)."""
        img = Image.open(io.BytesIO(content))

        # Resize if too large
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

        # Create thumbnail
        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE)

        return img_bytes, thumb_bytes
```

**Tasks:**
- [ ] Add Pillow to requirements
- [ ] Create image processor
- [ ] Integrate with photo uploads
- [ ] Add WebP conversion option

---

### Phase 3: Low Priority (Future)

#### 3.1 Rate Limiting Middleware
Implement the configured rate limits using Redis.

#### 3.2 Request Timing Middleware
Add performance monitoring middleware.

#### 3.3 Prometheus Metrics
Add metrics collection for monitoring.

#### 3.4 Database Connection Pooling
Optimize Motor connection pool settings.

#### 3.5 Read Replicas for Heavy Reads
Configure MongoDB secondary reads for discovery queries.

---

## Performance Testing Checklist

After implementing optimizations, verify with:

### Load Testing
```bash
# Install locust
pip install locust

# Run load test
locust -f tests/load_test.py --host=http://localhost:8000
```

### Database Query Analysis
```javascript
// Enable MongoDB profiler
db.setProfilingLevel(1, { slowms: 100 })

// View slow queries
db.system.profile.find().sort({ ts: -1 }).limit(10)
```

### Cache Hit Rates
```python
# Add to cache service
async def get_stats(self):
    info = await self.redis.info("stats")
    return {
        "hits": info.get("keyspace_hits", 0),
        "misses": info.get("keyspace_misses", 0),
        "hit_rate": hits / (hits + misses) if (hits + misses) > 0 else 0
    }
```

---

## Quick Reference: What Changed

| File | Change |
|------|--------|
| `app/chat/service.py` | N+1 fix, pagination fix, cursor pagination, bulk mark read |
| `app/models/message.py` | Added indexes, added `read_at` field |
| `app/core/cache.py` | **NEW** - Redis caching infrastructure |
| `app/main.py` | Cache lifecycle, detailed health check |

---

## Estimated Impact

| Optimization | Query Reduction | Latency Improvement |
|--------------|-----------------|---------------------|
| N+1 Fix | 50-100x fewer queries | 80-95% faster |
| DB Pagination | Proportional to data size | 50-70% faster |
| Cursor Pagination | 1 query per request | 20-30% faster |
| Bulk Mark Read | N to 1 query | 60-80% faster |
| Indexes | Depends on data size | 10-50% faster |
| Caching | Varies | 90-99% faster (cache hits) |

---

## Next Steps

1. **Immediate:** Run the application and verify no regressions
2. **This Week:** Integrate cache into conversation/user fetching
3. **Next Sprint:** Implement Redis pub/sub for WebSocket scaling
4. **Following Sprint:** Add push notifications and message queue

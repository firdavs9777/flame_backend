# Flame Backend - Complete Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [Project Architecture](#project-architecture)
3. [Core Components](#core-components)
4. [Data Models](#data-models)
5. [Authentication System](#authentication-system)
6. [Chat System](#chat-system)
7. [Community Features](#community-features)
8. [WebSocket Implementation](#websocket-implementation)
9. [Storage System](#storage-system)
10. [API Endpoints Reference](#api-endpoints-reference)
11. [Configuration & Environment](#configuration--environment)
12. [Running the Application](#running-the-application)

---

## Overview

Flame is a dating application backend built with **FastAPI** and **MongoDB** (using Beanie ODM). It provides:

- User authentication (email/password + social auth: Google, Apple, Facebook)
- Real-time messaging with WebSocket support
- User discovery and matching (swipe-based)
- Media uploads (photos, videos, voice messages, stickers)
- Push notification support
- Blocking and reporting functionality

### Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.109.0 |
| Database | MongoDB with Motor (async) + Beanie ODM |
| Authentication | JWT (python-jose) + bcrypt |
| WebSocket | FastAPI WebSocket + websockets 12.0 |
| Storage | DigitalOcean Spaces (S3-compatible) via boto3 |
| Email | Mailgun |
| Caching | Redis (configured but not fully implemented) |
| HTTP Client | httpx (async) |

---

## Project Architecture

```
flame_backend/
├── app/
│   ├── main.py                 # Application entry point
│   ├── core/                   # Core utilities and configuration
│   │   ├── config.py           # Settings and environment variables
│   │   ├── database.py         # MongoDB connection management
│   │   ├── security.py         # JWT, password hashing utilities
│   │   ├── dependencies.py     # FastAPI dependency injection
│   │   ├── exceptions.py       # Custom exception classes
│   │   ├── storage.py          # DigitalOcean Spaces file uploads
│   │   ├── email.py            # Mailgun email service
│   │   └── location.py         # OpenStreetMap reverse geocoding
│   ├── models/                 # Beanie document models
│   │   ├── user.py             # User model with preferences
│   │   ├── conversation.py     # Chat conversation model
│   │   ├── message.py          # Message model (text, media, stickers)
│   │   ├── match.py            # Match model
│   │   ├── swipe.py            # Swipe model (like/pass/super_like)
│   │   ├── block.py            # Block model
│   │   ├── report.py           # Report model
│   │   ├── device.py           # Device model for push notifications
│   │   ├── refresh_token.py    # Refresh token tracking
│   │   └── sticker.py          # Sticker pack models
│   ├── auth/                   # Authentication module
│   │   ├── routes.py           # Auth API endpoints
│   │   ├── service.py          # Auth business logic
│   │   ├── social.py           # Social auth (Google, Apple, Facebook)
│   │   └── schemas.py          # Pydantic request/response schemas
│   ├── chat/                   # Chat module
│   │   ├── routes.py           # Chat API endpoints
│   │   ├── service.py          # Chat business logic
│   │   ├── websocket.py        # WebSocket connection manager
│   │   └── schemas.py          # Chat schemas
│   └── community/              # Community/Discovery module
│       ├── routes.py           # Community API endpoints
│       ├── service.py          # Discovery, matching, blocking logic
│       └── schemas.py          # Community schemas
├── requirements.txt
└── .env                        # Environment variables (not in repo)
```

---

## Core Components

### 1. Configuration (`app/core/config.py`)

The `Settings` class uses Pydantic Settings to manage configuration:

```python
class Settings(BaseSettings):
    # App Configuration
    APP_NAME: str = "Flame API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/v1"

    # Database
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "flame_db"

    # JWT Configuration
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Storage (DigitalOcean Spaces)
    DO_SPACES_KEY: str = ""
    DO_SPACES_SECRET: str = ""
    SPACES_BUCKET: str = "my-projects-media"
    SPACES_CDN_URL: str = "https://..."

    # Email (Mailgun)
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""

    # Social Auth
    GOOGLE_CLIENT_ID: str = ""
    APPLE_CLIENT_ID: str = ""
    FACEBOOK_APP_ID: str = ""
```

**Key Points:**
- Loads from `.env` file automatically
- JWT secret is auto-generated if not provided (WARNING: should be set explicitly in production)
- Rate limiting values defined but not yet implemented in middleware

### 2. Database (`app/core/database.py`)

Uses Motor (async MongoDB driver) with Beanie ODM:

```python
class Database:
    client: AsyncIOMotorClient = None

db = Database()

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(
        database=db.client[settings.MONGODB_DB_NAME],
        document_models=[
            User, Match, Swipe, Conversation, Message,
            Block, Report, Device, RefreshToken,
            Sticker, StickerPack, UserStickerPack, RecentSticker,
        ],
    )

async def close_mongo_connection():
    if db.client:
        db.client.close()
```

**Lifecycle:** Connected via FastAPI's lifespan context manager in `main.py`.

### 3. Security (`app/core/security.py`)

Provides authentication utilities:

| Function | Purpose |
|----------|---------|
| `verify_password(plain, hashed)` | Verify password against bcrypt hash |
| `get_password_hash(password)` | Hash password with bcrypt |
| `create_access_token(subject, expires_delta)` | Create JWT access token (default: 60 min) |
| `create_refresh_token(subject)` | Create JWT refresh token (default: 30 days) |
| `decode_token(token)` | Decode and validate JWT |
| `generate_verification_code()` | Generate 6-digit email verification code |
| `generate_password_reset_token()` | Generate secure URL-safe token |

**JWT Payload Structure:**
```json
{
  "sub": "user_id",
  "exp": "expiration_timestamp",
  "type": "access" | "refresh",
  "iat": "issued_at_timestamp",
  "jti": "unique_token_id"  // Only for refresh tokens
}
```

### 4. Dependencies (`app/core/dependencies.py`)

FastAPI dependency injection for authentication:

```python
# Requires valid access token, returns User
async def get_current_user(credentials: HTTPAuthorizationCredentials) -> User

# Optional auth - returns User or None
async def get_current_user_optional(authorization: str) -> Optional[User]

# Requires valid token AND verified email
async def get_verified_user(current_user: User) -> User
```

**Usage in routes:**
```python
@router.get("/protected")
async def protected_route(current_user: User = Depends(get_current_user)):
    return {"user_id": str(current_user.id)}
```

### 5. Exceptions (`app/core/exceptions.py`)

Custom exception hierarchy extending `HTTPException`:

| Exception | Status Code | Code |
|-----------|-------------|------|
| `ValidationError` | 400 | VALIDATION_ERROR |
| `InvalidCredentialsError` | 401 | INVALID_CREDENTIALS |
| `UnauthorizedError` | 401 | UNAUTHORIZED |
| `TokenExpiredError` | 401 | TOKEN_EXPIRED |
| `ForbiddenError` | 403 | FORBIDDEN |
| `NotFoundError` | 404 | NOT_FOUND |
| `EmailExistsError` | 409 | EMAIL_EXISTS |
| `AlreadyMatchedError` | 409 | ALREADY_MATCHED |
| `RateLimitedError` | 429 | RATE_LIMITED |
| `ServerError` | 500 | SERVER_ERROR |

**Response Format:**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": {...}
  }
}
```

---

## Data Models

### User Model (`app/models/user.py`)

The central model with embedded documents:

```python
class User(Document):
    # Core fields
    email: EmailStr                    # Unique, indexed
    password_hash: str
    name: str                          # 2-50 chars
    age: int                           # 18-100
    gender: Gender                     # male, female, non_binary, other
    looking_for: Gender
    bio: Optional[str]                 # Max 500 chars
    interests: List[str]               # 1-10 items
    photos: List[Photo]                # Embedded documents
    location: Optional[Location]       # Embedded with coordinates

    # Status
    is_online: bool = False
    is_verified: bool = False
    last_active: datetime

    # Embedded settings
    preferences: UserPreferences       # min_age, max_age, max_distance
    notification_settings: NotificationSettings
    settings: UserSettings

    # Auth
    verification_code: Optional[str]   # 6-digit code
    verification_code_expires: Optional[datetime]
    password_reset_token: Optional[str]
    password_reset_token_expires: Optional[datetime]

    # Premium features
    super_likes_remaining: int = 3
    super_likes_reset_at: Optional[datetime]
    is_premium: bool = False
    premium_expires_at: Optional[datetime]

    # Social auth IDs
    google_id: Optional[str]
    apple_id: Optional[str]
    facebook_id: Optional[str]
```

**Embedded Models:**
```python
class Photo(BaseModel):
    id: str
    url: str
    is_primary: bool = False
    order: int = 0

class Location(BaseModel):
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    coordinates: Optional[Coordinates]

class Coordinates(BaseModel):
    latitude: float
    longitude: float

class UserPreferences(BaseModel):
    min_age: int = 18
    max_age: int = 50
    max_distance: int = 50  # miles
    show_distance: bool = True
    show_online_status: bool = True
```

**Indexes:**
- `email` (unique)
- `google_id`, `apple_id`, `facebook_id`
- Compound: `(location.coordinates.latitude, location.coordinates.longitude)`

### Conversation Model (`app/models/conversation.py`)

```python
class Conversation(Document):
    match_id: str                      # Links to Match, unique indexed
    user1_id: str                      # Indexed
    user2_id: str                      # Indexed

    # Last message cache for quick access
    last_message_id: Optional[str]
    last_message_content: Optional[str]
    last_message_sender_id: Optional[str]
    last_message_at: Optional[datetime]

    # Per-user unread counts
    user1_unread_count: int = 0
    user2_unread_count: int = 0

    # Pinned messages (up to 5)
    pinned_messages: List[PinnedMessage] = []

    # Mute settings per user
    user1_muted_until: Optional[datetime]
    user2_muted_until: Optional[datetime]
```

**Helper Methods:**
- `get_other_user_id(user_id)` - Get the other participant
- `get_unread_count(user_id)` - Get unread count for specific user
- `increment_unread(for_user_id)` - Increment unread for user
- `reset_unread(for_user_id)` - Reset unread count

### Message Model (`app/models/message.py`)

```python
class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    GIF = "gif"
    STICKER = "sticker"
    FILE = "file"

class MessageStatus(str, Enum):
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"

class Message(Document):
    conversation_id: str               # Indexed
    sender_id: str                     # Indexed
    content: str
    type: MessageType = TEXT
    status: MessageStatus = SENT
    timestamp: datetime

    # Media URLs (optional based on type)
    image_url: Optional[str]
    video_url: Optional[str]
    audio_url: Optional[str]
    file_url: Optional[str]
    sticker_id: Optional[str]

    # Media metadata
    media_info: Optional[MediaInfo]    # duration, dimensions, thumbnail, etc.

    # Reply feature
    reply_to: Optional[ReplyInfo]

    # Reactions (emoji reactions)
    reactions: List[Reaction] = []

    # Edit/Delete tracking
    is_edited: bool = False
    edited_at: Optional[datetime]
    is_deleted: bool = False
    deleted_at: Optional[datetime]
```

**Indexes:**
- `conversation_id`
- `sender_id`
- Compound: `(conversation_id, timestamp)` - For paginated message retrieval
- Compound: `(conversation_id, is_deleted)` - For filtering deleted messages

### Match Model (`app/models/match.py`)

```python
class Match(Document):
    user1_id: str                      # Indexed
    user2_id: str                      # Indexed
    matched_at: datetime
    is_active: bool = True             # False when unmatched

    # Track if each user has seen the match
    user1_seen: bool = False
    user2_seen: bool = False
```

### Swipe Model (`app/models/swipe.py`)

```python
class SwipeType(str, Enum):
    LIKE = "like"
    PASS = "pass"
    SUPER_LIKE = "super_like"

class Swipe(Document):
    swiper_id: str                     # Who swiped
    swiped_id: str                     # Who was swiped on
    swipe_type: SwipeType
    created_at: datetime
```

**Index:** Compound `(swiper_id, swiped_id)` for quick duplicate checks

### Block & Report Models

```python
class Block(Document):
    blocker_id: str
    blocked_id: str
    created_at: datetime

class Report(Document):
    reporter_id: str
    reported_id: str
    reason: ReportReason               # inappropriate_content, fake_profile, etc.
    details: Optional[str]
    status: ReportStatus = PENDING     # pending, reviewed, resolved, dismissed
```

### Sticker Models (`app/models/sticker.py`)

```python
class Sticker(Document):
    pack_id: str                       # Which pack this belongs to
    emoji: str                         # For emoji search
    image_url: str
    thumbnail_url: str
    order: int = 0

class StickerPack(Document):
    name: str
    description: str
    thumbnail_url: str
    author: str = "Flame"
    is_official: bool = True
    is_premium: bool = False
    sticker_count: int = 0

class UserStickerPack(Document):
    user_id: str
    pack_id: str
    added_at: datetime

class RecentSticker(Document):
    user_id: str
    sticker_id: str
    used_at: datetime
```

---

## Authentication System

### Registration Flow (`app/auth/service.py`)

```
1. Client sends: email, password, name, age, gender, looking_for, bio, interests, photos[], latitude, longitude

2. Server validates:
   - Email not already registered
   - Password strength (8+ chars, uppercase, lowercase, number)
   - Age >= 18
   - At least 1 photo

3. Server processes:
   - Upload photos to DigitalOcean Spaces (handles base64 or URLs)
   - Reverse geocode coordinates to get city/state/country
   - Hash password with bcrypt
   - Generate 6-digit verification code
   - Create User document

4. Server sends verification email via Mailgun

5. Server returns:
   - User object
   - Access token (60 min)
   - Refresh token (30 days)
```

### Login Flow

```
1. Client sends: email, password, device_token (optional)

2. Server validates:
   - Email exists
   - Password matches hash

3. Server updates:
   - is_online = true
   - last_active = now
   - Register device token if provided

4. Server returns:
   - User object
   - Access token
   - Refresh token
```

### Token Refresh Flow

```
1. Client sends: refresh_token

2. Server validates:
   - Token is valid JWT
   - Token type is "refresh"
   - Token not revoked in database

3. Server actions:
   - Revoke old refresh token
   - Create new access + refresh tokens

4. Server returns:
   - New access_token
   - New refresh_token
```

### Email Verification Flow

```
1. User receives 6-digit code via email

2. Client sends: email, code

3. Server validates:
   - Code matches stored code
   - Code not expired (15 min limit)

4. Server updates:
   - is_verified = true
   - Clear verification_code
```

### Password Reset Flow

```
1. Client sends: email (forgot-password endpoint)

2. Server actions:
   - Generate secure token
   - Store token with 1-hour expiration
   - Send email with reset link

3. Client sends: token, new_password (reset-password endpoint)

4. Server validates:
   - Token exists and not expired
   - Password meets requirements

5. Server actions:
   - Update password hash
   - Clear reset token
   - Revoke all refresh tokens (security)
```

### Social Authentication (Google/Apple/Facebook)

Each social provider follows similar flow:

```
1. Client authenticates with provider, gets token
2. Client sends token to server
3. Server verifies token with provider's API
4. Server finds or creates user:
   - If social ID exists -> return existing user
   - If email exists -> link social account
   - Otherwise -> create new user (needs profile completion)
5. Server returns tokens
```

**Note:** Social auth users have empty `password_hash` and may need to complete their profile (age, gender, photos, etc.).

---

## Chat System

### ChatService (`app/chat/service.py`)

#### Getting Conversations

```python
async def get_conversations(user: User, limit: int, offset: int):
    # 1. Query conversations where user is participant
    # 2. For each conversation:
    #    - Fetch other user's profile
    #    - Get last message info (cached in conversation)
    #    - Get unread count for current user
    #    - Check mute status
    # 3. Return paginated results sorted by updated_at
```

#### Sending Messages

```python
async def send_message(
    conversation_id: str,
    sender: User,
    content: str,
    message_type: MessageType,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    # ... other media URLs
    reply_to_id: Optional[str] = None,
):
    # 1. Verify user has access to conversation
    # 2. If replying, build ReplyInfo with original message preview
    # 3. Create Message document
    # 4. Update conversation:
    #    - Cache last message info
    #    - Increment unread count for recipient
    #    - Update updated_at
    # 5. Return message
```

#### Message Types Support

| Type | Content | Additional Fields |
|------|---------|-------------------|
| TEXT | Message text | - |
| IMAGE | Image URL | `image_url` |
| VIDEO | Video URL | `video_url`, `media_info.thumbnail_url`, `duration`, `width`, `height` |
| AUDIO | Audio URL | `audio_url`, `media_info.duration` |
| VOICE | Voice URL | `audio_url`, `media_info.duration` |
| GIF | GIF URL | `image_url` |
| STICKER | Sticker URL | `sticker_id` |
| FILE | File URL | `file_url`, `media_info.file_size`, `mime_type` |

#### Reactions

```python
async def add_reaction(message_id: str, user: User, emoji: str):
    # Remove any existing reaction from this user
    # Add new reaction with emoji, user_id, timestamp

async def remove_reaction(message_id: str, user: User):
    # Filter out reactions from this user
```

#### Pinned Messages

```python
async def pin_message(conversation_id: str, message_id: str, user: User):
    # Verify message is in conversation
    # Check not already pinned
    # Limit: max 5 pinned messages
    # Add to pinned_messages array

async def unpin_message(conversation_id: str, message_id: str, user: User):
    # Remove from pinned_messages array
```

#### Edit/Delete Messages

```python
async def edit_message(message_id: str, user: User, new_content: str):
    # Only sender can edit
    # Only TEXT messages
    # 48-hour time limit
    # Mark is_edited = true

async def delete_message(message_id: str, user: User, for_everyone: bool):
    # Soft delete: is_deleted = true
    # Content replaced with "This message was deleted"
```

#### Muting Conversations

```python
async def mute_conversation(conversation_id: str, user: User, duration_hours: Optional[int]):
    # duration_hours = None -> Mute forever (100 years)
    # duration_hours = 0 -> Unmute
    # duration_hours = N -> Mute for N hours
```

### StickerService (`app/chat/service.py`)

- `get_sticker_packs()` - List all available packs
- `get_sticker_pack(pack_id)` - Get pack with all stickers
- `get_user_sticker_packs(user)` - User's saved packs
- `add_sticker_pack(user, pack_id)` - Save pack to user's collection
- `remove_sticker_pack(user, pack_id)` - Remove from collection
- `get_recent_stickers(user, limit)` - Recently used stickers
- `record_sticker_use(user, sticker_id)` - Track usage (keeps last 50)

---

## WebSocket Implementation

### Connection Manager (`app/chat/websocket.py`)

```python
class ConnectionManager:
    active_connections: Dict[str, WebSocket]      # user_id -> WebSocket
    user_conversations: Dict[str, Set[str]]       # user_id -> conversation_ids

    async def connect(websocket, user_id):
        # Accept WebSocket
        # Store connection
        # Update user online status
        # Subscribe to user's conversations

    def disconnect(user_id):
        # Remove from active_connections
        # Remove conversation subscriptions

    async def send_personal_message(message, user_id):
        # Send to specific user if connected

    async def broadcast_to_conversation(message, conversation_id, exclude_user):
        # Send to all participants except sender
```

### WebSocket Events

**Client -> Server:**

| Event | Payload | Description |
|-------|---------|-------------|
| `ping` | - | Keep-alive |
| `typing` | `{conversation_id}` | User started typing |
| `stop_typing` | `{conversation_id}` | User stopped typing |
| `message_read` | `{conversation_id, message_ids[]}` | Mark messages as read |
| `recording_voice` | `{conversation_id}` | User is recording voice |

**Server -> Client:**

| Event | Payload | Description |
|-------|---------|-------------|
| `pong` | - | Response to ping |
| `user_typing` | `{conversation_id, user_id}` | Other user is typing |
| `user_stop_typing` | `{conversation_id, user_id}` | Other user stopped typing |
| `new_message` | `{conversation_id, message}` | New message received |
| `message_edited` | `{conversation_id, message}` | Message was edited |
| `message_deleted` | `{conversation_id, message_id}` | Message was deleted |
| `reaction_added` | `{conversation_id, message_id, emoji, user_id}` | Reaction added |
| `reaction_removed` | `{conversation_id, message_id, user_id}` | Reaction removed |
| `message_pinned` | `{conversation_id, message_id, pinned_by}` | Message pinned |
| `message_unpinned` | `{conversation_id, message_id}` | Message unpinned |
| `message_status` | `{conversation_id, message_ids[], status}` | Messages read |
| `new_match` | `{match, user, conversation_id}` | New match created |
| `user_online` | `{user_id}` | User came online |
| `user_offline` | `{user_id}` | User went offline |
| `user_recording_voice` | `{conversation_id, user_id}` | User recording voice |

### Connection Endpoint

```
ws://host/ws?token=<access_token>

1. Token validated from query parameter
2. User retrieved from token
3. Connection accepted
4. User marked online
5. Subscribed to all user's conversations
6. Listening loop for events
7. On disconnect: mark offline, cleanup
```

---

## Community Features

### Discovery (`app/community/service.py`)

```python
async def get_potential_matches(user: User, limit: int, offset: int):
    # 1. Get already-swiped user IDs
    # 2. Get blocked users (both directions)
    # 3. Query users matching preferences:
    #    - Gender matches looking_for (both ways)
    #    - Age within preferences
    #    - Discovery enabled
    # 4. Filter out swiped + blocked
    # 5. Calculate distance using Haversine formula
    # 6. Filter by max_distance preference
    # 7. Calculate common interests
    # 8. Return paginated results
```

**Haversine Formula:** Calculates great-circle distance between two points on Earth (in miles).

### Swipe System

```python
async def like(swiper: User, swiped_id: str) -> Tuple[bool, Optional[Match]]:
    # 1. Validate not already swiped
    # 2. Create Swipe(type=LIKE)
    # 3. Check for mutual like:
    #    - Query: swiped_id liked/super_liked swiper?
    # 4. If mutual:
    #    - Create Match
    #    - Create Conversation
    #    - Return (True, Match)
    # 5. Else: Return (False, None)

async def super_like(swiper: User, swiped_id: str):
    # Same as like but:
    # - Check super_likes_remaining > 0
    # - Reset daily if past reset time
    # - Decrement counter
    # - Return remaining count

async def undo_last_swipe(user: User):
    # Premium only
    # Get last swipe
    # If was match, deactivate match + delete conversation
    # Delete swipe record
```

### Match Management

```python
async def get_matches(user: User, limit, offset, new_only):
    # Query active matches
    # For each:
    #   - Get other user profile
    #   - Check if new (unseen)
    #   - Get last message from conversation
    # Filter by new_only if requested

async def unmatch(user: User, match_id: str):
    # Verify user is part of match
    # Set is_active = false
    # Delete conversation
```

### Blocking

```python
async def block_user(blocker: User, blocked_id: str):
    # Create Block record
    # Deactivate any existing match

async def unblock_user(blocker: User, blocked_id: str):
    # Delete Block record

async def get_blocked_users(user: User):
    # Return list of blocked users with names
```

---

## Storage System

### StorageService (`app/core/storage.py`)

Handles file uploads to DigitalOcean Spaces (S3-compatible):

```python
class StorageService:
    # Uploads organized under project folder:
    # {bucket}/{project_folder}/{type}/{timestamp}-{filename}

    # Available methods:
    async def upload_file(file: UploadFile, folder: str) -> str
    async def upload_bytes(data: bytes, filename: str, folder: str) -> str
    async def delete_file(url: str) -> bool

    # Specialized uploads:
    async def upload_user_photo(user_id: str, file: UploadFile) -> str
    async def upload_message_image(conversation_id: str, file: UploadFile) -> str
    async def upload_message_video(conversation_id: str, file: UploadFile) -> str
    async def upload_message_audio(conversation_id: str, file: UploadFile) -> str
    async def upload_voice_message(conversation_id: str, file: UploadFile) -> str
    async def upload_message_file(conversation_id: str, file: UploadFile) -> str
    async def upload_video_thumbnail(conversation_id: str, file: UploadFile) -> str
    async def upload_sticker(pack_id: str, file: UploadFile) -> str

    # Base64 support (for profile photos from mobile):
    async def upload_base64_image(base64_string: str, user_id: str) -> str
```

**Folder Structure:**
```
{bucket}/{project}/
├── photos/              # User profile photos
├── messages/
│   ├── images/         # Message images
│   ├── videos/         # Message videos
│   ├── audio/          # Audio files
│   ├── voice/          # Voice messages
│   ├── files/          # File attachments
│   └── thumbnails/     # Video thumbnails
└── stickers/           # Sticker images
```

---

## API Endpoints Reference

### Authentication (`/v1/auth`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/register` | No | Create new account |
| POST | `/login` | No | Login with email/password |
| POST | `/refresh` | No | Refresh access token |
| POST | `/logout` | Yes | Logout current user |
| POST | `/forgot-password` | No | Request password reset |
| POST | `/reset-password` | No | Reset password with token |
| POST | `/verify-email` | No | Verify email with code |
| POST | `/resend-verification` | Yes | Resend verification code |
| POST | `/change-password` | Yes | Change current password |
| POST | `/google` | No | Google OAuth login |
| POST | `/apple` | No | Apple OAuth login |
| POST | `/facebook` | No | Facebook OAuth login |

### User Profile (`/v1/users`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/me` | Yes | Get current user profile |
| PATCH | `/me` | Yes | Update profile fields |
| PATCH | `/me/location` | Yes | Update location |
| PATCH | `/me/preferences` | Yes | Update preferences |
| PATCH | `/me/notifications` | Yes | Update notification settings |
| POST | `/me/photos` | Yes | Upload new photo |
| DELETE | `/me/photos/{photo_id}` | Yes | Delete a photo |
| PATCH | `/me/photos/reorder` | Yes | Reorder photos |
| GET | `/{user_id}` | Yes | Get user's public profile |
| DELETE | `/me` | Yes | Delete account |

### Discovery (`/v1`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/discover` | Yes | Get potential matches |

### Swipes (`/v1/swipes`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/like` | Yes | Like a user |
| POST | `/pass` | Yes | Pass on a user |
| POST | `/super-like` | Yes | Super like a user |
| POST | `/undo` | Yes* | Undo last swipe (premium) |

### Matches (`/v1/matches`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | Yes | Get all matches |
| DELETE | `/{match_id}` | Yes | Unmatch |

### Conversations (`/v1/conversations`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | Yes | Get all conversations |
| GET | `/{id}/messages` | Yes | Get messages (paginated) |
| POST | `/{id}/messages` | Yes | Send text message |
| POST | `/{id}/messages/image` | Yes | Send image |
| POST | `/{id}/messages/video` | Yes | Send video |
| POST | `/{id}/messages/audio` | Yes | Send audio |
| POST | `/{id}/messages/voice` | Yes | Send voice message |
| POST | `/{id}/messages/sticker` | Yes | Send sticker |
| PATCH | `/{id}/messages/{msg_id}` | Yes | Edit message |
| DELETE | `/{id}/messages/{msg_id}` | Yes | Delete message |
| POST | `/{id}/messages/{msg_id}/reactions` | Yes | Add reaction |
| DELETE | `/{id}/messages/{msg_id}/reactions` | Yes | Remove reaction |
| POST | `/{id}/pin` | Yes | Pin message |
| DELETE | `/{id}/pin/{msg_id}` | Yes | Unpin message |
| POST | `/{id}/mute` | Yes | Mute conversation |
| POST | `/{id}/read` | Yes | Mark messages read |

### Stickers (`/v1/stickers`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/packs` | Yes | Get all sticker packs |
| GET | `/packs/{pack_id}` | Yes | Get pack with stickers |
| GET | `/my-packs` | Yes | Get user's saved packs |
| POST | `/my-packs/{pack_id}` | Yes | Add pack to collection |
| DELETE | `/my-packs/{pack_id}` | Yes | Remove pack |
| GET | `/recent` | Yes | Get recent stickers |

### Reports & Blocks (`/v1`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/reports` | Yes | Report a user |
| POST | `/blocks` | Yes | Block a user |
| DELETE | `/blocks/{user_id}` | Yes | Unblock a user |
| GET | `/blocks` | Yes | Get blocked users |

### Devices (`/v1/devices`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Yes | Register device for push notifications |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `ws://host/ws?token=<access_token>` | Real-time messaging |

### Utility

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |

---

## Configuration & Environment

### Required Environment Variables

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=flame_db

# JWT (IMPORTANT: Set this explicitly in production!)
JWT_SECRET_KEY=your-secure-secret-key

# DigitalOcean Spaces
DO_SPACES_KEY=your-spaces-key
DO_SPACES_SECRET=your-spaces-secret
SPACES_BUCKET=your-bucket-name
SPACES_REGION=sfo3
SPACES_ENDPOINT=sfo3.digitaloceanspaces.com
SPACES_CDN_URL=https://your-bucket.sfo3.cdn.digitaloceanspaces.com

# Mailgun
MAILGUN_API_KEY=your-mailgun-key
MAILGUN_DOMAIN=your-domain.com
FROM_EMAIL=noreply@your-domain.com

# Social Auth (as needed)
GOOGLE_CLIENT_ID=your-google-client-id
APPLE_CLIENT_ID=your-apple-client-id
FACEBOOK_APP_ID=your-facebook-app-id
```

### Optional Settings

```bash
# App
DEBUG=false
APP_NAME=Flame API
FRONTEND_URL=https://your-frontend.com

# JWT Expiration
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Rate Limiting (not yet implemented)
RATE_LIMIT_LOGIN=5
RATE_LIMIT_REGISTER=3
RATE_LIMIT_API=100

# Redis (configured but not used)
REDIS_URL=redis://localhost:6379
```

---

## Running the Application

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with required variables

# Run with uvicorn (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# Run with gunicorn + uvicorn workers
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

# Or with uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Documentation

Once running, access:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## Summary

This Flame backend provides a complete dating app API with:

1. **Robust Authentication** - Email/password with JWT, social auth, email verification
2. **Real-time Messaging** - WebSocket with typing indicators, read receipts, reactions
3. **Rich Media Support** - Photos, videos, voice messages, stickers
4. **Discovery System** - Location-based matching with preferences
5. **Social Features** - Matching, blocking, reporting
6. **Scalable Architecture** - Async MongoDB, CDN-backed storage

The codebase follows FastAPI best practices with clear separation of concerns between routes, services, and models.

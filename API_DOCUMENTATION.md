# Flame API - Complete Endpoint Documentation

## Base URL
```
Development: http://localhost:8000/v1
Production: https://api.flame.app/v1
```

## Headers
```
Authorization: Bearer <access_token>  (for protected routes)
Content-Type: application/json
```

---

# Authentication Endpoints

## 1. Register
Creates a new user account and sends verification code to email.

```http
POST /v1/auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "name": "John Doe",
  "age": 25,
  "gender": "male",
  "looking_for": "female",
  "bio": "Looking for something meaningful",
  "interests": ["Music", "Travel", "Food", "Photography"],
  "photos": ["https://example.com/photo1.jpg"]
}
```

**Validation:**
- `email`: Required, valid email, unique
- `password`: Required, min 8 chars, must have uppercase, lowercase, number
- `name`: Required, 2-50 characters
- `age`: Required, 18-100
- `gender`: Required, one of: `male`, `female`, `non_binary`, `other`
- `looking_for`: Required, one of: `male`, `female`, `non_binary`, `other`
- `bio`: Optional, max 500 characters
- `interests`: Required, 1-10 items
- `photos`: Required, 1-6 URLs

**Response (201):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "usr_abc123",
      "email": "user@example.com",
      "name": "John Doe",
      "age": 25,
      "gender": "male",
      "looking_for": "female",
      "bio": "Looking for something meaningful",
      "interests": ["Music", "Travel", "Food", "Photography"],
      "photos": ["https://cdn.example.com/photo1.jpg"],
      "location": null,
      "is_online": true,
      "is_verified": false,
      "last_active": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-15T10:30:00Z",
      "preferences": {
        "min_age": 18,
        "max_age": 50,
        "max_distance": 50
      }
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
      "expires_in": 3600
    }
  }
}
```

---

## 2. Login
Authenticates user and returns tokens.

```http
POST /v1/auth/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "device_token": "fcm_device_token"
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "user": { ... },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
      "expires_in": 3600
    }
  }
}
```

**Error (401):**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid email or password"
  }
}
```

---

## 3. Verify Email
Verify email with 6-digit code.

```http
POST /v1/auth/verify-email
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Email successfully verified"
}
```

---

## 4. Resend Verification Code
Sends a new verification code to email.

```http
POST /v1/auth/resend-verification
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "Verification code sent to your email"
}
```

---

## 5. Forgot Password
Sends password reset code to email.

```http
POST /v1/auth/forgot-password
```

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Password reset code sent to your email"
}
```

---

## 6. Reset Password
Reset password using 6-digit code.

```http
POST /v1/auth/reset-password
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "password": "NewSecurePass123",
  "password_confirmation": "NewSecurePass123"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Password successfully reset"
}
```

---

## 7. Refresh Token
Get new access token using refresh token.

```http
POST /v1/auth/refresh
```

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 3600
  }
}
```

---

## 8. Logout
Logout and invalidate session.

```http
POST /v1/auth/logout
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "Successfully logged out"
}
```

---

## 9. Change Password
Change password for authenticated user.

```http
POST /v1/auth/change-password
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "current_password": "OldPassword123",
  "new_password": "NewPassword123",
  "new_password_confirmation": "NewPassword123"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Password successfully changed"
}
```

---

## 10. Google Sign In

```http
POST /v1/auth/google
```

**Request Body:**
```json
{
  "id_token": "google_id_token",
  "device_token": "fcm_device_token"
}
```

**Response:** Same as login response.

---

## 11. Apple Sign In

```http
POST /v1/auth/apple
```

**Request Body:**
```json
{
  "id_token": "apple_id_token",
  "authorization_code": "apple_auth_code",
  "device_token": "fcm_device_token"
}
```

**Response:** Same as login response.

---

## 12. Facebook Sign In

```http
POST /v1/auth/facebook
```

**Request Body:**
```json
{
  "access_token": "facebook_access_token",
  "device_token": "fcm_device_token"
}
```

**Response:** Same as login response.

---

# User Profile Endpoints

## 13. Get Current User Profile

```http
GET /v1/users/me
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "usr_abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "age": 25,
    "gender": "male",
    "looking_for": "female",
    "bio": "Looking for something meaningful",
    "interests": ["Music", "Travel"],
    "photos": [
      {
        "id": "photo_1",
        "url": "https://cdn.example.com/photo1.jpg",
        "is_primary": true,
        "order": 0
      }
    ],
    "location": {
      "city": "New York",
      "state": "NY",
      "country": "USA",
      "coordinates": {
        "latitude": 40.7128,
        "longitude": -74.0060
      }
    },
    "is_online": true,
    "is_verified": true,
    "last_active": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-01T00:00:00Z",
    "preferences": {
      "min_age": 18,
      "max_age": 35,
      "max_distance": 50,
      "show_distance": true,
      "show_online_status": true
    },
    "settings": {
      "notifications_enabled": true,
      "discovery_enabled": true,
      "dark_mode": false
    }
  }
}
```

---

## 14. Update Profile

```http
PATCH /v1/users/me
Authorization: Bearer <access_token>
```

**Request Body (partial update):**
```json
{
  "name": "John Updated",
  "bio": "Updated bio",
  "interests": ["Music", "Sports"],
  "looking_for": "female"
}
```

**Response (200):**
```json
{
  "success": true,
  "data": { ... }
}
```

---

## 15. Update Location

```http
PATCH /v1/users/me/location
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "latitude": 40.7128,
  "longitude": -74.0060
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "location": {
      "city": "New York",
      "state": "NY",
      "country": "USA",
      "coordinates": {
        "latitude": 40.7128,
        "longitude": -74.0060
      }
    }
  }
}
```

---

## 16. Update Preferences

```http
PATCH /v1/users/me/preferences
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "min_age": 20,
  "max_age": 35,
  "max_distance": 25,
  "show_distance": true,
  "show_online_status": false
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "preferences": {
      "min_age": 20,
      "max_age": 35,
      "max_distance": 25,
      "show_distance": true,
      "show_online_status": false
    }
  }
}
```

---

## 17. Update Notification Settings

```http
PATCH /v1/users/me/notifications
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "new_matches": true,
  "new_messages": true,
  "super_likes": true,
  "promotions": false
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "notifications": {
      "new_matches": true,
      "new_messages": true,
      "super_likes": true,
      "promotions": false
    }
  }
}
```

---

## 18. Upload Photo

```http
POST /v1/users/me/photos
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Request Body:**
```
photo: <binary file>
is_primary: false
```

**Response (201):**
```json
{
  "success": true,
  "data": {
    "id": "photo_123",
    "url": "https://cdn.example.com/photo_123.jpg",
    "is_primary": false,
    "order": 2
  }
}
```

---

## 19. Delete Photo

```http
DELETE /v1/users/me/photos/{photo_id}
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "Photo deleted successfully"
}
```

---

## 20. Reorder Photos

```http
PATCH /v1/users/me/photos/reorder
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "photo_ids": ["photo_2", "photo_1", "photo_3"]
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "photos": [
      {"id": "photo_2", "order": 0, "is_primary": true},
      {"id": "photo_1", "order": 1, "is_primary": false},
      {"id": "photo_3", "order": 2, "is_primary": false}
    ]
  }
}
```

---

## 21. Get User by ID

```http
GET /v1/users/{user_id}
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "usr_xyz789",
    "name": "Jane Doe",
    "age": 24,
    "gender": "female",
    "bio": "Adventure seeker",
    "interests": ["Travel", "Hiking"],
    "photos": ["https://cdn.example.com/photo1.jpg"],
    "location": "Brooklyn, NY",
    "distance": 5.2,
    "is_online": false,
    "last_active": "2024-01-15T09:00:00Z"
  }
}
```

---

## 22. Delete Account

```http
DELETE /v1/users/me
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "password": "currentPassword123",
  "reason": "Found someone"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Account successfully deleted"
}
```

---

# Discovery Endpoints

## 23. Get Potential Matches

```http
GET /v1/discover?limit=10&offset=0
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `limit`: Number of profiles (default: 10, max: 50)
- `offset`: Pagination offset

**Response (200):**
```json
{
  "success": true,
  "data": {
    "users": [
      {
        "id": "usr_xyz789",
        "name": "Jane",
        "age": 24,
        "gender": "female",
        "bio": "Adventure seeker",
        "interests": ["Travel", "Hiking", "Photography"],
        "photos": ["https://cdn.example.com/photo1.jpg"],
        "location": "Brooklyn, NY",
        "distance": 5.2,
        "is_online": true,
        "last_active": "2024-01-15T10:00:00Z",
        "common_interests": ["Travel", "Photography"]
      }
    ],
    "pagination": {
      "total": 150,
      "limit": 10,
      "offset": 0,
      "has_more": true
    }
  }
}
```

---

# Swipe Endpoints

## 24. Like User (Swipe Right)

```http
POST /v1/swipes/like
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "user_id": "usr_xyz789"
}
```

**Response - No Match (200):**
```json
{
  "success": true,
  "data": {
    "liked": true,
    "is_match": false
  }
}
```

**Response - Match! (200):**
```json
{
  "success": true,
  "data": {
    "liked": true,
    "is_match": true,
    "match": {
      "id": "match_abc123",
      "user": {
        "id": "usr_xyz789",
        "name": "Jane",
        "photos": ["https://cdn.example.com/photo1.jpg"]
      },
      "matched_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

---

## 25. Pass User (Swipe Left)

```http
POST /v1/swipes/pass
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "user_id": "usr_xyz789"
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "passed": true
  }
}
```

---

## 26. Super Like User

```http
POST /v1/swipes/super-like
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "user_id": "usr_xyz789"
}
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "super_liked": true,
    "is_match": false,
    "remaining_super_likes": 2
  }
}
```

---

## 27. Undo Last Swipe

```http
POST /v1/swipes/undo
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "undone": true,
    "user": {
      "id": "usr_xyz789",
      "name": "Jane"
    }
  }
}
```

---

# Match Endpoints

## 28. Get All Matches

```http
GET /v1/matches?limit=20&offset=0&new_only=false
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `limit`: Number of matches (default: 20, max: 50)
- `offset`: Pagination offset
- `new_only`: Filter only new matches (boolean)

**Response (200):**
```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "id": "match_abc123",
        "user": {
          "id": "usr_xyz789",
          "name": "Jane",
          "age": 24,
          "photos": ["https://cdn.example.com/photo1.jpg"],
          "is_online": true,
          "last_active": "2024-01-15T10:00:00Z"
        },
        "matched_at": "2024-01-15T08:00:00Z",
        "is_new": true,
        "last_message": null
      }
    ],
    "pagination": {
      "total": 25,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  }
}
```

---

## 29. Unmatch User

```http
DELETE /v1/matches/{match_id}
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "Successfully unmatched"
}
```

---

# Chat Endpoints

## 30. Get Conversations

```http
GET /v1/conversations?limit=20&offset=0
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "conversations": [
      {
        "id": "conv_abc123",
        "match_id": "match_abc123",
        "other_user": {
          "id": "usr_xyz789",
          "name": "Jane",
          "photos": ["https://cdn.example.com/photo1.jpg"],
          "is_online": true
        },
        "last_message": {
          "id": "msg_123",
          "content": "Hey! How are you?",
          "sender_id": "usr_xyz789",
          "timestamp": "2024-01-15T10:30:00Z",
          "status": "delivered"
        },
        "unread_count": 2,
        "updated_at": "2024-01-15T10:30:00Z"
      }
    ],
    "pagination": {
      "total": 10,
      "limit": 20,
      "offset": 0,
      "has_more": false
    }
  }
}
```

---

## 31. Get Messages in Conversation

```http
GET /v1/conversations/{conversation_id}/messages?limit=50&before=msg_id
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `limit`: Number of messages (default: 50, max: 100)
- `before`: Message ID for pagination (get older messages)

**Response (200):**
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "msg_123",
        "sender_id": "usr_xyz789",
        "content": "Hey! How are you?",
        "type": "text",
        "timestamp": "2024-01-15T10:30:00Z",
        "status": "read"
      },
      {
        "id": "msg_124",
        "sender_id": "usr_abc123",
        "content": "I'm great! Nice to match!",
        "type": "text",
        "timestamp": "2024-01-15T10:31:00Z",
        "status": "delivered"
      }
    ],
    "has_more": true
  }
}
```

---

## 32. Send Message

```http
POST /v1/conversations/{conversation_id}/messages
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "content": "Hey! Nice to meet you!",
  "type": "text"
}
```

**Response (201):**
```json
{
  "success": true,
  "data": {
    "id": "msg_125",
    "sender_id": "usr_abc123",
    "content": "Hey! Nice to meet you!",
    "type": "text",
    "timestamp": "2024-01-15T10:35:00Z",
    "status": "sent"
  }
}
```

---

## 33. Send Image Message

```http
POST /v1/conversations/{conversation_id}/messages/image
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Request Body:**
```
image: <binary file>
```

**Response (201):**
```json
{
  "success": true,
  "data": {
    "id": "msg_126",
    "sender_id": "usr_abc123",
    "content": "https://cdn.example.com/messages/msg_126.jpg",
    "type": "image",
    "timestamp": "2024-01-15T10:36:00Z",
    "status": "sent"
  }
}
```

---

## 34. Mark Messages as Read

```http
POST /v1/conversations/{conversation_id}/read
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "message_ids": ["msg_123", "msg_124"]
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Messages marked as read"
}
```

---

# Reporting & Blocking Endpoints

## 35. Report User

```http
POST /v1/reports
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "user_id": "usr_xyz789",
  "reason": "inappropriate_content",
  "details": "User sent inappropriate messages"
}
```

**Reason Options:**
- `inappropriate_content`
- `fake_profile`
- `harassment`
- `spam`
- `underage`
- `other`

**Response (201):**
```json
{
  "success": true,
  "message": "Report submitted successfully"
}
```

---

## 36. Block User

```http
POST /v1/blocks
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "user_id": "usr_xyz789"
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "User blocked successfully"
}
```

---

## 37. Unblock User

```http
DELETE /v1/blocks/{user_id}
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "User unblocked successfully"
}
```

---

## 38. Get Blocked Users

```http
GET /v1/blocks
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "data": {
    "blocked_users": [
      {
        "id": "usr_xyz789",
        "name": "Jane",
        "blocked_at": "2024-01-15T10:00:00Z"
      }
    ]
  }
}
```

---

# Device Registration

## 39. Register Device

```http
POST /v1/devices
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "token": "fcm_device_token",
  "platform": "ios"
}
```

**Platform Options:** `ios`, `android`

**Response (201):**
```json
{
  "success": true,
  "message": "Device registered successfully"
}
```

---

# WebSocket

## Connection

```
wss://api.flame.app/ws?token=<access_token>
```

## Client to Server Events

### Ping
```json
{"event": "ping"}
```

### Typing
```json
{
  "event": "typing",
  "data": {"conversation_id": "conv_abc123"}
}
```

### Stop Typing
```json
{
  "event": "stop_typing",
  "data": {"conversation_id": "conv_abc123"}
}
```

### Message Read
```json
{
  "event": "message_read",
  "data": {
    "conversation_id": "conv_abc123",
    "message_ids": ["msg_123", "msg_124"]
  }
}
```

## Server to Client Events

### Pong
```json
{"event": "pong"}
```

### New Message
```json
{
  "event": "new_message",
  "data": {
    "conversation_id": "conv_abc123",
    "message": {
      "id": "msg_127",
      "sender_id": "usr_xyz789",
      "content": "Hello!",
      "type": "text",
      "timestamp": "2024-01-15T10:40:00Z"
    }
  }
}
```

### New Match
```json
{
  "event": "new_match",
  "data": {
    "match_id": "match_xyz789",
    "user": {
      "id": "usr_xyz789",
      "name": "Jane",
      "photos": ["https://cdn.example.com/photo1.jpg"]
    }
  }
}
```

### User Typing
```json
{
  "event": "user_typing",
  "data": {
    "conversation_id": "conv_abc123",
    "user_id": "usr_xyz789"
  }
}
```

### User Stop Typing
```json
{
  "event": "user_stop_typing",
  "data": {
    "conversation_id": "conv_abc123",
    "user_id": "usr_xyz789"
  }
}
```

### Message Status
```json
{
  "event": "message_status",
  "data": {
    "conversation_id": "conv_abc123",
    "message_ids": ["msg_123"],
    "status": "read"
  }
}
```

### User Online
```json
{
  "event": "user_online",
  "data": {"user_id": "usr_xyz789"}
}
```

### User Offline
```json
{
  "event": "user_offline",
  "data": {"user_id": "usr_xyz789"}
}
```

---

# Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password |
| `UNAUTHORIZED` | 401 | Missing or invalid token |
| `TOKEN_EXPIRED` | 401 | Access token has expired |
| `FORBIDDEN` | 403 | Action not allowed |
| `NOT_FOUND` | 404 | Resource not found |
| `EMAIL_EXISTS` | 409 | Email already registered |
| `ALREADY_MATCHED` | 409 | Already matched with user |
| `RATE_LIMITED` | 429 | Too many requests |
| `SERVER_ERROR` | 500 | Internal server error |

---

# Data Types

## Gender
```typescript
type Gender = 'male' | 'female' | 'non_binary' | 'other';
```

## Message Type
```typescript
type MessageType = 'text' | 'image' | 'gif';
```

## Message Status
```typescript
type MessageStatus = 'sending' | 'sent' | 'delivered' | 'read' | 'failed';
```

## Report Reason
```typescript
type ReportReason = 'inappropriate_content' | 'fake_profile' | 'harassment' | 'spam' | 'underage' | 'other';
```

## Platform
```typescript
type Platform = 'ios' | 'android';
```

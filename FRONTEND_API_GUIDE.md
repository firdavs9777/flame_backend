# Flame API - Frontend Developer Guide

## Base URL
```
Development: http://localhost:8000/v1
Production: https://flame.banatalk.com/v1
```

## Headers
```
Authorization: Bearer <access_token>  (for protected routes)
Content-Type: application/json
```

---

# Authentication

## 1. Register New User

**Location is required** - user must grant location permission before registration.

```http
POST /v1/auth/register
Content-Type: application/json
```

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "name": "John Doe",
  "age": 25,
  "gender": "male",
  "looking_for": "female",
  "bio": "Looking for something meaningful",
  "interests": ["Music", "Travel", "Food"],
  "photos": ["https://example.com/photo1.jpg"],
  "latitude": 37.7749,
  "longitude": -122.4194
}
```

**Validation Rules:**
| Field | Rules |
|-------|-------|
| `email` | Valid email, unique |
| `password` | Min 8 chars, 1 uppercase, 1 lowercase, 1 number |
| `name` | 2-50 characters |
| `age` | 18-100 |
| `gender` | `male`, `female`, `non_binary`, `other` |
| `looking_for` | `male`, `female`, `non_binary`, `other` |
| `bio` | Optional, max 500 chars |
| `interests` | 1-10 items |
| `photos` | 1-6 URLs |
| `latitude` | -90 to 90 (required) |
| `longitude` | -180 to 180 (required) |

**Response (201):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "696c6e271c766eb895ab556d",
      "email": "user@example.com",
      "name": "John Doe",
      "age": 25,
      "gender": "male",
      "looking_for": "female",
      "bio": "Looking for something meaningful",
      "interests": ["Music", "Travel", "Food"],
      "photos": ["https://my-projects-media.sfo3.cdn.digitaloceanspaces.com/flame_backend/photos/1737225600000-user123-abc.jpg"],
      "location": {
        "city": "San Francisco",
        "state": "California",
        "country": "United States",
        "coordinates": {
          "latitude": 37.7749,
          "longitude": -122.4194
        }
      },
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

> **Note:** A 6-digit verification code is sent to the user's email.

---

## 2. Verify Email

```http
POST /v1/auth/verify-email
Content-Type: application/json
```

**Request:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email successfully verified"
}
```

> Code expires in **15 minutes**

---

## 3. Resend Verification Code

```http
POST /v1/auth/resend-verification
Authorization: Bearer <access_token>
```

---

## 4. Login

```http
POST /v1/auth/login
Content-Type: application/json
```

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "device_token": "fcm_token_for_push_notifications"
}
```

**Response:** Same as register response.

---

## 5. Refresh Token

```http
POST /v1/auth/refresh
Content-Type: application/json
```

**Request:**
```json
{
  "refresh_token": "your_refresh_token"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "new_access_token",
    "refresh_token": "new_refresh_token",
    "expires_in": 3600
  }
}
```

---

## 6. Logout

```http
POST /v1/auth/logout
Authorization: Bearer <access_token>
```

---

## 7. Forgot Password

```http
POST /v1/auth/forgot-password
Content-Type: application/json
```

**Request:**
```json
{
  "email": "user@example.com"
}
```

> Sends a 6-digit reset code to email.

---

## 8. Reset Password

```http
POST /v1/auth/reset-password
Content-Type: application/json
```

**Request:**
```json
{
  "token": "123456",
  "password": "NewSecurePass123",
  "password_confirmation": "NewSecurePass123"
}
```

---

## 9. Change Password (Authenticated)

```http
POST /v1/auth/change-password
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "current_password": "OldPass123",
  "new_password": "NewPass123",
  "new_password_confirmation": "NewPass123"
}
```

---

## Social Authentication

### Google Sign-In
```http
POST /v1/auth/google
Content-Type: application/json

{
  "id_token": "google_id_token_from_sdk",
  "device_token": "fcm_token"
}
```

### Apple Sign-In
```http
POST /v1/auth/apple
Content-Type: application/json

{
  "id_token": "apple_id_token",
  "authorization_code": "apple_auth_code",
  "device_token": "fcm_token"
}
```

### Facebook Sign-In
```http
POST /v1/auth/facebook
Content-Type: application/json

{
  "access_token": "facebook_access_token",
  "device_token": "fcm_token"
}
```

---

# User Profile

## Get Current User

```http
GET /v1/users/me
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "696c6e271c766eb895ab556d",
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
      "city": "San Francisco",
      "state": "California",
      "country": "United States",
      "coordinates": {
        "latitude": 37.7749,
        "longitude": -122.4194
      }
    },
    "is_online": true,
    "is_verified": true,
    "last_active": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T10:30:00Z",
    "preferences": {
      "min_age": 18,
      "max_age": 50,
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

## Update Profile

```http
PATCH /v1/users/me
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request (all fields optional):**
```json
{
  "name": "John Updated",
  "age": 26,
  "bio": "New bio here",
  "interests": ["Music", "Sports", "Travel"]
}
```

---

## Update Location

```http
PATCH /v1/users/me/location
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "latitude": 40.7128,
  "longitude": -74.0060
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "location": {
      "city": "New York",
      "state": "New York",
      "country": "United States",
      "coordinates": {
        "latitude": 40.7128,
        "longitude": -74.0060
      }
    }
  }
}
```

---

## Update Preferences

```http
PATCH /v1/users/me/preferences
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "min_age": 21,
  "max_age": 35,
  "max_distance": 25,
  "show_distance": true,
  "show_online_status": true
}
```

---

## Update Notification Settings

```http
PATCH /v1/users/me/notifications
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "new_matches": true,
  "new_messages": true,
  "super_likes": true,
  "promotions": false
}
```

---

# Photo Management

## Upload Photo

```http
POST /v1/users/me/photos
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Form Data:**
- `photo`: File (image/jpeg, image/png, image/webp)
- `is_primary`: boolean (optional)

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "photo_2_1705312200",
    "url": "https://my-projects-media.sfo3.cdn.digitaloceanspaces.com/flame_backend/photos/1737225600000-user123-abc.jpg",
    "is_primary": false,
    "order": 1
  }
}
```

---

## Delete Photo

```http
DELETE /v1/users/me/photos/{photo_id}
Authorization: Bearer <access_token>
```

> Must have at least 1 photo remaining.

---

## Reorder Photos

```http
PATCH /v1/users/me/photos/reorder
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "photo_ids": ["photo_2", "photo_1", "photo_3"]
}
```

> First photo becomes primary.

---

# Discovery

## Get Potential Matches

```http
GET /v1/discover?limit=10&offset=0
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Param | Default | Max | Description |
|-------|---------|-----|-------------|
| `limit` | 10 | 50 | Number of profiles to return |
| `offset` | 0 | - | Pagination offset |

**Response:**
```json
{
  "success": true,
  "data": {
    "users": [
      {
        "id": "user_xyz",
        "name": "Jane",
        "age": 24,
        "gender": "female",
        "bio": "Love hiking and coffee",
        "interests": ["Hiking", "Coffee", "Music"],
        "photos": ["https://cdn.example.com/jane1.jpg"],
        "location": "Brooklyn, NY",
        "distance": 5.2,
        "is_online": true,
        "last_active": "2024-01-15T10:30:00Z",
        "common_interests": ["Music"]
      }
    ],
    "pagination": {
      "total": 45,
      "limit": 10,
      "offset": 0,
      "has_more": true
    }
  }
}
```

> Distance is in miles, calculated from user's location.

---

# Swipes

## Like (Swipe Right)

```http
POST /v1/swipes/like
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "user_id": "target_user_id"
}
```

**Response (No Match):**
```json
{
  "success": true,
  "data": {
    "liked": true,
    "is_match": false
  }
}
```

**Response (Match!):**
```json
{
  "success": true,
  "data": {
    "liked": true,
    "is_match": true,
    "match": {
      "id": "match_123",
      "user": {
        "id": "target_user_id",
        "name": "Jane",
        "photos": ["https://cdn.example.com/jane1.jpg"]
      },
      "matched_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

---

## Pass (Swipe Left)

```http
POST /v1/swipes/pass
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "user_id": "target_user_id"
}
```

---

## Super Like

```http
POST /v1/swipes/super-like
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "user_id": "target_user_id"
}
```

**Response:**
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

> Users get 3 super likes per day (resets at midnight UTC).

---

## Undo Last Swipe (Premium)

```http
POST /v1/swipes/undo
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "undone": true,
    "user": {
      "id": "user_id",
      "name": "Jane"
    }
  }
}
```

> Requires premium subscription.

---

# Matches

## Get All Matches

```http
GET /v1/matches?limit=20&offset=0&new_only=false
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Param | Default | Description |
|-------|---------|-------------|
| `limit` | 20 | Max 50 |
| `offset` | 0 | Pagination |
| `new_only` | false | Only show unviewed matches |

**Response:**
```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "id": "match_123",
        "user": {
          "id": "user_xyz",
          "name": "Jane",
          "age": 24,
          "photos": ["https://cdn.example.com/jane1.jpg"],
          "is_online": true,
          "last_active": "2024-01-15T10:30:00Z"
        },
        "matched_at": "2024-01-15T10:30:00Z",
        "is_new": true,
        "last_message": {
          "id": "msg_abc",
          "content": "Hey! How are you?",
          "sender_id": "user_xyz",
          "timestamp": "2024-01-15T11:00:00Z"
        }
      }
    ],
    "pagination": {
      "total": 12,
      "limit": 20,
      "offset": 0,
      "has_more": false
    }
  }
}
```

---

## Unmatch

```http
DELETE /v1/matches/{match_id}
Authorization: Bearer <access_token>
```

---

# Chat

## Get Conversations

```http
GET /v1/conversations?limit=20&offset=0
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "conversations": [
      {
        "id": "conv_123",
        "match_id": "match_123",
        "other_user": {
          "id": "user_xyz",
          "name": "Jane",
          "photos": ["https://cdn.example.com/jane1.jpg"],
          "is_online": true
        },
        "last_message": {
          "id": "msg_abc",
          "content": "Hey! How are you?",
          "sender_id": "user_xyz",
          "timestamp": "2024-01-15T11:00:00Z"
        },
        "unread_count": 2,
        "updated_at": "2024-01-15T11:00:00Z"
      }
    ]
  }
}
```

---

## Get Messages

```http
GET /v1/conversations/{conversation_id}/messages?limit=50&before={message_id}
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "msg_abc",
        "content": "Hey! How are you?",
        "image_url": null,
        "sender_id": "user_xyz",
        "status": "read",
        "created_at": "2024-01-15T11:00:00Z"
      }
    ],
    "has_more": true
  }
}
```

---

## Send Message

```http
POST /v1/conversations/{conversation_id}/messages
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "content": "Hey! Nice to meet you!"
}
```

---

## Send Image Message

```http
POST /v1/conversations/{conversation_id}/messages/image
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Form Data:**
- `image`: File

---

## Mark Messages as Read

```http
POST /v1/conversations/{conversation_id}/read
Authorization: Bearer <access_token>
```

---

# Block & Report

## Block User

```http
POST /v1/blocks
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "user_id": "user_to_block"
}
```

---

## Unblock User

```http
DELETE /v1/blocks/{user_id}
Authorization: Bearer <access_token>
```

---

## Get Blocked Users

```http
GET /v1/blocks
Authorization: Bearer <access_token>
```

---

## Report User

```http
POST /v1/reports
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "user_id": "user_to_report",
  "reason": "inappropriate_content",
  "details": "Optional additional details"
}
```

**Reason options:**
- `inappropriate_content`
- `fake_profile`
- `harassment`
- `spam`
- `underage`
- `other`

---

# Push Notifications

## Register Device

```http
POST /v1/devices
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "token": "fcm_device_token",
  "platform": "ios"
}
```

**Platform options:** `ios`, `android`

---

# WebSocket (Real-time Chat)

**IMPORTANT:** WebSocket connection is required for real-time messaging.

## Connection URL

```
wss://flame.banatalk.com/ws?token=<access_token>
```

## Complete React Native Implementation

```javascript
// websocket.js
import { useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

class WebSocketService {
  constructor() {
    this.ws = null;
    this.listeners = {};
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  async connect() {
    const token = await AsyncStorage.getItem('access_token');
    if (!token) return;

    this.ws = new WebSocket(`wss://flame.banatalk.com/ws?token=${token}`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.startPing();
    };

    this.ws.onmessage = (event) => {
      const { event: eventName, data } = JSON.parse(event.data);
      this.emit(eventName, data);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.stopPing();
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  startPing() {
    this.pingInterval = setInterval(() => {
      this.send('ping', {});
    }, 30000); // Ping every 30 seconds
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
    }
  }

  send(event, data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    }
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => callback(data));
    }
  }

  disconnect() {
    this.stopPing();
    if (this.ws) {
      this.ws.close();
    }
  }
}

export const wsService = new WebSocketService();
```

## Events to Send (Client → Server)

| Event | Data | Description |
|-------|------|-------------|
| `ping` | `{}` | Keep connection alive |
| `typing` | `{ conversation_id }` | User started typing |
| `stop_typing` | `{ conversation_id }` | User stopped typing |
| `message_read` | `{ conversation_id, message_ids }` | Mark messages as read |

```javascript
// Send typing indicator
wsService.send('typing', { conversation_id: 'conv_123' });

// Send stop typing
wsService.send('stop_typing', { conversation_id: 'conv_123' });

// Mark messages as read
wsService.send('message_read', {
  conversation_id: 'conv_123',
  message_ids: ['msg_1', 'msg_2']
});
```

## Events to Listen (Server → Client)

### 1. `new_message` - New Message Received

```javascript
wsService.on('new_message', (data) => {
  // data structure:
  {
    "conversation_id": "conv_123",
    "message": {
      "id": "msg_abc",
      "sender_id": "user_xyz",
      "content": "Hello!",
      "type": "text",
      "timestamp": "2024-01-15T10:30:00Z",
      "status": "sent"
    }
  }

  // Add message to chat screen
  addMessageToConversation(data.conversation_id, data.message);

  // Show notification if not on chat screen
  if (currentScreen !== 'chat') {
    showPushNotification(data.message);
  }
});
```

### 2. `new_match` - It's a Match!

```javascript
wsService.on('new_match', (data) => {
  // data structure:
  {
    "match": {
      "id": "match_123",
      "user": {
        "id": "user_abc",
        "name": "Jane",
        "photos": ["https://..."]
      },
      "matched_at": "2024-01-15T10:30:00Z"
    },
    "user": {
      "id": "user_abc",
      "name": "Jane",
      "photos": ["https://..."]
    }
  }

  // Show match animation/popup
  showMatchAnimation(data.user);

  // Refresh matches list
  refreshMatches();
});
```

### 3. `user_typing` - User is Typing

```javascript
wsService.on('user_typing', (data) => {
  // data structure:
  {
    "conversation_id": "conv_123",
    "user_id": "user_xyz"
  }

  // Show typing indicator in chat
  showTypingIndicator(data.conversation_id);
});
```

### 4. `user_stop_typing` - User Stopped Typing

```javascript
wsService.on('user_stop_typing', (data) => {
  // data structure:
  {
    "conversation_id": "conv_123",
    "user_id": "user_xyz"
  }

  // Hide typing indicator
  hideTypingIndicator(data.conversation_id);
});
```

### 5. `message_status` - Message Status Updated

```javascript
wsService.on('message_status', (data) => {
  // data structure:
  {
    "conversation_id": "conv_123",
    "message_ids": ["msg_1", "msg_2"],
    "status": "read"
  }

  // Update message status (show read receipts)
  updateMessageStatus(data.message_ids, data.status);
});
```

### 6. `user_online` / `user_offline` - User Status Changed

```javascript
wsService.on('user_online', (data) => {
  // data: { user_id: "..." }
  updateUserOnlineStatus(data.user_id, true);
});

wsService.on('user_offline', (data) => {
  // data: { user_id: "..." }
  updateUserOnlineStatus(data.user_id, false);
});
```

### 7. `pong` - Response to Ping

```javascript
wsService.on('pong', () => {
  // Connection is alive
});
```

## Usage in React Native Screens

### Chat Screen

```javascript
import { useEffect, useState } from 'react';
import { wsService } from './websocket';

function ChatScreen({ conversationId }) {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    // Listen for new messages
    const handleNewMessage = (data) => {
      if (data.conversation_id === conversationId) {
        setMessages(prev => [...prev, data.message]);
      }
    };

    // Listen for typing
    const handleTyping = (data) => {
      if (data.conversation_id === conversationId) {
        setIsTyping(true);
      }
    };

    const handleStopTyping = (data) => {
      if (data.conversation_id === conversationId) {
        setIsTyping(false);
      }
    };

    wsService.on('new_message', handleNewMessage);
    wsService.on('user_typing', handleTyping);
    wsService.on('user_stop_typing', handleStopTyping);

    return () => {
      wsService.off('new_message', handleNewMessage);
      wsService.off('user_typing', handleTyping);
      wsService.off('user_stop_typing', handleStopTyping);
    };
  }, [conversationId]);

  const sendTypingIndicator = () => {
    wsService.send('typing', { conversation_id: conversationId });
  };

  const sendStopTyping = () => {
    wsService.send('stop_typing', { conversation_id: conversationId });
  };

  return (
    // Your chat UI
  );
}
```

### App Root (Connect on Login)

```javascript
import { useEffect } from 'react';
import { wsService } from './websocket';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    if (isLoggedIn) {
      // Connect WebSocket after login
      wsService.connect();

      // Listen for matches globally
      wsService.on('new_match', (data) => {
        showMatchPopup(data);
      });
    }

    return () => {
      wsService.disconnect();
    };
  }, [isLoggedIn]);

  return (
    // Your app navigation
  );
}
```

## Connection Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│                    App Lifecycle                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  User Login                                              │
│      │                                                   │
│      ▼                                                   │
│  ┌──────────────────┐                                   │
│  │ wsService.connect()                                  │
│  └──────────────────┘                                   │
│      │                                                   │
│      ▼                                                   │
│  ┌──────────────────┐    ┌─────────────────────┐        │
│  │  Connected       │───►│ Ping every 30s      │        │
│  └──────────────────┘    └─────────────────────┘        │
│      │                                                   │
│      │ (If disconnected)                                │
│      ▼                                                   │
│  ┌──────────────────┐                                   │
│  │ Auto-reconnect   │ (up to 5 attempts)                │
│  └──────────────────┘                                   │
│      │                                                   │
│      ▼                                                   │
│  User Logout                                             │
│      │                                                   │
│      ▼                                                   │
│  ┌──────────────────┐                                   │
│  │ wsService.disconnect()                               │
│  └──────────────────┘                                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

# Error Handling

## Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `INVALID_CREDENTIALS` | 401 | Wrong email/password |
| `UNAUTHORIZED` | 401 | Missing/invalid token |
| `TOKEN_EXPIRED` | 401 | Token has expired |
| `FORBIDDEN` | 403 | Action not allowed |
| `NOT_FOUND` | 404 | Resource not found |
| `EMAIL_EXISTS` | 409 | Email already registered |
| `RATE_LIMITED` | 429 | Too many requests |
| `SERVER_ERROR` | 500 | Internal server error |

---

# Token Management

| Token | Expiry | Usage |
|-------|--------|-------|
| Access Token | 60 minutes | API requests |
| Refresh Token | 30 days | Get new access token |

## Auto-refresh Logic (React Native)

```javascript
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const api = axios.create({
  baseURL: 'https://flame.banatalk.com/v1',
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = await AsyncStorage.getItem('refresh_token');
        const { data } = await axios.post(
          'https://flame.banatalk.com/v1/auth/refresh',
          { refresh_token: refreshToken }
        );

        await AsyncStorage.setItem('access_token', data.data.access_token);
        await AsyncStorage.setItem('refresh_token', data.data.refresh_token);

        originalRequest.headers.Authorization = `Bearer ${data.data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Redirect to login
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
```

---

# Location Permission Flow

```javascript
import * as Location from 'expo-location';

async function requestLocationAndRegister(userData) {
  // 1. Request permission
  const { status } = await Location.requestForegroundPermissionsAsync();

  if (status !== 'granted') {
    Alert.alert(
      'Location Required',
      'Flame needs your location to find matches near you.'
    );
    return;
  }

  // 2. Get current location
  const location = await Location.getCurrentPositionAsync({});

  // 3. Register with location
  const response = await api.post('/auth/register', {
    ...userData,
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
  });

  return response.data;
}
```

---

# File Upload Limits

| Type | Max Size | Formats |
|------|----------|---------|
| Photos | 10 MB | JPEG, PNG, WebP |
| Max photos per user | 6 | - |

---

# Rate Limits

| Endpoint | Limit |
|----------|-------|
| Login | 5 per 15 minutes |
| Register | 3 per hour |
| General API | 100 per minute |

---

# Swagger Documentation

- Development: http://localhost:8000/docs
- Production: https://flame.banatalk.com/docs

---

# Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

# Contact

For API questions or issues, contact the backend team.

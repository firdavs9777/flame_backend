# Flame API - Frontend Developer Guide

## Base URL
```
Development: http://localhost:8000/v1
Production: https://api.flame.app/v1
```

## Authentication Flow

### 1. Register New User
```http
POST /v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123",
  "name": "John Doe",
  "age": 25,
  "gender": "male",
  "looking_for": "female",
  "bio": "Looking for something meaningful",
  "interests": ["Music", "Travel", "Food"],
  "photos": ["https://example.com/photo1.jpg"]
}
```

**Response:** Returns user object + tokens. A **6-digit verification code** is sent to the user's email.

### 2. Verify Email (6-digit code)
```http
POST /v1/auth/verify-email
Content-Type: application/json

{
  "email": "user@example.com",
  "code": "123456"
}
```

**Important:**
- Code expires in **15 minutes**
- User enters the 6-digit code from their email
- Show a numeric keypad input on mobile

### 3. Resend Verification Code
```http
POST /v1/auth/resend-verification
Authorization: Bearer <access_token>
```

Sends a new 6-digit code to the user's email.

### 4. Login
```http
POST /v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123",
  "device_token": "fcm_token_for_push_notifications"
}
```

### 5. Forgot Password
```http
POST /v1/auth/forgot-password
Content-Type: application/json

{
  "email": "user@example.com"
}
```

Sends a **6-digit reset code** to the email.

### 6. Reset Password (6-digit code)
```http
POST /v1/auth/reset-password
Content-Type: application/json

{
  "email": "user@example.com",
  "code": "123456",
  "password": "NewSecurePass123",
  "password_confirmation": "NewSecurePass123"
}
```

**Important:**
- Code expires in **15 minutes**
- Requires email + code + new password

---

## Verification Code UI Recommendations

### Email Verification Screen
```
┌─────────────────────────────────────┐
│                                     │
│     Verify Your Email 📧            │
│                                     │
│  We sent a 6-digit code to:         │
│  user@example.com                   │
│                                     │
│  ┌───┬───┬───┬───┬───┬───┐         │
│  │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │         │
│  └───┴───┴───┴───┴───┴───┘         │
│                                     │
│  Code expires in 14:32              │
│                                     │
│  [Resend Code]                      │
│                                     │
└─────────────────────────────────────┘
```

### Password Reset Screen
```
┌─────────────────────────────────────┐
│                                     │
│     Reset Password 🔐               │
│                                     │
│  Enter the code sent to:            │
│  user@example.com                   │
│                                     │
│  ┌───┬───┬───┬───┬───┬───┐         │
│  │   │   │   │   │   │   │         │
│  └───┴───┴───┴───┴───┴───┘         │
│                                     │
│  New Password:                      │
│  ┌─────────────────────────┐        │
│  │ ••••••••                │        │
│  └─────────────────────────┘        │
│                                     │
│  Confirm Password:                  │
│  ┌─────────────────────────┐        │
│  │ ••••••••                │        │
│  └─────────────────────────┘        │
│                                     │
│  [Reset Password]                   │
│                                     │
└─────────────────────────────────────┘
```

---

## Token Management

### Access Token
- Expires in **60 minutes**
- Include in all authenticated requests:
```
Authorization: Bearer <access_token>
```

### Refresh Token
- Expires in **30 days**
- Use to get a new access token:
```http
POST /v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "your_refresh_token"
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

## Error Handling

All errors follow this format:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": { "field": "specific error" }
  }
}
```

### Common Error Codes
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `INVALID_CREDENTIALS` | 401 | Wrong email/password |
| `UNAUTHORIZED` | 401 | Missing/invalid token |
| `TOKEN_EXPIRED` | 401 | Token has expired |
| `FORBIDDEN` | 403 | Action not allowed |
| `NOT_FOUND` | 404 | Resource not found |
| `EMAIL_EXISTS` | 409 | Email already registered |

---

## WebSocket Connection

```javascript
const ws = new WebSocket('wss://api.flame.app/ws?token=<access_token>');

// Events to send
ws.send(JSON.stringify({ event: 'ping' }));
ws.send(JSON.stringify({ event: 'typing', data: { conversation_id: 'xxx' } }));
ws.send(JSON.stringify({ event: 'stop_typing', data: { conversation_id: 'xxx' } }));

// Events to listen
ws.onmessage = (event) => {
  const { event: eventName, data } = JSON.parse(event.data);

  switch(eventName) {
    case 'new_message':
      // Handle new message
      break;
    case 'new_match':
      // Show match animation
      break;
    case 'user_typing':
      // Show typing indicator
      break;
  }
};
```

---

## Location Updates

The backend automatically converts GPS coordinates to city/state/country using reverse geocoding. **You only need to send latitude and longitude.**

### Update User Location
```http
PATCH /v1/users/me/location
Authorization: Bearer <access_token>
Content-Type: application/json

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

### Frontend Implementation (React Native)

```javascript
import * as Location from 'expo-location';

async function updateUserLocation() {
  // Request permission
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') {
    console.log('Location permission denied');
    return;
  }

  // Get current position
  const location = await Location.getCurrentPositionAsync({});

  // Send to backend (backend handles reverse geocoding)
  const response = await fetch('/v1/users/me/location', {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      latitude: location.coords.latitude,
      longitude: location.coords.longitude,
    }),
  });

  const data = await response.json();
  // data.data.location.city = "New York"
  // data.data.location.state = "New York"
}
```

### When to Update Location
- On app launch (if permission granted)
- When user opens discovery/swiping screen
- Periodically in background (optional)

### Distance in Discovery
When fetching potential matches, distance is calculated automatically:
```json
{
  "users": [
    {
      "id": "usr_xyz",
      "name": "Jane",
      "distance": 5.2,  // miles from current user
      "location": "Brooklyn, NY"
    }
  ]
}
```

---

## Photo Upload

Photos are uploaded to DigitalOcean Spaces and URLs are returned.

```http
POST /v1/users/me/photos
Content-Type: multipart/form-data

photo: <binary file>
is_primary: false
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "photo_123",
    "url": "https://my-projects-media.sfo3.cdn.digitaloceanspaces.com/users/xxx/photo.jpg",
    "is_primary": false,
    "order": 2
  }
}
```

---

## Password Requirements

- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number

---

## Gender Options

```typescript
type Gender = 'male' | 'female' | 'non_binary' | 'other';
```

---

## Questions?

Contact the backend team or check the Swagger docs at:
- Development: http://localhost:8000/docs
- Production: https://api.flame.app/docs

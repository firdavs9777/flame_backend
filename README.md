# Flame Dating App - Backend API

FastAPI backend for the Flame dating app with MongoDB.

> **Frontend Developers:** See [FRONTEND_API_GUIDE.md](./FRONTEND_API_GUIDE.md) for API integration guide.

## Project Structure

```
app/
├── auth/           # Authentication module (register, login, social auth)
├── community/      # Community module (profiles, discovery, swipes, matches)
├── chat/           # Chat module (conversations, messages, WebSocket)
├── core/           # Core utilities (config, database, security, exceptions)
├── models/         # MongoDB models (User, Match, Message, etc.)
└── main.py         # FastAPI application entry point
```

## Setup

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your MongoDB URL and other settings
```

4. Run the server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication (`/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login
- `POST /refresh` - Refresh tokens
- `POST /logout` - Logout
- `POST /forgot-password` - Request password reset
- `POST /reset-password` - Reset password
- `POST /verify-email` - Verify email
- `POST /resend-verification` - Resend verification email
- `POST /change-password` - Change password
- `POST /google` - Google sign in
- `POST /apple` - Apple sign in
- `POST /facebook` - Facebook sign in

### Users (`/v1/users`)
- `GET /me` - Get current user profile
- `PATCH /me` - Update profile
- `PATCH /me/location` - Update location
- `PATCH /me/preferences` - Update preferences
- `PATCH /me/notifications` - Update notification settings
- `POST /me/photos` - Upload photo
- `DELETE /me/photos/:id` - Delete photo
- `PATCH /me/photos/reorder` - Reorder photos
- `GET /:id` - Get user profile
- `DELETE /me` - Delete account

### Discovery (`/v1/discover`)
- `GET /` - Get potential matches

### Swipes (`/v1/swipes`)
- `POST /like` - Like a user
- `POST /pass` - Pass on a user
- `POST /super-like` - Super like a user
- `POST /undo` - Undo last swipe

### Matches (`/v1/matches`)
- `GET /` - Get all matches
- `DELETE /:id` - Unmatch

### Chat (`/v1/conversations`)
- `GET /` - Get conversations
- `GET /:id/messages` - Get messages
- `POST /:id/messages` - Send message
- `POST /:id/messages/image` - Send image
- `POST /:id/read` - Mark as read

### Reports & Blocks (`/v1`)
- `POST /reports` - Report user
- `POST /blocks` - Block user
- `DELETE /blocks/:id` - Unblock user
- `GET /blocks` - Get blocked users

### Devices (`/v1/devices`)
- `POST /` - Register device for push notifications

### WebSocket
- `WS /ws?token=<access_token>` - Real-time messaging

## WebSocket Events

### Client → Server
- `ping` - Keep alive
- `typing` - User is typing
- `stop_typing` - User stopped typing
- `message_read` - Mark messages as read

### Server → Client
- `pong` - Ping response
- `new_message` - New message received
- `message_status` - Message status update
- `user_typing` - Other user is typing
- `user_online` - User came online
- `user_offline` - User went offline
- `new_match` - New match notification

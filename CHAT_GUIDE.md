# Flame Chat & WebSocket Guide

Complete guide for implementing real-time chat in the Flame dating app.

---

## Table of Contents

1. [WebSocket Connection](#websocket-connection)
2. [Chat REST API Endpoints](#chat-rest-api-endpoints)
3. [Message Types](#message-types)
4. [Media Messages](#media-messages)
5. [Reactions](#reactions)
6. [Reply to Messages](#reply-to-messages)
7. [Edit & Delete Messages](#edit--delete-messages)
8. [Pin Messages](#pin-messages)
9. [Mute Conversations](#mute-conversations)
10. [Stickers](#stickers)
11. [WebSocket Events](#websocket-events)
12. [React Native Implementation](#react-native-implementation)

---

## WebSocket Connection

### Connection URL

```
wss://your-api-domain.com/ws?token=YOUR_ACCESS_TOKEN
```

### Authentication

The WebSocket connection requires a valid JWT access token passed as a query parameter.

```javascript
const wsUrl = `wss://api.yourapp.com/ws?token=${accessToken}`;
```

### Connection Codes

| Code | Reason | Action |
|------|--------|--------|
| 4001 | Unauthorized | Token invalid/expired - refresh and reconnect |
| 1000 | Normal closure | Clean disconnect |
| 1006 | Abnormal closure | Network issue - attempt reconnect |

---

## Chat REST API Endpoints

Base URL: `/api/v1/conversations`

### Get All Conversations

```http
GET /conversations
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "conversations": [
      {
        "id": "conv_123",
        "match_id": "match_456",
        "other_user": {
          "id": "user_789",
          "name": "Sarah",
          "photos": ["https://cdn.../photo1.jpg"],
          "is_online": true
        },
        "last_message": {
          "id": "msg_001",
          "content": "Hey! How are you?",
          "sender_id": "user_789",
          "timestamp": "2024-01-15T10:30:00Z",
          "status": "delivered"
        },
        "unread_count": 2,
        "pinned_messages": [],
        "is_muted": false,
        "muted_until": null,
        "updated_at": "2024-01-15T10:30:00Z"
      }
    ],
    "pagination": { ... }
  }
}
```

### Get Messages

```http
GET /conversations/{conversation_id}/messages?limit=50&before={message_id}
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "msg_001",
        "sender_id": "user_123",
        "content": "Hello!",
        "type": "text",
        "timestamp": "2024-01-15T10:00:00Z",
        "status": "read",
        "is_edited": false,
        "is_deleted": false,
        "reactions": [
          { "emoji": "❤️", "user_id": "user_456", "created_at": "..." }
        ],
        "reply_to": null
      }
    ],
    "has_more": true
  }
}
```

---

## Message Types

The chat supports multiple message types:

| Type | Description |
|------|-------------|
| `text` | Regular text message |
| `image` | Photo message |
| `video` | Video message with thumbnail |
| `audio` | Audio file message |
| `voice` | Voice recording |
| `gif` | GIF animation |
| `sticker` | Sticker from a pack |
| `file` | Generic file attachment |

---

## Media Messages

### Send Image

```http
POST /conversations/{conversation_id}/messages/image
Authorization: Bearer {token}
Content-Type: multipart/form-data

image: (file)
reply_to_id: (optional) message_id to reply to
```

### Send Video

```http
POST /conversations/{conversation_id}/messages/video
Authorization: Bearer {token}
Content-Type: multipart/form-data

video: (file)
thumbnail: (optional file) video thumbnail
duration: (optional int) duration in seconds
width: (optional int)
height: (optional int)
reply_to_id: (optional)
```

### Send Audio

```http
POST /conversations/{conversation_id}/messages/audio
Authorization: Bearer {token}
Content-Type: multipart/form-data

audio: (file)
duration: (optional int) duration in seconds
reply_to_id: (optional)
```

### Send Voice Message

```http
POST /conversations/{conversation_id}/messages/voice
Authorization: Bearer {token}
Content-Type: multipart/form-data

voice: (file)
duration: (optional int) duration in seconds
reply_to_id: (optional)
```

**Media Response:**
```json
{
  "success": true,
  "data": {
    "id": "msg_123",
    "sender_id": "user_456",
    "content": "https://cdn.../video.mp4",
    "type": "video",
    "video_url": "https://cdn.../video.mp4",
    "media_info": {
      "duration": 30,
      "width": 1920,
      "height": 1080,
      "thumbnail_url": "https://cdn.../thumb.jpg",
      "file_size": 5242880,
      "mime_type": "video/mp4"
    },
    "timestamp": "2024-01-15T10:00:00Z",
    "status": "sent"
  }
}
```

---

## Reactions

Add emoji reactions to messages (like Telegram/Instagram).

### Add Reaction

```http
POST /conversations/{conversation_id}/messages/{message_id}/reactions
Authorization: Bearer {token}
Content-Type: application/json

{
  "emoji": "❤️"
}
```

### Remove Reaction

```http
DELETE /conversations/{conversation_id}/messages/{message_id}/reactions
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "reactions": [
      { "emoji": "❤️", "user_id": "user_123", "created_at": "2024-01-15T10:00:00Z" },
      { "emoji": "😂", "user_id": "user_456", "created_at": "2024-01-15T10:01:00Z" }
    ]
  }
}
```

---

## Reply to Messages

Send a message as a reply to another message.

### Send Reply

```http
POST /conversations/{conversation_id}/messages
Authorization: Bearer {token}
Content-Type: application/json

{
  "content": "Great idea!",
  "type": "text",
  "reply_to_id": "msg_original_123"
}
```

**Response with Reply:**
```json
{
  "success": true,
  "data": {
    "id": "msg_456",
    "content": "Great idea!",
    "type": "text",
    "reply_to": {
      "message_id": "msg_original_123",
      "sender_id": "user_789",
      "sender_name": "Sarah",
      "content": "Should we meet at 7pm?",
      "type": "text"
    },
    ...
  }
}
```

---

## Edit & Delete Messages

### Edit Message

Edit text messages within 48 hours.

```http
PATCH /conversations/{conversation_id}/messages/{message_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "content": "Updated message content"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "msg_123",
    "content": "Updated message content",
    "is_edited": true,
    ...
  }
}
```

### Delete Message

```http
DELETE /conversations/{conversation_id}/messages/{message_id}?for_everyone=true
Authorization: Bearer {token}
```

---

## Pin Messages

Pin important messages in a conversation (max 5 pins).

### Pin Message

```http
POST /conversations/{conversation_id}/pin
Authorization: Bearer {token}
Content-Type: application/json

{
  "message_id": "msg_123"
}
```

### Unpin Message

```http
DELETE /conversations/{conversation_id}/pin/{message_id}
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "pinned_messages": [
      {
        "message_id": "msg_123",
        "content": "Meeting at 7pm tomorrow",
        "pinned_by": "user_456",
        "pinned_at": "2024-01-15T10:00:00Z"
      }
    ]
  }
}
```

---

## Mute Conversations

### Mute Conversation

```http
POST /conversations/{conversation_id}/mute
Authorization: Bearer {token}
Content-Type: application/json

{
  "duration_hours": 8
}
```

**Duration options:**
- `1` - 1 hour
- `8` - 8 hours
- `24` - 1 day
- `168` - 1 week
- `null` - Forever
- `0` - Unmute

---

## Stickers

### Get All Sticker Packs

```http
GET /stickers/packs
Authorization: Bearer {token}
```

### Get Sticker Pack Details

```http
GET /stickers/packs/{pack_id}
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "pack": {
      "id": "pack_123",
      "name": "Love & Romance",
      "description": "Express your feelings",
      "thumbnail_url": "https://cdn.../thumb.webp",
      "author": "Flame",
      "is_official": true,
      "is_premium": false,
      "sticker_count": 24
    },
    "stickers": [
      {
        "id": "sticker_1",
        "emoji": "❤️",
        "image_url": "https://cdn.../heart.webp",
        "thumbnail_url": "https://cdn.../heart_thumb.webp"
      }
    ]
  }
}
```

### Get My Sticker Packs

```http
GET /stickers/my-packs
Authorization: Bearer {token}
```

### Add Sticker Pack

```http
POST /stickers/my-packs/{pack_id}
Authorization: Bearer {token}
```

### Remove Sticker Pack

```http
DELETE /stickers/my-packs/{pack_id}
Authorization: Bearer {token}
```

### Get Recent Stickers

```http
GET /stickers/recent?limit=20
Authorization: Bearer {token}
```

### Send Sticker

```http
POST /conversations/{conversation_id}/messages/sticker
Authorization: Bearer {token}
Content-Type: application/json

{
  "sticker_id": "sticker_123",
  "reply_to_id": null
}
```

---

## WebSocket Events

### Events You Send (Client -> Server)

```javascript
// Ping (keep-alive)
{ "event": "ping" }

// Typing indicator
{ "event": "typing", "data": { "conversation_id": "conv_123" } }

// Stop typing
{ "event": "stop_typing", "data": { "conversation_id": "conv_123" } }

// Recording voice message
{ "event": "recording_voice", "data": { "conversation_id": "conv_123" } }

// Mark messages as read
{
  "event": "message_read",
  "data": {
    "conversation_id": "conv_123",
    "message_ids": ["msg_1", "msg_2"]
  }
}
```

### Events You Receive (Server -> Client)

#### New Message
```json
{
  "event": "new_message",
  "data": {
    "conversation_id": "conv_123",
    "message": {
      "id": "msg_456",
      "sender_id": "user_789",
      "content": "Hello!",
      "type": "text",
      "timestamp": "2024-01-15T10:00:00Z",
      "status": "sent",
      "reactions": [],
      "reply_to": null
    }
  }
}
```

#### Message Edited
```json
{
  "event": "message_edited",
  "data": {
    "conversation_id": "conv_123",
    "message": { ... }
  }
}
```

#### Message Deleted
```json
{
  "event": "message_deleted",
  "data": {
    "conversation_id": "conv_123",
    "message_id": "msg_456"
  }
}
```

#### Reaction Added
```json
{
  "event": "reaction_added",
  "data": {
    "conversation_id": "conv_123",
    "message_id": "msg_456",
    "emoji": "❤️",
    "user_id": "user_789"
  }
}
```

#### Reaction Removed
```json
{
  "event": "reaction_removed",
  "data": {
    "conversation_id": "conv_123",
    "message_id": "msg_456",
    "user_id": "user_789"
  }
}
```

#### Message Pinned
```json
{
  "event": "message_pinned",
  "data": {
    "conversation_id": "conv_123",
    "message_id": "msg_456",
    "pinned_by": "user_789"
  }
}
```

#### Message Unpinned
```json
{
  "event": "message_unpinned",
  "data": {
    "conversation_id": "conv_123",
    "message_id": "msg_456"
  }
}
```

#### User Typing
```json
{
  "event": "user_typing",
  "data": {
    "conversation_id": "conv_123",
    "user_id": "user_456"
  }
}
```

#### User Recording Voice
```json
{
  "event": "user_recording_voice",
  "data": {
    "conversation_id": "conv_123",
    "user_id": "user_456"
  }
}
```

#### New Match
```json
{
  "event": "new_match",
  "data": {
    "match": {
      "id": "match_789",
      "user": { "id": "user_456", "name": "Sarah", "photos": [...] },
      "matched_at": "2024-01-15T10:00:00Z"
    },
    "user": { "id": "user_456", "name": "Sarah", "photos": [...] },
    "conversation_id": "conv_123"
  }
}
```

#### User Online/Offline
```json
{ "event": "user_online", "data": { "user_id": "user_456" } }
{ "event": "user_offline", "data": { "user_id": "user_456" } }
```

---

## React Native Implementation

### WebSocket Service

```javascript
class WebSocketService {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
  }

  connect(accessToken) {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`wss://api.yourapp.com/ws?token=${accessToken}`);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.startPingInterval();
        resolve();
      };

      this.ws.onclose = (event) => {
        this.stopPingInterval();
        if (event.code === 4001) {
          this.emit('auth_error');
        } else {
          this.attemptReconnect(accessToken);
        }
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.emit(data.event, data.data);
      };
    });
  }

  send(event, data = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    }
  }

  // Convenience methods
  sendTyping(conversationId) {
    this.send('typing', { conversation_id: conversationId });
  }

  sendStopTyping(conversationId) {
    this.send('stop_typing', { conversation_id: conversationId });
  }

  sendRecordingVoice(conversationId) {
    this.send('recording_voice', { conversation_id: conversationId });
  }

  sendMessageRead(conversationId, messageIds) {
    this.send('message_read', { conversation_id: conversationId, message_ids: messageIds });
  }

  // Event emitter
  on(event, callback) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event).add(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    this.listeners.get(event)?.delete(callback);
  }

  emit(event, data) {
    this.listeners.get(event)?.forEach(cb => cb(data));
  }
}

export default new WebSocketService();
```

### Send Media Message (React Native)

```javascript
import { launchImageLibrary } from 'react-native-image-picker';
import api from './api';

async function sendImageMessage(conversationId, replyToId = null) {
  const result = await launchImageLibrary({ mediaType: 'photo' });
  if (result.didCancel) return;

  const formData = new FormData();
  formData.append('image', {
    uri: result.assets[0].uri,
    type: result.assets[0].type,
    name: result.assets[0].fileName,
  });
  if (replyToId) formData.append('reply_to_id', replyToId);

  const response = await api.post(
    `/conversations/${conversationId}/messages/image`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );

  return response.data.data;
}

async function sendVoiceMessage(conversationId, audioPath, duration) {
  const formData = new FormData();
  formData.append('voice', {
    uri: audioPath,
    type: 'audio/ogg',
    name: 'voice.ogg',
  });
  formData.append('duration', duration);

  const response = await api.post(
    `/conversations/${conversationId}/messages/voice`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );

  return response.data.data;
}
```

### Message Bubble Component

```jsx
function MessageBubble({ message, isMe, onReply, onReact, onLongPress }) {
  return (
    <TouchableOpacity onLongPress={onLongPress}>
      <View style={[styles.bubble, isMe ? styles.myBubble : styles.theirBubble]}>
        {/* Reply preview */}
        {message.reply_to && (
          <View style={styles.replyPreview}>
            <Text style={styles.replyName}>{message.reply_to.sender_name}</Text>
            <Text style={styles.replyContent} numberOfLines={1}>
              {message.reply_to.content}
            </Text>
          </View>
        )}

        {/* Message content based on type */}
        {message.type === 'text' && (
          <Text style={styles.text}>{message.content}</Text>
        )}
        {message.type === 'image' && (
          <Image source={{ uri: message.image_url }} style={styles.image} />
        )}
        {message.type === 'video' && (
          <VideoPlayer
            source={{ uri: message.video_url }}
            thumbnail={{ uri: message.media_info?.thumbnail_url }}
          />
        )}
        {message.type === 'voice' && (
          <VoicePlayer
            source={{ uri: message.audio_url }}
            duration={message.media_info?.duration}
          />
        )}
        {message.type === 'sticker' && (
          <Image source={{ uri: message.content }} style={styles.sticker} />
        )}

        {/* Edited indicator */}
        {message.is_edited && (
          <Text style={styles.edited}>edited</Text>
        )}

        {/* Reactions */}
        {message.reactions?.length > 0 && (
          <View style={styles.reactions}>
            {message.reactions.map((r, i) => (
              <Text key={i} style={styles.reaction}>{r.emoji}</Text>
            ))}
          </View>
        )}

        {/* Timestamp and status */}
        <View style={styles.meta}>
          <Text style={styles.time}>
            {formatTime(message.timestamp)}
          </Text>
          {isMe && <StatusIcon status={message.status} />}
        </View>
      </View>
    </TouchableOpacity>
  );
}
```

### Sticker Picker Component

```jsx
function StickerPicker({ onSelect, onClose }) {
  const [packs, setPacks] = useState([]);
  const [selectedPack, setSelectedPack] = useState(null);
  const [stickers, setStickers] = useState([]);
  const [recentStickers, setRecentStickers] = useState([]);

  useEffect(() => {
    loadPacks();
    loadRecentStickers();
  }, []);

  const loadPacks = async () => {
    const res = await api.get('/stickers/my-packs');
    setPacks(res.data.data.packs);
    if (res.data.data.packs.length > 0) {
      selectPack(res.data.data.packs[0].id);
    }
  };

  const loadRecentStickers = async () => {
    const res = await api.get('/stickers/recent');
    setRecentStickers(res.data.data.stickers);
  };

  const selectPack = async (packId) => {
    setSelectedPack(packId);
    const res = await api.get(`/stickers/packs/${packId}`);
    setStickers(res.data.data.stickers);
  };

  return (
    <View style={styles.container}>
      {/* Pack tabs */}
      <ScrollView horizontal style={styles.packTabs}>
        <TouchableOpacity onPress={() => setSelectedPack('recent')}>
          <Text>🕐</Text>
        </TouchableOpacity>
        {packs.map(pack => (
          <TouchableOpacity key={pack.id} onPress={() => selectPack(pack.id)}>
            <Image source={{ uri: pack.thumbnail_url }} style={styles.packThumb} />
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Sticker grid */}
      <FlatList
        data={selectedPack === 'recent' ? recentStickers : stickers}
        numColumns={4}
        renderItem={({ item }) => (
          <TouchableOpacity onPress={() => onSelect(item.id)}>
            <Image source={{ uri: item.thumbnail_url }} style={styles.sticker} />
          </TouchableOpacity>
        )}
      />
    </View>
  );
}
```

---

## Quick Reference

### Message Flow

1. User types/records/selects media
2. Upload media (if applicable)
3. POST to appropriate endpoint
4. Add message to local state (optimistic)
5. Server broadcasts via WebSocket
6. Recipient receives `new_message` event

### Reaction Flow

1. User long-presses message
2. Shows emoji picker
3. POST to `/messages/{id}/reactions`
4. Server broadcasts `reaction_added`
5. Both users see reaction

### Voice Message Flow

1. User holds record button
2. Send `recording_voice` WebSocket event
3. Release to stop recording
4. Upload audio file
5. POST to `/messages/voice`
6. Server broadcasts `new_message`

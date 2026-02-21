from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set, Optional
import json
from datetime import datetime, timezone
from app.core.security import decode_token
from app.models.user import User
from app.models.conversation import Conversation
from app.core.redis import redis_pubsub

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for this worker."""

    def __init__(self):
        # Map user_id -> WebSocket connection (local to this worker)
        self.active_connections: Dict[str, WebSocket] = {}
        # Map user_id -> set of conversation_ids they're subscribed to
        self.user_conversations: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_conversations[user_id] = set()

        # Update user online status
        user = await User.get(user_id)
        if user:
            user.is_online = True
            user.last_active = datetime.now(timezone.utc)
            await user.save()

        # Subscribe to user's conversations
        conversations = await Conversation.find(
            {"$or": [{"user1_id": user_id}, {"user2_id": user_id}]}
        ).to_list()

        for conv in conversations:
            conv_id = str(conv.id)
            self.user_conversations[user_id].add(conv_id)

    def disconnect(self, user_id: str):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to a specific user if connected to this worker."""
        if user_id in self.active_connections:
            try:
                websocket = self.active_connections[user_id]
                await websocket.send_json(message)
                return True
            except Exception:
                return False
        return False

    async def broadcast_to_conversation_local(
        self, message: dict, conversation_id: str, exclude_user: Optional[str] = None
    ):
        """Broadcast to users connected to THIS worker only."""
        for user_id, conversations in self.user_conversations.items():
            if conversation_id in conversations and user_id != exclude_user:
                await self.send_personal_message(message, user_id)

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user is connected to this worker."""
        return user_id in self.active_connections

    def subscribe_to_conversation(self, user_id: str, conversation_id: str):
        """Subscribe a user to a conversation."""
        if user_id in self.user_conversations:
            self.user_conversations[user_id].add(conversation_id)


# Global connection manager (per worker)
manager = ConnectionManager()


async def handle_redis_message(data: dict):
    """Handle messages from Redis pub/sub."""
    msg_type = data.get("type")
    payload = data.get("data", {})

    if msg_type == "broadcast_conversation":
        # Broadcast to conversation
        message = payload.get("message")
        conversation_id = payload.get("conversation_id")
        exclude_user = payload.get("exclude_user")
        await manager.broadcast_to_conversation_local(message, conversation_id, exclude_user)

    elif msg_type == "personal_message":
        # Send to specific user
        message = payload.get("message")
        user_id = payload.get("user_id")
        await manager.send_personal_message(message, user_id)

    elif msg_type == "subscribe_conversation":
        # Subscribe user to conversation
        user_id = payload.get("user_id")
        conversation_id = payload.get("conversation_id")
        manager.subscribe_to_conversation(user_id, conversation_id)


async def get_user_from_token(token: str) -> Optional[User]:
    """Validate token and get user."""
    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return await User.get(user_id)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time messaging."""
    # Authenticate user
    user = await get_user_from_token(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = str(user.id)

    # Connect
    await manager.connect(websocket, user_id)

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message = json.loads(data)

            event = message.get("event")
            payload = message.get("data", {})

            if event == "ping":
                # Respond to ping
                await websocket.send_json({"event": "pong"})

            elif event == "typing":
                # User is typing - broadcast via Redis for multi-worker support
                conversation_id = payload.get("conversation_id")
                if conversation_id:
                    await redis_pubsub.publish(
                        "broadcast_conversation",
                        {
                            "conversation_id": conversation_id,
                            "exclude_user": user_id,
                            "message": {
                                "event": "user_typing",
                                "data": {
                                    "conversation_id": conversation_id,
                                    "user_id": user_id,
                                },
                            },
                        },
                    )

            elif event == "stop_typing":
                # User stopped typing
                conversation_id = payload.get("conversation_id")
                if conversation_id:
                    await redis_pubsub.publish(
                        "broadcast_conversation",
                        {
                            "conversation_id": conversation_id,
                            "exclude_user": user_id,
                            "message": {
                                "event": "user_stop_typing",
                                "data": {
                                    "conversation_id": conversation_id,
                                    "user_id": user_id,
                                },
                            },
                        },
                    )

            elif event == "message_read":
                # User read messages
                conversation_id = payload.get("conversation_id")
                message_ids = payload.get("message_ids", [])
                if conversation_id:
                    await redis_pubsub.publish(
                        "broadcast_conversation",
                        {
                            "conversation_id": conversation_id,
                            "exclude_user": user_id,
                            "message": {
                                "event": "message_status",
                                "data": {
                                    "conversation_id": conversation_id,
                                    "message_ids": message_ids,
                                    "status": "read",
                                },
                            },
                        },
                    )

            elif event == "recording_voice":
                # User is recording voice message
                conversation_id = payload.get("conversation_id")
                if conversation_id:
                    await redis_pubsub.publish(
                        "broadcast_conversation",
                        {
                            "conversation_id": conversation_id,
                            "exclude_user": user_id,
                            "message": {
                                "event": "user_recording_voice",
                                "data": {
                                    "conversation_id": conversation_id,
                                    "user_id": user_id,
                                },
                            },
                        },
                    )

    except WebSocketDisconnect:
        manager.disconnect(user_id)

        # Update user offline status
        user = await User.get(user_id)
        if user:
            user.is_online = False
            user.last_active = datetime.now(timezone.utc)
            await user.save()

    except Exception:
        manager.disconnect(user_id)


# =============================================================================
# Helper functions to be called from REST API handlers
# These publish to Redis so ALL workers can deliver to their connections
# =============================================================================

async def notify_new_message(conversation_id: str, message: dict, sender_id: str):
    """Notify users in a conversation about a new message."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": sender_id,
            "message": {
                "event": "new_message",
                "data": {
                    "conversation_id": conversation_id,
                    "message": message,
                },
            },
        },
    )


async def notify_new_match(user_id: str, match_data: dict, conversation_id: str = None):
    """Notify a user about a new match and subscribe them to the conversation."""
    # Subscribe both users to the new conversation via Redis
    if conversation_id:
        await redis_pubsub.publish(
            "subscribe_conversation",
            {"user_id": user_id, "conversation_id": conversation_id},
        )
        other_user_id = match_data.get("user", {}).get("id")
        if other_user_id:
            await redis_pubsub.publish(
                "subscribe_conversation",
                {"user_id": other_user_id, "conversation_id": conversation_id},
            )

    # Send match notification
    await redis_pubsub.publish(
        "personal_message",
        {
            "user_id": user_id,
            "message": {
                "event": "new_match",
                "data": match_data,
            },
        },
    )


async def notify_message_edited(conversation_id: str, message: dict, editor_id: str):
    """Notify users about an edited message."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": editor_id,
            "message": {
                "event": "message_edited",
                "data": {
                    "conversation_id": conversation_id,
                    "message": message,
                },
            },
        },
    )


async def notify_message_deleted(conversation_id: str, message_id: str, deleter_id: str):
    """Notify users about a deleted message."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": deleter_id,
            "message": {
                "event": "message_deleted",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                },
            },
        },
    )


async def notify_reaction_added(
    conversation_id: str, message_id: str, emoji: str, user_id: str
):
    """Notify users about a new reaction."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": user_id,
            "message": {
                "event": "reaction_added",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "emoji": emoji,
                    "user_id": user_id,
                },
            },
        },
    )


async def notify_reaction_removed(conversation_id: str, message_id: str, user_id: str):
    """Notify users about a removed reaction."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": user_id,
            "message": {
                "event": "reaction_removed",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "user_id": user_id,
                },
            },
        },
    )


async def notify_message_pinned(conversation_id: str, message_id: str, pinner_id: str):
    """Notify users about a pinned message."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": pinner_id,
            "message": {
                "event": "message_pinned",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "pinned_by": pinner_id,
                },
            },
        },
    )


async def notify_message_unpinned(
    conversation_id: str, message_id: str, unpinner_id: str
):
    """Notify users about an unpinned message."""
    await redis_pubsub.publish(
        "broadcast_conversation",
        {
            "conversation_id": conversation_id,
            "exclude_user": unpinner_id,
            "message": {
                "event": "message_unpinned",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                },
            },
        },
    )


async def notify_user_online(user_id: str, is_online: bool):
    """Notify conversations about user online status change."""
    conversations = await Conversation.find(
        {"$or": [{"user1_id": user_id}, {"user2_id": user_id}]}
    ).to_list()

    event = "user_online" if is_online else "user_offline"
    for conv in conversations:
        other_user_id = conv.get_other_user_id(user_id)
        await redis_pubsub.publish(
            "personal_message",
            {
                "user_id": other_user_id,
                "message": {
                    "event": event,
                    "data": {"user_id": user_id},
                },
            },
        )


# =============================================================================
# Debug endpoint to check WebSocket state
# =============================================================================

@router.get("/ws/debug")
async def websocket_debug():
    """Debug endpoint to check WebSocket state for this worker."""
    return {
        "active_connections": list(manager.active_connections.keys()),
        "user_subscriptions": {
            user_id: list(convs)
            for user_id, convs in manager.user_conversations.items()
        },
        "total_connections": len(manager.active_connections),
        "note": "This shows connections for THIS worker only",
    }

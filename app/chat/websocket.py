from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set, Optional
import json
from datetime import datetime, timezone
from app.core.security import decode_token
from app.models.user import User
from app.models.conversation import Conversation

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        # Map user_id -> WebSocket connection
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
            self.user_conversations[user_id].add(str(conv.id))

    def disconnect(self, user_id: str):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to a specific user."""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            await websocket.send_json(message)

    async def broadcast_to_conversation(
        self, message: dict, conversation_id: str, exclude_user: Optional[str] = None
    ):
        """Broadcast a message to all users in a conversation."""
        for user_id, conversations in self.user_conversations.items():
            if conversation_id in conversations and user_id != exclude_user:
                await self.send_personal_message(message, user_id)

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user is connected."""
        return user_id in self.active_connections


# Global connection manager
manager = ConnectionManager()


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
                # User is typing
                conversation_id = payload.get("conversation_id")
                if conversation_id:
                    await manager.broadcast_to_conversation(
                        {
                            "event": "user_typing",
                            "data": {
                                "conversation_id": conversation_id,
                                "user_id": user_id,
                            },
                        },
                        conversation_id,
                        exclude_user=user_id,
                    )

            elif event == "stop_typing":
                # User stopped typing
                conversation_id = payload.get("conversation_id")
                if conversation_id:
                    await manager.broadcast_to_conversation(
                        {
                            "event": "user_stop_typing",
                            "data": {
                                "conversation_id": conversation_id,
                                "user_id": user_id,
                            },
                        },
                        conversation_id,
                        exclude_user=user_id,
                    )

            elif event == "message_read":
                # User read messages
                conversation_id = payload.get("conversation_id")
                message_ids = payload.get("message_ids", [])
                if conversation_id:
                    await manager.broadcast_to_conversation(
                        {
                            "event": "message_status",
                            "data": {
                                "conversation_id": conversation_id,
                                "message_ids": message_ids,
                                "status": "read",
                            },
                        },
                        conversation_id,
                        exclude_user=user_id,
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


# Helper functions to be called from other parts of the app
async def notify_new_message(conversation_id: str, message: dict, sender_id: str):
    """Notify users in a conversation about a new message."""
    await manager.broadcast_to_conversation(
        {
            "event": "new_message",
            "data": {
                "conversation_id": conversation_id,
                "message": message,
            },
        },
        conversation_id,
        exclude_user=sender_id,
    )


async def notify_new_match(user_id: str, match_data: dict):
    """Notify a user about a new match."""
    await manager.send_personal_message(
        {
            "event": "new_match",
            "data": match_data,
        },
        user_id,
    )


async def notify_user_online(user_id: str, is_online: bool):
    """Notify conversations about user online status change."""
    conversations = await Conversation.find(
        {"$or": [{"user1_id": user_id}, {"user2_id": user_id}]}
    ).to_list()

    for conv in conversations:
        other_user_id = conv.get_other_user_id(user_id)
        event = "user_online" if is_online else "user_offline"
        await manager.send_personal_message(
            {
                "event": event,
                "data": {"user_id": user_id},
            },
            other_user_id,
        )

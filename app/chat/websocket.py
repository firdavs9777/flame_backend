from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set, Optional
import json
import asyncio
import logging
from datetime import datetime, timezone
from app.core.security import decode_token
from app.core.token_blocklist import is_jti_revoked, user_token_revoked
from app.core.cache import online_tracker
from app.models.user import User
from app.models.conversation import Conversation
from app.core.redis import redis_pubsub

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for this worker."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_conversations: Dict[str, Set[str]] = {}
        self._heartbeats: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_conversations[user_id] = set()

        # Persistence + presence
        user = await User.get(user_id)
        if user:
            user.is_online = True
            user.last_active = datetime.now(timezone.utc)
            await user.save()
        await online_tracker.set_online(user_id)

        # Subscribe to user's active conversations
        conversations = await Conversation.find(
            {"$or": [{"user1_id": user_id}, {"user2_id": user_id}], "is_active": True}
        ).to_list()
        for conv in conversations:
            self.user_conversations[user_id].add(str(conv.id))

        # Periodic presence refresh (Redis TTL = 120s)
        self._heartbeats[user_id] = asyncio.create_task(self._presence_loop(user_id))

    async def _presence_loop(self, user_id: str):
        try:
            while user_id in self.active_connections:
                await online_tracker.refresh(user_id)
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]
        hb = self._heartbeats.pop(user_id, None)
        if hb:
            hb.cancel()
        await online_tracker.set_offline(user_id)

    async def send_personal_message(self, message: dict, user_id: str) -> bool:
        ws = self.active_connections.get(user_id)
        if not ws:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            return False

    async def broadcast_to_conversation_local(
        self, message: dict, conversation_id: str, exclude_user: Optional[str] = None
    ):
        for user_id, conversations in list(self.user_conversations.items()):
            if conversation_id in conversations and user_id != exclude_user:
                await self.send_personal_message(message, user_id)

    def subscribe_to_conversation(self, user_id: str, conversation_id: str):
        if user_id in self.user_conversations:
            self.user_conversations[user_id].add(conversation_id)


manager = ConnectionManager()


async def handle_redis_message(data: dict):
    msg_type = data.get("type")
    payload = data.get("data", {})

    if msg_type == "broadcast_conversation":
        await manager.broadcast_to_conversation_local(
            payload.get("message"),
            payload.get("conversation_id"),
            payload.get("exclude_user"),
        )
    elif msg_type == "personal_message":
        await manager.send_personal_message(payload.get("message"), payload.get("user_id"))
    elif msg_type == "subscribe_conversation":
        manager.subscribe_to_conversation(payload.get("user_id"), payload.get("conversation_id"))


async def _validate_token(token: str) -> Optional[User]:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    jti = payload.get("jti")
    if await is_jti_revoked(jti):
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    if await user_token_revoked(user_id, payload.get("iat")):
        return None
    user = await User.get(user_id)
    if not user or user.is_deleted:
        return None
    return user


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    """WebSocket endpoint. Auth options (in order of preference):
      1. Sec-WebSocket-Protocol: bearer.<JWT>   (preferred — no URL leakage)
      2. First frame after connection: {"event":"auth","data":{"token":"..."}}
      3. ?token=<JWT> query (legacy — discouraged, logged in nginx access log).
    """
    # Try subprotocol-based auth first
    subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    proto_token = None
    for sp in [s.strip() for s in subprotocols.split(",") if s.strip()]:
        if sp.startswith("bearer."):
            proto_token = sp[len("bearer."):]
            break

    user: Optional[User] = None
    accepted_subprotocol: Optional[str] = None

    if proto_token:
        user = await _validate_token(proto_token)
        accepted_subprotocol = f"bearer.{proto_token}" if user else None
    if not user and token:
        user = await _validate_token(token)
    if not user:
        # Accept then await one frame for auth
        await websocket.accept()
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            data = json.loads(first)
            if data.get("event") == "auth":
                user = await _validate_token((data.get("data") or {}).get("token"))
        except Exception:
            user = None
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        # Already accepted
    else:
        if accepted_subprotocol:
            await websocket.accept(subprotocol=accepted_subprotocol)
        else:
            await websocket.accept()

    user_id = str(user.id)
    # Hook up manager state without re-accepting
    manager.active_connections[user_id] = websocket
    manager.user_conversations[user_id] = set()
    user.is_online = True
    user.last_active = datetime.now(timezone.utc)
    await user.save()
    await online_tracker.set_online(user_id)
    conversations = await Conversation.find(
        {"$or": [{"user1_id": user_id}, {"user2_id": user_id}], "is_active": True}
    ).to_list()
    for conv in conversations:
        manager.user_conversations[user_id].add(str(conv.id))
    manager._heartbeats[user_id] = asyncio.create_task(manager._presence_loop(user_id))

    # Announce online to matches
    await notify_user_online(user_id, True)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            event = message.get("event")
            payload = message.get("data", {}) or {}

            if event == "ping":
                await websocket.send_json({"event": "pong"})

            elif event == "typing":
                cid = payload.get("conversation_id")
                if cid:
                    await redis_pubsub.publish("broadcast_conversation", {
                        "conversation_id": cid,
                        "exclude_user": user_id,
                        "message": {"event": "user_typing", "data": {"conversation_id": cid, "user_id": user_id}},
                    })

            elif event == "stop_typing":
                cid = payload.get("conversation_id")
                if cid:
                    await redis_pubsub.publish("broadcast_conversation", {
                        "conversation_id": cid,
                        "exclude_user": user_id,
                        "message": {"event": "user_stop_typing", "data": {"conversation_id": cid, "user_id": user_id}},
                    })

            elif event == "message_read":
                cid = payload.get("conversation_id")
                message_ids = payload.get("message_ids", [])
                if cid:
                    await redis_pubsub.publish("broadcast_conversation", {
                        "conversation_id": cid,
                        "exclude_user": user_id,
                        "message": {
                            "event": "message_status",
                            "data": {
                                "conversation_id": cid,
                                "message_ids": message_ids,
                                "status": "read",
                            },
                        },
                    })

            elif event == "recording_voice":
                cid = payload.get("conversation_id")
                if cid:
                    await redis_pubsub.publish("broadcast_conversation", {
                        "conversation_id": cid,
                        "exclude_user": user_id,
                        "message": {
                            "event": "user_recording_voice",
                            "data": {"conversation_id": cid, "user_id": user_id},
                        },
                    })

            elif event == "stop_recording_voice":
                cid = payload.get("conversation_id")
                if cid:
                    await redis_pubsub.publish("broadcast_conversation", {
                        "conversation_id": cid,
                        "exclude_user": user_id,
                        "message": {
                            "event": "user_stop_recording_voice",
                            "data": {"conversation_id": cid, "user_id": user_id},
                        },
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error for user {user_id}: {e}")
    finally:
        await manager.disconnect(user_id)
        try:
            u = await User.get(user_id)
            if u:
                u.is_online = False
                u.last_active = datetime.now(timezone.utc)
                await u.save()
        except Exception:
            pass
        await notify_user_online(user_id, False)


# =============================================================================
# Helper functions called from REST handlers
# =============================================================================

async def notify_new_message(conversation_id: str, message: dict, sender_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": sender_id,
        "message": {"event": "new_message", "data": {"conversation_id": conversation_id, "message": message}},
    })


async def notify_new_match(
    recipient_id: str,
    match_payload: dict,
    conversation_id: Optional[str] = None,
    swiper_id: Optional[str] = None,
):
    """Notify the *recipient* about a new match and subscribe BOTH users to the
    conversation (so cross-worker, the swiper's existing socket also picks up
    messages in the new conv without needing to reconnect)."""
    if conversation_id:
        await redis_pubsub.publish("subscribe_conversation", {
            "user_id": recipient_id, "conversation_id": conversation_id
        })
        if swiper_id:
            await redis_pubsub.publish("subscribe_conversation", {
                "user_id": swiper_id, "conversation_id": conversation_id
            })

    await redis_pubsub.publish("personal_message", {
        "user_id": recipient_id,
        "message": {"event": "new_match", "data": match_payload},
    })


async def notify_message_edited(conversation_id: str, message: dict, editor_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": editor_id,
        "message": {"event": "message_edited", "data": {"conversation_id": conversation_id, "message": message}},
    })


async def notify_message_deleted(conversation_id: str, message_id: str, deleter_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": deleter_id,
        "message": {"event": "message_deleted", "data": {"conversation_id": conversation_id, "message_id": message_id}},
    })


async def notify_reaction_added(conversation_id: str, message_id: str, emoji: str, user_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": user_id,
        "message": {
            "event": "reaction_added",
            "data": {"conversation_id": conversation_id, "message_id": message_id, "emoji": emoji, "user_id": user_id},
        },
    })


async def notify_reaction_removed(conversation_id: str, message_id: str, user_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": user_id,
        "message": {
            "event": "reaction_removed",
            "data": {"conversation_id": conversation_id, "message_id": message_id, "user_id": user_id},
        },
    })


async def notify_message_pinned(conversation_id: str, message_id: str, pinner_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": pinner_id,
        "message": {
            "event": "message_pinned",
            "data": {"conversation_id": conversation_id, "message_id": message_id, "pinned_by": pinner_id},
        },
    })


async def notify_message_unpinned(conversation_id: str, message_id: str, unpinner_id: str):
    await redis_pubsub.publish("broadcast_conversation", {
        "conversation_id": conversation_id,
        "exclude_user": unpinner_id,
        "message": {
            "event": "message_unpinned",
            "data": {"conversation_id": conversation_id, "message_id": message_id},
        },
    })


async def notify_user_online(user_id: str, is_online: bool):
    """Notify the other side of every active conversation about presence change."""
    conversations = await Conversation.find(
        {"$or": [{"user1_id": user_id}, {"user2_id": user_id}], "is_active": True}
    ).to_list()

    event = "user_online" if is_online else "user_offline"
    for conv in conversations:
        other_user_id = conv.get_other_user_id(user_id)
        await redis_pubsub.publish("personal_message", {
            "user_id": other_user_id,
            "message": {"event": event, "data": {"user_id": user_id}},
        })


# =============================================================================
# DEBUG-only endpoint
# =============================================================================
from app.core.config import settings as _settings

if _settings.DEBUG:
    @router.get("/ws/debug")
    async def websocket_debug():
        return {
            "active_connections": list(manager.active_connections.keys()),
            "user_subscriptions": {uid: list(c) for uid, c in manager.user_conversations.items()},
            "total_connections": len(manager.active_connections),
        }

from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from typing import Optional
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.message import MessageType
from app.chat.schemas import SendMessageRequest, MarkReadRequest
from app.chat.service import ChatService

router = APIRouter(prefix="/conversations", tags=["Chat"])


@router.get("")
async def get_conversations(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """Get all conversations."""
    results, total = await ChatService.get_conversations(
        current_user,
        limit=limit,
        offset=offset,
    )

    return {
        "success": True,
        "data": {
            "conversations": [
                {
                    "id": str(r["conversation"].id),
                    "match_id": r["conversation"].match_id,
                    "other_user": {
                        "id": str(r["other_user"].id),
                        "name": r["other_user"].name,
                        "photos": [p.url for p in r["other_user"].photos],
                        "is_online": r["other_user"].is_online,
                    },
                    "last_message": r["last_message"],
                    "unread_count": r["unread_count"],
                    "updated_at": r["conversation"].updated_at.isoformat(),
                }
                for r in results
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        },
    }


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=50, le=100),
    before: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """Get messages in a conversation."""
    messages, has_more = await ChatService.get_messages(
        conversation_id,
        current_user,
        limit=limit,
        before=before,
    )

    return {
        "success": True,
        "data": {
            "messages": [
                {
                    "id": str(msg.id),
                    "sender_id": msg.sender_id,
                    "content": msg.content,
                    "type": msg.type.value,
                    "timestamp": msg.timestamp.isoformat(),
                    "status": msg.status.value,
                }
                for msg in messages
            ],
            "has_more": has_more,
        },
    }


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: str,
    data: SendMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """Send a message."""
    message = await ChatService.send_message(
        conversation_id,
        current_user,
        data.content,
        data.type,
    )

    return {
        "success": True,
        "data": {
            "id": str(message.id),
            "sender_id": message.sender_id,
            "content": message.content,
            "type": message.type.value,
            "timestamp": message.timestamp.isoformat(),
            "status": message.status.value,
        },
    }


@router.post("/{conversation_id}/messages/image", status_code=status.HTTP_201_CREATED)
async def send_image_message(
    conversation_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Send an image message."""
    from app.core.storage import storage

    # Upload to DigitalOcean Spaces
    image_url = await storage.upload_message_image(conversation_id, image)

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        image_url,
        MessageType.IMAGE,
        image_url=image_url,
    )

    return {
        "success": True,
        "data": {
            "id": str(message.id),
            "sender_id": message.sender_id,
            "content": message.content,
            "type": message.type.value,
            "timestamp": message.timestamp.isoformat(),
            "status": message.status.value,
        },
    }


@router.post("/{conversation_id}/read")
async def mark_read(
    conversation_id: str,
    data: MarkReadRequest,
    current_user: User = Depends(get_current_user),
):
    """Mark messages as read."""
    await ChatService.mark_messages_read(
        conversation_id,
        current_user,
        data.message_ids,
    )

    return {"success": True, "message": "Messages marked as read"}

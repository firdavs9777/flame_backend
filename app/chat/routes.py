from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, status
from typing import Optional
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.message import MessageType, MediaInfo
from app.chat.schemas import (
    SendMessageRequest,
    SendStickerRequest,
    EditMessageRequest,
    ReactToMessageRequest,
    PinMessageRequest,
    MuteConversationRequest,
    MarkReadRequest,
)
from app.chat.service import ChatService, StickerService

router = APIRouter(prefix="/conversations", tags=["Chat"])


# =============================================================================
# Helper function to format message response
# =============================================================================

def format_message(msg) -> dict:
    """Format a message for API response."""
    result = {
        "id": str(msg.id),
        "sender_id": msg.sender_id,
        "content": msg.content,
        "type": msg.type.value,
        "timestamp": msg.timestamp.isoformat(),
        "status": msg.status.value,
        "is_edited": msg.is_edited,
        "is_deleted": msg.is_deleted,
    }

    # Add optional media URLs
    if msg.image_url:
        result["image_url"] = msg.image_url
    if msg.video_url:
        result["video_url"] = msg.video_url
    if msg.audio_url:
        result["audio_url"] = msg.audio_url
    if msg.file_url:
        result["file_url"] = msg.file_url
    if msg.sticker_id:
        result["sticker_id"] = msg.sticker_id

    # Add media info
    if msg.media_info:
        result["media_info"] = {
            "duration": msg.media_info.duration,
            "width": msg.media_info.width,
            "height": msg.media_info.height,
            "thumbnail_url": msg.media_info.thumbnail_url,
            "file_size": msg.media_info.file_size,
            "mime_type": msg.media_info.mime_type,
        }

    # Add reply info
    if msg.reply_to:
        result["reply_to"] = {
            "message_id": msg.reply_to.message_id,
            "sender_id": msg.reply_to.sender_id,
            "sender_name": msg.reply_to.sender_name,
            "content": msg.reply_to.content,
            "type": msg.reply_to.type.value,
        }

    # Add reactions
    if msg.reactions:
        result["reactions"] = [
            {
                "emoji": r.emoji,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in msg.reactions
        ]
    else:
        result["reactions"] = []

    return result


# =============================================================================
# Conversation Endpoints
# =============================================================================

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
                    "pinned_messages": [
                        {
                            "message_id": p.message_id,
                            "content": p.content,
                            "pinned_by": p.pinned_by,
                            "pinned_at": p.pinned_at.isoformat(),
                        }
                        for p in r["conversation"].pinned_messages
                    ],
                    "is_muted": r["is_muted"],
                    "muted_until": r["muted_until"],
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


# =============================================================================
# Message Endpoints
# =============================================================================

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
            "messages": [format_message(msg) for msg in messages],
            "has_more": has_more,
        },
    }


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: str,
    data: SendMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """Send a text message."""
    message = await ChatService.send_message(
        conversation_id,
        current_user,
        data.content,
        data.type,
        reply_to_id=data.reply_to_id,
    )

    message_data = format_message(message)

    # Notify recipient via WebSocket
    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.post("/{conversation_id}/messages/image", status_code=status.HTTP_201_CREATED)
async def send_image_message(
    conversation_id: str,
    image: UploadFile = File(...),
    reply_to_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
):
    """Send an image message."""
    from app.core.storage import storage

    image_url = await storage.upload_message_image(conversation_id, image)

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        image_url,
        MessageType.IMAGE,
        image_url=image_url,
        reply_to_id=reply_to_id,
    )

    message_data = format_message(message)

    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.post("/{conversation_id}/messages/video", status_code=status.HTTP_201_CREATED)
async def send_video_message(
    conversation_id: str,
    video: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(default=None),
    duration: Optional[int] = Form(default=None),
    width: Optional[int] = Form(default=None),
    height: Optional[int] = Form(default=None),
    reply_to_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
):
    """Send a video message."""
    from app.core.storage import storage

    video_url = await storage.upload_message_video(conversation_id, video)

    thumbnail_url = None
    if thumbnail:
        thumbnail_url = await storage.upload_video_thumbnail(conversation_id, thumbnail)

    media_info = MediaInfo(
        duration=duration,
        width=width,
        height=height,
        thumbnail_url=thumbnail_url,
        file_size=video.size if hasattr(video, 'size') else None,
        mime_type=video.content_type,
    )

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        video_url,
        MessageType.VIDEO,
        video_url=video_url,
        media_info=media_info,
        reply_to_id=reply_to_id,
    )

    message_data = format_message(message)

    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.post("/{conversation_id}/messages/audio", status_code=status.HTTP_201_CREATED)
async def send_audio_message(
    conversation_id: str,
    audio: UploadFile = File(...),
    duration: Optional[int] = Form(default=None),
    reply_to_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
):
    """Send an audio message."""
    from app.core.storage import storage

    audio_url = await storage.upload_message_audio(conversation_id, audio)

    media_info = MediaInfo(
        duration=duration,
        file_size=audio.size if hasattr(audio, 'size') else None,
        mime_type=audio.content_type,
    )

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        audio_url,
        MessageType.AUDIO,
        audio_url=audio_url,
        media_info=media_info,
        reply_to_id=reply_to_id,
    )

    message_data = format_message(message)

    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.post("/{conversation_id}/messages/voice", status_code=status.HTTP_201_CREATED)
async def send_voice_message(
    conversation_id: str,
    voice: UploadFile = File(...),
    duration: Optional[int] = Form(default=None),
    reply_to_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
):
    """Send a voice message."""
    from app.core.storage import storage

    voice_url = await storage.upload_voice_message(conversation_id, voice)

    media_info = MediaInfo(
        duration=duration,
        file_size=voice.size if hasattr(voice, 'size') else None,
        mime_type=voice.content_type,
    )

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        voice_url,
        MessageType.VOICE,
        audio_url=voice_url,
        media_info=media_info,
        reply_to_id=reply_to_id,
    )

    message_data = format_message(message)

    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.post("/{conversation_id}/messages/sticker", status_code=status.HTTP_201_CREATED)
async def send_sticker_message(
    conversation_id: str,
    data: SendStickerRequest,
    current_user: User = Depends(get_current_user),
):
    """Send a sticker message."""
    sticker = await StickerService.get_sticker(data.sticker_id)

    message = await ChatService.send_message(
        conversation_id,
        current_user,
        sticker.image_url,
        MessageType.STICKER,
        sticker_id=data.sticker_id,
        reply_to_id=data.reply_to_id,
    )

    # Record sticker use for recent stickers
    await StickerService.record_sticker_use(current_user, data.sticker_id)

    message_data = format_message(message)

    from app.chat.websocket import notify_new_message
    await notify_new_message(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.patch("/{conversation_id}/messages/{message_id}")
async def edit_message(
    conversation_id: str,
    message_id: str,
    data: EditMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """Edit a text message."""
    message = await ChatService.edit_message(message_id, current_user, data.content)
    message_data = format_message(message)

    # Notify via WebSocket
    from app.chat.websocket import notify_message_edited
    await notify_message_edited(conversation_id, message_data, str(current_user.id))

    return {
        "success": True,
        "data": message_data,
    }


@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: str,
    message_id: str,
    for_everyone: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
):
    """Delete a message."""
    message = await ChatService.delete_message(message_id, current_user, for_everyone)

    # Notify via WebSocket
    from app.chat.websocket import notify_message_deleted
    await notify_message_deleted(conversation_id, message_id, str(current_user.id))

    return {
        "success": True,
        "message": "Message deleted",
    }


# =============================================================================
# Reaction Endpoints
# =============================================================================

@router.post("/{conversation_id}/messages/{message_id}/reactions")
async def add_reaction(
    conversation_id: str,
    message_id: str,
    data: ReactToMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """Add a reaction to a message."""
    message = await ChatService.add_reaction(message_id, current_user, data.emoji)

    # Notify via WebSocket
    from app.chat.websocket import notify_reaction_added
    await notify_reaction_added(
        conversation_id,
        message_id,
        data.emoji,
        str(current_user.id),
    )

    return {
        "success": True,
        "data": {
            "reactions": [
                {
                    "emoji": r.emoji,
                    "user_id": r.user_id,
                    "created_at": r.created_at.isoformat(),
                }
                for r in message.reactions
            ]
        },
    }


@router.delete("/{conversation_id}/messages/{message_id}/reactions")
async def remove_reaction(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
):
    """Remove your reaction from a message."""
    message = await ChatService.remove_reaction(message_id, current_user)

    # Notify via WebSocket
    from app.chat.websocket import notify_reaction_removed
    await notify_reaction_removed(
        conversation_id,
        message_id,
        str(current_user.id),
    )

    return {
        "success": True,
        "data": {
            "reactions": [
                {
                    "emoji": r.emoji,
                    "user_id": r.user_id,
                    "created_at": r.created_at.isoformat(),
                }
                for r in message.reactions
            ]
        },
    }


# =============================================================================
# Pin Message Endpoints
# =============================================================================

@router.post("/{conversation_id}/pin")
async def pin_message(
    conversation_id: str,
    data: PinMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """Pin a message in conversation."""
    conv = await ChatService.pin_message(conversation_id, data.message_id, current_user)

    # Notify via WebSocket
    from app.chat.websocket import notify_message_pinned
    await notify_message_pinned(conversation_id, data.message_id, str(current_user.id))

    return {
        "success": True,
        "data": {
            "pinned_messages": [
                {
                    "message_id": p.message_id,
                    "content": p.content,
                    "pinned_by": p.pinned_by,
                    "pinned_at": p.pinned_at.isoformat(),
                }
                for p in conv.pinned_messages
            ]
        },
    }


@router.delete("/{conversation_id}/pin/{message_id}")
async def unpin_message(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
):
    """Unpin a message from conversation."""
    conv = await ChatService.unpin_message(conversation_id, message_id, current_user)

    # Notify via WebSocket
    from app.chat.websocket import notify_message_unpinned
    await notify_message_unpinned(conversation_id, message_id, str(current_user.id))

    return {
        "success": True,
        "data": {
            "pinned_messages": [
                {
                    "message_id": p.message_id,
                    "content": p.content,
                    "pinned_by": p.pinned_by,
                    "pinned_at": p.pinned_at.isoformat(),
                }
                for p in conv.pinned_messages
            ]
        },
    }


# =============================================================================
# Mute Conversation Endpoints
# =============================================================================

@router.post("/{conversation_id}/mute")
async def mute_conversation(
    conversation_id: str,
    data: MuteConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """Mute a conversation."""
    conv = await ChatService.mute_conversation(
        conversation_id,
        current_user,
        data.duration_hours,
    )

    # Get mute status for current user
    is_muted = False
    muted_until = None
    if str(current_user.id) == conv.user1_id and conv.user1_muted_until:
        is_muted = True
        muted_until = conv.user1_muted_until.isoformat()
    elif str(current_user.id) == conv.user2_id and conv.user2_muted_until:
        is_muted = True
        muted_until = conv.user2_muted_until.isoformat()

    return {
        "success": True,
        "data": {
            "is_muted": is_muted,
            "muted_until": muted_until,
        },
    }


# =============================================================================
# Read Status Endpoints
# =============================================================================

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


# =============================================================================
# Sticker Endpoints
# =============================================================================

sticker_router = APIRouter(prefix="/stickers", tags=["Stickers"])


@sticker_router.get("/packs")
async def get_sticker_packs(
    current_user: User = Depends(get_current_user),
):
    """Get all available sticker packs."""
    packs = await StickerService.get_sticker_packs()
    return {
        "success": True,
        "data": {
            "packs": [
                {
                    "id": str(pack.id),
                    "name": pack.name,
                    "description": pack.description,
                    "thumbnail_url": pack.thumbnail_url,
                    "author": pack.author,
                    "is_official": pack.is_official,
                    "is_premium": pack.is_premium,
                    "sticker_count": pack.sticker_count,
                }
                for pack in packs
            ]
        },
    }


@sticker_router.get("/packs/{pack_id}")
async def get_sticker_pack(
    pack_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a sticker pack with all stickers."""
    pack, stickers = await StickerService.get_sticker_pack(pack_id)
    return {
        "success": True,
        "data": {
            "pack": {
                "id": str(pack.id),
                "name": pack.name,
                "description": pack.description,
                "thumbnail_url": pack.thumbnail_url,
                "author": pack.author,
                "is_official": pack.is_official,
                "is_premium": pack.is_premium,
                "sticker_count": pack.sticker_count,
            },
            "stickers": [
                {
                    "id": str(s.id),
                    "emoji": s.emoji,
                    "image_url": s.image_url,
                    "thumbnail_url": s.thumbnail_url,
                }
                for s in stickers
            ],
        },
    }


@sticker_router.get("/my-packs")
async def get_my_sticker_packs(
    current_user: User = Depends(get_current_user),
):
    """Get user's saved sticker packs."""
    packs = await StickerService.get_user_sticker_packs(current_user)
    return {
        "success": True,
        "data": {
            "packs": [
                {
                    "id": str(pack.id),
                    "name": pack.name,
                    "description": pack.description,
                    "thumbnail_url": pack.thumbnail_url,
                    "author": pack.author,
                    "is_official": pack.is_official,
                    "is_premium": pack.is_premium,
                    "sticker_count": pack.sticker_count,
                }
                for pack in packs
            ]
        },
    }


@sticker_router.post("/my-packs/{pack_id}")
async def add_sticker_pack(
    pack_id: str,
    current_user: User = Depends(get_current_user),
):
    """Add a sticker pack to user's collection."""
    await StickerService.add_sticker_pack(current_user, pack_id)
    return {"success": True, "message": "Sticker pack added"}


@sticker_router.delete("/my-packs/{pack_id}")
async def remove_sticker_pack(
    pack_id: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a sticker pack from user's collection."""
    await StickerService.remove_sticker_pack(current_user, pack_id)
    return {"success": True, "message": "Sticker pack removed"}


@sticker_router.get("/recent")
async def get_recent_stickers(
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_user),
):
    """Get user's recently used stickers."""
    stickers = await StickerService.get_recent_stickers(current_user, limit)
    return {
        "success": True,
        "data": {
            "stickers": [
                {
                    "id": str(s.id),
                    "emoji": s.emoji,
                    "image_url": s.image_url,
                    "thumbnail_url": s.thumbnail_url,
                }
                for s in stickers
            ]
        },
    }

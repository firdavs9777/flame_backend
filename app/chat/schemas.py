from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.message import MessageType


# =============================================================================
# Message Schemas
# =============================================================================

class MediaInfoResponse(BaseModel):
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_url: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None


class ReplyInfoResponse(BaseModel):
    message_id: str
    sender_id: str
    sender_name: str
    content: str
    type: str


class ReactionResponse(BaseModel):
    emoji: str
    user_id: str
    created_at: str


class MessageResponse(BaseModel):
    id: str
    sender_id: str
    content: str
    type: str
    timestamp: str
    status: str
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    file_url: Optional[str] = None
    sticker_id: Optional[str] = None
    media_info: Optional[MediaInfoResponse] = None
    reply_to: Optional[ReplyInfoResponse] = None
    reactions: List[ReactionResponse] = []
    is_edited: bool = False
    is_deleted: bool = False


# =============================================================================
# Conversation Schemas
# =============================================================================

class ConversationUserResponse(BaseModel):
    id: str
    name: str
    photos: List[str]
    is_online: bool


class PinnedMessageResponse(BaseModel):
    message_id: str
    content: str
    pinned_by: str
    pinned_at: str


class ConversationResponse(BaseModel):
    id: str
    match_id: str
    other_user: ConversationUserResponse
    last_message: Optional[MessageResponse] = None
    unread_count: int
    pinned_messages: List[PinnedMessageResponse] = []
    is_muted: bool = False
    muted_until: Optional[str] = None
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    pagination: dict


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    has_more: bool


# =============================================================================
# Request Schemas
# =============================================================================

class SendMessageRequest(BaseModel):
    content: str
    type: MessageType = MessageType.TEXT
    reply_to_id: Optional[str] = None  # Message ID to reply to


class SendStickerRequest(BaseModel):
    sticker_id: str
    reply_to_id: Optional[str] = None


class EditMessageRequest(BaseModel):
    content: str


class ReactToMessageRequest(BaseModel):
    emoji: str = Field(..., max_length=10)


class PinMessageRequest(BaseModel):
    message_id: str


class MuteConversationRequest(BaseModel):
    duration_hours: Optional[int] = None  # None = forever, 0 = unmute


class MarkReadRequest(BaseModel):
    message_ids: List[str]


# =============================================================================
# WebSocket Event Schemas
# =============================================================================

class WSMessage(BaseModel):
    event: str
    data: dict


class WSTypingEvent(BaseModel):
    conversation_id: str


class WSMessageReadEvent(BaseModel):
    conversation_id: str
    message_ids: List[str]


class WSReactionEvent(BaseModel):
    conversation_id: str
    message_id: str
    emoji: str


# =============================================================================
# Sticker Schemas
# =============================================================================

class StickerResponse(BaseModel):
    id: str
    emoji: str
    image_url: str
    thumbnail_url: str


class StickerPackResponse(BaseModel):
    id: str
    name: str
    description: str
    thumbnail_url: str
    author: str
    is_official: bool
    is_premium: bool
    sticker_count: int
    stickers: List[StickerResponse] = []


class StickerPackListResponse(BaseModel):
    packs: List[StickerPackResponse]

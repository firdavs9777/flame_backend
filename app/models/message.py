from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import Optional, Annotated, List
from datetime import datetime, timezone
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    GIF = "gif"
    STICKER = "sticker"
    FILE = "file"


class MessageStatus(str, Enum):
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Reaction(BaseModel):
    """Reaction on a message."""
    emoji: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MediaInfo(BaseModel):
    """Media metadata for video/audio messages."""
    duration: Optional[int] = None  # Duration in seconds
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_url: Optional[str] = None
    file_size: Optional[int] = None  # Size in bytes
    mime_type: Optional[str] = None


class ReplyInfo(BaseModel):
    """Info about the message being replied to."""
    message_id: str
    sender_id: str
    sender_name: str
    content: str  # Preview/truncated content
    type: MessageType


class Message(Document):
    conversation_id: Annotated[str, Indexed()]
    sender_id: Annotated[str, Indexed()]
    content: str
    type: MessageType = MessageType.TEXT
    status: MessageStatus = MessageStatus.SENT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Media URLs
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    file_url: Optional[str] = None
    sticker_id: Optional[str] = None

    # Media metadata
    media_info: Optional[MediaInfo] = None

    # Reply feature
    reply_to: Optional[ReplyInfo] = None

    # Reactions (emoji reactions like Telegram)
    reactions: List[Reaction] = Field(default_factory=list)

    # Edit tracking
    is_edited: bool = False
    edited_at: Optional[datetime] = None

    # Deletion (soft delete for "deleted for everyone")
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    class Settings:
        name = "messages"
        indexes = [
            "conversation_id",
            "sender_id",
            [("conversation_id", 1), ("timestamp", -1)],
            [("conversation_id", 1), ("is_deleted", 1)],
        ]

from beanie import Document, Indexed
from pydantic import Field
from typing import Optional, Annotated
from datetime import datetime, timezone
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    GIF = "gif"


class MessageStatus(str, Enum):
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Message(Document):
    conversation_id: Annotated[str, Indexed()]
    sender_id: Annotated[str, Indexed()]
    content: str
    type: MessageType = MessageType.TEXT
    status: MessageStatus = MessageStatus.SENT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # For image messages
    image_url: Optional[str] = None

    class Settings:
        name = "messages"
        indexes = [
            "conversation_id",
            "sender_id",
            [("conversation_id", 1), ("timestamp", -1)],
        ]

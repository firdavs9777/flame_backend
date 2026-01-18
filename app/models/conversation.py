from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import Optional, Annotated, List
from datetime import datetime, timezone


class PinnedMessage(BaseModel):
    """Info about a pinned message."""
    message_id: str
    content: str  # Preview content
    pinned_by: str  # User ID who pinned
    pinned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Conversation(Document):
    match_id: Annotated[str, Indexed(unique=True)]
    user1_id: Annotated[str, Indexed()]
    user2_id: Annotated[str, Indexed()]

    # Last message info for quick access
    last_message_id: Optional[str] = None
    last_message_content: Optional[str] = None
    last_message_sender_id: Optional[str] = None
    last_message_at: Optional[datetime] = None

    # Unread counts
    user1_unread_count: int = 0
    user2_unread_count: int = 0

    # Pinned messages (can have multiple like Telegram)
    pinned_messages: List[PinnedMessage] = Field(default_factory=list)

    # Mute settings per user
    user1_muted_until: Optional[datetime] = None
    user2_muted_until: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "conversations"
        indexes = [
            "match_id",
            "user1_id",
            "user2_id",
            [("user1_id", 1), ("updated_at", -1)],
            [("user2_id", 1), ("updated_at", -1)],
        ]

    def get_other_user_id(self, user_id: str) -> str:
        """Get the other user's ID in the conversation."""
        return self.user2_id if self.user1_id == user_id else self.user1_id

    def get_unread_count(self, user_id: str) -> int:
        """Get unread count for a specific user."""
        if self.user1_id == user_id:
            return self.user1_unread_count
        return self.user2_unread_count

    def increment_unread(self, for_user_id: str):
        """Increment unread count for a user."""
        if self.user1_id == for_user_id:
            self.user1_unread_count += 1
        else:
            self.user2_unread_count += 1

    def reset_unread(self, for_user_id: str):
        """Reset unread count for a user."""
        if self.user1_id == for_user_id:
            self.user1_unread_count = 0
        else:
            self.user2_unread_count = 0

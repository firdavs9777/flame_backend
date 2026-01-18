from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone


class Match(Document):
    user1_id: Annotated[str, Indexed()]
    user2_id: Annotated[str, Indexed()]
    matched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True  # False when unmatched

    # Track if each user has seen the match
    user1_seen: bool = False
    user2_seen: bool = False

    class Settings:
        name = "matches"
        indexes = [
            "user1_id",
            "user2_id",
            [("user1_id", 1), ("user2_id", 1)],
        ]

    def get_other_user_id(self, user_id: str) -> str:
        """Get the other user's ID in the match."""
        return self.user2_id if self.user1_id == user_id else self.user1_id

    def is_new_for_user(self, user_id: str) -> bool:
        """Check if this match is new (unseen) for a user."""
        if self.user1_id == user_id:
            return not self.user1_seen
        return not self.user2_seen

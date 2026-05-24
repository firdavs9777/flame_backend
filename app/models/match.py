from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone
import pymongo


class Match(Document):
    """A mutual swipe. `user_low` < `user_high` lexicographically so that
    (user_low, user_high) is a canonical pair with a unique index — this is
    what prevents duplicate matches from concurrent likes."""
    user1_id: Annotated[str, Indexed()]
    user2_id: Annotated[str, Indexed()]
    user_low: Annotated[str, Indexed()]
    user_high: Annotated[str, Indexed()]
    matched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True  # False when unmatched / blocked

    user1_seen: bool = False
    user2_seen: bool = False

    class Settings:
        name = "matches"
        indexes = [
            pymongo.IndexModel(
                [("user_low", pymongo.ASCENDING), ("user_high", pymongo.ASCENDING)],
                unique=True,
                name="uniq_match_pair",
            ),
            [("user1_id", pymongo.ASCENDING), ("is_active", pymongo.ASCENDING), ("matched_at", pymongo.DESCENDING)],
            [("user2_id", pymongo.ASCENDING), ("is_active", pymongo.ASCENDING), ("matched_at", pymongo.DESCENDING)],
        ]

    @staticmethod
    def canonical_pair(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def get_other_user_id(self, user_id: str) -> str:
        return self.user2_id if self.user1_id == user_id else self.user1_id

    def is_new_for_user(self, user_id: str) -> bool:
        if self.user1_id == user_id:
            return not self.user1_seen
        return not self.user2_seen

from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone


class Block(Document):
    blocker_id: Annotated[str, Indexed()]
    blocked_id: Annotated[str, Indexed()]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "blocks"
        indexes = [
            "blocker_id",
            "blocked_id",
            [("blocker_id", 1), ("blocked_id", 1)],
        ]

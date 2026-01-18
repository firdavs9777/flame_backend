from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone
from enum import Enum


class SwipeType(str, Enum):
    LIKE = "like"
    PASS = "pass"
    SUPER_LIKE = "super_like"


class Swipe(Document):
    swiper_id: Annotated[str, Indexed()]
    swiped_id: Annotated[str, Indexed()]
    swipe_type: SwipeType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "swipes"
        indexes = [
            [("swiper_id", 1), ("swiped_id", 1)],  # Compound index for quick lookup
        ]

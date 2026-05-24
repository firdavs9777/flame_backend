from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone
from enum import Enum
import pymongo


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
            pymongo.IndexModel(
                [("swiper_id", pymongo.ASCENDING), ("swiped_id", pymongo.ASCENDING)],
                unique=True,
                name="uniq_swiper_swiped",
            ),
            [("swiper_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        ]

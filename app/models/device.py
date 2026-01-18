from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone
from enum import Enum


class Platform(str, Enum):
    IOS = "ios"
    ANDROID = "android"


class Device(Document):
    user_id: Annotated[str, Indexed()]
    token: Annotated[str, Indexed(unique=True)]
    platform: Platform
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "devices"
        indexes = [
            "user_id",
            "token",
        ]

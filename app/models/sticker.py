from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated, List
from datetime import datetime, timezone


class Sticker(Document):
    """Individual sticker within a pack."""
    pack_id: Annotated[str, Indexed()]
    emoji: str  # Associated emoji for search
    image_url: str
    thumbnail_url: str
    order: int = 0

    class Settings:
        name = "stickers"
        indexes = [
            "pack_id",
            [("pack_id", 1), ("order", 1)],
        ]


class StickerPack(Document):
    """Sticker pack collection."""
    name: str
    description: str = ""
    thumbnail_url: str
    author: str = "Flame"
    is_official: bool = True
    is_premium: bool = False
    sticker_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "sticker_packs"


class UserStickerPack(Document):
    """User's saved sticker packs."""
    user_id: Annotated[str, Indexed()]
    pack_id: str
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_sticker_packs"
        indexes = [
            "user_id",
            [("user_id", 1), ("pack_id", 1)],
        ]


class RecentSticker(Document):
    """User's recently used stickers."""
    user_id: Annotated[str, Indexed()]
    sticker_id: str
    used_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "recent_stickers"
        indexes = [
            [("user_id", 1), ("used_at", -1)],
        ]

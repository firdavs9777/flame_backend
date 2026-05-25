from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone
from pymongo import IndexModel, ASCENDING


class RefreshToken(Document):
    user_id: Annotated[str, Indexed()]
    token_jti: Annotated[str, Indexed(unique=True)]  # JWT ID
    is_revoked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    class Settings:
        name = "refresh_tokens"
        indexes = [
            "user_id",
            "token_jti",
            # TTL index: MongoDB auto-deletes documents when expires_at is in the past
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]

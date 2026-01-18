from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated
from datetime import datetime, timezone


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
            "expires_at",
        ]

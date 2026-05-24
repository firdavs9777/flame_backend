"""Token revocation list backed by Redis.

We use:
  - per-token blocklist  : revoke a single access token by JTI
  - per-user epoch       : revoke ALL tokens issued before a timestamp
    (used on logout / password-change / password-reset)
"""
from datetime import datetime, timezone
from typing import Optional
from app.core.cache import cache


def _jti_key(jti: str) -> str:
    return f"jwt:revoked:{jti}"


def _user_epoch_key(user_id: str) -> str:
    return f"jwt:userepoch:{user_id}"


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Revoke a single access token by its JTI."""
    if not jti or ttl_seconds <= 0:
        return
    await cache.set(_jti_key(jti), "1", ttl=ttl_seconds)


async def is_jti_revoked(jti: Optional[str]) -> bool:
    if not jti:
        return False
    return await cache.exists(_jti_key(jti))


async def revoke_all_for_user(user_id: str) -> None:
    """Mark every token issued before *now* as invalid for this user."""
    ts = int(datetime.now(timezone.utc).timestamp())
    await cache.set(_user_epoch_key(user_id), str(ts))


async def user_token_revoked(user_id: str, issued_at: Optional[float]) -> bool:
    if not issued_at:
        return False
    val = await cache.get(_user_epoch_key(user_id))
    if not val:
        return False
    try:
        epoch = int(val)
    except ValueError:
        return False
    return issued_at < epoch

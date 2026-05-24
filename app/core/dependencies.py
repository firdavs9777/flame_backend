from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from bson import ObjectId
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.core.token_blocklist import is_jti_revoked, user_token_revoked
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def _user_from_payload(payload: dict) -> Optional[User]:
    user_id = payload.get("sub")
    if not user_id:
        return None
    try:
        ObjectId(user_id)
    except Exception:
        return None
    return await User.get(user_id)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get current authenticated user from JWT token."""
    if not credentials:
        raise UnauthorizedError()
    token = credentials.credentials

    payload = decode_token(token)
    if not payload:
        raise UnauthorizedError()

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    jti = payload.get("sub_jti") or payload.get("jti")
    if await is_jti_revoked(jti):
        raise UnauthorizedError("Token revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()
    if await user_token_revoked(user_id, payload.get("iat")):
        raise UnauthorizedError("Session expired, please log in again")

    user = await _user_from_payload(payload)
    if not user or user.is_deleted:
        raise UnauthorizedError("User not found")

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    payload = decode_token(token)
    if not payload:
        return None

    jti = payload.get("jti")
    if await is_jti_revoked(jti):
        return None
    user_id = payload.get("sub")
    if user_id and await user_token_revoked(user_id, payload.get("iat")):
        return None

    user = await _user_from_payload(payload)
    if user and user.is_deleted:
        return None
    return user


async def get_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user and ensure email is verified."""
    if not current_user.is_verified:
        raise ForbiddenError("Email not verified")
    return current_user

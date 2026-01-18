from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedError, TokenExpiredError
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials

    payload = decode_token(token)
    if not payload:
        raise UnauthorizedError()

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()

    user = await User.get(user_id)
    if not user:
        raise UnauthorizedError("User not found")

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]  # Remove "Bearer " prefix
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return await User.get(user_id)


async def get_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user and ensure email is verified."""
    if not current_user.is_verified:
        raise UnauthorizedError("Email not verified")
    return current_user

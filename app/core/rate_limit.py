"""Rate limit dependencies for FastAPI. Token bucket via Redis INCR + EXPIRE.

Falls open (allows the request) when Redis is unavailable so we never take
the app down because of cache issues — but the limiter is best-effort then.
"""
from typing import Optional
from fastapi import Depends, Request
from app.core.cache import rate_limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import RateLimitedError
from app.models.user import User


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only behind our nginx; nginx sets X-Real-IP.
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def ip_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per-IP rate limit. Use for unauthenticated endpoints."""
    async def _dep(request: Request):
        ip = _client_ip(request)
        key = f"rl:ip:{scope}:{ip}"
        if await rate_limiter.is_rate_limited(key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts. Try again later.")
    return _dep


def user_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per-user rate limit. Use for authenticated endpoints."""
    async def _dep(current_user: User = Depends(get_current_user)):
        key = f"rl:user:{scope}:{current_user.id}"
        if await rate_limiter.is_rate_limited(key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} requests. Try again later.")
    return _dep


def ip_and_email_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per (IP, email) — for login/forgot-password to prevent both IP-spamming
    and targeted brute-force against a single account."""
    async def _dep(request: Request, body: Optional[dict] = None):
        ip = _client_ip(request)
        # Best-effort: read email from already-parsed body if available
        email = ""
        try:
            payload = await request.json()
            email = (payload or {}).get("email", "")
        except Exception:
            pass
        ip_key = f"rl:ip:{scope}:{ip}"
        email_key = f"rl:email:{scope}:{email}" if email else None
        if await rate_limiter.is_rate_limited(ip_key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts from your IP. Try again later.")
        if email_key and await rate_limiter.is_rate_limited(email_key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts. Try again later.")
    return _dep

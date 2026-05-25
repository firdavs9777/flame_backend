"""Rate limit dependencies for FastAPI. Token bucket via Redis INCR + EXPIRE.

Falls open (allows the request) when Redis is unavailable so we never take
the app down because of cache issues — but the limiter is best-effort then.
"""
import ipaddress
import logging
from typing import Optional
from fastapi import Depends, Request
from app.core.cache import rate_limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import RateLimitedError
from app.models.user import User

logger = logging.getLogger(__name__)


# Subnets we treat as our own infrastructure (loopback + RFC1918 + Docker default
# bridge). X-Forwarded-For / X-Real-IP are only honored when the direct peer is
# one of these — otherwise a public client could spoof their source IP.
_TRUSTED_PROXY_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),  # Docker default bridge
    ipaddress.ip_network("192.168.0.0/16"),
]


def _client_ip(request: Request) -> str:
    """Resolve the real client IP, trusting forwarded headers only from
    known-internal proxies (nginx)."""
    direct = (request.client.host if request.client else "0.0.0.0")
    try:
        direct_ip = ipaddress.ip_address(direct)
        is_trusted = any(direct_ip in net for net in _TRUSTED_PROXY_NETWORKS)
    except ValueError:
        is_trusted = False

    if is_trusted:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # Leftmost IP is the original client
            return xff.split(",")[0].strip()
        real = request.headers.get("X-Real-IP")
        if real:
            return real.strip()
    return direct


async def _rate_limited_with_warn(key: str, max_requests: int, window_seconds: int) -> bool:
    """Wrapper around rate_limiter.is_rate_limited that emits a warning when
    the underlying Redis call fails (fail-open path), so SRE notices."""
    try:
        return await rate_limiter.is_rate_limited(key, max_requests, window_seconds)
    except Exception as e:
        # rate_limiter already swallows exceptions internally, but keep this as
        # a defensive net in case its implementation changes.
        logger.warning("Rate limit check failed (allowing request): %s", e)
        return False


def ip_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per-IP rate limit. Use for unauthenticated endpoints."""
    async def _dep(request: Request):
        ip = _client_ip(request)
        key = f"rl:ip:{scope}:{ip}"
        if not rate_limiter.cache.is_connected():
            logger.warning(
                "Rate limit check skipped for %s (Redis unavailable, allowing request)",
                scope,
            )
            return
        if await _rate_limited_with_warn(key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts. Try again later.")
    return _dep


def user_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per-user rate limit. Use for authenticated endpoints."""
    async def _dep(current_user: User = Depends(get_current_user)):
        key = f"rl:user:{scope}:{current_user.id}"
        if not rate_limiter.cache.is_connected():
            logger.warning(
                "Rate limit check skipped for %s (Redis unavailable, allowing request)",
                scope,
            )
            return
        if await _rate_limited_with_warn(key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} requests. Try again later.")
    return _dep


def email_rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Per-email rate limit (email extracted from JSON request body).

    Use IN ADDITION to ip_rate_limit on endpoints like /login and
    /forgot-password so a distributed botnet can't bypass per-IP limits."""
    async def _dep(request: Request):
        try:
            body = await request.json()
            email = (body.get("email") or "").lower().strip()
        except Exception:
            email = ""
        if not email:
            return
        if not rate_limiter.cache.is_connected():
            logger.warning(
                "Rate limit check skipped for %s (Redis unavailable, allowing request)",
                scope,
            )
            return
        key = f"rl:email:{scope}:{email}"
        if await _rate_limited_with_warn(key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts. Try again later.")
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
        if not rate_limiter.cache.is_connected():
            logger.warning(
                "Rate limit check skipped for %s (Redis unavailable, allowing request)",
                scope,
            )
            return
        ip_key = f"rl:ip:{scope}:{ip}"
        email_key = f"rl:email:{scope}:{email}" if email else None
        if await _rate_limited_with_warn(ip_key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts from your IP. Try again later.")
        if email_key and await _rate_limited_with_warn(email_key, max_requests, window_seconds):
            raise RateLimitedError(f"Too many {scope} attempts. Try again later.")
    return _dep

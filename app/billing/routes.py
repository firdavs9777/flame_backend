"""Subscription / IAP verification endpoints.

Premium entitlement is driven exclusively by validated receipts from
Apple StoreKit or Google Play Billing. Direct writes to User.is_premium
must never happen elsewhere.

External setup required:
  - Apple: server-to-server notifications v2 → POST /v1/billing/apple/notify
           Set up shared secret in App Store Connect.
  - Google: Pub/Sub → POST /v1/billing/google/notify
            Set up RTDN topic and a verifier on the pubsub message.

For now, /verify endpoints accept the receipt from the client and re-verify
against the store before granting entitlement.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
import httpx
import logging

from app.core.dependencies import get_current_user
from app.core.exceptions import ValidationError, ForbiddenError
from app.core.rate_limit import user_rate_limit
from app.models.user import User
from app.models.subscription import (
    Subscription,
    SubscriptionPlatform,
    SubscriptionStatus,
)
from app.community.service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

_VERIFY_LIMIT = Depends(user_rate_limit("billing_verify", max_requests=20, window_seconds=3600))


class AppleVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_data: str  # base64 receipt from StoreKit
    product_id: str


class GoogleVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_token: str
    product_id: str
    package_name: str


@router.post("/apple/verify", dependencies=[_VERIFY_LIMIT])
async def verify_apple_receipt(
    data: AppleVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """Verify Apple receipt and grant entitlement.

    Currently a stub — Apple's verifyReceipt endpoint is being deprecated in
    favor of App Store Server API. Wire APPLE_SHARED_SECRET into config and
    implement actual verification before going live.
    """
    raise ForbiddenError(
        "Apple receipt verification not configured. "
        "Set APPLE_SHARED_SECRET and implement App Store Server API verification."
    )


@router.post("/google/verify", dependencies=[_VERIFY_LIMIT])
async def verify_google_purchase(
    data: GoogleVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """Verify Google Play purchase. Stub — requires Google service-account JSON."""
    raise ForbiddenError(
        "Google Play verification not configured. "
        "Set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON and implement androidpublisher v3."
    )


@router.get("/status")
async def billing_status(current_user: User = Depends(get_current_user)):
    """Return the user's current entitlement (and most recent subscription)."""
    active_sub = await Subscription.find_one({
        "user_id": str(current_user.id),
        "status": SubscriptionStatus.ACTIVE.value,
    })
    return {
        "success": True,
        "data": {
            "is_premium": SubscriptionService.is_premium(current_user),
            "premium_expires_at": current_user.premium_expires_at.isoformat()
                if current_user.premium_expires_at else None,
            "subscription": {
                "platform": active_sub.platform.value,
                "product_id": active_sub.product_id,
                "current_period_end": active_sub.current_period_end.isoformat()
                    if active_sub and active_sub.current_period_end else None,
            } if active_sub else None,
        },
    }


# Webhook stubs — wire these into store dashboards
@router.post("/apple/notify")
async def apple_server_notification(request: Request):
    """Apple App Store Server Notifications v2 endpoint.

    See: https://developer.apple.com/documentation/appstoreservernotifications
    Body is a JWS-signed payload. Verify the signature against Apple's
    public keys before trusting the payload.
    """
    logger.warning("Apple notify received but handler not implemented")
    return {"received": True}


@router.post("/google/notify")
async def google_rtdn(request: Request):
    """Google Play Real-Time Developer Notifications via Pub/Sub push."""
    logger.warning("Google RTDN received but handler not implemented")
    return {"received": True}

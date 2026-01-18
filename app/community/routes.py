from fastapi import APIRouter, Depends, UploadFile, File, Query, status
from typing import Optional, List
from app.core.dependencies import get_current_user
from app.models.user import User
from app.community.schemas import (
    UpdateProfileRequest,
    UpdateLocationRequest,
    UpdatePreferencesRequest,
    UpdateNotificationsRequest,
    ReorderPhotosRequest,
    DeleteAccountRequest,
    SwipeRequest,
    ReportRequest,
    BlockRequest,
    RegisterDeviceRequest,
)
from app.community.service import (
    UserService,
    DiscoveryService,
    SwipeService,
    MatchService,
    BlockService,
    ReportService,
)
from app.models.device import Device, Platform

router = APIRouter(tags=["Community"])


# Helper functions
def format_full_user(user: User) -> dict:
    """Format user for full response."""
    location = None
    if user.location:
        location = {
            "city": user.location.city,
            "state": user.location.state,
            "country": user.location.country,
            "coordinates": {
                "latitude": user.location.coordinates.latitude,
                "longitude": user.location.coordinates.longitude,
            } if user.location.coordinates else None,
        }

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "age": user.age,
        "gender": user.gender.value,
        "looking_for": user.looking_for.value,
        "bio": user.bio,
        "interests": user.interests,
        "photos": [
            {
                "id": p.id,
                "url": p.url,
                "is_primary": p.is_primary,
                "order": p.order,
            }
            for p in user.photos
        ],
        "location": location,
        "is_online": user.is_online,
        "is_verified": user.is_verified,
        "last_active": user.last_active.isoformat(),
        "created_at": user.created_at.isoformat(),
        "preferences": {
            "min_age": user.preferences.min_age,
            "max_age": user.preferences.max_age,
            "max_distance": user.preferences.max_distance,
            "show_distance": user.preferences.show_distance,
            "show_online_status": user.preferences.show_online_status,
        },
        "settings": {
            "notifications_enabled": user.settings.notifications_enabled,
            "discovery_enabled": user.settings.discovery_enabled,
            "dark_mode": user.settings.dark_mode,
        },
    }


def format_public_user(user: User, distance: Optional[float] = None, common_interests: Optional[List[str]] = None) -> dict:
    """Format user for public response."""
    location_str = None
    if user.location:
        parts = [user.location.city, user.location.state]
        location_str = ", ".join(filter(None, parts))

    return {
        "id": str(user.id),
        "name": user.name,
        "age": user.age,
        "gender": user.gender.value,
        "bio": user.bio,
        "interests": user.interests,
        "photos": [p.url for p in user.photos],
        "location": location_str,
        "distance": round(distance, 1) if distance else None,
        "is_online": user.is_online,
        "last_active": user.last_active.isoformat(),
        "common_interests": common_interests,
    }


# User Profile Endpoints
@router.get("/users/me")
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile."""
    return {
        "success": True,
        "data": format_full_user(current_user),
    }


@router.patch("/users/me")
async def update_profile(
    data: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
):
    """Update current user's profile."""
    updated = await UserService.update_profile(
        current_user,
        data.model_dump(exclude_unset=True),
    )
    return {
        "success": True,
        "data": format_full_user(updated),
    }


@router.patch("/users/me/location")
async def update_location(
    data: UpdateLocationRequest,
    current_user: User = Depends(get_current_user),
):
    """Update user location."""
    updated = await UserService.update_location(
        current_user,
        data.latitude,
        data.longitude,
    )
    location = None
    if updated.location:
        location = {
            "city": updated.location.city,
            "state": updated.location.state,
            "country": updated.location.country,
            "coordinates": {
                "latitude": updated.location.coordinates.latitude,
                "longitude": updated.location.coordinates.longitude,
            } if updated.location.coordinates else None,
        }
    return {
        "success": True,
        "data": {"location": location},
    }


@router.patch("/users/me/preferences")
async def update_preferences(
    data: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
):
    """Update user preferences."""
    updated = await UserService.update_preferences(
        current_user,
        data.model_dump(exclude_unset=True),
    )
    return {
        "success": True,
        "data": {
            "preferences": {
                "min_age": updated.preferences.min_age,
                "max_age": updated.preferences.max_age,
                "max_distance": updated.preferences.max_distance,
                "show_distance": updated.preferences.show_distance,
                "show_online_status": updated.preferences.show_online_status,
            }
        },
    }


@router.patch("/users/me/notifications")
async def update_notifications(
    data: UpdateNotificationsRequest,
    current_user: User = Depends(get_current_user),
):
    """Update notification settings."""
    updated = await UserService.update_notification_settings(
        current_user,
        data.model_dump(exclude_unset=True),
    )
    return {
        "success": True,
        "data": {
            "notifications": {
                "new_matches": updated.notification_settings.new_matches,
                "new_messages": updated.notification_settings.new_messages,
                "super_likes": updated.notification_settings.super_likes,
                "promotions": updated.notification_settings.promotions,
            }
        },
    }


@router.post("/users/me/photos", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    photo: UploadFile = File(...),
    is_primary: bool = False,
    current_user: User = Depends(get_current_user),
):
    """Upload a new photo."""
    from app.core.storage import storage

    # Upload to DigitalOcean Spaces
    photo_url = await storage.upload_user_photo(str(current_user.id), photo)

    new_photo = await UserService.add_photo(current_user, photo_url, is_primary)
    return {
        "success": True,
        "data": {
            "id": new_photo.id,
            "url": new_photo.url,
            "is_primary": new_photo.is_primary,
            "order": new_photo.order,
        },
    }


@router.delete("/users/me/photos/{photo_id}")
async def delete_photo(
    photo_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a photo."""
    await UserService.delete_photo(current_user, photo_id)
    return {"success": True, "message": "Photo deleted successfully"}


@router.patch("/users/me/photos/reorder")
async def reorder_photos(
    data: ReorderPhotosRequest,
    current_user: User = Depends(get_current_user),
):
    """Reorder photos."""
    photos = await UserService.reorder_photos(current_user, data.photo_ids)
    return {
        "success": True,
        "data": {
            "photos": [
                {"id": p.id, "order": p.order, "is_primary": p.is_primary}
                for p in photos
            ]
        },
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a user's public profile."""
    user = await UserService.get_user_by_id(user_id, current_user)
    return {
        "success": True,
        "data": format_public_user(user),
    }


@router.delete("/users/me")
async def delete_account(
    data: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
):
    """Delete user account."""
    await UserService.delete_account(current_user, data.password, data.reason)
    return {"success": True, "message": "Account successfully deleted"}


# Discovery Endpoints
@router.get("/discover")
async def discover(
    limit: int = Query(default=10, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """Get potential matches."""
    results, total = await DiscoveryService.get_potential_matches(
        current_user,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "data": {
            "users": [
                format_public_user(
                    r["user"],
                    distance=r.get("distance"),
                    common_interests=r.get("common_interests"),
                )
                for r in results
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        },
    }


# Swipe Endpoints
@router.post("/swipes/like")
async def like_user(
    data: SwipeRequest,
    current_user: User = Depends(get_current_user),
):
    """Like a user (swipe right)."""
    is_match, match = await SwipeService.like(current_user, data.user_id)

    response = {
        "success": True,
        "data": {
            "liked": True,
            "is_match": is_match,
        },
    }

    if match:
        matched_user = await User.get(data.user_id)
        match_data = {
            "id": str(match.id),
            "user": {
                "id": data.user_id,
                "name": matched_user.name if matched_user else None,
                "photos": [p.url for p in matched_user.photos] if matched_user else [],
            },
            "matched_at": match.matched_at.isoformat(),
        }
        response["data"]["match"] = match_data

        # Notify the other user about the match via WebSocket
        from app.chat.websocket import notify_new_match
        await notify_new_match(data.user_id, {
            "match": match_data,
            "user": {
                "id": str(current_user.id),
                "name": current_user.name,
                "photos": [p.url for p in current_user.photos],
            },
        })

    return response


@router.post("/swipes/pass")
async def pass_user(
    data: SwipeRequest,
    current_user: User = Depends(get_current_user),
):
    """Pass on a user (swipe left)."""
    await SwipeService.pass_user(current_user, data.user_id)
    return {
        "success": True,
        "data": {"passed": True},
    }


@router.post("/swipes/super-like")
async def super_like_user(
    data: SwipeRequest,
    current_user: User = Depends(get_current_user),
):
    """Super like a user."""
    is_match, match, remaining = await SwipeService.super_like(current_user, data.user_id)

    response = {
        "success": True,
        "data": {
            "super_liked": True,
            "is_match": is_match,
            "remaining_super_likes": remaining,
        },
    }

    if match:
        matched_user = await User.get(data.user_id)
        match_data = {
            "id": str(match.id),
            "user": {
                "id": data.user_id,
                "name": matched_user.name if matched_user else None,
                "photos": [p.url for p in matched_user.photos] if matched_user else [],
            },
            "matched_at": match.matched_at.isoformat(),
        }
        response["data"]["match"] = match_data

        # Notify the other user about the match via WebSocket
        from app.chat.websocket import notify_new_match
        await notify_new_match(data.user_id, {
            "match": match_data,
            "user": {
                "id": str(current_user.id),
                "name": current_user.name,
                "photos": [p.url for p in current_user.photos],
            },
        })

    return response


@router.post("/swipes/undo")
async def undo_swipe(current_user: User = Depends(get_current_user)):
    """Undo last swipe."""
    swipe = await SwipeService.undo_last_swipe(current_user)
    swiped_user = await User.get(swipe.swiped_id)
    return {
        "success": True,
        "data": {
            "undone": True,
            "user": {
                "id": swipe.swiped_id,
                "name": swiped_user.name if swiped_user else None,
            },
        },
    }


# Match Endpoints
@router.get("/matches")
async def get_matches(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    new_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
):
    """Get all matches."""
    results, total = await MatchService.get_matches(
        current_user,
        limit=limit,
        offset=offset,
        new_only=new_only,
    )
    return {
        "success": True,
        "data": {
            "matches": [
                {
                    "id": str(r["match"].id),
                    "user": {
                        "id": str(r["other_user"].id),
                        "name": r["other_user"].name,
                        "age": r["other_user"].age,
                        "photos": [p.url for p in r["other_user"].photos],
                        "is_online": r["other_user"].is_online,
                        "last_active": r["other_user"].last_active.isoformat(),
                    },
                    "matched_at": r["match"].matched_at.isoformat(),
                    "is_new": r["is_new"],
                    "last_message": r["last_message"],
                }
                for r in results
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        },
    }


@router.delete("/matches/{match_id}")
async def unmatch(
    match_id: str,
    current_user: User = Depends(get_current_user),
):
    """Unmatch with a user."""
    await MatchService.unmatch(current_user, match_id)
    return {"success": True, "message": "Successfully unmatched"}


# Reporting & Blocking Endpoints
@router.post("/reports", status_code=status.HTTP_201_CREATED)
async def report_user(
    data: ReportRequest,
    current_user: User = Depends(get_current_user),
):
    """Report a user."""
    await ReportService.report_user(
        current_user,
        data.user_id,
        data.reason,
        data.details,
    )
    return {"success": True, "message": "Report submitted successfully"}


@router.post("/blocks", status_code=status.HTTP_201_CREATED)
async def block_user(
    data: BlockRequest,
    current_user: User = Depends(get_current_user),
):
    """Block a user."""
    await BlockService.block_user(current_user, data.user_id)
    return {"success": True, "message": "User blocked successfully"}


@router.delete("/blocks/{user_id}")
async def unblock_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Unblock a user."""
    await BlockService.unblock_user(current_user, user_id)
    return {"success": True, "message": "User unblocked successfully"}


@router.get("/blocks")
async def get_blocked_users(current_user: User = Depends(get_current_user)):
    """Get list of blocked users."""
    blocked = await BlockService.get_blocked_users(current_user)
    return {
        "success": True,
        "data": {"blocked_users": blocked},
    }


# Device Registration
@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    data: RegisterDeviceRequest,
    current_user: User = Depends(get_current_user),
):
    """Register device for push notifications."""
    platform = Platform.IOS if data.platform == "ios" else Platform.ANDROID

    existing = await Device.find_one(Device.token == data.token)
    if existing:
        existing.user_id = str(current_user.id)
        existing.platform = platform
        await existing.save()
    else:
        device = Device(
            user_id=str(current_user.id),
            token=data.token,
            platform=platform,
        )
        await device.insert()

    return {"success": True, "message": "Device registered successfully"}

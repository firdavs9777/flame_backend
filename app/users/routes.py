from fastapi import APIRouter, Depends, status, UploadFile, File
from typing import List
import uuid

from app.core.dependencies import get_current_user
from app.core.storage import storage
from app.core.exceptions import AppException
from app.models.user import User, Photo

router = APIRouter(prefix="/users", tags=["Users"])

# Allowed file types
ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
]

MAX_PHOTOS = 6
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB for images


def validate_image_file(file: UploadFile) -> None:
    """Validate that the uploaded file is an allowed image type."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise AppException(
            status_code=400,
            code="INVALID_FILE_TYPE",
            message=f"File type not allowed. Supported: JPEG, PNG, GIF, WebP",
        )


@router.put("/{user_id}/profile-picture", status_code=status.HTTP_200_OK)
async def update_profile_picture(
    user_id: str,
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Update the user's primary profile picture.
    Replaces the current primary photo or adds as primary if none exists.
    """
    # Verify user is updating their own profile
    if str(current_user.id) != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="You can only update your own profile picture",
        )

    # Validate file type
    validate_image_file(photo)

    # Upload to storage
    photo_url = await storage.upload_user_photo(user_id, photo)

    # Create new photo object
    new_photo = Photo(
        id=str(uuid.uuid4()),
        url=photo_url,
        is_primary=True,
        order=0,
    )

    # Update existing photos: remove primary flag from others
    updated_photos = []
    for p in current_user.photos:
        if p.is_primary:
            # Optionally delete old primary from storage
            await storage.delete_file(p.url)
        else:
            updated_photos.append(p)

    # Add new primary photo at the beginning
    updated_photos.insert(0, new_photo)

    # Update user
    current_user.photos = updated_photos
    await current_user.save()

    return {
        "success": True,
        "data": {
            "id": new_photo.id,
            "url": new_photo.url,
            "is_primary": new_photo.is_primary,
            "order": new_photo.order,
        },
    }


@router.put("/{user_id}/photo", status_code=status.HTTP_200_OK)
async def add_single_photo(
    user_id: str,
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Add a single photo to the user's profile.
    """
    # Verify user is updating their own profile
    if str(current_user.id) != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="You can only update your own photos",
        )

    # Check max photos limit
    if len(current_user.photos) >= MAX_PHOTOS:
        raise AppException(
            status_code=400,
            code="MAX_PHOTOS_REACHED",
            message=f"Maximum {MAX_PHOTOS} photos allowed",
        )

    # Validate file type
    validate_image_file(photo)

    # Upload to storage
    photo_url = await storage.upload_user_photo(user_id, photo)

    # Create new photo object
    is_primary = len(current_user.photos) == 0  # Primary if first photo
    new_photo = Photo(
        id=str(uuid.uuid4()),
        url=photo_url,
        is_primary=is_primary,
        order=len(current_user.photos),
    )

    # Add to user's photos
    current_user.photos.append(new_photo)
    await current_user.save()

    return {
        "success": True,
        "data": {
            "id": new_photo.id,
            "url": new_photo.url,
            "is_primary": new_photo.is_primary,
            "order": new_photo.order,
        },
    }


@router.post("/{user_id}/photos", status_code=status.HTTP_201_CREATED)
async def upload_multiple_photos(
    user_id: str,
    photos: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload multiple photos at once (max 5 per request).
    """
    # Verify user is updating their own profile
    if str(current_user.id) != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="You can only update your own photos",
        )

    # Limit photos per request
    if len(photos) > 5:
        raise AppException(
            status_code=400,
            code="TOO_MANY_FILES",
            message="Maximum 5 photos per request",
        )

    # Check total photos limit
    remaining_slots = MAX_PHOTOS - len(current_user.photos)
    if len(photos) > remaining_slots:
        raise AppException(
            status_code=400,
            code="MAX_PHOTOS_EXCEEDED",
            message=f"Can only add {remaining_slots} more photo(s). Maximum {MAX_PHOTOS} photos allowed.",
        )

    # Validate all files first
    for photo in photos:
        validate_image_file(photo)

    # Upload all photos
    uploaded_photos = []
    current_order = len(current_user.photos)
    has_primary = any(p.is_primary for p in current_user.photos)

    for i, photo in enumerate(photos):
        photo_url = await storage.upload_user_photo(user_id, photo)

        new_photo = Photo(
            id=str(uuid.uuid4()),
            url=photo_url,
            is_primary=(not has_primary and i == 0),  # First photo is primary if none exists
            order=current_order + i,
        )
        uploaded_photos.append(new_photo)
        current_user.photos.append(new_photo)

        if new_photo.is_primary:
            has_primary = True

    await current_user.save()

    return {
        "success": True,
        "data": {
            "photos": [
                {
                    "id": p.id,
                    "url": p.url,
                    "is_primary": p.is_primary,
                    "order": p.order,
                }
                for p in uploaded_photos
            ],
            "total_photos": len(current_user.photos),
        },
    }


@router.delete("/{user_id}/photos/{photo_id}", status_code=status.HTTP_200_OK)
async def delete_photo(
    user_id: str,
    photo_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Delete a photo from the user's profile.
    """
    # Verify user is updating their own profile
    if str(current_user.id) != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="You can only delete your own photos",
        )

    # Find the photo
    photo_to_delete = None
    for p in current_user.photos:
        if p.id == photo_id:
            photo_to_delete = p
            break

    if not photo_to_delete:
        raise AppException(
            status_code=404,
            code="PHOTO_NOT_FOUND",
            message="Photo not found",
        )

    # Must have at least 1 photo
    if len(current_user.photos) <= 1:
        raise AppException(
            status_code=400,
            code="MIN_PHOTOS_REQUIRED",
            message="Must have at least 1 photo",
        )

    # Delete from storage
    await storage.delete_file(photo_to_delete.url)

    # Remove from user's photos
    current_user.photos = [p for p in current_user.photos if p.id != photo_id]

    # If deleted photo was primary, make first photo primary
    if photo_to_delete.is_primary and current_user.photos:
        current_user.photos[0].is_primary = True

    # Reorder remaining photos
    for i, p in enumerate(current_user.photos):
        p.order = i

    await current_user.save()

    return {
        "success": True,
        "message": "Photo deleted successfully",
        "data": {
            "remaining_photos": len(current_user.photos),
        },
    }


@router.put("/{user_id}/photos/reorder", status_code=status.HTTP_200_OK)
async def reorder_photos(
    user_id: str,
    photo_ids: List[str],
    current_user: User = Depends(get_current_user),
):
    """
    Reorder user's photos. First photo in the list becomes primary.
    """
    # Verify user is updating their own profile
    if str(current_user.id) != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="You can only reorder your own photos",
        )

    # Verify all photo IDs exist
    existing_ids = {p.id for p in current_user.photos}
    if set(photo_ids) != existing_ids:
        raise AppException(
            status_code=400,
            code="INVALID_PHOTO_IDS",
            message="Photo IDs don't match existing photos",
        )

    # Create photo map
    photo_map = {p.id: p for p in current_user.photos}

    # Reorder photos
    reordered = []
    for i, pid in enumerate(photo_ids):
        photo = photo_map[pid]
        photo.order = i
        photo.is_primary = (i == 0)  # First photo is primary
        reordered.append(photo)

    current_user.photos = reordered
    await current_user.save()

    return {
        "success": True,
        "data": {
            "photos": [
                {
                    "id": p.id,
                    "url": p.url,
                    "is_primary": p.is_primary,
                    "order": p.order,
                }
                for p in current_user.photos
            ],
        },
    }

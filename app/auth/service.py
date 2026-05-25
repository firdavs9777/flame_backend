from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid
import hashlib
from app.models.user import User, Photo, UserPreferences, Location, Coordinates, GeoPoint
from app.models.refresh_token import RefreshToken
from app.models.device import Device, Platform
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_verification_code,
    generate_password_reset_token,
)
from app.core.config import settings
from app.core.exceptions import (
    EmailExistsError,
    InvalidCredentialsError,
    NotFoundError,
    ValidationError,
    TokenExpiredError,
)
from app.auth.schemas import RegisterRequest, TokenResponse
from app.core.token_blocklist import revoke_all_for_user, revoke_jti
from pymongo.errors import DuplicateKeyError
import secrets


# Real bcrypt hash computed once at import time. Used to equalize timing on
# login when the user/email doesn't exist (defeats email-enumeration via timing).
_DUMMY_HASH = get_password_hash("not-a-real-password")


class AuthService:
    # Class-level alias so callers within the service can reference it explicitly.
    _DUMMY_HASH = _DUMMY_HASH

    @staticmethod
    async def register(data: RegisterRequest) -> Tuple[User, TokenResponse]:
        """Register a new user."""
        # Check if email exists
        existing_user = await User.find_one(User.email == data.email)
        if existing_user:
            raise EmailExistsError()

        # Upload photos to DigitalOcean Spaces
        from app.core.storage import storage

        # Generate a temporary user ID for photo uploads
        temp_user_id = str(uuid.uuid4())[:8]

        photo_urls = []
        for photo_data in data.photos:
            if storage.is_base64_image(photo_data):
                # Upload base64 image to cloud storage
                url = await storage.upload_base64_image(photo_data, temp_user_id)
                photo_urls.append(url)
            else:
                # Already a URL, use as-is
                photo_urls.append(photo_data)

        # Create photos list
        photos = [
            Photo(
                id=f"photo_{i}",
                url=url,
                is_primary=(i == 0),
                order=i,
            )
            for i, url in enumerate(photo_urls)
        ]

        # Reverse geocode (best-effort, short timeout — never blocks registration)
        from app.core.location import location_service
        try:
            city, state, country = await location_service.reverse_geocode(
                data.latitude, data.longitude
            )
        except Exception:
            city, state, country = None, None, None

        location = Location(
            city=city,
            state=state,
            country=country,
            coordinates=Coordinates(
                latitude=data.latitude,
                longitude=data.longitude,
            ),
        )
        location_geo = GeoPoint(coordinates=[data.longitude, data.latitude])

        # Create user
        verification_code = generate_verification_code()
        user = User(
            email=data.email,
            password_hash=get_password_hash(data.password),
            name=data.name,
            age=data.age,
            gender=data.gender,
            looking_for=data.looking_for,
            bio=data.bio,
            interests=data.interests,
            photos=photos,
            location=location,
            location_geo=location_geo,
            is_online=True,
            verification_code=verification_code,
            verification_code_expires=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

        try:
            await user.insert()
        except DuplicateKeyError:
            raise EmailExistsError()

        # Send verification email with 6-digit code
        from app.core.email import email_service
        await email_service.send_verification_code(
            to=user.email,
            name=user.name,
            code=verification_code,
        )

        # Create tokens
        tokens = await AuthService._create_tokens(str(user.id))

        return user, tokens

    @staticmethod
    async def login(email: str, password: str, device_token: Optional[str] = None) -> Tuple[User, TokenResponse]:
        """Authenticate user and return tokens. Constant-time wrt email existence."""
        user = await User.find_one(User.email == email)

        # Always run bcrypt against SOMETHING so attackers can't time-detect email existence.
        # Covers both "no user" and "user exists but is social-only (no password)".
        if not user or not user.password_hash:
            try:
                verify_password(password, AuthService._DUMMY_HASH)
            except Exception:
                pass
            raise InvalidCredentialsError()

        try:
            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError()
        except Exception as e:
            # Any malformed hash (e.g., legacy data) → treat as invalid creds, never 500
            if isinstance(e, InvalidCredentialsError):
                raise
            raise InvalidCredentialsError()

        # Update online status
        user.is_online = True
        user.last_active = datetime.now(timezone.utc)
        await user.save()

        # Register device if token provided
        if device_token:
            await AuthService._register_device(str(user.id), device_token)

        # Create tokens
        tokens = await AuthService._create_tokens(str(user.id))

        return user, tokens

    @staticmethod
    async def refresh_tokens(refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token. Atomic + detects token reuse."""
        payload = decode_token(refresh_token)
        if not payload:
            raise InvalidCredentialsError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise InvalidCredentialsError("Invalid token type")

        jti = payload.get("jti")
        if not jti:
            raise InvalidCredentialsError("Invalid refresh token")

        # Atomic compare-and-swap: only one concurrent request wins
        result = await RefreshToken.get_motor_collection().find_one_and_update(
            {"token_jti": jti, "is_revoked": False},
            {"$set": {"is_revoked": True}},
        )

        if result is None:
            # Either unknown jti or already revoked → possible token theft
            existing = await RefreshToken.find_one(RefreshToken.token_jti == jti)
            if existing and existing.is_revoked:
                # Revoke entire token family for this user
                await RefreshToken.find(RefreshToken.user_id == existing.user_id).update(
                    {"$set": {"is_revoked": True}}
                )
                await revoke_all_for_user(existing.user_id)
            raise InvalidCredentialsError("Token has been revoked")

        user_id = payload.get("sub")
        return await AuthService._create_tokens(user_id)

    @staticmethod
    async def logout(user_id: str, access_token: Optional[str] = None):
        """Logout user: invalidate ALL refresh tokens AND existing access tokens."""
        user = await User.get(user_id)
        if user:
            user.is_online = False
            await user.save()

        await RefreshToken.find(RefreshToken.user_id == user_id).update(
            {"$set": {"is_revoked": True}}
        )
        await revoke_all_for_user(user_id)

        # Explicitly revoke the current access token's JTI (defense-in-depth on top of epoch).
        if access_token:
            payload = decode_token(access_token)
            if payload and payload.get("jti"):
                exp = payload.get("exp", 0)
                ttl = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
                await revoke_jti(payload["jti"], ttl_seconds=ttl)

        # Unregister device(s) so push notifications stop after logout.
        await Device.find(Device.user_id == user_id).delete()

    @staticmethod
    async def forgot_password(email: str):
        """Send password reset token."""
        from app.core.email import email_service

        user = await User.find_one(User.email == email)
        if not user or not user.password_hash:
            # Don't reveal if email exists or if account is social-only
            return

        reset_token = generate_password_reset_token()
        token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        user.password_reset_token = token_hash
        user.password_reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await user.save()

        # Email gets the plaintext token; DB only has the SHA-256 hash.
        await email_service.send_password_reset_token(
            to=user.email,
            name=user.name,
            token=reset_token,
        )

    @staticmethod
    async def reset_password(token: str, password: str, password_confirmation: str):
        """Reset password using token from email. Atomic single-use."""
        if password != password_confirmation:
            raise ValidationError("Passwords do not match")

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        new_hash = get_password_hash(password)

        # Atomic: find a user with a valid unexpired token AND consume it in one op.
        # If two concurrent requests race with the same token, only one wins; the other
        # gets None back and we raise.
        result = await User.get_motor_collection().find_one_and_update(
            {
                "password_reset_token": token_hash,
                "password_reset_token_expires": {"$gt": now},
            },
            {
                "$set": {
                    "password_hash": new_hash,
                    "password_reset_token": None,
                    "password_reset_token_expires": None,
                    "updated_at": now,
                }
            },
        )

        if result is None:
            raise ValidationError("Invalid or expired reset token")

        user_id = str(result["_id"])

        # Revoke all refresh AND access tokens for security
        await RefreshToken.find(RefreshToken.user_id == user_id).update(
            {"$set": {"is_revoked": True}}
        )
        await revoke_all_for_user(user_id)

    @staticmethod
    async def verify_email(email: str, code: str):
        """Verify user email with 6-digit code. Locks after 5 wrong attempts."""
        user = await User.find_one(User.email == email)
        if not user or not user.verification_code:
            raise ValidationError("Invalid email or verification code")

        # Check expiration first - handle both naive and timezone-aware datetimes
        expires = user.verification_code_expires
        if expires is None:
            raise TokenExpiredError("Verification code has expired")
        now = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            raise TokenExpiredError("Verification code has expired")

        # Hard lock after too many failed attempts — burn the code, force a resend.
        if (user.verification_attempts or 0) >= 5:
            user.verification_code = None
            user.verification_code_expires = None
            user.verification_attempts = 0
            await user.save()
            raise ValidationError("Too many failed attempts. Request a new code.")

        if not secrets.compare_digest(user.verification_code, code):
            user.verification_attempts = (user.verification_attempts or 0) + 1
            await user.save()
            raise ValidationError("Invalid email or verification code")

        user.is_verified = True
        user.verification_code = None
        user.verification_code_expires = None
        user.verification_attempts = 0
        await user.save()

    @staticmethod
    async def resend_verification(user_id: str):
        """Resend verification code."""
        from app.core.email import email_service

        user = await User.get(user_id)
        if not user:
            raise NotFoundError("User not found")

        if user.is_verified:
            raise ValidationError("Email already verified")

        verification_code = generate_verification_code()
        user.verification_code = verification_code
        user.verification_code_expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        user.verification_attempts = 0  # fresh code → reset the attempts counter
        await user.save()

        # Send verification code
        await email_service.send_verification_code(
            to=user.email,
            name=user.name,
            code=verification_code,
        )

    @staticmethod
    async def change_password(
        user_id: str,
        current_password: str,
        new_password: str,
        new_password_confirmation: str,
    ):
        """Change user password."""
        if new_password != new_password_confirmation:
            raise ValidationError("Passwords do not match")

        if current_password == new_password:
            raise ValidationError("New password must be different from current password")

        user = await User.get(user_id)
        if not user:
            raise NotFoundError("User not found")

        if not user.password_hash:
            raise ValidationError("This account uses social sign-in. Set a password via password reset first.")

        try:
            if not verify_password(current_password, user.password_hash):
                raise InvalidCredentialsError("Current password is incorrect")
        except Exception as e:
            if isinstance(e, (InvalidCredentialsError, ValidationError)):
                raise
            raise InvalidCredentialsError("Current password is incorrect")

        user.password_hash = get_password_hash(new_password)
        await user.save()

        # Revoke all refresh AND access tokens for security
        await RefreshToken.find(RefreshToken.user_id == str(user.id)).update(
            {"$set": {"is_revoked": True}}
        )
        await revoke_all_for_user(str(user.id))

    @staticmethod
    async def _create_tokens(user_id: str) -> TokenResponse:
        """Create access and refresh tokens."""
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)

        # Store refresh token
        payload = decode_token(refresh_token)
        if payload:
            token_record = RefreshToken(
                user_id=user_id,
                token_jti=payload["jti"],
                expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            )
            await token_record.insert()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def _register_device(user_id: str, device_token: str, platform: Platform = Platform.IOS):
        """Register or update device for push notifications.

        If the same device token already exists for the same user, just refresh the
        timestamp. If it exists for a *different* user, the old binding is replaced
        (the previous user stops receiving pushes on that device — which is correct,
        since the device's current owner is now the new user). The actual security
        improvement here is partial: a stolen token still binds, but at least the
        rebinding is explicit and intentional rather than a silent overwrite.
        """
        now = datetime.now(timezone.utc)
        existing = await Device.find_one(Device.token == device_token)
        if existing:
            if existing.user_id != user_id:
                # Device changed hands — invalidate old binding cleanly.
                existing.user_id = user_id
                existing.platform = platform
            existing.updated_at = now
            await existing.save()
        else:
            device = Device(
                user_id=user_id,
                token=device_token,
                platform=platform,
            )
            await device.insert()

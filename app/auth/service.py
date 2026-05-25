from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid
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
from app.core.token_blocklist import revoke_all_for_user
from pymongo.errors import DuplicateKeyError
import secrets


class AuthService:
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
        """Authenticate user and return tokens."""
        user = await User.find_one(User.email == email)
        if not user:
            raise InvalidCredentialsError()

        # Reject social-only accounts trying to use password login
        if not user.password_hash:
            raise InvalidCredentialsError()

        try:
            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError()
        except (ValueError, Exception) as e:
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
    async def logout(user_id: str):
        """Logout user: invalidate ALL refresh tokens AND existing access tokens."""
        user = await User.get(user_id)
        if user:
            user.is_online = False
            await user.save()

        await RefreshToken.find(RefreshToken.user_id == user_id).update(
            {"$set": {"is_revoked": True}}
        )
        await revoke_all_for_user(user_id)

    @staticmethod
    async def forgot_password(email: str):
        """Send password reset token."""
        from app.core.email import email_service

        user = await User.find_one(User.email == email)
        if not user:
            # Don't reveal if email exists
            return

        reset_token = generate_password_reset_token()
        user.password_reset_token = reset_token
        user.password_reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await user.save()

        # Send email with reset token
        await email_service.send_password_reset_token(
            to=user.email,
            name=user.name,
            token=reset_token,
        )

    @staticmethod
    async def reset_password(token: str, password: str, password_confirmation: str):
        """Reset password using token from email."""
        if password != password_confirmation:
            raise ValidationError("Passwords do not match")

        user = await User.find_one(User.password_reset_token == token)
        if not user:
            raise ValidationError("Invalid or expired reset token")

        # Handle both naive and timezone-aware datetimes from database
        expires = user.password_reset_token_expires
        now = datetime.now(timezone.utc)
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if not expires or expires < now:
            raise TokenExpiredError("Reset token has expired")

        user.password_hash = get_password_hash(password)
        user.password_reset_token = None
        user.password_reset_token_expires = None
        await user.save()

        # Revoke all refresh AND access tokens for security
        await RefreshToken.find(RefreshToken.user_id == str(user.id)).update(
            {"$set": {"is_revoked": True}}
        )
        await revoke_all_for_user(str(user.id))

    @staticmethod
    async def verify_email(email: str, code: str):
        """Verify user email with 6-digit code. Constant-time compare."""
        user = await User.find_one(User.email == email)
        if not user or not user.verification_code:
            raise ValidationError("Invalid email or verification code")
        if not secrets.compare_digest(user.verification_code, code):
            raise ValidationError("Invalid email or verification code")

        # Check expiration - handle both naive and timezone-aware datetimes
        expires = user.verification_code_expires
        if expires is None:
            raise TokenExpiredError("Verification code has expired")

        now = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            raise TokenExpiredError("Verification code has expired")

        user.is_verified = True
        user.verification_code = None
        user.verification_code_expires = None
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
        """Register or update device for push notifications."""
        existing = await Device.find_one(Device.token == device_token)
        if existing:
            existing.user_id = user_id
            existing.updated_at = datetime.now(timezone.utc)
            await existing.save()
        else:
            device = Device(
                user_id=user_id,
                token=device_token,
                platform=platform,
            )
            await device.insert()

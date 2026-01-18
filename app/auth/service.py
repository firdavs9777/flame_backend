from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from app.models.user import User, Photo, UserPreferences, Location, Coordinates
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
import secrets


class AuthService:
    @staticmethod
    async def register(data: RegisterRequest) -> Tuple[User, TokenResponse]:
        """Register a new user."""
        # Check if email exists
        existing_user = await User.find_one(User.email == data.email)
        if existing_user:
            raise EmailExistsError()

        # Create photos list
        photos = [
            Photo(
                id=f"photo_{i}",
                url=url,
                is_primary=(i == 0),
                order=i,
            )
            for i, url in enumerate(data.photos)
        ]

        # Reverse geocode location
        from app.core.location import location_service
        city, state, country = await location_service.reverse_geocode(
            data.latitude, data.longitude
        )

        location = Location(
            city=city,
            state=state,
            country=country,
            coordinates=Coordinates(
                latitude=data.latitude,
                longitude=data.longitude
            ),
        )

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
            is_online=True,
            verification_code=verification_code,
            verification_code_expires=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

        await user.insert()

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

        if not verify_password(password, user.password_hash):
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
        """Refresh access token using refresh token."""
        payload = decode_token(refresh_token)
        if not payload:
            raise InvalidCredentialsError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise InvalidCredentialsError("Invalid token type")

        jti = payload.get("jti")
        if not jti:
            raise InvalidCredentialsError("Invalid refresh token")

        # Check if token is revoked
        token_record = await RefreshToken.find_one(RefreshToken.token_jti == jti)
        if not token_record or token_record.is_revoked:
            raise InvalidCredentialsError("Token has been revoked")

        # Revoke old token
        token_record.is_revoked = True
        await token_record.save()

        user_id = payload.get("sub")

        # Create new tokens
        return await AuthService._create_tokens(user_id)

    @staticmethod
    async def logout(user_id: str, refresh_token: Optional[str] = None):
        """Logout user and invalidate tokens."""
        # Update user status
        user = await User.get(user_id)
        if user:
            user.is_online = False
            await user.save()

        # Revoke refresh token if provided
        if refresh_token:
            payload = decode_token(refresh_token)
            if payload and payload.get("jti"):
                token_record = await RefreshToken.find_one(
                    RefreshToken.token_jti == payload["jti"]
                )
                if token_record:
                    token_record.is_revoked = True
                    await token_record.save()

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

        if not user.password_reset_token_expires or user.password_reset_token_expires < datetime.now(timezone.utc):
            raise TokenExpiredError("Reset token has expired")

        user.password_hash = get_password_hash(password)
        user.password_reset_token = None
        user.password_reset_token_expires = None
        await user.save()

        # Revoke all refresh tokens for security
        await RefreshToken.find(RefreshToken.user_id == str(user.id)).update(
            {"$set": {"is_revoked": True}}
        )

    @staticmethod
    async def verify_email(email: str, code: str):
        """Verify user email with 6-digit code."""
        user = await User.find_one(User.email == email)
        if not user:
            raise NotFoundError("User not found")

        if not user.verification_code or user.verification_code != code:
            raise ValidationError("Invalid verification code")

        if user.verification_code_expires < datetime.now(timezone.utc):
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

        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")

        user.password_hash = get_password_hash(new_password)
        await user.save()

        # Revoke all other refresh tokens for security
        await RefreshToken.find(RefreshToken.user_id == str(user.id)).update(
            {"$set": {"is_revoked": True}}
        )

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

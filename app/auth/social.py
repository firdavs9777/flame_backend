from typing import Optional, Tuple
import httpx
from jose import jwt
from app.models.user import User, Gender, UserPreferences
from app.core.config import settings
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.auth.service import AuthService
from app.auth.schemas import TokenResponse
from datetime import datetime, timezone


class SocialAuthService:
    @staticmethod
    async def google_auth(
        id_token: str,
        device_token: Optional[str] = None,
    ) -> Tuple[User, TokenResponse]:
        """Authenticate with Google ID token."""
        # Verify Google token
        google_user = await SocialAuthService._verify_google_token(id_token)
        if not google_user:
            raise InvalidCredentialsError("Invalid Google token")

        google_id = google_user.get("sub")
        email = google_user.get("email")
        name = google_user.get("name", "")

        # Find or create user
        user = await User.find_one(User.google_id == google_id)
        if not user:
            existing = await User.find_one(User.email == email)
            if existing:
                # Block auto-linking to password-based accounts — prevents takeover
                if existing.password_hash and existing.password_hash != "":
                    raise InvalidCredentialsError(
                        "An account with this email already exists. "
                        "Sign in with your password to link Google."
                    )
                # Only auto-link to other social accounts or unfinished social signups
                if not google_user.get("email_verified"):
                    raise InvalidCredentialsError("Google email is not verified")
                existing.google_id = google_id
                await existing.save()
                user = existing
            else:
                # Create new user (will need to complete profile)
                user = User(
                    email=email,
                    password_hash="",  # No password for social auth
                    name=name,
                    age=18,  # Default, user needs to update
                    gender=Gender.OTHER,  # Default, user needs to update
                    looking_for=Gender.OTHER,  # Default, user needs to update
                    interests=[""],  # Will need to be filled
                    google_id=google_id,
                    is_verified=True,  # Google email is verified
                )
                await user.insert()

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
    async def apple_auth(
        id_token: str,
        authorization_code: str,
        device_token: Optional[str] = None,
    ) -> Tuple[User, TokenResponse]:
        """Authenticate with Apple."""
        # Verify Apple token
        apple_user = await SocialAuthService._verify_apple_token(id_token)
        if not apple_user:
            raise InvalidCredentialsError("Invalid Apple token")

        apple_id = apple_user.get("sub")
        email = apple_user.get("email")

        # Find or create user
        user = await User.find_one(User.apple_id == apple_id)
        if not user:
            existing = None
            if email:
                existing = await User.find_one(User.email == email)
            if existing:
                if existing.password_hash and existing.password_hash != "":
                    raise InvalidCredentialsError(
                        "An account with this email already exists. "
                        "Sign in with your password to link Apple."
                    )
                existing.apple_id = apple_id
                await existing.save()
                user = existing
            else:
                # Create new user
                user = User(
                    email=email or f"{apple_id}@privaterelay.appleid.com",
                    password_hash="",
                    name="Apple User",  # Apple may not provide name
                    age=18,
                    gender=Gender.OTHER,
                    looking_for=Gender.OTHER,
                    interests=[""],
                    apple_id=apple_id,
                    is_verified=True,
                )
                await user.insert()

        user.is_online = True
        user.last_active = datetime.now(timezone.utc)
        await user.save()

        if device_token:
            await AuthService._register_device(str(user.id), device_token)

        tokens = await AuthService._create_tokens(str(user.id))

        return user, tokens

    @staticmethod
    async def facebook_auth(
        access_token: str,
        device_token: Optional[str] = None,
    ) -> Tuple[User, TokenResponse]:
        """Authenticate with Facebook."""
        # Verify Facebook token and get user info
        fb_user = await SocialAuthService._verify_facebook_token(access_token)
        if not fb_user:
            raise InvalidCredentialsError("Invalid Facebook token")

        facebook_id = fb_user.get("id")
        email = fb_user.get("email")
        name = fb_user.get("name", "")

        # Find or create user
        user = await User.find_one(User.facebook_id == facebook_id)
        if not user:
            existing = None
            if email:
                existing = await User.find_one(User.email == email)
            if existing:
                if existing.password_hash and existing.password_hash != "":
                    raise InvalidCredentialsError(
                        "An account with this email already exists. "
                        "Sign in with your password to link Facebook."
                    )
                existing.facebook_id = facebook_id
                await existing.save()
                user = existing
            else:
                user = User(
                    email=email or f"{facebook_id}@facebook.com",
                    password_hash="",
                    name=name,
                    age=18,
                    gender=Gender.OTHER,
                    looking_for=Gender.OTHER,
                    interests=[""],
                    facebook_id=facebook_id,
                    is_verified=bool(email),
                )
                await user.insert()

        user.is_online = True
        user.last_active = datetime.now(timezone.utc)
        await user.save()

        if device_token:
            await AuthService._register_device(str(user.id), device_token)

        tokens = await AuthService._create_tokens(str(user.id))

        return user, tokens

    @staticmethod
    async def _verify_google_token(id_token: str) -> Optional[dict]:
        """Verify Google ID token locally against Google's published JWKs."""
        import logging
        log = logging.getLogger(__name__)
        try:
            header = jwt.get_unverified_header(id_token)
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
                if response.status_code != 200:
                    return None
                keys = response.json().get("keys", [])

            key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
            if not key:
                return None

            payload = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=settings.GOOGLE_CLIENT_ID,
                issuer=["https://accounts.google.com", "accounts.google.com"],
                options={"verify_at_hash": False},
            )
            return payload
        except Exception as e:
            log.warning("Google token verification failed: %s", e)
            return None

    @staticmethod
    async def _verify_apple_token(id_token: str) -> Optional[dict]:
        """Verify Apple ID token and return user info."""
        try:
            # Decode without verification first to get header
            header = jwt.get_unverified_header(id_token)

            # Fetch Apple's public keys
            async with httpx.AsyncClient() as client:
                response = await client.get("https://appleid.apple.com/auth/keys")
                if response.status_code != 200:
                    return None

                keys = response.json().get("keys", [])

                # Find the key matching the token's kid
                key = next((k for k in keys if k["kid"] == header["kid"]), None)
                if not key:
                    return None

                # Verify and decode the token
                payload = jwt.decode(
                    id_token,
                    key,
                    algorithms=["RS256"],
                    audience=settings.APPLE_CLIENT_ID,
                    issuer="https://appleid.apple.com",
                )
                return payload
        except Exception:
            return None

    @staticmethod
    async def _verify_facebook_token(access_token: str) -> Optional[dict]:
        """Verify Facebook access token and return user info."""
        try:
            async with httpx.AsyncClient() as client:
                # Verify the token was issued for our app
                app_token = f"{settings.FACEBOOK_APP_ID}|{settings.FACEBOOK_APP_SECRET}"
                debug_response = await client.get(
                    "https://graph.facebook.com/debug_token",
                    params={"input_token": access_token, "access_token": app_token},
                )
                if debug_response.status_code != 200:
                    return None
                debug_data = debug_response.json().get("data", {})
                if not debug_data.get("is_valid") or str(debug_data.get("app_id")) != settings.FACEBOOK_APP_ID:
                    return None

                # Fetch user info
                response = await client.get(
                    "https://graph.facebook.com/me",
                    params={"access_token": access_token, "fields": "id,name,email,picture"},
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception:
            return None

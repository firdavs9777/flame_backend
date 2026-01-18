from fastapi import APIRouter, Depends, status
from app.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    ChangePasswordRequest,
    GoogleAuthRequest,
    AppleAuthRequest,
    FacebookAuthRequest,
    MessageResponse,
)
from app.auth.service import AuthService
from app.auth.social import SocialAuthService
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def format_user_response(user: User) -> dict:
    """Format user object for response."""
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
        "gender": user.gender.value if hasattr(user.gender, 'value') else user.gender,
        "looking_for": user.looking_for.value if hasattr(user.looking_for, 'value') else user.looking_for,
        "bio": user.bio,
        "interests": user.interests,
        "photos": [p.url for p in user.photos],
        "location": location,
        "is_online": user.is_online,
        "is_verified": user.is_verified,
        "last_active": user.last_active.isoformat(),
        "created_at": user.created_at.isoformat(),
        "preferences": {
            "min_age": user.preferences.min_age,
            "max_age": user.preferences.max_age,
            "max_distance": user.preferences.max_distance,
        },
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest):
    """Register a new user account."""
    user, tokens = await AuthService.register(data)
    return {
        "success": True,
        "data": {
            "user": format_user_response(user),
            "tokens": tokens.model_dump(),
        },
    }


@router.post("/login")
async def login(data: LoginRequest):
    """Authenticate user and return tokens."""
    user, tokens = await AuthService.login(
        email=data.email,
        password=data.password,
        device_token=data.device_token,
    )
    return {
        "success": True,
        "data": {
            "user": format_user_response(user),
            "tokens": tokens.model_dump(),
        },
    }


@router.post("/refresh")
async def refresh_token(data: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    tokens = await AuthService.refresh_tokens(data.refresh_token)
    return {
        "success": True,
        "data": tokens.model_dump(),
    }


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout current user."""
    await AuthService.logout(str(current_user.id))
    return {"success": True, "message": "Successfully logged out"}


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Send password reset code to email."""
    await AuthService.forgot_password(data.email)
    return {"success": True, "message": "Password reset code sent to your email"}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """Reset password using token from email."""
    await AuthService.reset_password(
        token=data.token,
        password=data.password,
        password_confirmation=data.password_confirmation,
    )
    return {"success": True, "message": "Password successfully reset"}


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest):
    """Verify user email with 6-digit code."""
    await AuthService.verify_email(email=data.email, code=data.code)
    return {"success": True, "message": "Email successfully verified"}


@router.post("/resend-verification")
async def resend_verification(current_user: User = Depends(get_current_user)):
    """Resend verification code to email."""
    await AuthService.resend_verification(str(current_user.id))
    return {"success": True, "message": "Verification code sent to your email"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Change user password."""
    await AuthService.change_password(
        user_id=str(current_user.id),
        current_password=data.current_password,
        new_password=data.new_password,
        new_password_confirmation=data.new_password_confirmation,
    )
    return {"success": True, "message": "Password successfully changed"}


# Social Authentication


@router.post("/google")
async def google_auth(data: GoogleAuthRequest):
    """Authenticate with Google."""
    user, tokens = await SocialAuthService.google_auth(
        id_token=data.id_token,
        device_token=data.device_token,
    )
    return {
        "success": True,
        "data": {
            "user": format_user_response(user),
            "tokens": tokens.model_dump(),
        },
    }


@router.post("/apple")
async def apple_auth(data: AppleAuthRequest):
    """Authenticate with Apple."""
    user, tokens = await SocialAuthService.apple_auth(
        id_token=data.id_token,
        authorization_code=data.authorization_code,
        device_token=data.device_token,
    )
    return {
        "success": True,
        "data": {
            "user": format_user_response(user),
            "tokens": tokens.model_dump(),
        },
    }


@router.post("/facebook")
async def facebook_auth(data: FacebookAuthRequest):
    """Authenticate with Facebook."""
    user, tokens = await SocialAuthService.facebook_auth(
        access_token=data.access_token,
        device_token=data.device_token,
    )
    return {
        "success": True,
        "data": {
            "user": format_user_response(user),
            "tokens": tokens.model_dump(),
        },
    }

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from app.models.user import Gender
import re


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    age: int
    gender: Gender
    looking_for: Gender
    bio: Optional[str] = None
    interests: List[str]
    photos: List[str]
    location: Optional[str] = None
    is_online: bool
    is_verified: bool
    last_active: str
    created_at: str
    preferences: dict


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=2, max_length=50)
    age: int = Field(ge=18, le=100)
    gender: Gender
    looking_for: Gender
    bio: Optional[str] = Field(default=None, max_length=500)
    interests: List[str] = Field(min_length=1, max_length=10)
    photos: List[str] = Field(min_length=1, max_length=6)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_token: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)
    password_confirmation: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    new_password_confirmation: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class GoogleAuthRequest(BaseModel):
    id_token: str
    device_token: Optional[str] = None


class AppleAuthRequest(BaseModel):
    id_token: str
    authorization_code: str
    device_token: Optional[str] = None


class FacebookAuthRequest(BaseModel):
    access_token: str
    device_token: Optional[str] = None


class MessageResponse(BaseModel):
    success: bool = True
    message: str

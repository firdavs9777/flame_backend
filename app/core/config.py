from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Flame API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/v1"
    FRONTEND_URL: str = "https://banatalk.com"

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "flame_db"

    # JWT
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Rate Limiting
    RATE_LIMIT_LOGIN: int = 5  # per 15 minutes
    RATE_LIMIT_REGISTER: int = 3  # per hour
    RATE_LIMIT_API: int = 100  # per minute

    # Photo Upload
    MAX_PHOTO_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_PHOTO_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    MAX_PHOTOS_PER_USER: int = 6

    # DigitalOcean Spaces (S3-compatible storage)
    DO_SPACES_KEY: str = ""
    DO_SPACES_SECRET: str = ""
    SPACES_BUCKET: str = "my-projects-media"
    SPACES_REGION: str = "sfo3"
    SPACES_ENDPOINT: str = "sfo3.digitaloceanspaces.com"
    SPACES_CDN_URL: str = "https://my-projects-media.sfo3.cdn.digitaloceanspaces.com"
    SPACES_PROJECT_FOLDER: str = "flame_backend"  # Project-specific folder prefix

    # Email - Mailgun
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    MAILGUN_REGION: str = "us"
    FROM_NAME: str = "Flame"
    FROM_EMAIL: str = "noreply@flame.app"

    # Email - SendGrid (backup)
    SENDGRID_API_KEY: str = ""

    # Social Auth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    APPLE_CLIENT_ID: str = ""
    APPLE_TEAM_ID: str = ""
    APPLE_KEY_ID: str = ""
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""

    # Firebase
    FIREBASE_PROJECT_ID: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

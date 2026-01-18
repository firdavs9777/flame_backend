import boto3
from botocore.config import Config
from typing import Optional
from fastapi import UploadFile
import uuid
from datetime import datetime
from app.core.config import settings


class StorageService:
    """DigitalOcean Spaces storage service (S3-compatible)."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.SPACES_ENDPOINT}",
            aws_access_key_id=settings.DO_SPACES_KEY,
            aws_secret_access_key=settings.DO_SPACES_SECRET,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.SPACES_BUCKET
        self.cdn_url = settings.SPACES_CDN_URL
        self.project_folder = settings.SPACES_PROJECT_FOLDER
        self.bucket_url = f"https://{settings.SPACES_BUCKET}.{settings.SPACES_ENDPOINT}"

    def _build_key(self, folder: str, filename: str) -> str:
        """Build the full S3 key with project folder prefix."""
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        return f"{self.project_folder}/{folder}/{timestamp}-{filename}"

    def _fix_url(self, key: str) -> str:
        """Ensure URL is properly formatted with CDN."""
        return f"{self.cdn_url}/{key}"

    async def upload_file(
        self,
        file: UploadFile,
        folder: str = "uploads",
        filename: Optional[str] = None,
    ) -> str:
        """
        Upload a file to DigitalOcean Spaces.
        Returns the CDN URL of the uploaded file.
        """
        if not filename:
            ext = file.filename.split(".")[-1] if file.filename else "jpg"
            filename = f"{uuid.uuid4()}.{ext}"

        # Build key with project folder prefix
        key = self._build_key(folder, filename)

        # Read file content
        content = await file.read()

        # Upload to Spaces
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
            ACL="public-read",
        )

        # Reset file position
        await file.seek(0)

        return self._fix_url(key)

    async def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder: str = "uploads",
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload raw bytes to DigitalOcean Spaces.
        Returns the CDN URL of the uploaded file.
        """
        # Build key with project folder prefix
        key = self._build_key(folder, filename)

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ACL="public-read",
        )

        return self._fix_url(key)

    async def delete_file(self, url: str) -> bool:
        """
        Delete a file from DigitalOcean Spaces.
        """
        try:
            # Extract key from URL
            key = url.replace(f"{self.cdn_url}/", "")

            self.client.delete_object(
                Bucket=self.bucket,
                Key=key,
            )
            return True
        except Exception:
            return False

    async def upload_user_photo(self, user_id: str, file: UploadFile) -> str:
        """Upload a user profile photo."""
        ext = file.filename.split(".")[-1] if file.filename else "jpg"
        filename = f"{user_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="photos", filename=filename)

    async def upload_message_image(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a message image."""
        ext = file.filename.split(".")[-1] if file.filename else "jpg"
        filename = f"{conversation_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages", filename=filename)


# Global storage instance
storage = StorageService()

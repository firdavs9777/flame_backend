import boto3
from botocore.config import Config
from typing import Optional
from fastapi import UploadFile
import uuid
import base64
import re
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
        return await self.upload_file(file, folder="messages/images", filename=filename)

    async def upload_message_video(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a message video."""
        ext = file.filename.split(".")[-1] if file.filename else "mp4"
        filename = f"{conversation_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages/videos", filename=filename)

    async def upload_message_audio(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a message audio file."""
        ext = file.filename.split(".")[-1] if file.filename else "mp3"
        filename = f"{conversation_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages/audio", filename=filename)

    async def upload_voice_message(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a voice message."""
        ext = file.filename.split(".")[-1] if file.filename else "ogg"
        filename = f"{conversation_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages/voice", filename=filename)

    async def upload_message_file(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a generic file attachment."""
        ext = file.filename.split(".")[-1] if file.filename else "bin"
        filename = f"{conversation_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages/files", filename=filename)

    async def upload_video_thumbnail(self, conversation_id: str, file: UploadFile) -> str:
        """Upload a video thumbnail."""
        ext = file.filename.split(".")[-1] if file.filename else "jpg"
        filename = f"{conversation_id}-thumb-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="messages/thumbnails", filename=filename)

    async def upload_sticker(self, pack_id: str, file: UploadFile) -> str:
        """Upload a sticker image."""
        ext = file.filename.split(".")[-1] if file.filename else "webp"
        filename = f"{pack_id}-{uuid.uuid4()}.{ext}"
        return await self.upload_file(file, folder="stickers", filename=filename)

    async def upload_base64_image(self, base64_string: str, user_id: str) -> str:
        """
        Upload a base64 encoded image to DigitalOcean Spaces.
        Handles both raw base64 and data URL formats.
        Returns the CDN URL of the uploaded file.
        """
        # Handle data URL format (e.g., "data:image/jpeg;base64,/9j/4AAQ...")
        if base64_string.startswith("data:"):
            # Extract content type and base64 data
            match = re.match(r"data:([^;]+);base64,(.+)", base64_string)
            if match:
                content_type = match.group(1)
                base64_data = match.group(2)
            else:
                content_type = "image/jpeg"
                base64_data = base64_string.split(",")[1] if "," in base64_string else base64_string
        else:
            content_type = "image/jpeg"
            base64_data = base64_string

        # Determine file extension from content type
        ext_map = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        ext = ext_map.get(content_type, "jpg")

        # Decode base64
        try:
            image_data = base64.b64decode(base64_data)
        except Exception:
            raise ValueError("Invalid base64 image data")

        # Generate filename
        filename = f"{user_id}-{uuid.uuid4()}.{ext}"

        # Upload to Spaces
        return await self.upload_bytes(
            data=image_data,
            filename=filename,
            folder="photos",
            content_type=content_type,
        )

    def is_base64_image(self, string: str) -> bool:
        """Check if a string is a base64 encoded image."""
        if not string:
            return False
        # Check for data URL format
        if string.startswith("data:image"):
            return True
        # Check for raw base64 (starts with common image headers)
        if string.startswith("/9j/"):  # JPEG
            return True
        if string.startswith("iVBOR"):  # PNG
            return True
        if string.startswith("R0lGO"):  # GIF
            return True
        if string.startswith("UklGR"):  # WEBP
            return True
        # Check if it's a very long string (likely base64)
        if len(string) > 1000 and not string.startswith("http"):
            return True
        return False


# Global storage instance
storage = StorageService()

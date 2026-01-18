from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings


class Database:
    client: AsyncIOMotorClient = None


db = Database()


async def connect_to_mongo():
    """Create database connection."""
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)

    # Import models here to avoid circular imports
    from app.models.user import User
    from app.models.match import Match
    from app.models.swipe import Swipe
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.models.block import Block
    from app.models.report import Report
    from app.models.device import Device
    from app.models.refresh_token import RefreshToken
    from app.models.sticker import Sticker, StickerPack, UserStickerPack, RecentSticker

    await init_beanie(
        database=db.client[settings.MONGODB_DB_NAME],
        document_models=[
            User,
            Match,
            Swipe,
            Conversation,
            Message,
            Block,
            Report,
            Device,
            RefreshToken,
            Sticker,
            StickerPack,
            UserStickerPack,
            RecentSticker,
        ],
    )


async def close_mongo_connection():
    """Close database connection."""
    if db.client:
        db.client.close()


def get_database():
    """Get database instance."""
    return db.client[settings.MONGODB_DB_NAME]

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
import certifi


class Database:
    client: AsyncIOMotorClient = None


db = Database()


async def _drop_conflicting_indexes(database):
    """Drop indexes that have changed shape (e.g. plain → TTL) so Beanie can recreate them.

    Idempotent: silently continues if the index doesn't exist or is already correct.
    """
    import logging
    logger = logging.getLogger(__name__)

    # refresh_tokens.expires_at: was a plain index, now a TTL index
    try:
        collection = database["refresh_tokens"]
        info = await collection.index_information()
        idx = info.get("expires_at_1")
        if idx is not None and "expireAfterSeconds" not in idx:
            await collection.drop_index("expires_at_1")
            logger.info("Dropped legacy expires_at_1 index on refresh_tokens to make room for TTL index")
    except Exception as e:
        logger.warning("Index migration check failed (non-fatal): %s", e)


async def connect_to_mongo():
    """Create database connection."""
    db.client = AsyncIOMotorClient(settings.MONGODB_URL, tlsCAFile=certifi.where())

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
    from app.models.subscription import Subscription

    # Migrate index changes before init_beanie
    await _drop_conflicting_indexes(db.client[settings.MONGODB_DB_NAME])

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
            Subscription,
        ],
    )


async def close_mongo_connection():
    """Close database connection."""
    if db.client:
        db.client.close()


def get_database():
    """Get database instance."""
    return db.client[settings.MONGODB_DB_NAME]

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_url, serverSelectionTimeoutMS=2000)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def ensure_indexes() -> None:
    db = get_db()
    await db.reports.create_index([("uploaded_at", -1)])
    await db.reports.create_index("report_id", unique=True)
    await db.vitals_timeline.create_index([("recorded_at", -1), ("type", 1)])
    await db.labs_timeline.create_index([("recorded_at", -1), ("test", 1)])
    await db.diagnoses_master.create_index("condition")
    await db.medications_master.create_index("name")
    await db.suggestions.create_index([("severity", 1), ("dismissed", 1), ("created_at", -1)])
    await db.suggestions.create_index("report_id")
    await db.report_embeddings.create_index("report_id", unique=True)
    await db.consensus_meta.create_index("report_id", unique=True)

    # ── multi-user partitioning ───────────────────────────────────────────
    await db.users.create_index("username", unique=True)
    # Every domain doc carries user_id; compound indexes keep per-user reads fast.
    await db.reports.create_index([("user_id", 1), ("uploaded_at", -1)])
    await db.vitals_timeline.create_index([("user_id", 1), ("recorded_at", -1), ("type", 1)])
    await db.labs_timeline.create_index([("user_id", 1), ("recorded_at", -1), ("test", 1)])
    await db.diagnoses_master.create_index([("user_id", 1), ("condition", 1)])
    await db.medications_master.create_index([("user_id", 1), ("name", 1)])
    await db.suggestions.create_index([("user_id", 1), ("severity", 1), ("dismissed", 1), ("created_at", -1)])
    await db.report_embeddings.create_index("user_id")

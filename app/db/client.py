"""MongoDB connection (D-23: synchronous PyMongo).

Usage:
    from app.db.client import get_db
    db = get_db()
"""
from pymongo import MongoClient
from pymongo.database import Database

from app import config

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return one shared MongoClient per process.

    A MongoClient keeps a pool of connections, so it is created once and reused.
    tz_aware=True returns dates as UTC-aware datetimes, matching the rest of the code (D-16).
    """
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_URI, tz_aware=True)
    return _client


def get_db(name: str | None = None) -> Database:
    """Return the project database, or another one by name (tests use their own)."""
    return get_client()[name or config.MONGO_DB]

"""Shared test setup. Tests need MongoDB running: docker compose up -d"""
from datetime import datetime, timedelta, timezone

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from app.db.client import get_client

TEST_DB = "tracking_test"  # never the real database
T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="session", autouse=True)
def mongo_running():
    try:
        get_client().admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.exit("MongoDB is not reachable. Start it with: docker compose up -d")


@pytest.fixture
def db():
    """An empty test database for each test."""
    client = get_client()
    client.drop_database(TEST_DB)
    yield client[TEST_DB]
    client.drop_database(TEST_DB)


def make_event(event_id, shipment_id, hour, event_type="arrived_at_hub",
               facility_id="HUB-BUD-01", courier_id=None):
    """An event `hour` hours after T0."""
    return {"_id": event_id, "shipment_id": shipment_id, "event_type": event_type,
            "ts": T0 + timedelta(hours=hour), "facility_id": facility_id,
            "courier_id": courier_id, "location": {"city": "Budapest", "country": "HU"},
            "source": "scanner"}

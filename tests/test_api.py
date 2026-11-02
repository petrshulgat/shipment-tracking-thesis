"""API tests. TestClient sends HTTP requests to the app in-process, no server needed."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import database
from app.db import queries
from conftest import T0, make_event


@pytest.fixture
def client(db):
    """Point every endpoint at the empty test database instead of the real one."""
    app.dependency_overrides[database] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def window(start_h, end_h):
    """Query parameters for the time window [T0 + start_h, T0 + end_h)."""
    return {"start": (T0 + timedelta(hours=start_h)).isoformat(),
            "end": (T0 + timedelta(hours=end_h)).isoformat()}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# --- status (AP-05) ---

def test_status_unknown_shipment_is_404(client):
    assert client.get("/shipments/missing/status").status_code == 404


def test_status_null_before_first_event(client, db):
    queries.create_shipment(db, {"_id": "S1"})  # D-18
    r = client.get("/shipments/S1/status")
    assert r.status_code == 200
    assert r.json() == {"shipment_id": "S1", "current_status": None}


def test_status_after_event(client, db):
    queries.create_shipment(db, {"_id": "S1"})
    queries.update_current_status(db, [make_event("e1", "S1", 1, "picked_up", courier_id="CUR-0001")])
    assert client.get("/shipments/S1/status").json()["current_status"] == {
        "status": "picked_up", "last_event_ts": "2026-03-01T01:00:00Z",
        "last_facility_id": "HUB-BUD-01", "last_courier_id": "CUR-0001"}


# --- history (AP-06) ---

def test_history_sorted_and_renamed_id(client, db):
    queries.insert_events(db, [make_event("e2", "S1", 2), make_event("e1", "S1", 1)])
    body = client.get("/shipments/S1/events").json()
    assert [e["event_id"] for e in body] == ["e1", "e2"]
    assert "_id" not in body[0]


def test_history_unknown_shipment_is_empty_list(client):
    r = client.get("/shipments/missing/events")
    assert r.status_code == 200 and r.json() == []


# --- facility / courier events (AP-07, AP-11) ---

def test_facility_events_window_and_limit(client, db):
    queries.insert_events(db, [make_event(f"e{h}", "S1", h) for h in range(10)])
    r = client.get("/facilities/HUB-BUD-01/events", params=window(2, 6))
    assert [e["event_id"] for e in r.json()] == ["e2", "e3", "e4", "e5"]
    r = client.get("/facilities/HUB-BUD-01/events", params={**window(2, 6), "limit": 2})
    assert len(r.json()) == 2


@pytest.mark.parametrize("limit", [0, 1001])
def test_limit_out_of_range_is_422(client, limit):
    r = client.get("/facilities/HUB-BUD-01/events", params={**window(0, 1), "limit": limit})
    assert r.status_code == 422


def test_start_after_end_is_422(client):
    assert client.get("/couriers/CUR-0001/events", params=window(5, 1)).status_code == 422


def test_time_without_timezone_is_utc(client, db):
    queries.insert_events(db, [make_event("e1", "S1", 1)])
    r = client.get("/facilities/HUB-BUD-01/events",
                   params={"start": "2026-03-01T00:00:00", "end": "2026-03-01T02:00:00"})
    assert [e["event_id"] for e in r.json()] == ["e1"]


def test_courier_events(client, db):
    queries.insert_events(db, [make_event("e1", "S1", 1, "picked_up", courier_id="CUR-0001"),
                               make_event("e2", "S1", 2, "sorted")])
    r = client.get("/couriers/CUR-0001/events", params=window(0, 24))
    assert [e["event_id"] for e in r.json()] == ["e1"]


# --- metrics (AP-10) ---

def test_metrics(client, db):
    db.analytics.insert_one({
        "metric": "delivery_success_rate", "scope": {"type": "courier", "value": "CUR-0001"},
        "period_start": T0, "period_end": T0 + timedelta(days=1), "value": 0.94, "n": 100,
        "computed_at": T0 + timedelta(days=1, hours=1), "run_id": "etl_test"})
    r = client.get("/metrics", params={"metric": "delivery_success_rate", "scope_type": "courier",
                                       "start": T0.isoformat()})
    assert r.status_code == 200
    assert r.json()[0]["value"] == 0.94 and r.json()[0]["scope"]["value"] == "CUR-0001"


def test_metrics_unknown_name_is_422(client):
    r = client.get("/metrics", params={"metric": "speed", "scope_type": "global",
                                       "start": T0.isoformat()})
    assert r.status_code == 422

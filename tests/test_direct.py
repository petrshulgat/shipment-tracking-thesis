"""End-to-end test of the direct insert path: generator -> inserter -> MongoDB -> API."""
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import database
from app.db import queries
from app.ingestion.direct import reset_database, run_direct

N_EVENTS = 1000


def test_all_generated_events_are_stored(db):
    reset_database(db)
    stats = run_direct(db, N_EVENTS, batch_size=100)
    # Acceptance criterion 1 / NFR-06: events generated == events stored
    assert stats["generated"] == stats["inserted"] == db.events.count_documents({}) == N_EVENTS
    assert stats["shipments"] == db.shipments.count_documents({})
    assert stats["batches"] == N_EVENTS // 100


def test_status_equals_last_event(db):
    reset_database(db)
    run_direct(db, N_EVENTS, batch_size=100)
    for shipment in db.shipments.find():
        last = queries.get_history(db, shipment["_id"])[-1]
        status = shipment["current_status"]
        assert status["status"] == last["event_type"]
        assert status["last_event_ts"] == last["ts"]
        assert status["last_facility_id"] == last["facility_id"]


def test_rerun_adds_nothing(db):
    reset_database(db)
    run_direct(db, N_EVENTS, batch_size=100)
    stats = run_direct(db, N_EVENTS, batch_size=100)  # same seed, no reset
    assert stats["inserted"] == 0 and stats["shipments"] == 0  # D-19
    assert db.events.count_documents({}) == N_EVENTS


def test_single_event_batches(db):
    reset_database(db)
    stats = run_direct(db, 50, batch_size=1)
    assert stats["inserted"] == 50 and stats["batches"] == 50


def test_api_shows_generated_shipment(db):
    reset_database(db)
    run_direct(db, N_EVENTS, batch_size=100)
    app.dependency_overrides[database] = lambda: db
    try:
        client = TestClient(app)
        status = client.get("/shipments/SHP-0000001/status").json()["current_status"]
        history = client.get("/shipments/SHP-0000001/events").json()
    finally:
        app.dependency_overrides.clear()
    assert history[0]["event_type"] == "label_created"
    assert status["status"] == history[-1]["event_type"]

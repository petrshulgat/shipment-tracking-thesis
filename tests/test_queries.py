from datetime import timedelta

import pytest
from pymongo.errors import BulkWriteError

from app.db import queries
from conftest import T0, make_event


# --- AP-02 / AP-03 insert events (D-19) ---

def test_insert_events_skips_duplicates(db):
    assert queries.insert_events(db, [make_event("e1", "S1", 1), make_event("e2", "S1", 2)]) == 2
    # e2 is a retry of an already stored event
    assert queries.insert_events(db, [make_event("e2", "S1", 2), make_event("e3", "S1", 3)]) == 1
    assert db.events.count_documents({}) == 3


def test_insert_events_raises_other_errors(db):
    # A validator that rejects events without ts causes a non-duplicate write error.
    db.create_collection("events", validator={"$jsonSchema": {"required": ["ts"]}})
    bad = make_event("e1", "S1", 1)
    del bad["ts"]
    with pytest.raises(BulkWriteError):
        queries.insert_events(db, [bad])


def test_insert_events_empty_batch(db):
    assert queries.insert_events(db, []) == 0


# --- AP-04 status update (D-10, D-18, D-21) ---

def test_status_set_when_shipment_has_none(db):
    queries.create_shipment(db, {"_id": "S1"})  # pre-created without status (D-18)
    assert queries.update_current_status(db, [make_event("e1", "S1", 1)]) == 1
    status = queries.get_current_status(db, "S1")["current_status"]
    assert status["status"] == "arrived_at_hub"
    assert status["last_event_ts"] == T0 + timedelta(hours=1)


def test_latest_event_in_batch_wins(db):
    queries.create_shipment(db, {"_id": "S1"})
    # the newest event arrives first, an older one last
    batch = [make_event("e2", "S1", 5, "out_for_delivery"), make_event("e1", "S1", 2, "sorted")]
    queries.update_current_status(db, batch)
    assert queries.get_current_status(db, "S1")["current_status"]["status"] == "out_for_delivery"


def test_older_event_does_not_overwrite_newer_status(db):
    queries.create_shipment(db, {"_id": "S1"})
    queries.update_current_status(db, [make_event("e2", "S1", 5, "out_for_delivery")])
    assert queries.update_current_status(db, [make_event("e1", "S1", 2, "sorted")]) == 0
    assert queries.get_current_status(db, "S1")["current_status"]["status"] == "out_for_delivery"


def test_status_update_one_write_per_shipment(db):
    queries.create_shipment(db, {"_id": "S1"})
    queries.create_shipment(db, {"_id": "S2"})
    batch = [make_event("e1", "S1", 1), make_event("e2", "S1", 2), make_event("e3", "S2", 1)]
    assert queries.update_current_status(db, batch) == 2


# --- AP-05 / AP-06 reads ---

def test_get_current_status_unknown_shipment(db):
    assert queries.get_current_status(db, "missing") is None


def test_history_sorted_by_ts(db):
    queries.insert_events(db, [make_event("e3", "S1", 3), make_event("e1", "S1", 1),
                               make_event("e2", "S1", 2), make_event("x1", "S2", 1)])
    assert [e["_id"] for e in queries.get_history(db, "S1")] == ["e1", "e2", "e3"]


# --- AP-07 / AP-11 time range queries (D-25) ---

def test_events_by_facility_window_and_limit(db):
    queries.insert_events(db, [make_event(f"e{h}", "S1", h) for h in range(10)]
                          + [make_event("other", "S1", 1, facility_id="HUB-VIE-01")])
    start, end = T0 + timedelta(hours=2), T0 + timedelta(hours=6)  # [2, 6)
    assert [e["_id"] for e in queries.events_by_facility(db, "HUB-BUD-01", start, end)] == \
        ["e2", "e3", "e4", "e5"]
    assert len(queries.events_by_facility(db, "HUB-BUD-01", start, end, limit=2)) == 2


def test_events_by_courier(db):
    queries.insert_events(db, [make_event("e1", "S1", 1, "picked_up", courier_id="CUR-0001"),
                               make_event("e2", "S1", 2, "sorted"),
                               make_event("e3", "S2", 3, "delivered", courier_id="CUR-0001")])
    result = queries.events_by_courier(db, "CUR-0001", T0, T0 + timedelta(days=1))
    assert [e["_id"] for e in result] == ["e1", "e3"]


# --- AP-10 metrics ---

def test_get_metrics_filters_and_sorts(db):
    day = timedelta(days=1)
    db.analytics.insert_many([
        {"metric": "failed_attempts", "scope": {"type": "global", "value": None}, "period_start": T0 + day},
        {"metric": "failed_attempts", "scope": {"type": "global", "value": None}, "period_start": T0},
        {"metric": "failed_attempts", "scope": {"type": "courier", "value": "CUR-0001"}, "period_start": T0},
        {"metric": "failed_attempts", "scope": {"type": "global", "value": None}, "period_start": T0 - day},
    ])
    result = queries.get_metrics(db, "failed_attempts", "global", T0)
    assert [m["period_start"] for m in result] == [T0, T0 + day]

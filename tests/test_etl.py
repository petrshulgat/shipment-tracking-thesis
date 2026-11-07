"""ETL tests with a small hand-computed dataset (acceptance criterion 3, NFR-10).

Hand-computed metrics for the day [T0, T0 + 1 day):
    S1 is delivered at hour 5 and was created 10 h before T0: 15 h
    S2 is delivered at hour 10 and was created 20 h before T0: 30 h
    avg_delivery_time_s = (15 h + 30 h) / 2 = 22.5 h = 81,000 s, n = 2
    delivered = 2, delivery_failed = 1, so success rate = 2/3, n = 3
    CUR-1: 1 delivered, 0 failed. CUR-2: 1 delivered, 1 failed.
    HUB-A has 2 events, HUB-B has 1. DEP-A is not a hub and is not counted.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.db import queries
from app.etl import metrics
from app.etl.run import load_metrics, run_etl, run_range
from app.etl.scheduler import daily_window
from conftest import T0, make_event

START, END = T0, T0 + timedelta(days=1)
NOW = END + timedelta(hours=1)


@pytest.fixture
def sample(db):
    db.facilities.insert_many([{"_id": "HUB-A", "type": "hub"}, {"_id": "HUB-B", "type": "hub"},
                               {"_id": "DEP-A", "type": "depot"}])
    db.shipments.insert_many([{"_id": "S1", "created_at": T0 - timedelta(hours=10)},
                              {"_id": "S2", "created_at": T0 - timedelta(hours=20)},
                              {"_id": "S3", "created_at": T0 - timedelta(hours=40)}])
    queries.insert_events(db, [
        make_event("e1", "S1", 1, "arrived_at_hub", "HUB-A"),
        make_event("e2", "S1", 2, "sorted", "HUB-A"),
        make_event("e3", "S2", 3, "arrived_at_hub", "HUB-B"),
        make_event("e4", "S1", 4, "out_for_delivery", "DEP-A", "CUR-1"),
        make_event("e5", "S1", 5, "delivered", "DEP-A", "CUR-1"),
        make_event("e6", "S2", 6, "delivery_failed", "DEP-A", "CUR-2"),
        make_event("e7", "S2", 10, "delivered", "DEP-A", "CUR-2"),
        # Outside the window: exactly at the end (excluded), and on the day before
        make_event("e8", "S1", 24, "sorted", "HUB-A"),
        make_event("e9", "S3", -2, "delivered", "DEP-A", "CUR-1"),
    ])
    return db


def metric_doc(metric="failed_attempts", scope_type="global", scope_value=None, value=1,
               start=START, end=END):
    return {"metric": metric, "scope": {"type": scope_type, "value": scope_value},
            "period_start": start, "period_end": end, "value": value, "n": 1}


def by_scope(docs):
    return {d["scope"]["value"]: d for d in docs}


# --- Events per hub (D-14) ---

def test_hub_counts_only_hubs_inside_the_window(sample):
    docs = by_scope(metrics.events_per_hub(sample, START, END))
    assert {hub: d["value"] for hub, d in docs.items()} == {"HUB-A": 2, "HUB-B": 1}


# --- Average delivery time (D-12) ---

def test_avg_delivery_time_matches_hand_calculation(sample):
    [doc] = metrics.avg_delivery_time_s(sample, START, END)
    assert doc["value"] == 81_000 and doc["n"] == 2


def test_avg_delivery_time_empty_day_gives_no_document(sample):
    assert metrics.avg_delivery_time_s(sample, T0 + timedelta(days=5), T0 + timedelta(days=6)) == []


# --- Load step (D-15) ---

def test_load_writes_documents(db):
    assert load_metrics(db, [metric_doc()], "run-1", NOW, START, END) == 0
    doc = db.analytics.find_one()
    assert doc["value"] == 1 and doc["n"] == 1
    assert doc["run_id"] == "run-1" and doc["computed_at"] == NOW


def test_load_rerun_overwrites_and_never_duplicates(db):
    load_metrics(db, [metric_doc(value=1)], "run-1", NOW, START, END)
    load_metrics(db, [metric_doc(value=7)], "run-2", NOW, START, END)
    assert db.analytics.count_documents({}) == 1
    assert db.analytics.find_one()["value"] == 7


def test_load_keeps_scopes_apart(db):
    docs = [metric_doc(), metric_doc(scope_type="courier", scope_value="CUR-1"),
            metric_doc(scope_type="courier", scope_value="CUR-2")]
    load_metrics(db, docs, "run-1", NOW, START, END)
    assert db.analytics.count_documents({}) == 3


def test_load_removes_outdated_documents(db):
    # CUR-9 no longer appears after a recompute, so its old document must go
    load_metrics(db, [metric_doc(), metric_doc(scope_type="courier", scope_value="CUR-9")],
                 "run-1", NOW, START, END)
    assert load_metrics(db, [metric_doc()], "run-2", NOW, START, END) == 1
    assert db.analytics.count_documents({"scope.value": "CUR-9"}) == 0


def test_load_keeps_other_periods(db):
    next_day = (END, END + timedelta(days=1))
    load_metrics(db, [metric_doc(start=next_day[0], end=next_day[1])], "run-1", NOW, *next_day)
    load_metrics(db, [metric_doc()], "run-2", NOW, START, END)
    assert db.analytics.count_documents({}) == 2


# --- Delivery metrics and schedule ---

def test_delivery_metrics_global_and_per_courier(sample):
    docs = metrics.delivery_metrics(sample, START, END)
    rate = by_scope(d for d in docs if d["metric"] == "delivery_success_rate")
    failed = by_scope(d for d in docs if d["metric"] == "failed_attempts")

    assert rate[None]["value"] == pytest.approx(2 / 3) and rate[None]["n"] == 3
    assert rate["CUR-1"]["value"] == 1 and rate["CUR-1"]["n"] == 1
    assert rate["CUR-2"]["value"] == 0.5 and rate["CUR-2"]["n"] == 2
    assert {scope: d["value"] for scope, d in failed.items()} == {None: 1, "CUR-1": 0, "CUR-2": 1}


def test_daily_window_is_the_two_previous_days():
    now = datetime(2026, 3, 10, 1, 0, 30, tzinfo=timezone.utc)
    assert daily_window(now) == (datetime(2026, 3, 8, tzinfo=timezone.utc),
                                 datetime(2026, 3, 10, tzinfo=timezone.utc))


# --- The whole job ---

def test_full_run_matches_hand_calculation(sample):
    result = run_etl(sample, START, END)
    # 1 average + 3 rates + 3 failed attempts + 2 hubs
    assert result["written"] == sample.analytics.count_documents({}) == 9
    assert sample.analytics.find_one({"metric": "avg_delivery_time_s"})["value"] == 81_000


def test_full_rerun_changes_nothing(sample):
    run_etl(sample, START, END)
    first = sorted((d["metric"], str(d["scope"]["value"]), d["value"]) for d in sample.analytics.find())
    run_etl(sample, START, END)
    second = sorted((d["metric"], str(d["scope"]["value"]), d["value"]) for d in sample.analytics.find())
    assert first == second


def test_full_run_range_covers_each_day(sample):
    results = run_range(sample, T0 - timedelta(days=1), T0 + timedelta(days=2))
    assert len(results) == 3
    assert sample.analytics.distinct("period_start") == [
        T0 - timedelta(days=1), T0, T0 + timedelta(days=1)]


def test_full_run_results_reach_the_metrics_query(sample):
    run_etl(sample, START, END)
    [doc] = queries.get_metrics(sample, "avg_delivery_time_s", "global", START)
    assert doc["n"] == 2

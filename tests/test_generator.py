"""Generator tests. No database needed: reference data is built in memory."""
from collections import Counter
from datetime import timedelta

import pytest

from generator.dataset import (COURIER_EVENTS, MAX_ATTEMPTS, PERIOD_DAYS, PERIOD_START,
                               generate_dataset)
from generator.reference_data import build_couriers, build_facilities

FACILITIES = build_facilities()
COURIERS = build_couriers([f["_id"] for f in FACILITIES if f["type"] == "depot"])

# Which event may follow which (D-27)
ALLOWED_NEXT = {
    "label_created": {"picked_up"},
    "picked_up": {"arrived_at_hub"},
    "arrived_at_hub": {"sorted"},
    "sorted": {"in_transit", "out_for_delivery"},
    "in_transit": {"arrived_at_hub"},
    "out_for_delivery": {"delivered", "delivery_failed"},
    "delivery_failed": {"out_for_delivery", "returned"},
    "delivered": set(),
    "returned": set(),
}


def dataset(n_events, seed=42):
    return list(generate_dataset(n_events, FACILITIES, COURIERS, seed))


def all_events(data):
    return [e for _, events in data for e in events]


@pytest.fixture(scope="module")
def big():
    return dataset(20_000)


@pytest.mark.parametrize("n", [0, 1, 37, 1000])
def test_exact_event_count(n):
    assert len(all_events(dataset(n))) == n


def test_same_seed_same_data():
    assert dataset(500, seed=1) == dataset(500, seed=1)
    assert dataset(500, seed=1) != dataset(500, seed=2)


def test_unique_ids(big):
    events = all_events(big)
    assert len({e["_id"] for e in events}) == len(events)
    assert len({s["_id"] for s, _ in big}) == len(big)
    assert all(e["_id"].startswith(e["shipment_id"] + "-") for e in events)  # D-29


def test_timestamps(big):
    period_end = PERIOD_START + timedelta(days=PERIOD_DAYS)
    for shipment, events in big:
        assert events[0]["event_type"] == "label_created"
        assert events[0]["ts"] == shipment["created_at"]
        times = [e["ts"] for e in events]
        assert all(a < b for a, b in zip(times, times[1:]))  # strictly increasing (D-21)
        assert all(PERIOD_START <= t < period_end for t in times)
        assert all(t.microsecond == 0 for t in times)  # whole seconds (D-28)


def test_event_order(big):
    for _, events in big:
        types = [e["event_type"] for e in events]
        for current, following in zip(types, types[1:]):
            assert following in ALLOWED_NEXT[current], types


def test_delivery_attempts(big):
    for _, events in big:
        counts = Counter(e["event_type"] for e in events)
        assert counts["delivery_failed"] <= MAX_ATTEMPTS
        if counts["returned"]:
            assert counts["delivery_failed"] == MAX_ATTEMPTS


def test_failure_rate_is_about_10_percent(big):
    counts = Counter(e["event_type"] for e in all_events(big))
    rate = counts["delivery_failed"] / (counts["delivered"] + counts["delivery_failed"])
    assert 0.07 < rate < 0.13


def test_courier_only_on_courier_events(big):
    courier_ids = {c["_id"] for c in COURIERS}
    for e in all_events(big):
        if e["event_type"] in COURIER_EVENTS:
            assert e["courier_id"] in courier_ids
        else:
            assert e["courier_id"] is None


def test_same_city_has_no_transit(big):
    for shipment, events in big:
        if shipment["origin"] == shipment["destination"]:
            assert "in_transit" not in {e["event_type"] for e in events}


def test_some_shipments_still_in_progress(big):
    last_types = {events[-1]["event_type"] for _, events in big}
    assert last_types - {"delivered", "returned"}  # D-28

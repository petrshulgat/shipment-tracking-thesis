"""Simulated shipments and their tracking events (FR-01, FR-02, FR-12).

Usage:
    for shipment, events in generate_dataset(100_000, facilities, couriers):
        ...

- Event order follows D-27; timestamps of one shipment always increase (D-21).
- Shipments are created over a 30-day period; events after its end are dropped,
  so the last shipments are still in progress (D-28).
- Exactly `n_events` events are produced, one shipment at a time, so memory
  stays small even for 10M events (D-28).
- The same seed gives the same dataset (NFR-09).
"""
import random
from datetime import datetime, timedelta, timezone

from generator.reference_data import DEFAULT_SEED, FIRST_NAMES, LAST_NAMES

PERIOD_START = datetime(2026, 3, 1, tzinfo=timezone.utc)
PERIOD_DAYS = 30

FAILURE_RATE = 0.10   # chance that one delivery attempt fails (D-27)
MAX_ATTEMPTS = 3      # after this many failed attempts the shipment is returned

SERVICE_TYPES = ["standard", "express"]
SERVICE_WEIGHTS = [0.7, 0.3]
SPEED = {"standard": 1.0, "express": 0.5}  # express waits half as long between events

COURIER_EVENTS = {"picked_up", "out_for_delivery", "delivered", "delivery_failed"}  # D-08
SYSTEM_EVENTS = {"label_created", "returned"}


def build_network(facilities, couriers):
    """Group facilities by city.

    Returns (cities, couriers_by_depot). Each city is {"code", "hub", "depots"};
    only depots that have at least one courier are used.
    """
    couriers_by_depot = {}
    for c in couriers:
        couriers_by_depot.setdefault(c["home_facility_id"], []).append(c["_id"])

    by_code = {}
    for f in sorted(facilities, key=lambda f: f["_id"]):
        code = f["_id"].split("-")[1]  # "HUB-BUD-01" -> "BUD"
        city = by_code.setdefault(code, {"code": code, "hub": None, "depots": []})
        if f["type"] == "hub":
            city["hub"] = f
        elif f["_id"] in couriers_by_depot:
            city["depots"].append(f)

    cities = [c for _, c in sorted(by_code.items()) if c["hub"] and c["depots"]]
    if not cities:
        raise ValueError("need at least one city with a hub and a depot with couriers")
    return cities, couriers_by_depot


def _person(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _route(rng, origin, dest, origin_depot, dest_depot, couriers_by_depot):
    """The steps of one shipment (D-27): (event_type, facility, courier_id, gap in hours (min, max))."""
    pickup_courier = rng.choice(couriers_by_depot[origin_depot["_id"]])
    steps = [
        ("label_created", origin_depot, None, (0, 0)),
        ("picked_up", origin_depot, pickup_courier, (2, 24)),
        ("arrived_at_hub", origin["hub"], None, (1, 8)),
        ("sorted", origin["hub"], None, (0.5, 4)),
    ]
    if dest is not origin:  # different city: travel to the destination hub
        steps += [
            ("in_transit", origin["hub"], None, (0.5, 6)),
            ("arrived_at_hub", dest["hub"], None, (4, 24)),
            ("sorted", dest["hub"], None, (0.5, 4)),
        ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        courier = rng.choice(couriers_by_depot[dest_depot["_id"]])
        wait = (2, 12) if attempt == 1 else (12, 30)  # retries happen the next day
        steps.append(("out_for_delivery", dest_depot, courier, wait))
        if rng.random() >= FAILURE_RATE:
            steps.append(("delivered", dest_depot, courier, (1, 8)))
            return steps
        steps.append(("delivery_failed", dest_depot, courier, (1, 8)))
    steps.append(("returned", dest_depot, None, (12, 48)))
    return steps


def _source(event_type):
    if event_type in SYSTEM_EVENTS:
        return "system"
    return "courier_app" if event_type in COURIER_EVENTS else "scanner"


def make_shipment(rng, number, cities, couriers_by_depot, period_start=PERIOD_START, period_days=PERIOD_DAYS):
    """One shipment document (without current_status, D-18) and all its events."""
    origin, dest = rng.choice(cities), rng.choice(cities)
    origin_depot, dest_depot = rng.choice(origin["depots"]), rng.choice(dest["depots"])
    service_type = rng.choices(SERVICE_TYPES, weights=SERVICE_WEIGHTS)[0]
    # Whole seconds: BSON dates keep only milliseconds (D-28)
    created_at = period_start + timedelta(seconds=rng.randrange(period_days * 86400))
    shipment_id = f"SHP-{number:07d}"  # D-29

    shipment = {
        "_id": shipment_id,
        "sender": {"name": _person(rng), "city": origin["hub"]["city"], "country": origin["hub"]["country"]},
        "recipient": {"name": _person(rng), "city": dest["hub"]["city"], "country": dest["hub"]["country"]},
        "origin": f"{origin['hub']['country']}-{origin['code']}",
        "destination": f"{dest['hub']['country']}-{dest['code']}",
        "service_type": service_type,
        "created_at": created_at,
    }

    events, ts = [], created_at
    steps = _route(rng, origin, dest, origin_depot, dest_depot, couriers_by_depot)
    for seq, (event_type, facility, courier_id, (low, high)) in enumerate(steps, start=1):
        # gap > 0 for every step after the first, so ts strictly increases (D-21)
        ts = ts + timedelta(seconds=round(rng.uniform(low, high) * 3600 * SPEED[service_type]))
        events.append({
            "_id": f"{shipment_id}-{seq:02d}",  # D-29
            "shipment_id": shipment_id,
            "event_type": event_type,
            "ts": ts,
            "facility_id": facility["_id"],
            "courier_id": courier_id,
            "location": {"city": facility["city"], "country": facility["country"]},
            "source": _source(event_type),
        })
    return shipment, events


def generate_dataset(n_events, facilities, couriers, seed=DEFAULT_SEED,
                     period_start=PERIOD_START, period_days=PERIOD_DAYS):
    """Yield (shipment, events) pairs until exactly n_events events are produced."""
    rng = random.Random(seed)
    cities, couriers_by_depot = build_network(facilities, couriers)
    period_end = period_start + timedelta(days=period_days)

    produced, number = 0, 0
    while produced < n_events:
        number += 1
        shipment, events = make_shipment(rng, number, cities, couriers_by_depot, period_start, period_days)
        events = [e for e in events if e["ts"] < period_end]  # still in progress at period end
        events = events[: n_events - produced]                # hit the exact count
        produced += len(events)
        yield shipment, events

"""MongoDB aggregation pipelines for the batch ETL.

Pure functions: they only build pipeline lists and never touch the database.
Window is always [start, end) on events.ts (ts must be a BSON Date).
"""

DELIVERY_EVENTS = ["delivered", "delivery_failed"]


def _window(start, end):
    return {"ts": {"$gte": start, "$lt": end}}


def avg_delivery_time(start, end):
    """One document: {_id: None, n, avg_ms} for deliveries in the window."""
    return [
        {"$match": {**_window(start, end), "event_type": "delivered"}},
        {"$lookup": {"from": "shipments", "localField": "shipment_id",
                     "foreignField": "_id", "as": "s",
                     "pipeline": [{"$project": {"created_at": 1}}]}},
        {"$unwind": "$s"},
        {"$group": {"_id": None,
                    "n": {"$sum": 1},
                    "avg_ms": {"$avg": {"$subtract": ["$ts", "$s.created_at"]}}}},
    ]


def delivery_outcomes(start, end, by_courier):
    """Counts of delivered / failed. One doc per courier, or one global doc."""
    match = {**_window(start, end), "event_type": {"$in": DELIVERY_EVENTS}}
    if by_courier:
        match["courier_id"] = {"$ne": None}
    return [
        {"$match": match},
        {"$group": {
            "_id": "$courier_id" if by_courier else None,
            "delivered": {"$sum": {"$cond": [{"$eq": ["$event_type", "delivered"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$event_type", "delivery_failed"]}, 1, 0]}},
        }},
    ]


def events_per_hub(start, end, hub_ids):
    """One doc per hub: {_id: facility_id, count}."""
    return [
        {"$match": {**_window(start, end), "facility_id": {"$in": hub_ids}}},
        {"$group": {"_id": "$facility_id", "count": {"$sum": 1}}},
    ]
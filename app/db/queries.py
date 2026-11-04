"""PyMongo queries, one function per access pattern (docs/schema_and_queries.md).

Every function takes the database as its first argument, so the API, the ingestion
code, the tests and the benchmarks all run exactly the same queries.
The ETL queries (AP-08, AP-09) live in app/etl/.
"""
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

DUPLICATE_KEY_ERROR = 11000
DEFAULT_LIMIT = 100  # D-25


def _insert_skipping_duplicates(collection, docs):
    """Insert docs, skipping ones whose _id already exists (D-19). Returns the number inserted.

    ordered=False: a duplicate _id does not stop the rest of the batch.
    Any error other than a duplicate key is raised.
    """
    if not docs:
        return 0
    try:
        return len(collection.insert_many(docs, ordered=False).inserted_ids)
    except BulkWriteError as e:
        if any(err["code"] != DUPLICATE_KEY_ERROR for err in e.details["writeErrors"]):
            raise
        return e.details["nInserted"]


# AP-01 create shipment
def create_shipment(db, shipment):
    db.shipments.insert_one(shipment)


# AP-01 for many shipments at once (generator / inserter); safe to rerun
def insert_shipments(db, shipments):
    return _insert_skipping_duplicates(db.shipments, shipments)


# AP-02 / AP-03 insert events
def insert_events(db, events):
    return _insert_skipping_duplicates(db.events, events)


def status_from_event(event):
    """The current_status document. Both ingestion paths use it, so their status matches."""
    return {"status": event["event_type"],
            "last_event_ts": event["ts"],
            "last_facility_id": event.get("facility_id"),
            "last_courier_id": event.get("courier_id")}


# AP-04 update current status (direct insert path only)
def update_current_status(db, events):
    """Set current_status from a batch of events. Returns the number of shipments changed.

    One update per shipment, using its event with the latest ts in the batch.
    The filter only matches if that event is newer than the stored status, or if
    the shipment has no status yet (D-10, D-18). ts values never tie (D-21).
    """
    latest = {}
    for e in events:
        current = latest.get(e["shipment_id"])
        if current is None or e["ts"] > current["ts"]:
            latest[e["shipment_id"]] = e

    ops = [
        UpdateOne(
            {"_id": shipment_id,
             "$or": [{"current_status.last_event_ts": {"$lt": e["ts"]}},
                     {"current_status.last_event_ts": {"$exists": False}}]},
            {"$set": {"current_status": status_from_event(e)}},
        )
        for shipment_id, e in latest.items()
    ]
    if not ops:
        return 0
    return db.shipments.bulk_write(ops, ordered=False).modified_count


# AP-05 current status
def get_current_status(db, shipment_id):
    """Returns None if the shipment does not exist.

    A shipment without events yet has no current_status field (D-18).
    """
    return db.shipments.find_one({"_id": shipment_id}, {"current_status": 1})


# AP-06 event history (complete, FR-07)
def get_history(db, shipment_id):
    return list(db.events.find({"shipment_id": shipment_id}).sort("ts", 1))


# AP-07 events by facility and time range [start, end)
def events_by_facility(db, facility_id, start, end, limit=DEFAULT_LIMIT):
    return list(db.events.find({"facility_id": facility_id,
                                "ts": {"$gte": start, "$lt": end}})
                .sort("ts", 1).limit(limit))


# AP-10 get metrics
def get_metrics(db, metric, scope_type, start):
    return list(db.analytics.find({"metric": metric, "scope.type": scope_type,
                                   "period_start": {"$gte": start}})
                .sort("period_start", 1))


# AP-11 events by courier and time range [start, end)
def events_by_courier(db, courier_id, start, end, limit=DEFAULT_LIMIT):
    return list(db.events.find({"courier_id": courier_id,
                                "ts": {"$gte": start, "$lt": end}})
                .sort("ts", 1).limit(limit))

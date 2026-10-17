# Schema, Access Patterns and Queries

## 1. Access patterns

| ID | Operation | Req. | Type | Collection | Filter / sort / returns | Frequency | Target |
|---|---|---|---|---|---|---|---|
| AP-01 | Create shipment | FR-01 | write | shipments | insert one | low | none |
| AP-02 | Insert event micro-batch (streaming) | FR-02/03 | write | events | `insert_many`, unordered, 100 to 5,000 docs | very high | >= 5,000 events/s (NFR-01) |
| AP-03 | Bulk load events | FR-04 | write | events | `insert_many` in large chunks | batch | none (measured) |
| AP-04 | Update current status per batch | FR-05 | write | shipments | filter `_id`, `last_event_ts` older than new ts; set `current_status` | very high | must not slow AP-02 |
| AP-05 | Get current status | FR-06 | read | shipments | filter `_id`; returns `current_status` | high | p95 < 20 ms at 1M events (NFR-03) |
| AP-06 | Get event history | FR-07 | read | events | filter `shipment_id`; sort `ts` asc | high | p95 < 50 ms at 1M events (NFR-02) |
| AP-07 | Events by facility and time range | FR-08 | read | events | filter `facility_id`, `ts` range; sort `ts` | medium | none yet |
| AP-08 | ETL scan and aggregation | FR-09 | scan | events (+ shipments, couriers) | group by shipment, event type, hub, courier over a time window | batch | roughly linear runtime (NFR-05) |
| AP-09 | Write ETL results | FR-10 | write | analytics | upsert metric docs | batch | none |
| AP-10 | Get metrics via API | FR-10 | read | analytics | filter `metric`, `scope.type`, `period_start` | medium | none yet |
| AP-11 | Events by courier and time range (new) | FR-08 (extension) | read | events | filter `courier_id`, `ts` range; sort `ts` | low | none yet |

## 2. Example documents

### shipments
```json
{
  "_id": "SHP-889021",
  "sender": {"name": "Acme Kft.", "city": "Debrecen", "country": "HU"},
  "recipient": {"name": "J. Smith", "city": "Vienna", "country": "AT"},
  "origin": "HU-DEB",
  "destination": "AT-VIE",
  "service_type": "express",
  "created_at": "2026-03-01T08:00:00Z",
  "current_status": {
    "status": "arrived_at_hub",
    "last_event_ts": "2026-03-04T10:15:00Z",
    "last_facility_id": "HUB-BUD-01",
    "last_courier_id": null
  }
}
```

### events
```json
{
  "_id": "evt_000123",
  "shipment_id": "SHP-889021",
  "event_type": "arrived_at_hub",
  "ts": "2026-03-04T10:15:00Z",
  "facility_id": "HUB-BUD-01",
  "courier_id": null,
  "location": {"city": "Budapest", "country": "HU"},
  "source": "scanner"
}
```
`courier_id` is set only for courier-handled events (`picked_up`, `out_for_delivery`, `delivered`, `delivery_failed`). For the other event types it is `null` (or omitted).

### facilities
```json
{"_id": "HUB-BUD-01", "name": "Budapest Hub", "type": "hub", "city": "Budapest", "country": "HU"}
```

### couriers
```json
{"_id": "CUR-0042", "name": "K. Nagy", "home_facility_id": "HUB-DEB-01", "vehicle_type": "van"}
```

### analytics
```json
{
  "_id": "ObjectId(...)",
  "metric": "delivery_success_rate",
  "scope": {"type": "courier", "value": "CUR-0042"},
  "period_start": "2026-03-01T00:00:00Z",
  "period_end": "2026-03-02T00:00:00Z",
  "value": 0.94,
  "computed_at": "2026-03-02T01:00:00Z",
  "run_id": "etl_2026-03-02_01"
}
```

## 3. Queries (PyMongo)

```python
# AP-01 create shipment
db.shipments.insert_one(shipment_doc)

# AP-02 / AP-03 insert events (unordered: a duplicate _id does not stop the batch)
db.events.insert_many(batch, ordered=False)

# AP-04 status update, only if the new event is newer.
# In the consumer: build one UpdateOne per shipment (last event of the batch) and send with bulk_write.
db.shipments.update_one(
    {"_id": shipment_id,
     "$or": [{"current_status.last_event_ts": {"$lt": ts}},
             {"current_status.last_event_ts": {"$exists": False}}]},
    {"$set": {"current_status": {"status": event_type,
                                 "last_event_ts": ts,
                                 "last_facility_id": facility_id,
                                 "last_courier_id": courier_id}}})

# AP-05 current status
db.shipments.find_one({"_id": shipment_id}, {"current_status": 1})

# AP-06 event history
db.events.find({"shipment_id": shipment_id}).sort("ts", 1)

# AP-07 events by facility and time range
db.events.find({"facility_id": facility_id,
                "ts": {"$gte": start, "$lt": end}}).sort("ts", 1)

# AP-08 ETL example: events per hub per day
db.events.aggregate([
    {"$match": {"ts": {"$gte": start, "$lt": end}}},
    {"$group": {"_id": {"hub": "$facility_id",
                        "day": {"$dateTrunc": {"date": "$ts", "unit": "day"}}},
                "count": {"$sum": 1}}}
])

# AP-08 ETL example: delivery success rate per courier
db.events.aggregate([
    {"$match": {"ts": {"$gte": start, "$lt": end},
                "event_type": {"$in": ["delivered", "delivery_failed"]},
                "courier_id": {"$ne": None}}},
    {"$group": {"_id": "$courier_id",
                "delivered": {"$sum": {"$cond": [{"$eq": ["$event_type", "delivered"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$event_type", "delivery_failed"]}, 1, 0]}}}},
    {"$set": {"success_rate": {"$divide": ["$delivered", {"$add": ["$delivered", "$failed"]}]}}}
])

# AP-09 write ETL results (upsert: reruns do not duplicate)
db.analytics.update_one(
    {"metric": m, "scope.type": st, "scope.value": sv, "period_start": ps, "period_end": pe},
    {"$set": {"value": v, "computed_at": now, "run_id": run_id}}, upsert=True)

# AP-10 get metrics
db.analytics.find({"metric": metric, "scope.type": t, "period_start": {"$gte": start}})

# AP-11 events by courier and time range
db.events.find({"courier_id": courier_id,
                "ts": {"$gte": start, "$lt": end}}).sort("ts", 1)
```

## 4. Index plan (the "full" configuration for experiment O-02)

| Collection | Index | Serves | In "minimal" |
|---|---|---|---|
| shipments | `_id` (automatic) | AP-04, AP-05 | yes |
| events | `_id` (automatic) | idempotent inserts | yes |
| events | `(shipment_id, ts)` | AP-06 | yes |
| events | `(facility_id, ts)` | AP-07 | no |
| events | `(courier_id, ts)`, partial: `courier_id` exists as a string | AP-11 | no |
| events | `(ts)` | AP-08 time window | no |
| analytics | `(metric, scope.type, period_start)` | AP-10 | yes |

Configurations: `none` = automatic `_id` indexes only; `minimal` = rows marked yes; `full` = all rows.

## 5. Rules

- **Status update rule:** `current_status` changes only if the new event `ts` is greater than `last_event_ts`. Kafka guarantees order only inside one partition (NFR-08), so micro-batches can still deliver late events.
- **Idempotency:** `_id` = `event_id`; a duplicate insert raises a duplicate key error that the consumer ignores (O-05).
- **Reference, don't embed:** events store `facility_id` and `courier_id`; names live in `facilities` and `couriers`.

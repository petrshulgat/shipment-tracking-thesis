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

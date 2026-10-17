"""One function per metric: run a pipeline, return a list of analytics docs.

computed_at and run_id are added later by run.py.
"""
from . import pipelines


def _doc(metric, scope_type, scope_value, value, n, start, end):
    return {
        "metric": metric,
        "scope": {"type": scope_type, "value": scope_value},
        "period_start": start,
        "period_end": end,
        "value": value,
        "n": n,  # denominator / count behind the value
    }


def avg_delivery_time_s(db, start, end):
    rows = list(db.events.aggregate(pipelines.avg_delivery_time(start, end)))
    if not rows:
        return []
    r = rows[0]
    return [_doc("avg_delivery_time_s", "global", None, r["avg_ms"] / 1000, r["n"], start, end)]


def delivery_metrics(db, start, end):
    """delivery_success_rate and failed_attempts, for global and per courier."""
    docs = []
    for by_courier, scope_type in ((False, "global"), (True, "courier")):
        for r in db.events.aggregate(pipelines.delivery_outcomes(start, end, by_courier)):
            scope_value = r["_id"]  # None for global
            total = r["delivered"] + r["failed"]
            docs.append(_doc("delivery_success_rate", scope_type, scope_value,
                             r["delivered"] / total, total, start, end))
            docs.append(_doc("failed_attempts", scope_type, scope_value,
                             r["failed"], r["failed"], start, end))
    return docs


def events_per_hub(db, start, end):
    hub_ids = [f["_id"] for f in db.facilities.find({"type": "hub"}, {"_id": 1})]
    if not hub_ids:
        return []
    return [_doc("events_per_hub", "hub", r["_id"], r["count"], r["count"], start, end)
            for r in db.events.aggregate(pipelines.events_per_hub(start, end, hub_ids))]


ALL_METRICS = [avg_delivery_time_s, delivery_metrics, events_per_hub]
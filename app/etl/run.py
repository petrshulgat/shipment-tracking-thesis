"""Batch ETL runner.

CLI:  python -m app.etl.run --start 2026-03-01 --end 2026-03-04
Runs one day at a time over [start, end).
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

from pymongo import UpdateOne

from app.db.client import get_db  # assumed: returns the pymongo Database
from .metrics import ALL_METRICS


def run_etl(db, start, end):
    """Compute all metrics for one window [start, end) and load them into analytics.

    Safe to rerun: upserts overwrite, stale docs of the same period are removed.
    """
    now = datetime.now(timezone.utc)
    run_id = f"etl_{start:%Y-%m-%d}_{now:%Y%m%dT%H%M%S}"
    t0 = time.perf_counter()

    # Extract + Transform
    docs = []
    for metric_fn in ALL_METRICS:
        docs.extend(metric_fn(db, start, end))

    # Load
    ops = [
        UpdateOne(
            {"metric": d["metric"], "scope.type": d["scope"]["type"],
             "scope.value": d["scope"]["value"],
             "period_start": d["period_start"], "period_end": d["period_end"]},
            {"$set": {"value": d["value"], "n": d["n"],
                      "computed_at": now, "run_id": run_id}},
            upsert=True,
        )
        for d in docs
    ]
    if ops:
        db.analytics.bulk_write(ops, ordered=False)

    # Cleanup only after a successful load
    deleted = db.analytics.delete_many(
        {"period_start": start, "period_end": end, "run_id": {"$ne": run_id}}
    ).deleted_count

    return {"run_id": run_id, "written": len(docs), "deleted_stale": deleted,
            "seconds": round(time.perf_counter() - t0, 3)}


def run_range(db, start, end):
    """Run the ETL day by day over [start, end)."""
    results, day = [], start
    while day < end:
        results.append(run_etl(db, day, day + timedelta(days=1)))
        day += timedelta(days=1)
    return results


def _parse(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, type=_parse)
    p.add_argument("--end", required=True, type=_parse)
    a = p.parse_args()
    for r in run_range(get_db(), a.start, a.end):
        print(r)
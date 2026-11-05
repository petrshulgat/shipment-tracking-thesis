"""Query speed experiment (FR-13, NFR-02, NFR-03, NFR-04, D-34).

Run inside Docker:  docker compose run --rm --build query-benchmark
Quick smoke run:    docker compose run --rm query-benchmark python -m benchmarks.query_benchmark --sizes 1000 --rounds 1

For each dataset size and index config: load the data, save the query plans,
then time each query. Results are appended run by run, as in insert_benchmark.py.
"""
import argparse
import csv
import json
import math
import os
import random
import re
import time
from datetime import timedelta

import httpx2

from app.db import queries
from app.db.client import get_db
from app.ingestion.bulk import run_bulk
from app.ingestion.common import reset_database
from benchmarks.insert_benchmark import BENCHMARK_DB, INDEX_CONFIGS, RESULTS_DIR, SIZES, write_environment
from generator.dataset import PERIOD_DAYS, PERIOD_START
from generator.reference_data import DEFAULT_SEED

API_URL = os.getenv("BENCHMARK_API_URL", "http://benchmark-api:8000")
ROUNDS = 3
FAST_CALLS, SCAN_CALLS = 1000, 100      # calls per round (D-34)
FAST_WARMUP, SCAN_WARMUP = 100, 10      # calls before measuring, not counted

QUERIES = ["AP-05", "AP-06", "AP-07", "AP-11"]
API_QUERIES = ["AP-05", "AP-06"]

# Which queries must read every event in each index config (schema_and_queries.md section 4)
FULL_SCANS = {"none": {"AP-06", "AP-07", "AP-11"}, "minimal": {"AP-07", "AP-11"}, "full": set()}

DB_CALLS = {
    "AP-05": queries.get_current_status,
    "AP-06": queries.get_history,
    "AP-07": queries.events_by_facility,
    "AP-11": queries.events_by_courier,
}
API_PATHS = {"AP-05": "/shipments/{}/status", "AP-06": "/shipments/{}/events"}

RESULT_COLUMNS = ["level", "query", "index_config", "n_events", "round", "calls",
                  "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"]
PLAN_COLUMNS = ["query", "index_config", "n_events", "stage", "index_name",
                "docs_examined", "keys_examined", "returned"]


def percentile(sorted_values, p):
    """Nearest-rank percentile: the smallest value that p% of the values do not exceed."""
    return sorted_values[max(math.ceil(p / 100 * len(sorted_values)) - 1, 0)]


def call_counts(query, index_config):
    """(calls per round, warm-up calls): scans are slow, so they get fewer calls (D-34)."""
    if query in FULL_SCANS[index_config]:
        return SCAN_CALLS, SCAN_WARMUP
    return FAST_CALLS, FAST_WARMUP


def load_ids(db):
    return {
        "shipments": [s["_id"] for s in db.shipments.find({}, {"_id": 1}).sort("_id")],
        "facilities": [f["_id"] for f in db.facilities.find({}, {"_id": 1}).sort("_id")],
        "couriers": [c["_id"] for c in db.couriers.find({}, {"_id": 1}).sort("_id")],
    }


def random_day(rng):
    """A one-day window [start, end) inside the data period."""
    start = PERIOD_START + timedelta(days=rng.randrange(PERIOD_DAYS))
    return start, start + timedelta(days=1)


def make_inputs(query, rng, ids, count):
    """Arguments for `count` calls of a query. A fixed seed gives every config the same inputs."""
    if query in ("AP-05", "AP-06"):
        return [(rng.choice(ids["shipments"]),) for _ in range(count)]
    key = "facilities" if query == "AP-07" else "couriers"
    return [(rng.choice(ids[key]), *random_day(rng)) for _ in range(count)]


def measure(call, inputs):
    """Run call(*args) for each input. Returns latencies in milliseconds, sorted."""
    times = []
    for args in inputs:
        t0 = time.perf_counter()
        call(*args)
        times.append((time.perf_counter() - t0) * 1000)
    return sorted(times)


def api_call(client, query):
    """A function that sends one real HTTP request for this query."""
    def call(shipment_id):
        client.get(API_PATHS[query].format(shipment_id)).raise_for_status()
    return call


def result_row(level, query, index_config, n_events, round_number, times):
    return {
        "level": level, "query": query, "index_config": index_config, "n_events": n_events,
        "round": round_number, "calls": len(times),
        "mean_ms": round(sum(times) / len(times), 3),
        "p50_ms": round(percentile(times, 50), 3), "p95_ms": round(percentile(times, 95), 3),
        "p99_ms": round(percentile(times, 99), 3), "max_ms": round(times[-1], 3),
    }


def explain_query(db, query, ids):
    """MongoDB's explanation of how it ran the query. Same filters as app/db/queries.py."""
    start, end = PERIOD_START + timedelta(days=15), PERIOD_START + timedelta(days=16)
    if query == "AP-05":
        cursor = db.shipments.find({"_id": ids["shipments"][0]}, {"current_status": 1})
    elif query == "AP-06":
        cursor = db.events.find({"shipment_id": ids["shipments"][0]}).sort("ts", 1)
    elif query == "AP-07":
        cursor = (db.events.find({"facility_id": "HUB-BUD-01", "ts": {"$gte": start, "$lt": end}})
                  .sort("ts", 1).limit(queries.DEFAULT_LIMIT))
    else:
        cursor = (db.events.find({"courier_id": ids["couriers"][0], "ts": {"$gte": start, "$lt": end}})
                  .sort("ts", 1).limit(queries.DEFAULT_LIMIT))
    return cursor.explain()


def summarise_plan(explain):
    """Reduce an explain() result to what matters: scan or index, and the work done."""
    plan = json.dumps(explain["queryPlanner"]["winningPlan"], default=str)  # plans contain dates
    if "COLLSCAN" in plan:
        stage = "COLLSCAN"
    elif "IXSCAN" in plan:
        stage = "IXSCAN"
    else:
        stage = "ID_LOOKUP"  # direct read by _id
    index_name = re.search(r'"indexName": "([^"]+)"', plan)
    stats = explain["executionStats"]
    return {"stage": stage, "index_name": index_name.group(1) if index_name else "",
            "docs_examined": stats["totalDocsExamined"], "keys_examined": stats["totalKeysExamined"],
            "returned": stats["nReturned"]}


def plan_runs(sizes):
    return [(n, i) for n in sizes for i in INDEX_CONFIGS]


def run_combination(db, n_events, index_config, rounds, client, write_result, write_plan):
    """Load one dataset, save its query plans, then measure every query."""
    reset_database(db, index_config)
    run_bulk(db, n_events)
    ids = load_ids(db)

    for query in QUERIES:
        summary = summarise_plan(explain_query(db, query, ids))
        write_plan({"query": query, "index_config": index_config, "n_events": n_events, **summary})

    levels = [("database", q, lambda *args, c=DB_CALLS[q]: c(db, *args)) for q in QUERIES]
    if client:
        levels += [("api", q, api_call(client, q)) for q in API_QUERIES]

    for level, query, call in levels:
        rng = random.Random(DEFAULT_SEED)  # same inputs for every index config
        calls, warmup = call_counts(query, index_config)
        measure(call, make_inputs(query, rng, ids, warmup))
        for round_number in range(1, rounds + 1):
            times = measure(call, make_inputs(query, rng, ids, calls))
            row = result_row(level, query, index_config, n_events, round_number, times)
            write_result(row)
            print(f"{level} {query} {index_config} {n_events} round {round_number}: "
                  f"p50 {row['p50_ms']} ms, p95 {row['p95_ms']} ms", flush=True)


def wait_for_api(client, attempts=60):
    for _ in range(attempts):
        try:
            client.get("/health").raise_for_status()
            return
        except httpx2.HTTPError:
            time.sleep(1)
    raise RuntimeError(f"API not reachable at {API_URL}")


def run_experiment(db, sizes, rounds, client, results_path, plans_path):
    with open(results_path, "w", newline="") as rf, open(plans_path, "w", newline="") as pf:
        results = csv.DictWriter(rf, fieldnames=RESULT_COLUMNS)
        plans = csv.DictWriter(pf, fieldnames=PLAN_COLUMNS)
        results.writeheader()
        plans.writeheader()

        def write_result(row):
            results.writerow(row)
            rf.flush()

        def write_plan(row):
            plans.writerow(row)
            pf.flush()

        for n_events, index_config in plan_runs(sizes):
            run_combination(db, n_events, index_config, rounds, client, write_result, write_plan)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", type=int, nargs="+", default=SIZES)
    p.add_argument("--rounds", type=int, default=ROUNDS)
    p.add_argument("--no-api", action="store_true", help="skip the API-level measurements")
    a = p.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_db(BENCHMARK_DB)
    write_environment(db, RESULTS_DIR / "environment.txt")
    client = None if a.no_api else httpx2.Client(base_url=API_URL, timeout=60)
    if client:
        wait_for_api(client)
    run_experiment(db, a.sizes, a.rounds, client,
                   RESULTS_DIR / "query_results.csv", RESULTS_DIR / "query_plans.csv")
    db.client.drop_database(BENCHMARK_DB)
    print("Finished. Results: benchmarks/results/query_results.csv")

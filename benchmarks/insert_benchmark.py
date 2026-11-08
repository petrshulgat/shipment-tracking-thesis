"""Insert performance experiment (FR-13, NFR-01, D-32).

Run inside Docker:  docker compose run --rm --build benchmark
Quick smoke run:    docker compose run --rm benchmark python -m benchmarks.insert_benchmark --sizes 1000 --repeats 1

Every run starts from a reset database and appends one row to the results CSV,
so finished runs are kept even if the experiment stops halfway.
Uses its own database, so the demo data in `tracking` stays untouched.
"""
import argparse
import csv
import os
import platform
from pathlib import Path

import pymongo

from app.db.client import get_db
from app.ingestion.bulk import DEFAULT_CHUNK_SIZE, run_bulk
from app.ingestion.common import reset_database
from app.ingestion.direct import run_direct

BENCHMARK_DB = "tracking_benchmark"
RESULTS_DIR = Path(__file__).parent / "results"

# (method name, path function, batch size)
METHODS = [
    ("single", run_direct, 1),
    ("batch_100", run_direct, 100),
    ("batch_1000", run_direct, 1000),
    ("batch_5000", run_direct, 5000),
    ("bulk", run_bulk, DEFAULT_CHUNK_SIZE),
]
INDEX_CONFIGS = ["none", "minimal", "full"]
SIZES = [100_000, 1_000_000]
REPEATS = 3  # several runs per test (NFR-09)
SINGLE_MAX_EVENTS = 100_000  # single inserts are too slow for more (D-32)

COLUMNS = ["method", "batch_size", "index_config", "n_events", "repeat", "shipments", "batches",
           "shipment_s", "insert_s", "status_s", "db_seconds", "events_per_s", "insert_only_events_per_s"]


def run_once(db, method, run, batch_size, index_config, n_events, repeat):
    """One measurement: reset, load, check that nothing was lost (NFR-06), return a CSV row."""
    reset_database(db, index_config)
    stats = run(db, n_events, batch_size)
    stored = db.events.count_documents({})
    if stored != n_events:
        raise RuntimeError(f"{method}: stored {stored} events, expected {n_events}")
    return {
        "method": method, "batch_size": batch_size, "index_config": index_config,
        "n_events": n_events, "repeat": repeat, "shipments": stats["shipments"],
        "batches": stats["batches"], "shipment_s": round(stats["shipment_s"], 3),
        "insert_s": round(stats["insert_s"], 3), "status_s": round(stats["status_s"], 3),
        "db_seconds": stats["db_seconds"], "events_per_s": stats["events_per_s"],
        "insert_only_events_per_s": round(stats["inserted"] / stats["insert_s"]),
    }


def plan_runs(sizes, repeats, methods=None, index_configs=None):
    """All combinations. The repeat loop is outermost, so slow periods on the laptop
    affect one repeat of each combination rather than all repeats of one.
    methods and index_configs optionally pick a subset (D-37)."""
    return [(m, r, b, i, n, repeat)
            for repeat in range(1, repeats + 1)
            for n in sizes
            for i in (index_configs or INDEX_CONFIGS)
            for m, r, b in METHODS
            if (methods is None or m in methods)
            and (m != "single" or n <= SINGLE_MAX_EVENTS)]


def run_experiment(db, sizes, repeats, out_path, methods=None, index_configs=None):
    runs = plan_runs(sizes, repeats, methods, index_configs)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for number, args in enumerate(runs, start=1):
            row = run_once(db, *args)
            writer.writerow(row)
            f.flush()
            print(f"[{number}/{len(runs)}] {row['method']} {row['index_config']} "
                  f"{row['n_events']} events: {row['events_per_s']} events/s", flush=True)
    return len(runs)


def write_environment(db, path):
    """Record the test environment next to the results (NFR-09)."""
    cpu = "unknown"
    memory = "unknown"
    if os.path.exists("/proc/cpuinfo"):  # visible inside the Linux container
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        cpu = next((l.split(":")[1].strip() for l in lines if l.startswith("model name")), cpu)
        memory = Path("/proc/meminfo").read_text().splitlines()[0].split(":")[1].strip()
    path.write_text(
        f"CPU: {cpu}\n"
        f"CPUs visible to Docker: {os.cpu_count()}\n"
        f"Memory visible to Docker: {memory}\n"
        f"MongoDB: {db.client.server_info()['version']}\n"
        f"Python: {platform.python_version()}\n"
        f"PyMongo: {pymongo.version}\n"
        f"Write concern: MongoDB default\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", type=int, nargs="+", default=SIZES)
    p.add_argument("--repeats", type=int, default=REPEATS)
    p.add_argument("--methods", nargs="+", choices=[m for m, _, _ in METHODS])
    p.add_argument("--index-configs", nargs="+", choices=INDEX_CONFIGS)
    p.add_argument("--out", default="insert_results.csv", help="file name in benchmarks/results/")
    a = p.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_db(BENCHMARK_DB)
    write_environment(db, RESULTS_DIR / "environment.txt")
    total = run_experiment(db, a.sizes, a.repeats, RESULTS_DIR / a.out, a.methods, a.index_configs)
    db.client.drop_database(BENCHMARK_DB)
    print(f"Finished {total} runs. Results: benchmarks/results/{a.out}")

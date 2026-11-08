"""ETL runtime experiment (FR-13, NFR-05, D-36, D-37).

Run inside Docker:  docker compose run --rm benchmark python -m benchmarks.etl_benchmark
Quick smoke run:    docker compose run --rm benchmark python -m benchmarks.etl_benchmark --sizes 1000 --repeats 1

For each dataset size and index config: load the data once, then time the ETL
over the same 7 days several times. `minimal` vs `full` shows whether the
`events_ts` index helps the ETL (D-36).
"""
import argparse
import csv
import time
from datetime import datetime, timedelta, timezone

from app.db.client import get_db
from app.etl.run import run_range
from app.ingestion.bulk import run_bulk
from app.ingestion.common import reset_database
from benchmarks.insert_benchmark import BENCHMARK_DB, RESULTS_DIR

ETL_START = datetime(2026, 3, 8, tzinfo=timezone.utc)
ETL_DAYS = 7
ETL_END = ETL_START + timedelta(days=ETL_DAYS)

SIZES = [100_000, 1_000_000, 10_000_000]
INDEX_CONFIGS = ["minimal", "full"]
REPEATS = 3

COLUMNS = ["n_events", "index_config", "repeat", "days", "events_in_window",
           "docs_written", "seconds", "seconds_per_day"]


def run_once(db, n_events, index_config, repeat):
    """Time one ETL run over the 7 days. Analytics is emptied first, so every
    repeat does the same work (inserts, not updates of existing documents)."""
    db.analytics.delete_many({})
    t0 = time.perf_counter()
    results = run_range(db, ETL_START, ETL_END)
    seconds = time.perf_counter() - t0
    return {
        "n_events": n_events, "index_config": index_config, "repeat": repeat, "days": ETL_DAYS,
        "events_in_window": db.events.count_documents({"ts": {"$gte": ETL_START, "$lt": ETL_END}}),
        "docs_written": sum(r["written"] for r in results),
        "seconds": round(seconds, 3), "seconds_per_day": round(seconds / ETL_DAYS, 3),
    }


def run_experiment(db, sizes, index_configs, repeats, out_path):
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for n_events in sizes:
            for index_config in index_configs:
                reset_database(db, index_config)
                run_bulk(db, n_events)
                for repeat in range(1, repeats + 1):
                    row = run_once(db, n_events, index_config, repeat)
                    writer.writerow(row)
                    f.flush()
                    print(f"ETL {index_config} {n_events} events, repeat {repeat}: "
                          f"{row['seconds_per_day']} s per day", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", type=int, nargs="+", default=SIZES)
    p.add_argument("--index-configs", nargs="+", choices=INDEX_CONFIGS, default=INDEX_CONFIGS)
    p.add_argument("--repeats", type=int, default=REPEATS)
    p.add_argument("--out", default="etl_results.csv", help="file name in benchmarks/results/")
    a = p.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_db(BENCHMARK_DB)
    run_experiment(db, a.sizes, a.index_configs, a.repeats, RESULTS_DIR / a.out)
    db.client.drop_database(BENCHMARK_DB)
    print(f"Finished. Results: benchmarks/results/{a.out}")

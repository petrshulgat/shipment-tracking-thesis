"""Bulk insert path (FR-04, AP-03, D-02, D-17).

CLI:  python -m app.ingestion.bulk --events 1000000 [--chunk-size 10000] [--seed 42] [--reset]

Shipments are written with their final current_status, already computed by the
generator, and events follow in large chunks. No status updates run (no AP-04).
"""
import argparse

from app.db.client import get_db
from app.db.indexes import INDEX_CONFIGS
from app.ingestion.common import load_dataset, reset_database
from generator.reference_data import DEFAULT_SEED

DEFAULT_CHUNK_SIZE = 10_000  # D-31


def run_bulk(db, n_events, chunk_size=DEFAULT_CHUNK_SIZE, seed=DEFAULT_SEED):
    return load_dataset(db, n_events, chunk_size, seed, update_status=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--events", type=int, default=100_000)
    p.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--reset", action="store_true", help="drop shipments and events first")
    p.add_argument("--indexes", choices=list(INDEX_CONFIGS), default="full",
                   help="index config applied by --reset (D-36)")
    a = p.parse_args()

    db = get_db()
    if a.reset:
        reset_database(db, a.indexes)
    print(run_bulk(db, a.events, a.chunk_size, a.seed))

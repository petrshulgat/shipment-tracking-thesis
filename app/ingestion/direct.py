"""Direct insert path (FR-03, FR-05, D-02, D-30).

CLI:  python -m app.ingestion.direct --events 100000 [--batch-size 1000] [--seed 42] [--reset]

For each batch of `batch_size` events:
  1. insert the shipments those events belong to, without current_status (D-18)
  2. insert the events (AP-02, duplicates skipped, D-19)
  3. update current_status of the affected shipments (AP-04, D-10)
"""
import argparse

from app.db.client import get_db
from app.db.indexes import INDEX_CONFIGS
from app.ingestion.common import load_dataset, reset_database
from generator.reference_data import DEFAULT_SEED

DEFAULT_BATCH_SIZE = 1000  # D-33


def run_direct(db, n_events, batch_size=DEFAULT_BATCH_SIZE, seed=DEFAULT_SEED):
    return load_dataset(db, n_events, batch_size, seed, update_status=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--events", type=int, default=100_000)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--reset", action="store_true", help="drop shipments and events first")
    p.add_argument("--indexes", choices=list(INDEX_CONFIGS), default="minimal",
                   help="index config applied by --reset (O-02)")
    a = p.parse_args()

    db = get_db()
    if a.reset:
        reset_database(db, a.indexes)
    print(run_direct(db, a.events, a.batch_size, a.seed))
    print("Try in Swagger (http://localhost:8000/docs): shipment SHP-0000001")

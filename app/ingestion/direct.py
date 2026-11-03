"""Direct insert path (FR-03, FR-05, D-02, D-30).

CLI:  python -m app.ingestion.direct --events 100000 [--batch-size 1000] [--seed 42] [--reset]

For each batch of `batch_size` events:
  1. insert the shipments those events belong to, without current_status (D-18)
  2. insert the events (AP-02, duplicates skipped, D-19)
  3. update current_status of the affected shipments (AP-04, D-10)
"""
import argparse
import time

from app.db import queries
from app.db.client import get_db
from app.db.indexes import INDEX_CONFIGS, apply_indexes
from generator.dataset import generate_dataset
from generator.reference_data import DEFAULT_SEED, load_reference_data

DEFAULT_BATCH_SIZE = 1000  # temporary default, O-03 is still open


def reset_database(db, index_config="minimal"):
    """Start from a clean state (D-05): empty shipments and events, fresh reference data and indexes."""
    db.shipments.drop()
    db.events.drop()
    load_reference_data(db)
    apply_indexes(db, index_config)


def run_direct(db, n_events, batch_size=DEFAULT_BATCH_SIZE, seed=DEFAULT_SEED):
    """Generate n_events events and write them batch by batch. Returns counts and timing."""
    facilities = list(db.facilities.find().sort("_id"))
    couriers = list(db.couriers.find().sort("_id"))
    if not facilities or not couriers:
        raise RuntimeError("No reference data. Run with --reset or: python -m generator.reference_data")

    stats = {"generated": 0, "inserted": 0, "shipments": 0, "status_updates": 0, "batches": 0}
    shipments, events = [], []  # waiting to be written

    def write_batch(batch):
        # Shipments first: AP-04 can only update shipments that exist (D-18)
        stats["shipments"] += queries.insert_shipments(db, shipments)
        shipments.clear()
        stats["inserted"] += queries.insert_events(db, batch)
        stats["status_updates"] += queries.update_current_status(db, batch)
        stats["batches"] += 1

    t0 = time.perf_counter()
    for shipment, shipment_events in generate_dataset(n_events, facilities, couriers, seed):
        shipments.append(shipment)
        events.extend(shipment_events)
        stats["generated"] += len(shipment_events)
        while len(events) >= batch_size:  # every batch is exactly batch_size, except the last
            write_batch(events[:batch_size])
            events = events[batch_size:]
    if shipments or events:
        write_batch(events)

    seconds = time.perf_counter() - t0
    stats["seconds"] = round(seconds, 2)
    # Includes generation time; the benchmarks will measure insert time separately (FR-13)
    stats["events_per_s"] = round(stats["inserted"] / seconds) if seconds else None
    return stats


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

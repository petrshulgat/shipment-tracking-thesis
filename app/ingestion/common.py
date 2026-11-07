"""The write loop shared by both ingestion paths (D-02).

direct.py and bulk.py differ only in the batch size and in who sets current_status.
Only database calls are timed, not data generation (D-32).
"""
import time

from app.db import queries
from app.db.indexes import apply_indexes
from generator.dataset import generate_dataset
from generator.reference_data import DEFAULT_SEED, load_reference_data


def reset_database(db, index_config="full"):  # D-36
    """Start from a clean state (D-05): empty shipments and events, fresh reference data and indexes."""
    db.shipments.drop()
    db.events.drop()
    load_reference_data(db)
    apply_indexes(db, index_config)


def load_dataset(db, n_events, batch_size, seed=DEFAULT_SEED, update_status=True):
    """Generate n_events events and write them in batches. Returns counts and timing.

    update_status=True:  direct path, shipments start without a status, AP-04 runs per batch.
    update_status=False: bulk path, the generator already set the final status (D-17).
    """
    facilities = list(db.facilities.find().sort("_id"))
    couriers = list(db.couriers.find().sort("_id"))
    if not facilities or not couriers:
        raise RuntimeError("No reference data. Run with --reset or: python -m generator.reference_data")

    stats = {"generated": 0, "inserted": 0, "shipments": 0, "status_updates": 0, "batches": 0,
             "shipment_s": 0.0, "insert_s": 0.0, "status_s": 0.0}
    shipments, events = [], []  # waiting to be written

    def timed(seconds_key, function, docs):
        t0 = time.perf_counter()
        result = function(db, docs)
        stats[seconds_key] += time.perf_counter() - t0
        return result

    def write_batch(batch):
        # Shipments first: AP-04 can only update shipments that exist (D-18)
        stats["shipments"] += timed("shipment_s", queries.insert_shipments, shipments)
        shipments.clear()
        stats["inserted"] += timed("insert_s", queries.insert_events, batch)
        if update_status:
            stats["status_updates"] += timed("status_s", queries.update_current_status, batch)
        stats["batches"] += 1

    dataset = generate_dataset(n_events, facilities, couriers, seed, with_status=not update_status)
    for shipment, shipment_events in dataset:
        shipments.append(shipment)
        events.extend(shipment_events)
        stats["generated"] += len(shipment_events)
        while len(events) >= batch_size:  # every batch is exactly batch_size, except the last
            write_batch(events[:batch_size])
            events = events[batch_size:]
    if shipments or events:
        write_batch(events)

    db_seconds = stats["shipment_s"] + stats["insert_s"] + stats["status_s"]
    stats["db_seconds"] = round(db_seconds, 3)
    stats["events_per_s"] = round(stats["inserted"] / db_seconds) if db_seconds else None
    return stats

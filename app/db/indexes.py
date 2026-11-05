"""Index configurations for experiment O-02: none / minimal / full.

Usage:
    from app.db.indexes import apply_indexes
    apply_indexes(db, "full")

CLI:
    python -m app.db.indexes minimal
"""
from pymongo import ASCENDING, IndexModel
from pymongo.database import Database

# Every config lists the indexes per collection. The automatic _id index is
# always present and is not listed here.
INDEX_CONFIGS: dict[str, dict[str, list[IndexModel]]] = {
    "none": {},
    "minimal": {
        "events": [
            IndexModel([("shipment_id", ASCENDING), ("ts", ASCENDING)],
                       name="events_shipment_ts"),                      # AP-06
        ],
        "analytics": [
            IndexModel([("metric", ASCENDING), ("scope.type", ASCENDING),
                        ("period_start", ASCENDING)],
                       name="analytics_metric_scope_period"),           # AP-10
        ],
    },
    "full": {
        "events": [
            IndexModel([("shipment_id", ASCENDING), ("ts", ASCENDING)],
                       name="events_shipment_ts"),                      # AP-06
            IndexModel([("facility_id", ASCENDING), ("ts", ASCENDING)],
                       name="events_facility_ts"),                      # AP-07
            IndexModel([("courier_id", ASCENDING), ("ts", ASCENDING)],
                       name="events_courier_ts",                        # AP-11
                       # Matches every string, skips null (D-35)
                       partialFilterExpression={"courier_id": {"$gt": ""}}),
            IndexModel([("ts", ASCENDING)], name="events_ts"),          # AP-08
        ],
        "analytics": [
            IndexModel([("metric", ASCENDING), ("scope.type", ASCENDING),
                        ("period_start", ASCENDING)],
                       name="analytics_metric_scope_period"),           # AP-10
        ],
    },
}

COLLECTIONS = ["shipments", "events", "facilities", "couriers", "analytics"]


def drop_secondary_indexes(db: Database) -> None:
    """Remove every index except _id, so each experiment starts from a known state."""
    for name in COLLECTIONS:
        db[name].drop_indexes()  # keeps the _id index


def apply_indexes(db: Database, config: str) -> None:
    """Reset indexes and create the ones defined for `config`."""
    if config not in INDEX_CONFIGS:
        raise ValueError(f"Unknown index config '{config}'. Use: {list(INDEX_CONFIGS)}")
    drop_secondary_indexes(db)
    for collection, models in INDEX_CONFIGS[config].items():
        if models:
            db[collection].create_indexes(models)


if __name__ == "__main__":
    import argparse

    from app.db.client import get_db

    p = argparse.ArgumentParser()
    p.add_argument("config", choices=list(INDEX_CONFIGS))
    apply_indexes(get_db(), p.parse_args().config)

"""Reference data: facilities (hubs and depots) and couriers (FR-15, D-08).

CLI:  python -m generator.reference_data [--hubs 10] [--depots 40] [--couriers 200] [--seed 42]
Clears and refills `facilities` and `couriers`, so running it twice gives the same data (NFR-09).
"""
import argparse
import random

from app.db.client import get_db

DEFAULT_SEED = 42

# (code, city, country). One hub per city; depots are spread over the same cities.
CITIES = [
    ("BUD", "Budapest", "HU"),
    ("DEB", "Debrecen", "HU"),
    ("SZE", "Szeged", "HU"),
    ("VIE", "Vienna", "AT"),
    ("GRZ", "Graz", "AT"),
    ("BTS", "Bratislava", "SK"),
    ("KSC", "Kosice", "SK"),
    ("PRG", "Prague", "CZ"),
    ("BRN", "Brno", "CZ"),
    ("WAW", "Warsaw", "PL"),
]
FIRST_NAMES = ["Anna", "Balazs", "Eva", "Jan", "Katalin", "Lukas", "Marek", "Petra", "Tomas", "Zsofia"]
LAST_NAMES = ["Nagy", "Kovacs", "Novak", "Horvath", "Huber", "Svoboda", "Kowalski", "Toth", "Gruber", "Szabo"]
VEHICLE_TYPES = ["van", "car", "bike"]


def build_facilities(n_hubs=10, n_depots=40):
    """Hubs first (one per city), then depots spread round-robin over the hub cities."""
    if not 1 <= n_hubs <= len(CITIES):
        raise ValueError(f"n_hubs must be between 1 and {len(CITIES)}")
    cities = CITIES[:n_hubs]
    facilities = [
        {"_id": f"HUB-{code}-01", "name": f"{city} Hub", "type": "hub", "city": city, "country": country}
        for code, city, country in cities
    ]
    depots_in_city = {}
    for i in range(n_depots):
        code, city, country = cities[i % n_hubs]
        depots_in_city[code] = depots_in_city.get(code, 0) + 1
        n = depots_in_city[code]
        facilities.append(
            {"_id": f"DEP-{code}-{n:02d}", "name": f"{city} Depot {n}", "type": "depot",
             "city": city, "country": country}
        )
    return facilities


def build_couriers(depot_ids, n_couriers=200, seed=DEFAULT_SEED):
    """Couriers work from depots (pickup and last-mile delivery). Same seed -> same couriers."""
    rng = random.Random(seed)
    return [
        {"_id": f"CUR-{i:04d}",
         "name": f"{rng.choice(FIRST_NAMES)[0]}. {rng.choice(LAST_NAMES)}",
         "home_facility_id": rng.choice(depot_ids),
         "vehicle_type": rng.choice(VEHICLE_TYPES)}
        for i in range(1, n_couriers + 1)
    ]


def load_reference_data(db, n_hubs=10, n_depots=40, n_couriers=200, seed=DEFAULT_SEED):
    """Replace facilities and couriers in the database. Returns the counts written."""
    facilities = build_facilities(n_hubs, n_depots)
    depot_ids = [f["_id"] for f in facilities if f["type"] == "depot"]
    if not depot_ids and n_couriers:
        raise ValueError("couriers need at least one depot")
    couriers = build_couriers(depot_ids, n_couriers, seed)

    db.facilities.delete_many({})
    db.couriers.delete_many({})
    db.facilities.insert_many(facilities)
    if couriers:
        db.couriers.insert_many(couriers)
    return {"facilities": len(facilities), "couriers": len(couriers)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hubs", type=int, default=10)
    p.add_argument("--depots", type=int, default=40)
    p.add_argument("--couriers", type=int, default=200)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    a = p.parse_args()
    print(load_reference_data(get_db(), a.hubs, a.depots, a.couriers, a.seed))

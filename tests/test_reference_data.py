from generator.reference_data import load_reference_data


def test_counts_and_types(db):
    assert load_reference_data(db) == {"facilities": 50, "couriers": 200}
    assert db.facilities.count_documents({"type": "hub"}) == 10
    assert db.facilities.count_documents({"type": "depot"}) == 40


def test_couriers_belong_to_existing_depots(db):
    load_reference_data(db)
    depot_ids = {f["_id"] for f in db.facilities.find({"type": "depot"})}
    assert {c["home_facility_id"] for c in db.couriers.find()} <= depot_ids


def test_running_twice_gives_same_data(db):
    load_reference_data(db)
    first = (list(db.facilities.find().sort("_id")), list(db.couriers.find().sort("_id")))
    load_reference_data(db)
    second = (list(db.facilities.find().sort("_id")), list(db.couriers.find().sort("_id")))
    assert first == second

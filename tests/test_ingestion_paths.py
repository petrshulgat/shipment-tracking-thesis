"""Bulk path, and the comparison of both paths (FR-04, D-17, acceptance criterion 2)."""
from app.db import queries
from app.ingestion.bulk import run_bulk
from app.ingestion.common import reset_database
from app.ingestion.direct import run_direct
from benchmarks.insert_benchmark import plan_runs, run_experiment

N_EVENTS = 1000


def statuses(db):
    return {s["_id"]: s["current_status"] for s in db.shipments.find()}


def test_bulk_stores_everything_without_status_updates(db):
    reset_database(db)
    stats = run_bulk(db, N_EVENTS, chunk_size=300)
    assert stats["inserted"] == db.events.count_documents({}) == N_EVENTS
    assert stats["status_updates"] == 0 and stats["status_s"] == 0  # no AP-04 (D-17)


def test_both_paths_give_identical_status(db):
    reset_database(db)
    run_direct(db, N_EVENTS, batch_size=100)
    direct = statuses(db)

    reset_database(db)
    run_bulk(db, N_EVENTS, chunk_size=300)
    assert statuses(db) == direct


def test_timing_counts_only_database_calls(db):
    reset_database(db)
    stats = run_direct(db, N_EVENTS, batch_size=100)
    assert stats["db_seconds"] > 0
    assert stats["events_per_s"] == round(N_EVENTS / (stats["shipment_s"] + stats["insert_s"] + stats["status_s"]))


def test_plan_runs_skips_single_at_1m():
    runs = plan_runs([100_000, 1_000_000], repeats=3)
    assert len(runs) == 81  # (5 + 4 methods) * 3 index configs * 3 repeats (D-32)
    assert not [r for r in runs if r[0] == "single" and r[4] == 1_000_000]


def test_experiment_writes_one_row_per_run(db, tmp_path):
    out = tmp_path / "results.csv"
    total = run_experiment(db, sizes=[200], repeats=1, out_path=out)
    assert total == 15  # 5 methods * 3 index configs
    assert len(out.read_text().splitlines()) == total + 1  # plus header


def test_status_history_after_bulk_load(db):
    reset_database(db)
    run_bulk(db, N_EVENTS, chunk_size=300)
    shipment = db.shipments.find_one({"_id": "SHP-0000001"})
    last = queries.get_history(db, "SHP-0000001")[-1]
    assert shipment["current_status"]["status"] == last["event_type"]


def test_plan_runs_subset_for_10m():
    runs = plan_runs([10_000_000], repeats=3, methods=["batch_1000", "bulk"], index_configs=["full"])
    assert len(runs) == 6  # 2 methods * 1 index config * 3 repeats (D-37)
    assert {r[0] for r in runs} == {"batch_1000", "bulk"} and {r[3] for r in runs} == {"full"}

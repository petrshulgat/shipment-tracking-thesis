"""ETL benchmark, AP-10 measurement and the scalability report (D-37)."""
import csv

from app.ingestion.bulk import run_bulk
from app.ingestion.common import reset_database
from benchmarks.etl_benchmark import ETL_DAYS, run_experiment as run_etl_experiment
from benchmarks.query_benchmark import (FULL_SCANS, explain_query, load_ids, run_experiment,
                                        summarise_plan)
from benchmarks.scalability_report import insert_series, linear_reference, medians, query_series
from app.etl.run import run_range
from benchmarks.etl_benchmark import ETL_END, ETL_START


def test_etl_benchmark_writes_one_row_per_repeat(db, tmp_path):
    out = tmp_path / "etl.csv"
    run_etl_experiment(db, sizes=[2000], index_configs=["minimal", "full"], repeats=2, out_path=out)
    rows = list(csv.DictReader(open(out)))
    assert len(rows) == 4
    assert all(int(r["days"]) == ETL_DAYS and int(r["docs_written"]) > 0 for r in rows)
    # Analytics is emptied before each repeat, so every repeat writes the same documents
    assert rows[0]["docs_written"] == rows[1]["docs_written"]


def test_ap10_plan_uses_analytics_index(db):
    for index_config in ("none", "full"):
        reset_database(db, index_config)
        run_bulk(db, 2000)
        run_range(db, ETL_START, ETL_END)
        stage = summarise_plan(explain_query(db, "AP-10", load_ids(db)))["stage"]
        assert (stage == "COLLSCAN") == ("AP-10" in FULL_SCANS[index_config]), stage


def test_query_benchmark_with_ap10_and_subset(db, tmp_path):
    results, plans = tmp_path / "results.csv", tmp_path / "plans.csv"
    run_experiment(db, sizes=[2000], rounds=1, client=None, results_path=results, plans_path=plans,
                   index_configs=["full"], query_names=["AP-10"])
    rows = list(csv.DictReader(open(results)))
    assert [(r["query"], r["index_config"]) for r in rows] == [("AP-10", "full")]


def test_scalability_medians_and_filters():
    rows = [{"level": "database", "index_config": "full", "query": "AP-05", "n_events": "100", "p95_ms": v}
            for v in ("1", "3", "2")]
    rows.append({"level": "api", "index_config": "full", "query": "AP-05", "n_events": "100", "p95_ms": "9"})
    rows.append({"level": "database", "index_config": "none", "query": "AP-05", "n_events": "100", "p95_ms": "9"})
    assert query_series(rows) == {"AP-05": {100: 2.0}}

    inserts = [{"index_config": "full", "method": "bulk", "n_events": "10", "events_per_s": "5"},
               {"index_config": "full", "method": "single", "n_events": "10", "events_per_s": "1"}]
    assert insert_series(inserts) == {"bulk": {10: 5.0}}
    assert medians([{"s": "a", "n_events": "1", "v": "4"}], "s", "v") == {"a": {1: 4.0}}


def test_linear_reference_grows_with_size():
    assert linear_reference({100: 2.0, 1000: 5.0, 10000: 30.0}) == {100: 2.0, 1000: 20.0, 10000: 200.0}

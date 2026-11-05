import random

import pytest

from app.ingestion.bulk import run_bulk
from app.ingestion.common import reset_database
from benchmarks.insert_benchmark import INDEX_CONFIGS
from benchmarks.query_benchmark import (FULL_SCANS, QUERIES, call_counts, explain_query, load_ids,
                                        make_inputs, measure, percentile, plan_runs, run_experiment,
                                        summarise_plan)
from benchmarks.query_report import summarise, target_checks


def test_percentile_nearest_rank():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile(values, 99) == 99
    assert percentile([7], 95) == 7


def test_scans_get_fewer_calls():
    assert call_counts("AP-07", "minimal") == (100, 10)
    assert call_counts("AP-07", "full") == (1000, 100)
    assert call_counts("AP-05", "none") == (1000, 100)


def test_plan_runs():
    assert plan_runs([100_000, 1_000_000]) == [
        (n, i) for n in (100_000, 1_000_000) for i in INDEX_CONFIGS]


def test_measure_returns_sorted_times():
    times = measure(lambda x: x, [(1,), (2,), (3,)])
    assert len(times) == 3 and times == sorted(times)


def test_same_seed_same_inputs():
    ids = {"shipments": ["S1", "S2", "S3"], "facilities": ["F1", "F2"], "couriers": ["C1", "C2"]}
    assert make_inputs("AP-07", random.Random(1), ids, 20) == make_inputs("AP-07", random.Random(1), ids, 20)


@pytest.mark.parametrize("index_config", INDEX_CONFIGS)
def test_plans_match_expected_scans(db, index_config):
    # explain() must confirm which queries are full scans, or the experiment is mislabelled
    reset_database(db, index_config)
    run_bulk(db, 2000)
    ids = load_ids(db)
    for query in QUERIES:
        stage = summarise_plan(explain_query(db, query, ids))["stage"]
        assert (stage == "COLLSCAN") == (query in FULL_SCANS[index_config]), (query, stage)


def test_full_config_uses_the_index_built_for_each_query(db):
    # "Not a full scan" is not enough: AP-11 once used events_ts and read far too many documents
    reset_database(db, "full")
    run_bulk(db, 20_000)
    ids = load_ids(db)
    expected = {"AP-06": "events_shipment_ts", "AP-07": "events_facility_ts", "AP-11": "events_courier_ts"}
    for query, index_name in expected.items():
        assert summarise_plan(explain_query(db, query, ids))["index_name"] == index_name


def test_experiment_writes_results_and_plans(db, tmp_path):
    results, plans = tmp_path / "results.csv", tmp_path / "plans.csv"
    run_experiment(db, sizes=[500], rounds=1, client=None, results_path=results, plans_path=plans)
    # 4 queries * 3 index configs, plus a header line
    assert len(results.read_text().splitlines()) == 13
    assert len(plans.read_text().splitlines()) == 13


def test_report_checks_targets():
    rows = [{"level": "database", "n_events": "1000000", "index_config": "minimal", "query": "AP-05",
             "calls": "1000", "p50_ms": "1", "p95_ms": p95, "p99_ms": "3"} for p95 in ("2", "2.5", "3")]
    summary = summarise(rows)
    assert summary[0]["p95_ms"] == 2.5  # median of the rounds
    assert target_checks(summary)[0].endswith("pass")

# ETL Plan

Thesis: MongoDB-based shipment tracking pipeline (event ingestion, batch ETL, benchmarking)

Related: FR-09, FR-10, FR-11, NFR-05, AP-08, AP-09, AP-10, decisions D-03, D-11 to D-16.

## 1. Purpose

A batch ETL job turns raw tracking events into aggregated metrics. It reads from `events` (and `shipments`), computes metrics with MongoDB aggregation pipelines, and writes the results to `analytics`. It does not depend on how an event arrived (direct insert or bulk load). There is no real-time ETL (D-03).

| Step | In this project |
|---|---|
| Extract | Read events of one time window, plus `shipments.created_at`, inside the aggregation pipeline (`$match`, `$lookup`) |
| Transform | Compute counts, rates and averages (`$group`, `$cond`, `$avg`) |
| Load | Python upserts metric documents into `analytics` |

## 2. Inputs

| Source | Fields used | Notes |
|---|---|---|
| `events` | `event_type`, `ts`, `facility_id`, `courier_id`, `shipment_id` | Main source. Filtered by `ts` window |
| `shipments` | `created_at` | Joined by `$lookup` on `_id` (indexed). Only for average delivery time |
| `facilities` | `_id`, `type` | Read once in Python to get the hub IDs (few documents, no `$lookup`) |

- **Window:** one day, `[period_start, period_end)`, applied to `events.ts` (D-11).
- **Data types:** `events.ts` and `shipments.created_at` must be BSON `Date`, not ISO strings (D-16).

## 3. Metrics

| Metric | Scope | Formula |
|---|---|---|
| `avg_delivery_time_s` | global | Average of (`delivered` event `ts` − `shipments.created_at`) for deliveries in the window, in seconds (D-12) |
| `delivery_success_rate` | global, courier | delivered / (delivered + delivery_failed) (D-13) |
| `failed_attempts` | global, courier | Count of `delivery_failed` events |
| `events_per_hub` | hub | Count of events per `facility_id`, only facilities with `type: "hub"` (D-14) |

Notes:
- Courier metrics only use events with a non-null `courier_id`.
- A group with no delivery attempts produces no document (no division by zero).

## 4. Output format

Collection `analytics`, one document per metric, scope and period:

```json
{
  "metric": "delivery_success_rate",
  "scope": {"type": "courier", "value": "CUR-0042"},
  "period_start": "2026-03-01T00:00:00Z",
  "period_end": "2026-03-02T00:00:00Z",
  "value": 0.94,
  "n": 100,
  "computed_at": "2026-03-02T01:00:00Z",
  "run_id": "etl_2026-03-01_20260302T010000"
}
```

- `n` is the number of items behind the value (for a rate: delivered + failed). It separates 94 of 100 from 9 of 10.
- For the global scope, `scope.value` is `null`.
- Dates are stored as BSON `Date`.

**Upsert key:** `metric`, `scope.type`, `scope.value`, `period_start`, `period_end`. The filter uses the dotted fields, not the whole `scope` object, because equality on an embedded document depends on field order.

## 5. Schedule (FR-11)

- A daily job runs at 01:00 UTC.
- It computes the previous day and recomputes the day before, to catch late events (D-15).
- The scheduler runs in a separate container with APScheduler (D-20).
- A manual CLI runs a date range: `python -m app.etl.run --start YYYY-MM-DD --end YYYY-MM-DD`. The benchmarks use it to time the ETL over 100k, 1M and 10M events (NFR-05).

## 6. Rerun behavior

1. Compute all metrics for the window.
2. Write with `bulk_write` of `UpdateOne(..., upsert=True)`. A rerun overwrites existing documents and never duplicates them.
3. After a successful write, delete documents of the same period whose `run_id` differs from the current run. This removes stale metrics, for example a courier who no longer appears after a recompute.
4. If the job fails midway, nothing is deleted, and a rerun is safe.

## 7. Indexes and performance

- The `$match` on `ts` uses an index only in the `full` configuration (`events_ts`). In `none` and `minimal` it is a collection scan. This difference is a result of experiment O-02.
- `$lookup` into `shipments` uses the automatic `_id` index.
- ETL runtime is measured per dataset size (100k, 1M, 10M) and is expected to grow roughly linearly (NFR-05).

## 8. Validation

Acceptance criterion 3: insert a small set of hand-made events, run the ETL, and compare each metric with a manually computed value. Also rerun the ETL for the same window and check that the document count in `analytics` does not change.

## 9. Implementation timing

The code is written in Month 5. A draft skeleton exists in `app/etl/` (`pipelines.py`, `metrics.py`, `run.py`, `scheduler.py`).
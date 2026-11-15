# Shipment Tracking on MongoDB

Bachelor's thesis project: a shipment/delivery tracking backend built on MongoDB, and a set of
experiments that measure how fast it is and how it scales.

Tracking events (a package was picked up, arrived at a hub, was delivered, ...) are written to
MongoDB through two ingestion paths. A FastAPI service answers questions such as *"where is my
package?"*, and a daily batch ETL job calculates delivery statistics. The core of the thesis is the
benchmarks: insert speed, query speed and ETL runtime for different index configurations and dataset
sizes (100k, 1M and 10M events).

**Stack:** Python 3.14, MongoDB 7, PyMongo, FastAPI, APScheduler, Docker Compose, pytest, matplotlib.

---

## How it works

```
 data generator ──► direct insert  (batches of 1,000 + status update) ─┐
 (fixed seed)  └──► bulk loader    (chunks of 10,000, status precomputed) ─┤
                                                                           ▼
                                 MongoDB: shipments, events, facilities, couriers, analytics
                                    │                         ▲
                                    ▼                         │
                         FastAPI (Swagger UI)        daily batch ETL (01:00 UTC)
                    status, history, events, metrics   writes metrics to `analytics`
```

| Part | What it does | Code |
|---|---|---|
| Data generator | Creates realistic shipments and events over a 30-day period (1–30 March 2026). A fixed random seed gives the same data every run. | `generator/` |
| Direct insert path | Writes events in small batches of 1,000 and updates each shipment's `current_status` after every batch, like a live system would. | `app/ingestion/direct.py` |
| Bulk loader | Writes large chunks of 10,000 events as fast as possible; the final status is precomputed by the generator. | `app/ingestion/bulk.py` |
| Database layer | Connection, the three index configurations (`none` / `minimal` / `full`) and all queries. | `app/db/` |
| API | Read-only endpoints for status, history, events by facility or courier, and metrics. Swagger UI is the user interface. | `app/api/` |
| Batch ETL | Aggregation pipelines that compute average delivery time, delivery success rate, failed attempts and events per hub, one day at a time. Re-running a day never creates duplicates. | `app/etl/` |
| Benchmarks | Insert, query, ETL and scalability experiments; results are saved as CSV tables and charts. | `benchmarks/` |

### Collections

| Collection | Holds |
|---|---|
| `shipments` | One document per shipment, including its `current_status` |
| `events` | One document per tracking event (append-only, the largest collection) |
| `facilities` | 10 hubs and 40 depots |
| `couriers` | 200 couriers |
| `analytics` | Metrics written by the ETL, one document per metric, scope and day |

---

## Quick start

Requirements: Docker Desktop.

```bash
docker compose up -d
```

This starts three containers:

| Container | Purpose |
|---|---|
| `mongo` | MongoDB, on `localhost:27017` |
| `api` | The API, with Swagger UI at **http://localhost:8000/docs** |
| `etl-scheduler` | Runs the ETL automatically every day at 01:00 UTC |

The database starts empty. Load demo data (100,000 events through the direct path) and compute the
metrics:

```bash
docker compose exec api python -m app.ingestion.direct --events 100000 --reset
```

```bash
docker compose exec api python -m app.etl.run --start 2026-03-01 --end 2026-04-01
```

Stop everything, keeping the data and the logs:

```bash
docker compose stop
```

---

## Using the API (Swagger UI)

Open **http://localhost:8000/docs**. To call an endpoint: click its row, click **Try it out**,
fill in the fields, click **Execute**, then read the **Response body**.

| Endpoint | Question it answers | Example values |
|---|---|---|
| `GET /shipments/{shipment_id}/status` | Where is this package now? | `SHP-0000001` |
| `GET /shipments/{shipment_id}/events` | What happened to this package, in time order? | `SHP-0000001` |
| `GET /facilities/{facility_id}/events` | What happened at this facility in a time range? | `DEP-BRN-01`, start `2026-03-01T00:00:00Z`, end `2026-04-01T00:00:00Z` |
| `GET /couriers/{courier_id}/events` | What did this courier handle in a time range? | `CUR-0001`, same dates |
| `GET /metrics` | What did the ETL calculate? | `delivery_success_rate`, `courier`, start `2026-03-01T00:00:00Z` |
| `GET /health` | Is the API connected to MongoDB? | – |

Example answer from the status endpoint:

```json
{
  "shipment_id": "SHP-0000001",
  "current_status": {
    "status": "delivered",
    "last_event_ts": "2026-03-08T23:13:51Z",
    "last_facility_id": "DEP-BRN-02",
    "last_courier_id": "CUR-0035"
  }
}
```

---

## Other commands

| Task | Command |
|---|---|
| Load data with the bulk loader instead | `docker compose exec api python -m app.ingestion.bulk --events 100000 --reset` |
| Apply a different index configuration | `docker compose exec api python -m app.db.indexes minimal` |
| Run the scheduled ETL job once, now | `docker compose exec etl-scheduler python -c "from app.etl.scheduler import daily_job; daily_job()"` |
| See when the scheduler ran | `docker compose logs -t etl-scheduler` |

### Tests

The tests need MongoDB running on `localhost:27017` (`docker compose up -d mongo`).

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python -m pytest
```

On Linux or macOS use `.venv/bin/python` instead of `.venv/Scripts/python`.

---

## Benchmarks

All benchmarks run inside Docker, against a separate `tracking_benchmark` database, so the demo data
is never touched. Each measurement is repeated 3 times and the median is reported. Results land in
`benchmarks/results/`, and the test machine is described in `benchmarks/results/environment.txt`.

| Experiment | Command |
|---|---|
| Insert speed (100k, 1M) | `docker compose run --rm --build benchmark` |
| Query speed (100k, 1M) | `docker compose run --rm --build query-benchmark` |
| ETL runtime (100k, 1M, 10M) | `docker compose run --rm --build benchmark python -m benchmarks.etl_benchmark` |
| Insert speed at 10M (D-37) | `docker compose run --rm benchmark python -m benchmarks.insert_benchmark --sizes 10000000 --methods batch_1000 bulk --index-configs full --out insert_results_10m.csv` |
| Query speed at 10M (D-37) | `docker compose run --rm query-benchmark python -m benchmarks.query_benchmark --sizes 10000000 --index-configs full --queries AP-05 AP-06 AP-07 AP-10 AP-11 --suffix _10m` |

On the test laptop the 10M insert run took about 70 minutes, the 10M query run about 11 minutes and the ETL run about 27 minutes.

Charts and summary tables are made from the CSV results with:

```bash
.venv/Scripts/python -m benchmarks.report
```

```bash
.venv/Scripts/python -m benchmarks.query_report
```

```bash
.venv/Scripts/python -m benchmarks.scalability_report
```

### Main results

Measured on one laptop (Intel i5-10210U, 8 GB of memory for Docker).

| Finding | Numbers | Chart |
|---|---|---|
| The right index makes queries hundreds of times faster | At 1M events, facility and courier queries take 460–610 ms with `minimal` indexes and about 1.5 ms with `full` (p95) | `query_latency.png` |
| Batching makes inserts much faster | Single inserts reach about 700 events/s; batches of 1,000 reach about 29,000 events/s with `full` indexes; bulk is fastest | `insert_throughput.png` |
| Indexes cost write speed | `full` indexes make batch inserts about 28% slower than `minimal`; the price for fast reads | `insert_throughput.png` |
| Indexed queries stay fast as data grows | From 100k to 10M events (100× more data), all indexed queries stay under 4 ms (p95) | `scalability_queries.png` |
| ETL runtime grows linearly | From 1M to 10M events the ETL takes about 10× longer; the `events_ts` index makes it 2–3× faster (9.6 vs 23.4 s per day at 10M) | `scalability_etl.png` |
| Inserts slow down at 10M | Bulk: 50k → 18.7k events/s from 1M to 10M; data and indexes together nearly fill MongoDB's 3.4 GB cache (probable cause) | `scalability_inserts.png` |

All performance requirements (NFR-01 to NFR-05 in `docs/requirements.md`) are met.

---

## Project layout

```
app/
  api/          FastAPI app, routes and response schemas
  db/           client.py (connection), indexes.py (none/minimal/full), queries.py
  ingestion/    direct.py, bulk.py, common.py (shared load and reset logic)
  etl/          pipelines.py (aggregations), run.py (ETL runner), scheduler.py
generator/      data generator and reference data (facilities, couriers)
benchmarks/     experiments, reports, and results/ (CSV tables and PNG charts)
tests/          pytest tests for ingestion, queries, API, ETL and benchmarks
docs/           requirements, design decisions, schema and queries, ETL plan, diagrams
```

## Documentation

| File | Contents |
|---|---|
| `docs/requirements.md` | Functional and non-functional requirements (FR-xx, NFR-xx), acceptance criteria |
| `docs/design_decisions_log.md` | Every design decision with alternatives, reason and trade-off (D-xx) |
| `docs/schema_and_queries.md` | Document schemas, access patterns (AP-xx), queries and indexes |
| `docs/etl_plan.md` | ETL metrics, windows, idempotency and scheduling |
| `docs/architecure_design.md` | Architecture diagram |
| `docs/erd.md` | Entity-relationship diagram |

## Scope

Not included, by design (D-06, D-07): authentication, sharding or multi-node clusters, and a full web
user interface. Swagger UI is the interface.

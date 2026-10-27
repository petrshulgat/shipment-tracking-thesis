# Design Decisions Log

Thesis: MongoDB-based shipment tracking pipeline (event ingestion, batch ETL, benchmarking)

How to use: add a new row whenever a decision is made. Never delete old decisions; mark them "Superseded" and add the new one.

## Decided

| ID | Decision | Alternatives considered | Reason | Trade-off / downside | Status |
|---|---|---|---|---|---|
| D-01 | Store events in a separate `events` collection, not embedded in `shipments` | Embed events array in the shipment document | Unbounded array growth; better for high-frequency append-only inserts | Latest-status and history need separate reads | Decided |
| D-02 | Two ingestion paths: direct insert and bulk insert | Bulk only; API insert only | Direct insert shows a realistic per-event flow with status updates; bulk gives raw database throughput and fast large-dataset generation | Two code paths to maintain and compare | Decided |
| D-03 | Batch ETL for analytics (not real-time aggregation) | Real-time aggregation on every insert | Fits scope and the thesis plan; simpler to validate | Metrics are not real-time | Decided |
| D-04 | FastAPI as the API layer | Flask, Django REST | Async support, Pydantic validation, automatic Swagger docs | None significant | Decided |
| D-05 | Docker Compose for deployment | Manual local install | Reproducible, clean-database restarts for benchmarks | Docker overhead on a laptop | Decided |
| D-06 | No full UI; Swagger UI plus optional Streamlit dashboard | Full web application | Thesis focus is data engineering and performance, not interface design | Less visual polish | Decided |
| D-07 | Out of scope: authentication, sharding, multi-node clusters | Include them | Keeps the project within thesis size | Listed as future work | Decided |
| D-08 | Add couriers collection and optional courier_id on events | No couriers; courier info embedded in events | Enables per-courier ETL metrics (success rate, failed attempts) | One more reference collection and one more index on events | Decided |
| D-09 | Keep a denormalized current_status in shipments, updated per insert batch on the direct path | Derive status from the latest event at query time | Latest-status query is a single read by _id (NFR-03) | Extra write per batch; needs the out-of-order rule in section 5 | Decided |
| D-10 | Update current_status only when the new ts is newer than last_event_ts | Always overwrite | Late events must not overwrite newer status | Conditional update per shipment | Decided |
| D-11 | ETL window is one day, `[start, end)` on `events.ts` | Hourly window; one run over the whole dataset | Matches the daily schedule, and a day is a natural unit for reports and reruns | Metrics are available only after the day ends | Decided |
| D-12 | Average delivery time = `delivered` event `ts` minus `shipments.created_at` | From the first `picked_up` event | Simplest; needs only a `$lookup` on the indexed `_id` | Includes time before pickup, so it is less precise than pickup-to-delivery | Decided |
| D-13 | Success rate is attempt-based: delivered / (delivered + delivery_failed) | Shipment-based (share of shipments delivered on the first try) | Matches the existing courier query and FR-09 | Counts repeated attempts of the same shipment separately | Decided |
| D-14 | `events_per_hub` counts only facilities with `type: "hub"`; hub IDs are read once in Python | Count all `facility_id` values; `$lookup` into `facilities` | Matches "per hub" in FR-09; `facilities` is tiny, so no join is needed | One extra small read per ETL run | Decided |
| D-15 | Rerun: upsert, then delete same-period documents with another `run_id`; the daily job also recomputes the previous day | Insert only; delete the whole period before writing | Reruns never duplicate, stale metrics are removed, and late events are caught | Two days are recomputed every night | Decided |
| D-16 | `ts` and `created_at` are stored as BSON `Date`, not ISO strings | ISO strings | `$dateTrunc` and `$subtract` need real dates; dates also sort and compare correctly | The generator must produce real datetime values | Decided |
| D-17 | bulk-loaded shipments get current_status computed by the generator; bulk loader only inserts shipments and events, does not run AP-04 | post-load $merge pass; no status on bulk data | NFR-03 and FR-06 must work on 1M/10M datasets, and bulk throughput stays clean | the direct path does extra status writes that bulk doesn’t, so report this when comparing the two | Decided |
| D-18 | Direct insert path: the generator pre-creates shipments with no current_status field, then inserts events. |  | AP-04 needs existing shipment documents | shipments must exist before their events arrive | Decided |
| D-19 | Idempotent inserts: each event's `_id` is its unique `event_id`; events are written with `insert_many(ordered=False)` and duplicate key errors (code 11000) are ignored, any other write error is raised | Upsert per event; check for existence before insert | Meets NFR-07; a retried batch cannot create duplicates, and an unordered insert keeps writing past a duplicate; keeps insert_many speed for the benchmarks | The generator must create unique, repeatable event IDs; duplicate errors must be told apart from real errors | Decided (resolves O-04) |
| D-20 | ETL scheduler: APScheduler cron trigger at 01:00 UTC, in its own container; the CLI is kept for manual and benchmark runs | Sleep loop; system cron running the CLI | Cron-style trigger in a few lines of Python, no OS cron setup in the container | One extra dependency | Decided |
| D-21 | The generator gives the events of one shipment strictly increasing `ts` values | Allow equal `ts` and let the first generated event win | No ties, so the direct path (AP-04) and the bulk path (D-17) always give the same current_status (acceptance criterion 2) | Slightly less realistic: real scanners can produce equal timestamps | Decided |

## Open decisions 

| ID | Question | Options | Decide by |
|---|---|---|---|
| O-01 | `events` as regular or time-series collection | Regular + indexes; time-series; bucket pattern | Month 2, Week 2 |
| O-02 | Final index set for `events` and `shipments` | No index / minimal / full (compared as experiment variable) | Month 2, Week 3 |
| O-03 | Direct insert batch size | e.g. 1 / 100 / 1,000 / 5,000 events | Month 4 (experiment) |
| O-04 | Duplicate handling on retried inserts | Idempotent insert (unique event ID) | Resolved by D-19 |
| O-05 | Geospatial (`2dsphere`) index and location queries | Include / exclude | Month 2, Week 3 |
| O-06 | Dashboard: build or skip | Streamlit / skip | Month 6 |

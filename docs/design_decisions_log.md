# Design Decisions Log

Thesis: MongoDB-based shipment tracking pipeline (streaming ingestion, batch ETL, benchmarking)

How to use: add a new row whenever a decision is made. Never delete old decisions; mark them "Superseded" and add the new one.

## Decided

| ID | Decision | Alternatives considered | Reason | Trade-off / downside | Status |
|---|---|---|---|---|---|
| D-01 | Use Apache Kafka as the streaming ingestion layer | Redis Streams, MongoDB Change Streams, direct API insert | Decouples producers from storage; partitions keyed by `shipment_id` keep per-shipment order; allows measuring end-to-end latency and consumer lag | More setup and complexity | Decided (fallback: Redis Streams if Month 3 falls behind) |
| D-02 | Store events in a separate `events` collection, not embedded in `shipments` | Embed events array in the shipment document | Unbounded array growth; better for high-frequency append-only inserts | Latest-status and history need separate reads | Decided |
| D-03 | Two ingestion paths: Kafka streaming and direct bulk insert | Streaming only; API insert only | Streaming shows realistic flow; bulk gives raw database throughput and fast large-dataset generation | Two code paths to maintain and compare | Decided |
| D-04 | Batch ETL for analytics (not streaming ETL) | Streaming aggregation | Fits scope and the thesis plan; simpler to validate | Metrics are not real-time | Decided |
| D-05 | FastAPI as the API layer | Flask, Django REST | Async support, Pydantic validation, automatic Swagger docs | None significant | Decided |
| D-06 | Docker Compose for deployment | Manual local install | Reproducible, clean-database restarts for benchmarks | Docker overhead on a laptop | Decided |
| D-07 | No full UI; Swagger UI plus optional Streamlit dashboard | Full web application | Thesis focus is data engineering and performance, not interface design | Less visual polish | Decided |
| D-08 | Out of scope: authentication, sharding, multi-node clusters | Include them | Keeps the project within thesis size | Listed as future work | Decided |
| D-09 | Add couriers collection and optional courier_id on events | No couriers; courier info embedded in events | Enables per-courier ETL metrics (success rate, failed attempts) | One more reference collection and one more index on events | Decided |
| D-10 | Keep a denormalized current_status in shipments, updated per micro-batch | Derive status from the latest event at query time | Latest-status query is a single read by _id (NFR-03) | Extra write per batch; needs the out-of-order rule in section 5 | Decided |
| D-11 | Update current_status only when the new ts is newer than last_event_ts | Always overwrite | Late events must not overwrite newer status | Conditional update per shipment | Decided |
| D-12 | ETL window is one day, `[start, end)` on `events.ts` | Hourly window; one run over the whole dataset | Matches the daily schedule, and a day is a natural unit for reports and reruns | Metrics are available only after the day ends | Decided |
| D-13 | Average delivery time = `delivered` event `ts` minus `shipments.created_at` | From the first `picked_up` event | Simplest; needs only a `$lookup` on the indexed `_id` | Includes time before pickup, so it is less precise than pickup-to-delivery | Decided |
| D-14 | Success rate is attempt-based: delivered / (delivered + delivery_failed) | Shipment-based (share of shipments delivered on the first try) | Matches the existing courier query and FR-09 | Counts repeated attempts of the same shipment separately | Decided |
| D-15 | `events_per_hub` counts only facilities with `type: "hub"`; hub IDs are read once in Python | Count all `facility_id` values; `$lookup` into `facilities` | Matches "per hub" in FR-09; `facilities` is tiny, so no join is needed | One extra small read per ETL run | Decided |
| D-16 | Rerun: upsert, then delete same-period documents with another `run_id`; the daily job also recomputes the previous day | Insert only; delete the whole period before writing | Reruns never duplicate, stale metrics are removed, and late Kafka events are caught | Two days are recomputed every night | Decided |
| D-17 | `ts` and `created_at` are stored as BSON `Date`, not ISO strings | ISO strings | `$dateTrunc` and `$subtract` need real dates; dates also sort and compare correctly | The generator and consumer must convert timestamps | Decided |

## Open decisions 

| ID | Question | Options | Decide by |
|---|---|---|---|
| O-01 | `events` as regular or time-series collection | Regular + indexes; time-series; bucket pattern | Month 2, Week 2 |
| O-02 | Final index set for `events` and `shipments` | No index / minimal / full (compared as experiment variable) | Month 2, Week 3 |
| O-03 | Kafka partition count and consumer group setup | 1, 3, 6 partitions | Month 3 |
| O-04 | Consumer micro-batch size and flush interval | e.g. 100 / 1,000 / 5,000 events | Month 4 (experiment) |
| O-05 | Delivery semantics and duplicate handling | At-least-once + idempotent insert (unique event ID) | Month 3 |
| O-06 | Geospatial (`2dsphere`) index and location queries | Include / exclude | Month 2, Week 3 |
| O-07 | Dashboard: build or skip | Streamlit / skip | Month 6 |

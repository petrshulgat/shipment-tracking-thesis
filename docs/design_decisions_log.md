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

## Open decisions (to resolve in Month 2-4)

| ID | Question | Options | Decide by |
|---|---|---|---|
| O-01 | `events` as regular or time-series collection | Regular + indexes; time-series; bucket pattern | Month 2, Week 2 |
| O-02 | Final index set for `events` and `shipments` | No index / minimal / full (compared as experiment variable) | Month 2, Week 3 |
| O-03 | Kafka partition count and consumer group setup | 1, 3, 6 partitions | Month 3 |
| O-04 | Consumer micro-batch size and flush interval | e.g. 100 / 1,000 / 5,000 events | Month 4 (experiment) |
| O-05 | Delivery semantics and duplicate handling | At-least-once + idempotent insert (unique event ID) | Month 3 |
| O-06 | Geospatial (`2dsphere`) index and location queries | Include / exclude | Month 2, Week 3 |
| O-07 | Dashboard: build or skip | Streamlit / skip | Month 6 |

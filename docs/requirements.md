# Requirements

Thesis: MongoDB-based shipment tracking pipeline (streaming ingestion, batch ETL, benchmarking)

Status: draft v1. Numeric targets are initial values; refine them after the first baseline measurements in Month 4.

## 1. Goal and scope

Build and evaluate a shipment tracking system on MongoDB that ingests high-frequency tracking events (Kafka streaming and bulk insert), serves shipment status and history queries, computes analytical metrics with batch ETL, and measures performance and scalability.

**In scope:** event ingestion, data model and indexing, query API, batch ETL, large dataset simulation, benchmarking.
**Out of scope:** authentication, sharding, multi-node deployment, full user interface, real carrier integration.

## 2. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Create a shipment with ID, sender, recipient, origin, destination, and service type | Must |
| FR-02 | Record a tracking event (shipment ID, event type, timestamp, location, facility, source) | Must |
| FR-03 | Ingest events through a Kafka topic with a consumer writing micro-batches to MongoDB | Must |
| FR-04 | Ingest events through a direct bulk insert path | Must |
| FR-05 | Update the shipment's current status when a new event arrives | Must |
| FR-06 | Return the current status of a shipment | Must |
| FR-07 | Return the full event history of a shipment in time order | Must |
| FR-08 | Query events by facility and time range | Should |
| FR-09 | Run a batch ETL job that computes: average delivery time, delivery success rate, failed attempts, events per hub | Must |
| FR-10 | Store ETL results in an `analytics` collection and expose them through the API | Must |
| FR-11 | Schedule the ETL job to run automatically | Should |
| FR-12 | Generate a simulated dataset of configurable size (100k, 1M, 10M events) | Must |
| FR-13 | Run benchmarks (insert throughput, query latency, ETL runtime) and export results as tables and charts | Must |
| FR-14 | Show metrics and benchmark results in a dashboard | Could |

## 3. Non-functional requirements

| ID | Category | Requirement | Initial target |
|---|---|---|---|
| NFR-01 | Performance | Streaming consumer insert throughput | At least 5,000 events/s on the test machine |
| NFR-02 | Performance | Shipment history query latency (indexed), p95 | Under 50 ms at 1M events |
| NFR-03 | Performance | Latest-status query latency, p95 | Under 20 ms at 1M events |
| NFR-04 | Scalability | Query latency growth with dataset size | Roughly flat for indexed queries across 100k, 1M, 10M events (to be verified) |
| NFR-05 | Scalability | ETL runtime growth with dataset size | Approximately linear |
| NFR-06 | Correctness | Events produced equals events stored | 100%, no loss |
| NFR-07 | Correctness | No duplicate events after retries | Idempotent inserts using a unique event ID |
| NFR-08 | Correctness | Events of one shipment stay in order | Guaranteed by Kafka key = `shipment_id` |
| NFR-09 | Reproducibility | Whole system starts with one command | Docker Compose |
| NFR-10 | Reproducibility | Experiments repeatable | Fixed random seed, documented environment, several runs per test |
| NFR-11 | Maintainability | Core logic covered by automated tests | pytest for ingestion, queries, and ETL |

## 4. Constraints and assumptions

- Runs on a single machine (laptop or desktop) using Docker Compose.
- Data is simulated; the event model is based on public carrier tracking APIs and GS1 EPCIS concepts.
- Event types: label created, picked up, arrived at hub, sorted, in transit, out for delivery, delivered, delivery failed, returned.
- Technology: Python, FastAPI, MongoDB, Apache Kafka, Docker Compose.

## 5. Acceptance criteria

1. The demo runs from a clean start: generator produces events, Kafka delivers them, the document count in MongoDB rises, and the counts match.
2. API returns correct status and history for sampled shipments.
3. ETL output matches a manually computed sample.
4. Benchmark results exist for all planned experiments, with the test environment described.

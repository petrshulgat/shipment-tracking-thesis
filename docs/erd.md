# Entity Relationship Diagram

Renders automatically on GitHub, GitLab, VS Code (Markdown preview with Mermaid support) and https://mermaid.live.

```mermaid
erDiagram
  FACILITIES ||--o{ EVENTS : "facility_id"
  FACILITIES ||--o{ COURIERS : "home_facility_id"
  COURIERS |o--o{ EVENTS : "courier_id (optional)"
  SHIPMENTS ||--o{ EVENTS : "shipment_id"
  SHIPMENTS {
    string _id PK "shipment_id"
    object sender
    object recipient
    string origin
    string destination
    string service_type
    date created_at
    object current_status "status, last_event_ts, last_facility_id, last_courier_id"
  }
  EVENTS {
    string _id PK "event_id"
    string shipment_id FK
    string event_type
    date ts
    string facility_id FK
    string courier_id FK "nullable"
    object location
    string source
  }
  FACILITIES {
    string _id PK "facility_id"
    string name
    string type
    string city
    string country
  }
  COURIERS {
    string _id PK "courier_id"
    string name
    string home_facility_id FK
    string vehicle_type
  }
  ANALYTICS {
    objectid _id PK
    string metric
    object scope "type, value"
    date period_start
    date period_end
    number value
    date computed_at
    string run_id
  }
```

## Notes

- MongoDB has no foreign keys. `FK` marks a logical reference that the generator, consumer, and API must keep consistent.
- `shipments` to `events`: one-to-many, served by index `(shipment_id, ts)` (AP-06).
- `facilities` to `events`: one-to-many through `facility_id`, served by `(facility_id, ts)` (AP-07).
- `couriers` to `events`: optional. `courier_id` is null for events that are not courier-handled; served by the partial index `(courier_id, ts)` (AP-11).
- `facilities` to `couriers`: each courier has one home facility.
- `current_status` is an embedded object in `shipments`, a denormalized copy of the latest event, updated per micro-batch (D-10, D-11).
- `analytics` has no reference lines: `scope.value` holds a courier ID, facility ID, or service type as a plain value.
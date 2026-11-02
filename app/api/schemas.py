"""Response models (D-24).

They describe the JSON each endpoint returns. FastAPI checks every response
against them and shows them in Swagger UI.
MongoDB stores IDs as `_id`; `validation_alias="_id"` reads that field and the
API returns it under a clearer name (`event_id`, `shipment_id`).
"""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MetricName(StrEnum):  # FR-09 metrics, docs/etl_plan.md section 3
    avg_delivery_time_s = "avg_delivery_time_s"
    delivery_success_rate = "delivery_success_rate"
    failed_attempts = "failed_attempts"
    events_per_hub = "events_per_hub"


class ScopeType(StrEnum):
    global_ = "global"  # `global` is a Python keyword, so the name gets a trailing _
    courier = "courier"
    hub = "hub"


class Location(BaseModel):
    city: str | None = None
    country: str | None = None


class Event(BaseModel):
    event_id: str = Field(validation_alias="_id")
    shipment_id: str
    event_type: str
    ts: datetime
    facility_id: str | None = None
    courier_id: str | None = None  # only for courier-handled events (D-08)
    location: Location | None = None
    source: str | None = None


class CurrentStatus(BaseModel):
    status: str
    last_event_ts: datetime
    last_facility_id: str | None = None
    last_courier_id: str | None = None


class ShipmentStatus(BaseModel):
    shipment_id: str = Field(validation_alias="_id")
    current_status: CurrentStatus | None = None  # None until the first event (D-18)


class Scope(BaseModel):
    type: ScopeType
    value: str | None = None  # None for the global scope


class Metric(BaseModel):
    metric: MetricName
    scope: Scope
    period_start: datetime
    period_end: datetime
    value: float
    n: int
    computed_at: datetime
    run_id: str

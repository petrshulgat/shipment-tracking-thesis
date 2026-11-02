"""HTTP endpoints (D-26). Each endpoint calls one function from app/db/queries.py.

Endpoints are plain `def` functions: PyMongo is synchronous, so FastAPI runs
them in a thread pool (D-23).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.api.schemas import Event, Metric, MetricName, ScopeType, ShipmentStatus
from app.db import queries
from app.db.client import get_db

router = APIRouter()

MAX_LIMIT = 1000  # D-26


def database() -> Database:
    """The database every endpoint receives through Depends(). Tests replace it."""
    return get_db()


def as_utc(dt: datetime) -> datetime:
    """Times sent without a timezone are treated as UTC (all stored dates are UTC, D-16)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = as_utc(start), as_utc(end)
    if start >= end:
        raise HTTPException(status_code=422, detail="start must be before end")
    return start, end


@router.get("/health", tags=["system"])
def health(db: Database = Depends(database)):
    db.command("ping")
    return {"status": "ok"}


@router.get("/shipments/{shipment_id}/status", response_model=ShipmentStatus, tags=["shipments"])
def shipment_status(shipment_id: str, db: Database = Depends(database)):
    """Current status of a shipment (AP-05, FR-06)."""
    doc = queries.get_current_status(db, shipment_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Shipment {shipment_id} not found")
    return doc


@router.get("/shipments/{shipment_id}/events", response_model=list[Event], tags=["shipments"])
def shipment_history(shipment_id: str, db: Database = Depends(database)):
    """Full event history in time order (AP-06, FR-07). Unknown shipment: empty list (D-26)."""
    return queries.get_history(db, shipment_id)


@router.get("/facilities/{facility_id}/events", response_model=list[Event], tags=["events"])
def facility_events(facility_id: str, start: datetime, end: datetime,
                    limit: int = Query(queries.DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
                    db: Database = Depends(database)):
    """Events at a facility in [start, end), oldest first (AP-07, FR-08, D-25)."""
    start, end = check_window(start, end)
    return queries.events_by_facility(db, facility_id, start, end, limit)


@router.get("/couriers/{courier_id}/events", response_model=list[Event], tags=["events"])
def courier_events(courier_id: str, start: datetime, end: datetime,
                   limit: int = Query(queries.DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
                   db: Database = Depends(database)):
    """Events handled by a courier in [start, end), oldest first (AP-11, FR-08, D-25)."""
    start, end = check_window(start, end)
    return queries.events_by_courier(db, courier_id, start, end, limit)


@router.get("/metrics", response_model=list[Metric], tags=["metrics"])
def metrics(metric: MetricName, scope_type: ScopeType, start: datetime,
            db: Database = Depends(database)):
    """ETL results from `analytics` with period_start >= start (AP-10, FR-10)."""
    return queries.get_metrics(db, metric.value, scope_type.value, as_utc(start))

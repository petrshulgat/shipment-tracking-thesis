"""FastAPI application. Run: uvicorn app.api.main:app --reload  (Swagger UI: /docs)"""
from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Shipment Tracking API",
    description="Read-only API over MongoDB: shipment status, history, events and ETL metrics.",
    version="0.1.0",
)
app.include_router(router)

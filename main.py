"""
REST API для средства мониторинга (Prometheus-подобное).
Построен по ER-модели из ЛР№1 и классам из ЛР№2.
"""
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
from enum import Enum

from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST,
)

app = FastAPI(
    title="Monitoring Service API",
    version="1.0.0",
    description="REST API для средства мониторинга (FR-01...FR-10)",
)

# Prometheus-метрики
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency",
    ["endpoint"],
)
ACTIVE_ALERTS = Gauge("monitoring_active_alerts", "Number of firing alerts")
TOTAL_METRICS = Gauge("monitoring_total_metrics", "Total registered metrics")


class MetricType(str, Enum):
    counter = "counter"
    gauge = "gauge"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    firing = "firing"
    resolved = "resolved"


db = {
    "sources": {}, "metrics": {}, "values": {},
    "rules": {}, "alerts": {}, "requests": {},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


# ---------- Schemas ----------
class MetricSourceIn(BaseModel):
    name: str
    address: str


class MetricIn(BaseModel):
    source_id: str
    name: str
    type: MetricType


class MetricValueIn(BaseModel):
    metric_id: str
    value: float
    timestamp: Optional[str] = None


class AlertRuleIn(BaseModel):
    metric_id: str
    name: str
    expression: str
    severity: Severity = Severity.warning


class AlertIn(BaseModel):
    rule_id: str
    message: Optional[str] = None


class VisualizationRequestIn(BaseModel):
    metric_id: str
    time_from: str
    time_to: str
    step: int = 60


# ---------- Middleware ----------
@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
    return response


# ---------- Routes ----------
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "time": now()}


@app.get("/metrics", tags=["export"])
def export_metrics():
    TOTAL_METRICS.set(len(db["metrics"]))
    firing = sum(1 for a in db["alerts"].values() if a["status"] == "firing")
    ACTIVE_ALERTS.set(firing)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/sources", status_code=201, tags=["sources"])
def create_source(body: MetricSourceIn):
    sid = new_id()
    db["sources"][sid] = {"id": sid, **body.model_dump(), "created_at": now()}
    return db["sources"][sid]


@app.get("/sources", tags=["sources"])
def list_sources():
    return list(db["sources"].values())


@app.get("/sources/{sid}", tags=["sources"])
def get_source(sid: str):
    if sid not in db["sources"]:
        raise HTTPException(404, "Source not found")
    return db["sources"][sid]


@app.post("/metrics", status_code=201, tags=["metrics"])
def create_metric(body: MetricIn):
    if body.source_id not in db["sources"]:
        raise HTTPException(400, "source_id does not exist")
    mid = new_id()
    db["metrics"][mid] = {"id": mid, **body.model_dump(), "created_at": now()}
    return db["metrics"][mid]


@app.post("/values", status_code=201, tags=["values"])
def create_value(body: MetricValueIn):
    if body.metric_id not in db["metrics"]:
        raise HTTPException(400, "metric_id does not exist")
    vid = new_id()
    db["values"][vid] = {
        "id": vid, **body.model_dump(),
        "timestamp": body.timestamp or now(),
    }
    return db["values"][vid]


@app.post("/rules", status_code=201, tags=["rules"])
def create_rule(body: AlertRuleIn):
    if body.metric_id not in db["metrics"]:
        raise HTTPException(400, "metric_id does not exist")
    if not body.expression:
        raise HTTPException(400, "expression is required")
    rid = new_id()
    db["rules"][rid] = {"id": rid, **body.model_dump(), "created_at": now()}
    return db["rules"][rid]


@app.post("/evaluate", status_code=201, tags=["alerting"])
def evaluate_rule(body: AlertIn):
    if body.rule_id not in db["rules"]:
        raise HTTPException(404, "Rule not found")
    aid = new_id()
    db["alerts"][aid] = {
        "id": aid, "rule_id": body.rule_id,
        "created_at": now(), "status": AlertStatus.firing.value,
        "message": body.message or "Alert triggered",
    }
    return db["alerts"][aid]


@app.post("/visualization/requests", status_code=201, tags=["visualization"])
def create_request(body: VisualizationRequestIn):
    if body.metric_id not in db["metrics"]:
        raise HTTPException(400, "metric_id does not exist")
    req_id = new_id()
    db["requests"][req_id] = {"id": req_id, **body.model_dump(), "created_at": now()}
    return db["requests"][req_id]
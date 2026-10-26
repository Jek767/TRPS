"""
10 модульных тестов для REST API средства мониторинга.
"""
import pytest
from fastapi.testclient import TestClient
from main import app, db

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    for key in db:
        db[key].clear()
    yield


# --- Базовые (2) ---
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_source():
    r = client.post("/sources", json={"name": "node-1", "address": "10.0.0.1"})
    assert r.status_code == 201
    sid = r.json()["id"]
    r = client.get(f"/sources/{sid}")
    assert r.status_code == 200


# --- E2E (1) ---
def test_full_monitoring_flow():
    src = client.post("/sources", json={"name": "node-1", "address": "10.0.0.1"}).json()
    metric = client.post("/metrics", json={
        "source_id": src["id"], "name": "cpu", "type": "gauge"
    }).json()
    val = client.post("/values", json={
        "metric_id": metric["id"], "value": 85.5
    }).json()
    assert val["value"] == 85.5
    rule = client.post("/rules", json={
        "metric_id": metric["id"], "name": "CPU high",
        "expression": "value > 80", "severity": "warning"
    }).json()
    alert = client.post("/evaluate", json={
        "rule_id": rule["id"], "message": "CPU > 80%"
    }).json()
    assert alert["status"] == "firing"
    req = client.post("/visualization/requests", json={
        "metric_id": metric["id"],
        "time_from": "2026-01-01T00:00:00Z",
        "time_to": "2026-01-02T00:00:00Z",
    }).json()
    assert "id" in req


# --- Негативные (7) ---
def test_rule_requires_expression():
    src = client.post("/sources", json={"name": "n", "address": "a"}).json()
    metric = client.post("/metrics", json={
        "source_id": src["id"], "name": "m", "type": "gauge"
    }).json()
    r = client.post("/rules", json={
        "metric_id": metric["id"], "name": "bad", "expression": ""
    })
    assert r.status_code == 400


def test_metric_on_unknown_source_returns_400():
    r = client.post("/metrics", json={
        "source_id": "no-such-id", "name": "m", "type": "gauge"
    })
    assert r.status_code == 400


def test_evaluate_unknown_rule_returns_404():
    r = client.post("/evaluate", json={"rule_id": "no-such-id"})
    assert r.status_code == 404


def test_value_on_unknown_metric_returns_400():
    r = client.post("/values", json={"metric_id": "no-such-id", "value": 42.0})
    assert r.status_code == 400


def test_visualization_on_unknown_metric_returns_400():
    r = client.post("/visualization/requests", json={
        "metric_id": "no-such-id",
        "time_from": "2026-01-01T00:00:00Z",
        "time_to": "2026-01-02T00:00:00Z",
    })
    assert r.status_code == 400


def test_get_unknown_source_returns_404():
    r = client.get("/sources/unknown-id")
    assert r.status_code == 404


def test_prometheus_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text or "monitoring_total_metrics" in r.text
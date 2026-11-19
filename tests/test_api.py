"""Tests for the FastAPI endpoints."""

from __future__ import annotations

from tests.conftest import sample_event


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "data-service"
    assert "version" in body


def test_ready_returns_ready_when_db_up(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ingest_accepts_valid_event(client):
    response = client.post("/v1/ingest", json=sample_event())
    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] is True
    assert body["event_id"] == "evt-001"
    assert body["schema_version"] == "1.1"
    assert isinstance(body["stored_id"], int)


def test_ingest_rejects_unsupported_schema_version(client):
    response = client.post("/v1/ingest", json=sample_event(schema_version="9.9"))
    assert response.status_code == 422


def test_ingest_rejects_missing_required_fields(client):
    payload = sample_event()
    del payload["event_id"]
    response = client.post("/v1/ingest", json=payload)
    assert response.status_code == 422


def test_ingest_is_idempotent_on_event_id_and_source(client):
    first = client.post("/v1/ingest", json=sample_event())
    second = client.post("/v1/ingest", json=sample_event())
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["stored_id"] == second.json()["stored_id"]
    records = client.get("/v1/records").json()
    assert len(records) == 1


def test_records_lists_ingested_events_newest_first(client):
    client.post("/v1/ingest", json=sample_event(event_id="evt-001"))
    client.post("/v1/ingest", json=sample_event(event_id="evt-002"))
    records = client.get("/v1/records").json()
    assert [r["event_id"] for r in records] == ["evt-002", "evt-001"]
    assert records[0]["payload"] == {"order_id": "ORD-1", "total_usd": 42.5}
    assert records[0]["trace_id"] == "trace-abc"


def test_records_filters_by_source_and_type(client):
    client.post("/v1/ingest", json=sample_event(event_id="evt-001", source="checkout"))
    client.post("/v1/ingest", json=sample_event(event_id="evt-002", source="search"))
    by_source = client.get("/v1/records", params={"source": "search"}).json()
    assert [r["event_id"] for r in by_source] == ["evt-002"]
    by_type = client.get(
        "/v1/records", params={"event_type": "order.completed"}
    ).json()
    assert len(by_type) == 2
    by_missing = client.get("/v1/records", params={"source": "nope"}).json()
    assert by_missing == []


def test_records_limit_is_enforced(client):
    for i in range(5):
        client.post("/v1/ingest", json=sample_event(event_id=f"evt-{i:03d}"))
    records = client.get("/v1/records", params={"limit": 2}).json()
    assert len(records) == 2
    assert client.get("/v1/records", params={"limit": 0}).status_code == 422
    assert client.get("/v1/records", params={"limit": 501}).status_code == 422


def test_metrics_endpoint_exposes_counters(client):
    client.get("/health")
    client.post("/v1/ingest", json=sample_event())
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "ingest_accepted_total" in response.text
    assert 'schema_version="1.1"' in response.text

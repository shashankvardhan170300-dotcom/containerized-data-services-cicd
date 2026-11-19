"""Shared fixtures for the service tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.service.db import EventStore
from src.service.main import create_app


@pytest.fixture()
def store(tmp_path):
    """A fresh SQLite store per test (in-memory file)."""
    event_store = EventStore(str(tmp_path / "test.db"))
    yield event_store
    event_store.close()


@pytest.fixture()
def client(store):
    """A TestClient bound to a fresh app + fresh store."""
    app = create_app(store=store)
    with TestClient(app) as test_client:
        yield test_client


def sample_event(**overrides):
    """A valid v1.1 ingest payload; override any field."""
    payload = {
        "schema_version": "1.1",
        "event_id": "evt-001",
        "source": "checkout",
        "event_type": "order.completed",
        "payload": {"order_id": "ORD-1", "total_usd": 42.5},
        "occurred_at": "2026-11-19T10:00:00Z",
        "trace_id": "trace-abc",
    }
    payload.update(overrides)
    return payload

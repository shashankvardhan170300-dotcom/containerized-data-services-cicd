"""Containerized data service.

A small FastAPI service demonstrating the patterns used to run data
services in production:

* ``GET /health`` — liveness probe (does the process answer?).
* ``GET /ready`` — readiness probe (can the service serve traffic?
  currently: is the database reachable?).
* ``POST /v1/ingest`` — accepts events that match a versioned data
  contract (see :mod:`src.contracts`) and stores them idempotently.
* ``GET /v1/records`` — query stored events, with optional filters.
* ``GET /metrics`` — Prometheus-style counters.

Run locally with::

    uvicorn src.service.main:app --reload --port 8000

or via Docker Compose (see the project README).
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from src.contracts.models import IngestEvent, IngestResponse, RecordOut
from src.service.config import Settings, load_settings
from src.service.db import EventStore


class Metrics:
    """Tiny in-process Prometheus-style counters (no extra dependency)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    def inc(self, name: str, **labels: str) -> None:
        key = name + "|" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1

    def render(self) -> str:
        lines: list[str] = []
        grouped: dict[str, list[tuple[str, int]]] = {}
        with self._lock:
            items = sorted(self._counters.items())
        for key, value in items:
            name, _, label_str = key.partition("|")
            grouped.setdefault(name, []).append((label_str, value))
        for name in sorted(grouped):
            lines.append(f"# HELP {name} counter")
            lines.append(f"# TYPE {name} counter")
            for label_str, value in grouped[name]:
                lines.append(f"{name}{{{label_str}}} {value}")
        return "\n".join(lines) + "\n"


metrics = Metrics()


def create_app(settings: Settings | None = None, store: EventStore | None = None) -> FastAPI:
    """Build the FastAPI app.

    Args:
        settings: Runtime settings; loaded from the environment when
            omitted.
        store: Event store; a SQLite store is created from settings
            when omitted. Tests pass their own store.
    """
    cfg = settings or load_settings()
    event_store = store or EventStore(cfg.db_path, pool_timeout=cfg.pool_timeout)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The store creates its schema on init; nothing else to start.
        yield
        event_store.close()

    app = FastAPI(
        title="data-service",
        description="Containerized data service with versioned data contracts.",
        version=cfg.version,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def _count_requests(request: Request, call_next):
        response = await call_next(request)
        metrics.inc(
            "http_requests_total",
            method=request.method,
            path=request.url.path,
            status=str(response.status_code),
        )
        return response

    @app.get("/health")
    def health() -> dict:
        """Liveness probe: the process is up."""
        return {"status": "ok", "service": cfg.service_name, "version": cfg.version}

    @app.get("/ready")
    def ready() -> dict:
        """Readiness probe: the database answers."""
        if not event_store.ping():
            raise HTTPException(status_code=503, detail="database unavailable")
        return {"status": "ready", "service": cfg.service_name}

    @app.post("/v1/ingest", response_model=IngestResponse, status_code=201)
    def ingest(event: IngestEvent) -> IngestResponse:
        """Validate an event against its data contract and store it."""
        stored_id = event_store.insert(event)
        metrics.inc("ingest_accepted_total", schema_version=event.schema_version)
        return IngestResponse(
            event_id=event.event_id,
            schema_version=event.schema_version,
            stored_id=stored_id,
        )

    @app.get("/v1/records", response_model=list[RecordOut])
    def list_records(
        source: str | None = Query(default=None, description="Filter by event source."),
        event_type: str | None = Query(default=None, description="Filter by event type."),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[RecordOut]:
        """Query stored events, newest first."""
        rows = event_store.list_records(source=source, event_type=event_type, limit=limit)
        return [RecordOut(**row) for row in rows]

    @app.get("/metrics", response_class=PlainTextResponse)
    def get_metrics() -> str:
        """Prometheus-style metrics exposition."""
        return metrics.render()

    return app


# Default app instance for `uvicorn src.service.main:app`.
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "src.service.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )

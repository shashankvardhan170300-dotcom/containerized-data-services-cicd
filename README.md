# Containerized Data Services & CI/CD

A containerized data service with versioned data contracts, Kubernetes
manifests, and a GitHub Actions CI/CD pipeline — built in Python with
FastAPI, Pydantic, and SQLite (demo store).

> **Portfolio reconstruction.** This project is not Walmart's
> proprietary code or infrastructure. It is a from-scratch
> reconstruction that demonstrates the same engineering patterns I
> used as a Data & ML Engineer at Walmart Global Tech (May 2025–
> present): Python FastAPI data services, data contracts with schema
> evolution, containerized deployments on Kubernetes, and CI/CD gates
> across many repositories. No employer code, credentials, or internal
> system names are used here, and no metrics beyond my own public
> resume are claimed.

## What it does

The service ingests events, validates them against a versioned data
contract, stores them idempotently, and serves them back over a query
API — the same shape as a production data service, minus the managed
cloud dependencies.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe — is the process up? |
| `GET /ready` | Readiness probe — is the database reachable? |
| `POST /v1/ingest` | Accept an event that matches a supported contract version (201) or reject it (422) |
| `GET /v1/records` | Query stored events, newest first; filter by `source` / `event_type`, paginate with `limit` |
| `GET /metrics` | Prometheus-style counters (`http_requests_total`, `ingest_accepted_total`) |

### Data contracts (`src/contracts/`)

Every event carries a `schema_version` (`1.0` or `1.1`). Unknown
versions are rejected, never silently ingested. Version 1.1 adds an
optional `trace_id` for lineage and accepts the legacy `type` field
as an alias for `event_type` — the small, boring compatibility
shims that keep schema evolution from breaking consumers.
Re-ingesting the same `(event_id, source)` returns the existing row
instead of duplicating it.

### Connection-pool tuning (`src/service/config.py`)

Pool knobs are read from the environment: `POOL_SIZE` (ready
connections), `POOL_TIMEOUT` (seconds to wait for a free connection
before failing fast), and `POOL_MAX_OVERFLOW` (burst headroom).
The SQLite demo store honours `POOL_TIMEOUT` as its connect timeout
and serialises writes behind a lock; a Postgres adapter would
consume all three knobs. The knobs are also wired into
`k8s/configmap.yaml` and `docker-compose.yml`.

## Project layout

```
src/
  service/        FastAPI app (main.py), settings (config.py), SQLite store (db.py)
  contracts/      Pydantic contract models + schema-version registry (models.py)
tests/            pytest: API tests (test_api.py) and contract tests (test_contracts.py)
k8s/              Deployment, Service, ConfigMap, HorizontalPodAutoscaler
.github/workflows/ci.yml   lint (ruff) -> test (pytest) -> build image -> deploy (disabled example)
scripts/smoke_test.sh      builds the image and curls /health (skips if Docker is absent)
Dockerfile        multi-stage, python:3.12-slim, non-root user, healthcheck
docker-compose.yml  service + Postgres 16 (local dev database; see Databases)
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx ruff        # dev/test tools
uvicorn src.service.main:app --reload --port 8000
```

Try it:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/ingest \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":"1.1","event_id":"evt-1","source":"checkout",
       "event_type":"order.completed",
       "payload":{"order_id":"ORD-1","total_usd":42.5},
       "occurred_at":"2026-11-19T10:00:00Z","trace_id":"trace-1"}'
curl "http://127.0.0.1:8000/v1/records?source=checkout"
curl http://127.0.0.1:8000/metrics
```

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```

18 tests: endpoint behaviour (health/readiness, ingest, idempotency,
filtering, limits, metrics) and contract validation (supported
versions, legacy alias, trace-id gating, missing fields).

## Docker

```bash
docker compose up --build     # service on :8000, Postgres on :5432
bash scripts/smoke_test.sh    # builds the image, curls /health, exits 0 if Docker is absent
```

The image is multi-stage (`python:3.12-slim`), runs as a non-root
user, and has a stdlib-only healthcheck (`/health`).

## Kubernetes

```bash
kubectl apply -f k8s/
```

The Deployment (2 replicas, rolling update) sets readiness/liveness
probes, CPU/memory requests and limits, and a hardened security
context (non-root, read-only root filesystem, all capabilities
dropped). The HPA scales 2–8 replicas on CPU/memory. All names,
namespaces, and the image reference
(`registry.example.com/data-service:latest`) are placeholders — replace
them with your registry and cluster values before deploying.

## Databases

The demo persists to SQLite (`DB_PATH`, default `data.db`) so the
service runs anywhere. `docker-compose.yml` also starts a Postgres 16
container for local development; the demo service does not use it yet
— set `DATABASE_URL` once a Postgres adapter is added. The store
interface (`EventStore.insert` / `list_records` / `ping`) is kept
small on purpose so the service code does not change when the
database behind it does.

## CI/CD

`.github/workflows/ci.yml` runs on pushes and PRs to `main`:

1. **lint** — `ruff check`
2. **test** — `pytest`
3. **build** — builds the Docker image (no push)
4. **deploy** — disabled example job (`if: false`); wire up your own
   registry login, image push, and `kubectl apply` before enabling.

## Author

Shashank Narayandas — Data & ML Engineer. M.S. Data Science,
Webster University. [LinkedIn](https://linkedin.com/in/shashank-ai-ml)

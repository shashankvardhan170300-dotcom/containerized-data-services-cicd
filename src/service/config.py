"""Runtime settings, read from the environment.

All values have safe local defaults. In production these come from the
ConfigMap / secrets injected by Kubernetes (see k8s/configmap.yaml).
The pool knobs are the ones tuned against production load: POOL_SIZE is
the number of connections the pool keeps ready, POOL_TIMEOUT is how long
a request waits for a free connection before failing fast, and
POOL_MAX_OVERFLOW is how many extra connections may be opened under
burst. The SQLite demo store honours POOL_TIMEOUT (as the connect
timeout) and serialises writes behind a lock; a Postgres adapter would
consume all three knobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str = "data-service"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "data.db"
    # Connection-pool tuning knobs (see module docstring).
    pool_size: int = 5
    pool_timeout: float = 5.0
    pool_max_overflow: int = 10
    max_ingest_payload_kb: int = 256


def load_settings() -> Settings:
    return Settings(
        service_name=os.environ.get("SERVICE_NAME", "data-service"),
        version=os.environ.get("SERVICE_VERSION", "0.1.0"),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        db_path=os.environ.get("DB_PATH", "data.db"),
        pool_size=int(os.environ.get("POOL_SIZE", "5")),
        pool_timeout=float(os.environ.get("POOL_TIMEOUT", "5.0")),
        pool_max_overflow=int(os.environ.get("POOL_MAX_OVERFLOW", "10")),
        max_ingest_payload_kb=int(os.environ.get("MAX_INGEST_PAYLOAD_KB", "256")),
    )

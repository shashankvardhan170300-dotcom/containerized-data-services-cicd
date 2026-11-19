"""Event store.

The demo store persists to SQLite so the service runs anywhere with no
external database. The interface is deliberately small (``insert``,
``list_records``, ``ping``) so the same service code can sit on top of
a pooled Postgres connection in production without changing the API
layer. Writes are serialised behind a lock; reads use the same
connection, which is safe for SQLite's file-backed model.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from src.contracts.models import IngestEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    event_id TEXT NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    trace_id TEXT,
    UNIQUE (event_id, source)
);
CREATE INDEX IF NOT EXISTS idx_events_source ON events (source);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
"""


class EventStore:
    """SQLite-backed event store.

    Args:
        db_path: Path to the SQLite file. Use ``:memory:`` for tests.
        pool_timeout: Seconds to wait for a locked database before
            failing. This is the knob tuned against production load.
    """

    def __init__(self, db_path: str = "data.db", pool_timeout: float = 5.0):
        self.db_path = db_path
        self.pool_timeout = pool_timeout
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            db_path, check_same_thread=False, timeout=pool_timeout
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def ping(self) -> bool:
        """Return True if the database answers a trivial query."""
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def insert(self, event: IngestEvent) -> int:
        """Store an event. Idempotent on (event_id, source).

        Returns the row id; re-ingesting the same event_id/source
        returns the existing row id instead of duplicating the row.
        """
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO events "
                "(schema_version, event_id, source, event_type, payload, "
                " occurred_at, trace_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.schema_version,
                    event.event_id,
                    event.source,
                    event.event_type,
                    json.dumps(event.payload),
                    event.occurred_at.isoformat(),
                    event.trace_id,
                ),
            )
            self._conn.commit()
            if cur.lastrowid:
                return cur.lastrowid
            row = self._conn.execute(
                "SELECT id FROM events WHERE event_id = ? AND source = ?",
                (event.event_id, event.source),
            ).fetchone()
            return int(row["id"])

    def list_records(
        self,
        source: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return stored events, newest first, with optional filters."""
        query = "SELECT * FROM events"
        clauses: list[str] = []
        params: list[object] = []
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "schema_version": row["schema_version"],
            "event_id": row["event_id"],
            "source": row["source"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"]),
            "occurred_at": datetime.fromisoformat(row["occurred_at"]),
            "trace_id": row["trace_id"],
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

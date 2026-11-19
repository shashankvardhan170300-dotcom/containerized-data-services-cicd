#!/usr/bin/env bash
# Smoke test: build the image and curl the health endpoint.
# Skips cleanly (exit 0) when Docker is not available.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
    echo "SKIP: docker is not installed; cannot build/run the image."
    exit 0
fi

IMAGE="data-service:smoke"
CONTAINER="data-service-smoke"
PORT="${SMOKE_PORT:-8123}"

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Building $IMAGE ..."
docker build -t "$IMAGE" .

echo "Starting $CONTAINER on port $PORT ..."
docker run -d --rm --name "$CONTAINER" -p "$PORT:8000" "$IMAGE" >/dev/null

echo "Waiting for /health ..."
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        echo "OK: health endpoint responded."
        curl -s "http://127.0.0.1:$PORT/health"; echo
        curl -s -X POST "http://127.0.0.1:$PORT/v1/ingest" \
            -H 'Content-Type: application/json' \
            -d '{"schema_version":"1.1","event_id":"smoke-1","source":"smoke","event_type":"smoke.ping","occurred_at":"2026-11-19T10:00:00Z"}'
        echo
        echo "Smoke test passed."
        exit 0
    fi
    sleep 1
done

echo "FAIL: health endpoint did not respond in time."
docker logs "$CONTAINER" || true
exit 1

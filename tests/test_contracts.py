"""Tests for the data-contract models."""

from __future__ import annotations

import pytest

from src.contracts.models import (
    SUPPORTED_SCHEMA_VERSIONS,
    ContractError,
    IngestEvent,
    parse_event,
)


def test_supported_versions_are_1_0_and_1_1():
    assert SUPPORTED_SCHEMA_VERSIONS == ("1.0", "1.1")


def test_valid_v11_event_parses():
    event = parse_event(
        {
            "schema_version": "1.1",
            "event_id": "evt-1",
            "source": "web",
            "event_type": "page.view",
            "payload": {"url": "/home"},
            "occurred_at": "2026-11-19T10:00:00Z",
            "trace_id": "t-1",
        }
    )
    assert isinstance(event, IngestEvent)
    assert event.trace_id == "t-1"


def test_schema_version_defaults_to_1_0():
    event = parse_event(
        {
            "event_id": "evt-1",
            "source": "web",
            "event_type": "page.view",
            "occurred_at": "2026-11-19T10:00:00Z",
        }
    )
    assert event.schema_version == "1.0"


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(ContractError, match="unsupported schema_version"):
        parse_event(
            {
                "schema_version": "3.0",
                "event_id": "evt-1",
                "source": "web",
                "event_type": "page.view",
                "occurred_at": "2026-11-19T10:00:00Z",
            }
        )


def test_legacy_type_field_is_accepted_as_event_type():
    event = parse_event(
        {
            "schema_version": "1.0",
            "event_id": "evt-1",
            "source": "web",
            "type": "page.view",
            "occurred_at": "2026-11-19T10:00:00Z",
        }
    )
    assert event.event_type == "page.view"


def test_trace_id_requires_schema_1_1():
    with pytest.raises(ContractError, match="trace_id"):
        parse_event(
            {
                "schema_version": "1.0",
                "event_id": "evt-1",
                "source": "web",
                "event_type": "page.view",
                "occurred_at": "2026-11-19T10:00:00Z",
                "trace_id": "t-1",
            }
        )


def test_missing_required_field_is_rejected():
    with pytest.raises(ContractError):
        parse_event(
            {
                "schema_version": "1.1",
                "source": "web",
                "event_type": "page.view",
                "occurred_at": "2026-11-19T10:00:00Z",
            }
        )


def test_empty_payload_is_allowed():
    event = parse_event(
        {
            "schema_version": "1.1",
            "event_id": "evt-1",
            "source": "web",
            "event_type": "heartbeat",
            "occurred_at": "2026-11-19T10:00:00Z",
        }
    )
    assert event.payload == {}

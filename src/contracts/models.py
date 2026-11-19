"""Data-contract models for the containerized data service.

This module implements the data-contract pattern: every event that enters
the service must match a versioned contract, and the contract version is
part of the payload. Producers that send an unknown version are rejected
instead of silently ingested, which is how schema evolution stays safe
across many services and consumers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Schema versions this service accepts. Bump the minor version for
#: backwards-compatible additions; a major bump is a new contract.
SUPPORTED_SCHEMA_VERSIONS = ("1.0", "1.1")


class ContractError(ValueError):
    """Raised when a payload fails contract validation."""


class IngestEvent(BaseModel):
    """A single event accepted by the ingest endpoint.

    Version 1.0 fields: ``schema_version``, ``event_id``, ``source``,
    ``event_type``, ``payload``, ``occurred_at``.

    Version 1.1 adds the optional ``trace_id`` for end-to-end lineage
    and accepts the legacy ``type`` field as an alias for ``event_type``.
    """

    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(
        default="1.0",
        description="Contract version of this payload, e.g. '1.0' or '1.1'.",
    )
    event_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    trace_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def _legacy_event_type_alias(cls, data: Any) -> Any:
        # v1.0 producers sent "type" instead of "event_type".
        if isinstance(data, dict) and "event_type" not in data and "type" in data:
            data = {**data, "event_type": data.pop("type")}
        return data

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema_version {value!r}; "
                f"supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        return value

    @field_validator("trace_id")
    @classmethod
    def _trace_id_requires_v11(cls, value: str | None, info) -> str | None:
        if value is not None and info.data.get("schema_version") == "1.0":
            raise ValueError("trace_id is only available from schema_version 1.1")
        return value


class IngestResponse(BaseModel):
    """Response returned after a successful ingest."""

    accepted: Literal[True] = True
    event_id: str
    schema_version: str
    stored_id: int


class RecordOut(BaseModel):
    """An event as returned by the query endpoint."""

    id: int
    schema_version: str
    event_id: str
    source: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    trace_id: str | None = None


def parse_event(raw: dict[str, Any]) -> IngestEvent:
    """Validate a raw dict against the contract.

    Raises:
        ContractError: if the payload does not match any supported
            contract version.
    """
    try:
        return IngestEvent.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError
        raise ContractError(str(exc)) from exc

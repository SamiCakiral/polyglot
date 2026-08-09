from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: UUID
    command_type: str
    actor_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    idempotency_key: str
    request_fingerprint: str
    expected_version: int | None
    received_at: datetime
    result_ref: UUID | None
    status: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CommandReservation:
    receipt: CommandReceipt
    created: bool


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: UUID
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    actor_type: str
    actor_id: UUID
    profile_id: UUID | None
    occurred_at: datetime
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID | None
    command_id: UUID
    privacy_class: str
    policy_revision_ids: list[UUID]
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class InboxReceipt:
    consumer_code: str
    event_id: UUID
    processed_at: datetime
    result_checksum: str


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    outbox_id: UUID
    event_id: UUID
    destination: str
    correlation_id: UUID
    created_at: datetime
    attempt_count: int
    lease_owner: str
    lease_expires_at: datetime

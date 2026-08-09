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
    result_payload: dict[str, JsonValue] | None
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
    policy_versions: dict[str, JsonValue]
    payload: dict[str, JsonValue]
    expires_at: datetime | None = None

    def to_envelope(self) -> dict[str, JsonValue]:
        envelope: dict[str, JsonValue] = {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "aggregate_version": self.aggregate_version,
            "actor_type": self.actor_type,
            "actor_id": str(self.actor_id),
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "correlation_id": str(self.correlation_id),
            "command_id": str(self.command_id),
            "payload": self.payload,
            "privacy_class": self.privacy_class,
            "policy_versions": self.policy_versions,
        }
        if self.profile_id is not None:
            envelope["profile_id"] = str(self.profile_id)
        if self.causation_id is not None:
            envelope["causation_id"] = str(self.causation_id)
        return envelope


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
    lease_token: UUID
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class JobClaim:
    job_id: UUID
    attempt_no: int
    worker_id: str
    lease_token: UUID
    lease_expires_at: datetime
    started_at: datetime


@dataclass(frozen=True, slots=True)
class RetentionPurgeResult:
    audit_id: UUID
    domain_event_count: int
    security_audit_count: int

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.event_contracts import canonical_event_versions
from polyglot.platform.fingerprint import canonical_json_bytes
from polyglot.platform.json_types import JsonValue

_ALLOWED_ACTOR_TYPES = frozenset({"account", "service", "support", "system"})
_ALLOWED_PRIVACY_CLASSES = frozenset({"public", "internal", "personal", "sensitive"})
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "cookie",
        "credential",
        "password",
        "prompt",
        "raw_audio",
        "refresh_token",
        "secret",
        "signed_url",
        "token",
        "transcript",
    }
)
_MAX_EVENT_PAYLOAD_BYTES = 65_536
_ALLOWED_PRIVATE_SUBJECT_TYPES = frozenset({"account", "profile"})


def _invalid_event(field: str, code: str = "invalid") -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION_FAILED,
        field_errors=[{"location": field, "code": code}],
    )


def _invalid_receipt(field: str) -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION_FAILED,
        field_errors=[{"location": field, "code": "invalid_reservation_state"}],
    )


def _contains_forbidden_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in _FORBIDDEN_PAYLOAD_KEYS or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


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

    def __post_init__(self) -> None:
        self.validate_reservation()

    def validate_reservation(self) -> None:
        if self.status != "started":
            raise _invalid_receipt("status")
        if self.result_ref is not None:
            raise _invalid_receipt("result_ref")
        if self.result_payload is not None:
            raise _invalid_receipt("result_payload")


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
    subject_type: str | None = None
    subject_id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.event_type, self.schema_version) not in canonical_event_versions():
            raise _invalid_event("event_type")
        identifiers = {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "command_id": self.command_id,
        }
        if self.profile_id is not None:
            identifiers["profile_id"] = self.profile_id
        if self.causation_id is not None:
            identifiers["causation_id"] = self.causation_id
        if self.subject_id is not None:
            identifiers["subject_id"] = self.subject_id
        for field, identifier in identifiers.items():
            if identifier.version != 7:
                raise _invalid_event(field)
        if self.actor_type not in _ALLOWED_ACTOR_TYPES:
            raise _invalid_event("actor_type")
        if self.privacy_class not in _ALLOWED_PRIVACY_CLASSES:
            raise _invalid_event("privacy_class")
        for field, instant in {
            "occurred_at": self.occurred_at,
            "recorded_at": self.recorded_at,
        }.items():
            if not _is_utc(instant):
                raise _invalid_event(field)
        if self.expires_at is not None and not _is_utc(self.expires_at):
            raise _invalid_event("expires_at")
        if self.privacy_class in {"personal", "sensitive"}:
            if self.expires_at is None:
                raise _invalid_event("expires_at", "required_for_private_event")
            if self.subject_type not in _ALLOWED_PRIVATE_SUBJECT_TYPES:
                raise _invalid_event("subject_type", "required_for_private_event")
            if self.subject_id is None:
                raise _invalid_event("subject_id", "required_for_private_event")
        try:
            payload_size = len(canonical_json_bytes(self.payload))
        except (TypeError, ValueError):
            raise _invalid_event("payload") from None
        if payload_size > _MAX_EVENT_PAYLOAD_BYTES or _contains_forbidden_key(self.payload):
            raise _invalid_event("payload")

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

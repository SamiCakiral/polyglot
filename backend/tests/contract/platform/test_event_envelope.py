import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator


def new_id() -> object:
    return Uuid7Generator().new()


def test_domain_event_serializes_with_the_canonical_w00_envelope() -> None:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    event = DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="example",
        aggregate_id=new_id(),
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="internal",
        policy_versions={"privacy_policy": "v1"},
        payload={"schema_version": 1},
    )

    envelope = event.to_envelope()
    schema = json.loads(
        (Path(__file__).parents[4] / "contracts/events/envelope.schema.json").read_text()
    )

    assert set(schema["required"]) <= envelope.keys()
    assert set(envelope) <= schema["properties"].keys()
    assert envelope["policy_versions"] == {"privacy_policy": "v1"}
    assert "policy_revision_ids" not in envelope
    assert "profile_id" not in envelope
    assert "causation_id" not in envelope


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"event_type": "not_registered"}, "event_type"),
        ({"event_id": uuid4()}, "event_id"),
        ({"privacy_class": "secret"}, "privacy_class"),
        ({"privacy_class": "unknown"}, "privacy_class"),
        ({"payload": {"access_token": "private"}}, "payload"),
        ({"payload": {"value": "x" * 70_000}}, "payload"),
    ],
)
def test_domain_event_rejects_noncanonical_or_private_boundaries(
    changes: dict[str, object],
    field: str,
) -> None:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    values = {
        "event_id": new_id(),
        "event_type": "account_registered",
        "schema_version": 1,
        "aggregate_type": "account",
        "aggregate_id": new_id(),
        "aggregate_version": 1,
        "actor_type": "system",
        "actor_id": new_id(),
        "profile_id": None,
        "occurred_at": now,
        "recorded_at": now,
        "correlation_id": new_id(),
        "causation_id": None,
        "command_id": new_id(),
        "privacy_class": "internal",
        "policy_versions": {"privacy": "v1"},
        "payload": {"account_id": str(new_id())},
        "expires_at": None,
    }
    values.update(changes)

    with pytest.raises(DomainError) as captured:
        DomainEvent(**values)

    assert captured.value.code is ErrorCode.VALIDATION_FAILED
    assert captured.value.field_errors == [{"location": field, "code": "invalid"}]


def test_account_private_event_accepts_subject_scope_without_profile() -> None:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    subject_id = new_id()
    event = DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="account",
        aggregate_id=subject_id,
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="personal",
        policy_versions={"retention": "v1"},
        payload={"account_id": str(subject_id)},
        expires_at=now,
        subject_type="account",
        subject_id=subject_id,
    )

    assert event.profile_id is None
    assert "subject_type" not in event.to_envelope()
    assert "subject_id" not in event.to_envelope()


@pytest.mark.parametrize(
    ("subject_type", "subject_id", "expires_at", "field"),
    [
        ("account", new_id(), None, "expires_at"),
        (None, None, datetime.now(UTC), "subject_type"),
        ("account", None, datetime.now(UTC), "subject_id"),
        ("tenant", new_id(), datetime.now(UTC), "subject_type"),
    ],
)
def test_private_domain_event_requires_expiration_and_subject_scope(
    subject_type: str | None,
    subject_id: object | None,
    expires_at: datetime | None,
    field: str,
) -> None:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    with pytest.raises(DomainError) as captured:
        DomainEvent(
            event_id=new_id(),
            event_type="account_registered",
            schema_version=1,
            aggregate_type="account",
            aggregate_id=new_id(),
            aggregate_version=1,
            actor_type="system",
            actor_id=new_id(),
            profile_id=None,
            occurred_at=now,
            recorded_at=now,
            correlation_id=new_id(),
            causation_id=None,
            command_id=new_id(),
            privacy_class="personal",
            policy_versions={"retention": "v1"},
            payload={"account_id": str(new_id())},
            expires_at=expires_at,
            subject_type=subject_type,
            subject_id=subject_id,
        )

    assert captured.value.field_errors == [
        {"location": field, "code": "required_for_private_event"}
    ]

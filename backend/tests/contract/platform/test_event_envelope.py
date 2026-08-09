import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def test_domain_event_serializes_with_the_canonical_w00_envelope() -> None:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    event = DomainEvent(
        event_id=uuid4(),
        event_type="example_recorded",
        schema_version=1,
        aggregate_type="example",
        aggregate_id=uuid4(),
        aggregate_version=1,
        actor_type="system",
        actor_id=uuid4(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=uuid4(),
        causation_id=None,
        command_id=uuid4(),
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

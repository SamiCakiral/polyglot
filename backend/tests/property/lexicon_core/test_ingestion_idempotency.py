from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.lexicon.core.application import (
    EncounterFact,
    IdempotencyLedger,
    LexiconProjector,
    ResolutionFact,
    redact_private_context,
)
from polyglot.platform.errors import DomainError, ErrorCode


def uid(number: int) -> UUID:
    return UUID(f"019feb20-0000-7000-8000-{number:012x}")


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def facts() -> tuple[EncounterFact | ResolutionFact, ...]:
    return (
        EncounterFact(uid(1), uid(2), uid(3), "piano", "a" * 64, "contexte", NOW),
        EncounterFact(uid(4), uid(2), uid(5), "piano", "b" * 64, "autre", NOW),
        ResolutionFact(uid(6), uid(2), uid(3), uid(10), NOW + timedelta(minutes=2)),
        ResolutionFact(uid(7), uid(2), uid(3), uid(11), NOW + timedelta(minutes=5)),
    )


@given(st.permutations(facts()))
def test_projection_rebuild_is_deterministic_for_every_ingestion_order(
    shuffled: tuple[EncounterFact | ResolutionFact, ...],
) -> None:
    assert LexiconProjector.rebuild(shuffled) == LexiconProjector.rebuild(facts())


def test_same_idempotency_key_and_fingerprint_has_one_effect() -> None:
    ledger = IdempotencyLedger()

    first = ledger.apply("RecordLexicalEncounter", "same-key", "a" * 64, uid(1))
    replay = ledger.apply("RecordLexicalEncounter", "same-key", "a" * 64, uid(99))

    assert first == replay == uid(1)
    assert ledger.effect_count == 1


def test_same_idempotency_key_with_different_payload_is_rejected() -> None:
    ledger = IdempotencyLedger()
    ledger.apply("CaptureLexicalGap", "same-key", "a" * 64, uid(1))

    with pytest.raises(DomainError) as error:
        ledger.apply("CaptureLexicalGap", "same-key", "b" * 64, uid(2))

    assert error.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


def test_late_resolution_changes_interpretation_not_raw_occurrence() -> None:
    original = facts()[0]
    projection = LexiconProjector.rebuild(facts())

    assert projection.encounters[uid(1)] == original
    assert projection.current_sense_by_mention[uid(3)] == uid(11)


def test_private_context_redaction_preserves_minimal_provenance_and_fact() -> None:
    original = facts()[0]
    redacted = redact_private_context(original, deleted_at=NOW + timedelta(hours=1))

    assert redacted.context_private is None
    assert redacted.context_fingerprint == original.context_fingerprint
    assert redacted.encounter_id == original.encounter_id
    assert redacted.exact_surface == original.exact_surface
    assert redacted.context_deleted_at == NOW + timedelta(hours=1)

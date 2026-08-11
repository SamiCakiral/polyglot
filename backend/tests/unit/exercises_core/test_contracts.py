import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
DEFINITION_ID = UUID("019fe009-0000-7000-8000-000000000001")
REVISION_ID = UUID("019fe009-0000-7000-8000-000000000002")
INSTANCE_ID = UUID("019fe009-0000-7000-8000-000000000003")
PROFILE_ID = UUID("019fe009-0000-7000-8000-000000000004")
PACK_REVISION_ID = UUID("019fe009-0000-7000-8000-000000000005")
CERTIFICATION_ID = UUID("019fe009-0000-7000-8000-000000000006")
ATTEMPT_ID = UUID("019fe009-0000-7000-8000-000000000007")
CORRECTION_ID = UUID("019fe009-0000-7000-8000-000000000008")
CASE_ID = UUID("019fe009-0000-7000-8000-000000000009")
FIXTURE = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-PRIMITIVES/primitives.json"
FIXTURE_METADATA = FIXTURE.with_name("fixture-metadata.json")


class FixedIds:
    def __init__(self, *values: UUID) -> None:
        self._values = iter(values)

    def new(self) -> UUID:
        return next(self._values)


def published_definition():
    from polyglot.modules.exercises.core.domain import AnswerKind, ExerciseDefinition

    return ExerciseDefinition.published(
        definition_id=DEFINITION_ID,
        revision_id=REVISION_ID,
        revision_no=1,
        primitive_id="EX-DISC-04",
        response_kinds=(AnswerKind.SINGLE_CHOICE,),
        language_certification_ids=(CERTIFICATION_ID,),
        modes=("functional_contrast",),
        target_weights=(("skill:contrast", 0.35),),
        correction_policy_id="policy:exact-choice:v1",
        hint_policy_id="policy:hints:v1",
        observation_policy_id="policy:observation:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )


def instance():
    from polyglot.modules.exercises.core.domain import ExerciseInstance

    return ExerciseInstance.create(
        instance_id=INSTANCE_ID,
        definition=published_definition(),
        language_pack_revision_id=PACK_REVISION_ID,
        seed=9009,
        stimulus_revision_ids=(REVISION_ID,),
    )


def test_core_registry_is_closed_and_fixture_covers_every_core_primitive() -> None:
    from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS, primitive_spec

    fixture = json.loads(FIXTURE.read_text())

    assert {item["primitive_id"] for item in fixture["primitives"]} == set(CORE_PRIMITIVE_IDS)
    assert len(CORE_PRIMITIVE_IDS) == 22
    for primitive_id in CORE_PRIMITIVE_IDS:
        item = next(
            entry for entry in fixture["primitives"] if entry["primitive_id"] == primitive_id
        )
        spec = primitive_spec(primitive_id)
        assert item["answer_kinds"] == [kind.value for kind in spec.answer_kinds]
        assert item["a11y"]["keyboard"] is True
        assert item["a11y"]["screen_reader"] is True
        assert {"positive", "negative", "ambiguous", "not_evaluable"}.issubset(item["case_ids"])


def test_each_core_primitive_declares_its_reader_and_evidence_contract() -> None:
    from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS, primitive_spec

    for primitive_id in CORE_PRIMITIVE_IDS:
        spec = primitive_spec(primitive_id)
        assert spec.reader_adapter
        assert spec.evidence_format
        assert spec.correction_strategies
        assert spec.learning_operation in {
            "exposure",
            "recognition",
            "recall",
            "transformation",
            "comprehension",
            "production",
            "interaction",
            "repair",
        }


def test_fixture_payload_is_hash_locked_for_offline_replay() -> None:
    metadata = json.loads(FIXTURE_METADATA.read_text())

    assert metadata["network_dependencies"] == []
    assert metadata["payloads"]["primitives.json"] == (
        "sha256:" + hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    )


def test_definition_rejects_response_kind_outside_primitive_adapter_contract() -> None:
    from polyglot.modules.exercises.core.domain import AnswerKind, ExerciseDefinition

    with pytest.raises(DomainError) as rejected:
        ExerciseDefinition.published(
            definition_id=DEFINITION_ID,
            revision_id=REVISION_ID,
            revision_no=1,
            primitive_id="EX-DISC-04",
            response_kinds=(AnswerKind.TEXT,),
            language_certification_ids=(CERTIFICATION_ID,),
            modes=("functional_contrast",),
            target_weights=(("skill:contrast", 0.35),),
            correction_policy_id="policy:exact-choice:v1",
            hint_policy_id="policy:hints:v1",
            observation_policy_id="policy:observation:v1",
            accessibility_features=("keyboard", "screen_reader", "untimed"),
        )

    assert rejected.value.code is ErrorCode.ANSWER_SHAPE_INVALID


def test_answer_union_rejects_a_free_payload_and_preserves_raw_answer_immutably() -> None:
    from polyglot.modules.exercises.core.domain import Answer, AnswerKind, Attempt

    with pytest.raises(DomainError) as rejected:
        Answer.create(
            kind=AnswerKind.SINGLE_CHOICE,
            raw_value={"unconstrained": "payload"},
            input_method="keyboard",
            submitted_at=NOW,
        )

    answer = Answer.create(
        kind=AnswerKind.SINGLE_CHOICE,
        raw_value="choice-a",
        input_method="keyboard",
        submitted_at=NOW,
    )
    attempt = Attempt.start(
        instance=instance(),
        profile_id=PROFILE_ID,
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=FixedIds(ATTEMPT_ID),
    )
    submitted = attempt.submit(answer=answer, idempotency_key="submit-1")

    assert rejected.value.code is ErrorCode.ANSWER_SHAPE_INVALID
    assert attempt.answer is None
    assert submitted.answer == answer
    assert submitted.answer.raw_value == "choice-a"


def test_attempt_cycle_is_immutable_and_idempotent_for_the_same_submission() -> None:
    from polyglot.modules.exercises.core.domain import Answer, AnswerKind, AttemptStatus

    attempt = __import__(
        "polyglot.modules.exercises.core.domain", fromlist=["Attempt"]
    ).Attempt.start(
        instance=instance(),
        profile_id=PROFILE_ID,
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=FixedIds(ATTEMPT_ID),
    )
    answer = Answer.create(
        kind=AnswerKind.SINGLE_CHOICE,
        raw_value="choice-a",
        input_method="keyboard",
        submitted_at=NOW,
    )

    submitted = attempt.submit(answer=answer, idempotency_key="submit-1")
    replayed = submitted.submit(answer=answer, idempotency_key="submit-1")
    correcting = submitted.start_correction()

    assert attempt.status is AttemptStatus.DRAFT
    assert submitted.status is AttemptStatus.SUBMITTED
    assert replayed == submitted
    assert correcting.status is AttemptStatus.CORRECTING

    with pytest.raises(DomainError) as conflict:
        submitted.submit(answer=answer, idempotency_key="other-key")

    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

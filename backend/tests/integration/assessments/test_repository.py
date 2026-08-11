from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.assessments.application import (
    PrepareAssessment,
    ResolveAssessmentReview,
    SaveAssessmentResponse,
)
from polyglot.modules.assessments.domain import AssessmentModality
from polyglot.modules.assessments.persistence import SqlAssessmentService
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_ID, NOW, PROFILE_ID


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


class SequenceIds:
    def __init__(self) -> None:
        self.value = 100

    def new(self) -> UUID:
        self.value += 1
        return UUID(f"019feb34-0000-7000-8000-{self.value:012x}")


def uid(value: int) -> UUID:
    return UUID(f"019feb35-0000-7000-8000-{value:012x}")


def service(
    factory: async_sessionmaker[AsyncSession], clock: MutableClock
) -> SqlAssessmentService:
    return SqlAssessmentService(factory, clock=clock, id_generator=SequenceIds())


async def test_prepare_is_idempotent_frozen_and_hides_solutions(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_profile: UUID
) -> None:
    clock = MutableClock(NOW)
    assessments = service(runtime_factory, clock)
    command = PrepareAssessment(
        run_id=uid(1),
        modality=AssessmentModality.READING,
        seed="stable-seed",
        target_snapshot={"band": "assess_b1"},
    )

    first = await assessments.prepare(ACCOUNT_ID, seeded_profile, command, idempotency_key="p1")
    replay = await assessments.prepare(ACCOUNT_ID, seeded_profile, command, idempotency_key="p1")

    assert first == replay
    assert first.status == "prepared"
    assert len(first.sections[0].items) == 18
    assert all("accepted" not in item.prompt for item in first.sections[0].items)
    with pytest.raises(DomainError) as caught:
        await assessments.prepare(
            ACCOUNT_ID,
            seeded_profile,
            PrepareAssessment(
                run_id=uid(2),
                modality=AssessmentModality.READING,
                seed="different",
                target_snapshot={},
            ),
            idempotency_key="p1",
        )
    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_pause_resume_preserves_remaining_time_and_response_version(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_profile: UUID
) -> None:
    clock = MutableClock(NOW)
    assessments = service(runtime_factory, clock)
    run = await assessments.prepare(
        ACCOUNT_ID,
        seeded_profile,
        PrepareAssessment(uid(10), AssessmentModality.READING, "pause-seed", {}),
        idempotency_key="pause-prepare",
    )
    run = await assessments.start(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="start"
    )
    item = run.sections[0].items[0]
    run = await assessments.save_response(
        ACCOUNT_ID,
        run.run_id,
        item.item_id,
        SaveAssessmentResponse({"kind": "single_choice", "value": "A"}, 0),
        expected_version=run.version,
        idempotency_key="pause-answer",
    )
    clock.instant += timedelta(minutes=5)
    run = await assessments.pause(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="pause"
    )
    assert run.remaining_time_ms == 20 * 60 * 1000

    clock.instant += timedelta(hours=2)
    run = await assessments.resume(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="resume"
    )
    assert run.deadline_at == clock.instant + timedelta(minutes=20)
    assert run.sections[0].items[0].answer == {"kind": "single_choice", "value": "A"}
    assert run.sections[0].items[0].response_version == 1


async def test_reading_submission_scores_and_emits_only_reading_evidence(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_profile: UUID
) -> None:
    clock = MutableClock(NOW)
    assessments = service(runtime_factory, clock)
    run = await assessments.prepare(
        ACCOUNT_ID,
        seeded_profile,
        PrepareAssessment(uid(20), AssessmentModality.READING, "score-seed", {}),
        idempotency_key="score-prepare",
    )
    run = await assessments.start(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="score-start"
    )
    for item in run.sections[0].items:
        run = await assessments.save_response(
            ACCOUNT_ID,
            run.run_id,
            item.item_id,
            SaveAssessmentResponse(
                {
                    "kind": "single_choice",
                    "value": item.prompt["options"][0],
                },
                0,
            ),
            expected_version=run.version,
            idempotency_key=f"score-answer-{item.item_id}",
        )
    completed = await assessments.submit(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="submit"
    )
    replay = await assessments.submit(
        ACCOUNT_ID, run.run_id, expected_version=run.version, idempotency_key="submit"
    )

    assert completed.status == replay.status == "completed"
    assert completed.result is not None
    assert completed.result.status == "valid"
    assert completed.result.score == pytest.approx(1)
    async with runtime_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(ACCOUNT_ID)}
        )
        modalities = set(
            (
                await session.execute(
                    text(
                        "SELECT modality FROM assessments.assessment_evidence "
                        "WHERE assessment_run_id=:run"
                    ),
                    {"run": run.run_id},
                )
            ).scalars()
        )
    assert modalities == {"reading"}


async def test_writing_requires_review_and_oral_self_assessment_has_no_false_score(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_profile: UUID
) -> None:
    clock = MutableClock(datetime(2026, 8, 10, 9, tzinfo=UTC))
    assessments = service(runtime_factory, clock)
    writing = await assessments.prepare(
        ACCOUNT_ID,
        PROFILE_ID,
        PrepareAssessment(uid(30), AssessmentModality.WRITING, "write-seed", {}),
        idempotency_key="write-prepare",
    )
    writing = await assessments.start(
        ACCOUNT_ID, writing.run_id, expected_version=writing.version, idempotency_key="write-start"
    )
    for item in writing.sections[0].items:
        writing = await assessments.save_response(
            ACCOUNT_ID,
            writing.run_id,
            item.item_id,
            SaveAssessmentResponse({"kind": "text", "value": "Una risposta completa."}, 0),
            expected_version=writing.version,
            idempotency_key=f"write-answer-{item.item_id}",
        )
    writing = await assessments.submit(
        ACCOUNT_ID,
        writing.run_id,
        expected_version=writing.version,
        idempotency_key="write-submit",
    )
    assert writing.status == "review_required"
    assert writing.result is None
    reviewed = await assessments.resolve_review(
        ACCOUNT_ID,
        writing.run_id,
        ResolveAssessmentReview(
            "WRITING_RUBRIC_V0",
            {
                "task_achievement": 3,
                "coherence": 3,
                "grammar": 3,
                "range": 3,
                "lexis_register": 3,
            },
        ),
        expected_version=writing.version,
        idempotency_key="review",
    )
    assert reviewed.status == "completed"
    assert reviewed.result is not None and reviewed.result.band == "assess_b3"

    oral = await assessments.prepare(
        ACCOUNT_ID,
        PROFILE_ID,
        PrepareAssessment(uid(31), AssessmentModality.SPEAKING, "oral-seed", {}),
        idempotency_key="oral-prepare",
    )
    oral = await assessments.start(
        ACCOUNT_ID, oral.run_id, expected_version=oral.version, idempotency_key="oral-start"
    )
    oral = await assessments.submit(
        ACCOUNT_ID, oral.run_id, expected_version=oral.version, idempotency_key="oral-submit"
    )
    assert oral.status == "completed"
    assert oral.result is not None
    assert oral.result.status == "not_evaluable"
    assert oral.result.score is None and oral.result.band is None


async def test_listening_requires_declared_audio_capability_without_silent_fallback(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_profile: UUID
) -> None:
    clock = MutableClock(datetime(2026, 8, 10, 10, tzinfo=UTC))
    assessments = service(runtime_factory, clock)

    with pytest.raises(DomainError) as caught:
        await assessments.prepare(
            ACCOUNT_ID,
            PROFILE_ID,
            PrepareAssessment(uid(40), AssessmentModality.LISTENING, "audio-seed", {}),
            idempotency_key="audio-missing",
        )
    assert caught.value.code is ErrorCode.ASSESSMENT_UNAVAILABLE

    prepared = await assessments.prepare(
        ACCOUNT_ID,
        PROFILE_ID,
        PrepareAssessment(
            uid(41),
            AssessmentModality.LISTENING,
            "audio-ready-seed",
            {},
            capabilities=("tts",),
        ),
        idempotency_key="audio-ready",
    )
    assert prepared.status == "prepared"
    assert all(item.media_ref is not None for item in prepared.sections[0].items)

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.exercises.core.application import (
    ContestCorrection,
    CorrectAttempt,
    MarkCorrectionRead,
    OpenAttempt,
    ResolveCorrectionCase,
    SaveDraft,
    SubmitAttempt,
    UseHint,
)
from polyglot.modules.exercises.core.domain import (
    AnswerKind,
    CorrectionResult,
    HintLevel,
)
from polyglot.modules.exercises.core.persistence import SqlExerciseService
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import (
    ACCOUNT_ID,
    ATTEMPT_ID,
    INSTANCE_ID,
    NOW,
    PROFILE_ID,
    seed_attempt,
    uid,
)


async def test_open_save_and_hint_are_replayable_versioned_commands(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    await migration_session.execute(text("DELETE FROM exercises.exercise_attempts"))
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)

    opened = await service.open_attempt(
        ACCOUNT_ID,
        INSTANCE_ID,
        OpenAttempt(ATTEMPT_ID, PROFILE_ID, 1, NOW),
        idempotency_key="open-1",
    )
    assert opened.status == "draft"
    assert opened.version == 1
    assert await service.open_attempt(
        ACCOUNT_ID,
        INSTANCE_ID,
        OpenAttempt(ATTEMPT_ID, PROFILE_ID, 1, NOW),
        idempotency_key="open-1",
    ) == opened

    drafted = await service.save_draft(
        ACCOUNT_ID,
        ATTEMPT_ID,
        SaveDraft({"text": "bozza"}, NOW),
        expected_version=1,
        idempotency_key="draft-1",
    )
    assert drafted.version == 2
    assert await service.save_draft(
        ACCOUNT_ID,
        ATTEMPT_ID,
        SaveDraft({"text": "bozza"}, NOW),
        expected_version=1,
        idempotency_key="draft-1",
    ) == drafted

    hinted = await service.use_hint(
        ACCOUNT_ID,
        ATTEMPT_ID,
        UseHint(
            hint_use_id=uid(40),
            hint_definition_revision_id=uid(41),
            level=HintLevel.H1,
            reason="orientation",
            answer_state_checksum="c" * 64,
            effect_policy_revision_id=uid(42),
            shown_at=NOW,
        ),
        expected_version=2,
        idempotency_key="hint-1",
    )
    assert hinted.version == 3


async def test_submit_is_exactly_replayable_and_rejects_key_reuse(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)
    command = SubmitAttempt(
        kind=AnswerKind.SELF_GRADE,
        raw_value="good",
        input_method="keyboard",
        input_locale="it-IT",
        submitted_at=NOW,
    )

    first = await service.submit_attempt(
        ACCOUNT_ID,
        ATTEMPT_ID,
        command,
        expected_version=1,
        idempotency_key="submit-exact",
    )
    replay = await service.submit_attempt(
        ACCOUNT_ID,
        ATTEMPT_ID,
        command,
        expected_version=1,
        idempotency_key="submit-exact",
    )

    assert replay == first
    assert first.status == "submitted"
    assert first.raw_answer == "good"
    assert first.version == 2

    with pytest.raises(DomainError) as conflict:
        await service.submit_attempt(
            ACCOUNT_ID,
            ATTEMPT_ID,
            SubmitAttempt(
                kind=AnswerKind.SELF_GRADE,
                raw_value="easy",
                input_method="keyboard",
                input_locale="it-IT",
                submitted_at=NOW,
            ),
            expected_version=1,
            idempotency_key="submit-exact",
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_concurrent_double_submit_returns_one_frozen_result(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)
    command = SubmitAttempt(
        kind=AnswerKind.SELF_GRADE,
        raw_value="good",
        input_method="keyboard",
        input_locale="it-IT",
        submitted_at=NOW,
    )

    left, right = await asyncio.gather(
        service.submit_attempt(
            ACCOUNT_ID,
            ATTEMPT_ID,
            command,
            expected_version=1,
            idempotency_key="submit-concurrent",
        ),
        service.submit_attempt(
            ACCOUNT_ID,
            ATTEMPT_ID,
            command,
            expected_version=1,
            idempotency_key="submit-concurrent",
        ),
    )

    assert left == right
    assert left.version == 2


async def test_submit_requires_expected_version(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)

    with pytest.raises(DomainError) as conflict:
        await service.submit_attempt(
            ACCOUNT_ID,
            ATTEMPT_ID,
            SubmitAttempt(
                kind=AnswerKind.SELF_GRADE,
                raw_value="good",
                input_method="keyboard",
                input_locale="it-IT",
                submitted_at=NOW,
            ),
            expected_version=2,
            idempotency_key="submit-stale",
        )
    assert conflict.value.code is ErrorCode.VERSION_CONFLICT


async def test_correction_read_contest_and_review_preserve_revision_history(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    correction_id = uid(50)
    await migration_session.execute(
        text(
            "UPDATE exercises.exercise_attempts SET status='corrected',"
            "answer_kind='self_grade',raw_answer='\"good\"'::jsonb,input_method='keyboard',"
            "input_locale='it-IT',submitted_at=:now,corrected_at=:now,"
            "idempotency_key='seed-submit',request_fingerprint=:fingerprint,"
            "version=2,updated_at=:now WHERE attempt_id=:attempt"
        ),
        {"attempt": ATTEMPT_ID, "now": NOW, "fingerprint": "d" * 64},
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.exercise_corrections "
            "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,"
            "target_coverage,strategy,alternatives,explanation,error_codes,criterion_scores,"
            "provenance_id,requires_review,is_current,result_payload,created_at) VALUES "
            "(:correction,:attempt,:profile,1,'correct',1,1,'self_assessment','[]','valid',"
            "'[]','{}',:provenance,false,true,'{}',:now)"
        ),
        {
            "correction": correction_id,
            "attempt": ATTEMPT_ID,
            "profile": PROFILE_ID,
            "provenance": uid(51),
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at) VALUES (:account,'active',1,1,1,:now,:now)"
        ),
        {"account": uid(70), "now": NOW},
    )
    await migration_session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id,account_id,role,granted_at,granted_by_actor_id) VALUES "
            "(:grant,:account,'reviewer',:now,:account)"
        ),
        {"grant": uid(52), "account": uid(70), "now": NOW},
    )
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)

    reviewed = await service.mark_correction_read(
        ACCOUNT_ID,
        ATTEMPT_ID,
        MarkCorrectionRead(NOW),
        expected_version=2,
        idempotency_key="read-1",
    )
    assert reviewed.correction_reviewed_at == NOW
    assert reviewed.version == 3

    case_id = uid(53)
    case = await service.contest_correction(
        ACCOUNT_ID,
        ATTEMPT_ID,
        ContestCorrection(case_id, "meaning_disputed", "alternative valide", NOW),
        expected_version=3,
        idempotency_key="contest-1",
    )
    assert case.status == "contested"
    assert case.version == 1

    resolved = await service.resolve_correction_case(
        uid(70),
        case_id,
        ResolveCorrectionCase(uid(54), correction_id, "uphold", "correction confirmee", NOW),
        expected_version=1,
        idempotency_key="resolve-1",
    )
    assert resolved.status == "resolved"
    assert resolved.resolution_correction_id == correction_id
    assert resolved.version == 2


async def test_unavailable_correction_is_not_recorded_as_success(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_attempt(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id,account_id,role,granted_at,granted_by_actor_id) VALUES "
            "(:grant,:account,'worker',:now,:account)"
        ),
        {"grant": uid(60), "account": ACCOUNT_ID, "now": NOW},
    )
    await migration_session.commit()
    service = SqlExerciseService(runtime_factory)
    submitted = await service.submit_attempt(
        ACCOUNT_ID,
        ATTEMPT_ID,
        SubmitAttempt(
            AnswerKind.SELF_GRADE,
            "good",
            "keyboard",
            "it-IT",
            NOW,
        ),
        expected_version=1,
        idempotency_key="submit-before-correction",
    )

    corrected = await service.correct_attempt(
        ACCOUNT_ID,
        ATTEMPT_ID,
        CorrectAttempt(
            correction_id=uid(61),
            result=CorrectionResult.not_evaluable("corrector unavailable"),
            provenance_id=uid(62),
            rubric_revision_id=None,
            proposed_answer=None,
            requires_review=True,
            created_at=NOW,
        ),
        expected_version=submitted.version,
        idempotency_key="correct-unavailable",
    )

    assert corrected.status == "not_evaluable"
    assert corrected.terminal_reason == "correction_unavailable"

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from itertools import count

import pytest
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.progress.application import SqlProgressQueryService
from polyglot.modules.progress.domain import (
    DelayBand,
    EvidenceSource,
    HelpLevel,
    LearningObservation,
    Modality,
    ObservationResult,
    ObservationRole,
)
from polyglot.modules.progress.persistence import SqlProgressRepository
from polyglot.platform.clock import FrozenClock

from .conftest import (
    ACCOUNT_A,
    ACCOUNT_B,
    NOW,
    PROFILE_A,
    seed_corrected_attempt,
    seed_profiles,
    set_actor,
    uid,
)


class SequenceIdGenerator:
    def __init__(self) -> None:
        self._values = count(1000)

    def new(self):
        return uid(next(self._values))


async def _seed_progress_event(
    session: AsyncSession,
    *,
    event_id,
    attempt_id,
) -> None:
    await session.execute(
        text(
            "INSERT INTO platform.domain_events "
            "(event_id,event_type,schema_version,aggregate_type,aggregate_id,aggregate_version,"
            "actor_type,actor_id,profile_id,occurred_at,recorded_at,correlation_id,command_id,"
            "privacy_class,policy_versions,payload,expires_at,subject_type,subject_id) VALUES "
            "(:event,'exercise_attempt_corrected',1,'attempt',:attempt,:version,'account',:actor,:profile,"
            ":now,:now,:correlation,:command,'personal','{}','{}',:expires,'profile',:profile)"
        ),
        {
            "event": event_id,
            "attempt": attempt_id,
            "version": event_id.int % 1000 + 1,
            "actor": ACCOUNT_A,
            "profile": PROFILE_A,
            "now": NOW,
            "correlation": uid(event_id.int % 1000 + 5000),
            "command": uid(event_id.int % 1000 + 6000),
            "expires": NOW + timedelta(days=365),
        },
    )


def _observation(attempt_id, correction_id, *, profile_id=PROFILE_A, index=1, value=0.75):
    return LearningObservation(
        observation_id=uid(100 + index),
        profile_id=profile_id,
        attempt_id=attempt_id,
        correction_id=correction_id,
        target_type="grammar_structure",
        target_id="it.futuro-prossimo",
        facet_key="controlled-production",
        modality=Modality.WRITING,
        operation="transform",
        role=ObservationRole.PRIMARY,
        result=ObservationResult.SUCCESS if value > 0 else ObservationResult.FAILURE,
        observation_value=value,
        correction_confidence=1,
        target_coverage=1,
        help_level=HelpLevel.H0,
        opportunity_id=uid(200 + index),
        pedagogical_session_id=f"session-{index}",
        context_family_id=f"context-{index}",
        source=EvidenceSource.PLANNED_SPRINT,
        delay_band=DelayBand.SAME_SESSION,
        policy_revision_id="OBSERVATION_V0",
        created_at=NOW + timedelta(minutes=index),
    )


async def test_ingestion_persists_facts_projection_debt_and_recommendation(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, correction = await seed_corrected_attempt(migration_session)
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=1)),
    )

    result = await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=uid(300),
        observations=(_observation(attempt, correction, value=-0.75),),
    )

    assert result.processed is True
    assert result.projection_count == 1
    assert result.need_count == 1
    assert result.recommendation_count == 1

    async with runtime_factory() as session:
        await set_actor(session, ACCOUNT_A)
        projection = (
            await session.execute(
                text(
                    "SELECT status,success_count,failure_count FROM progress.mastery_projections "
                    "WHERE profile_id=:profile"
                ),
                {"profile": PROFILE_A},
            )
        ).one()
        assert projection == ("in_progress", 0, 1)


async def test_event_delivery_is_idempotent_and_rebuild_has_same_fingerprint(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, correction = await seed_corrected_attempt(migration_session)
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=1)),
    )
    observation = _observation(attempt, correction)

    first = await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=uid(301),
        observations=(observation,),
    )
    replay = await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=uid(301),
        observations=(observation,),
    )
    rebuilt = await repository.rebuild_profile(actor_id=ACCOUNT_A, profile_id=PROFILE_A)

    assert first.processed is True
    assert replay.processed is False
    assert rebuilt.fingerprint == first.fingerprint


async def test_runtime_rls_hides_another_profiles_progress(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_profiles(migration_session)
    async with runtime_factory() as session:
        await set_actor(session, ACCOUNT_B)
        with pytest.raises(NoResultFound):
            (
                await session.execute(
                    text(
                        "SELECT profile_id FROM progress.mastery_projections "
                        "WHERE profile_id=:profile"
                    ),
                    {"profile": PROFILE_A},
                )
            ).one()


async def test_correction_event_is_translated_into_targeted_observation(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, _ = await seed_corrected_attempt(migration_session)
    event_id = uid(350)
    await _seed_progress_event(migration_session, event_id=event_id, attempt_id=attempt)
    await migration_session.commit()
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=1)),
    )

    result = await repository.consume_event(actor_id=ACCOUNT_A, event_id=event_id)

    assert result.projection_count == 1
    async with runtime_factory() as session:
        await set_actor(session, ACCOUNT_A)
        observation = (
            await session.execute(
                text(
                    "SELECT target_type,target_id,modality,operation,observation_value "
                    "FROM progress.learning_observations WHERE profile_id=:profile"
                ),
                {"profile": PROFILE_A},
            )
        ).one()
        assert observation[:4] == (
            "grammar_structure",
            "it.futuro-prossimo",
            "writing",
            "transform",
        )
        assert float(observation[4]) == pytest.approx(0.65)


async def test_progress_query_returns_four_separate_axes_and_explanations(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, correction = await seed_corrected_attempt(migration_session)
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=1)),
    )
    await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=uid(360),
        observations=(_observation(attempt, correction, value=-0.75),),
    )
    query = SqlProgressQueryService(runtime_factory)

    overview = await query.get_overview(ACCOUNT_A, PROFILE_A, cursor=None, limit=10)
    recommendations = await query.list_recommendations(
        ACCOUNT_A,
        PROFILE_A,
        cursor=None,
        limit=10,
        as_of=NOW + timedelta(hours=1),
    )

    assert tuple(axis.modality for axis in overview.modalities) == (
        "reading",
        "listening",
        "writing",
        "speaking",
    )
    assert overview.has_global_score is False
    assert overview.modalities[0].score is None
    assert overview.modalities[2].score is not None
    assert len(overview.facets[0].evidence_ids) == 1
    assert recommendations.items[0].reason_code == "prerequisite_learning_need"
    assert len(recommendations.items[0].authorized_fact_ids) == 1


async def test_revised_correction_appends_invalidations_and_replaces_credit(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, first_correction = await seed_corrected_attempt(migration_session)
    first_event = uid(370)
    second_event = uid(371)
    second_correction = uid(372)
    await _seed_progress_event(migration_session, event_id=first_event, attempt_id=attempt)
    await migration_session.execute(
        text(
            "UPDATE exercises.exercise_corrections SET is_current=false "
            "WHERE correction_id=:correction"
        ),
        {"correction": first_correction},
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.exercise_corrections "
            "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,target_coverage,"
            "strategy,alternatives,explanation,error_codes,criterion_scores,provenance_id,"
            "requires_review,supersedes_correction_id,is_current,result_payload,created_at) VALUES "
            "(:correction,:attempt,:profile,2,'incorrect',1,1,'manual','[]','revised','[]','{}',"
            ":provenance,false,:first,true,'{}',:created)"
        ),
        {
            "correction": second_correction,
            "attempt": attempt,
            "profile": PROFILE_A,
            "provenance": uid(373),
            "first": first_correction,
            "created": NOW + timedelta(hours=1),
        },
    )
    await _seed_progress_event(migration_session, event_id=second_event, attempt_id=attempt)
    await migration_session.commit()
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=2)),
    )
    first = _observation(attempt, first_correction, index=1, value=0.75)
    second = replace(
        _observation(attempt, second_correction, index=2, value=-0.75),
        opportunity_id=first.opportunity_id,
    )

    await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=first_event,
        observations=(first,),
    )
    await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=second_event,
        observations=(second,),
    )

    async with runtime_factory() as session:
        await set_actor(session, ACCOUNT_A)
        assert (
            await session.scalar(text("SELECT count(*) FROM progress.learning_observations")) == 2
        )
        assert await session.scalar(text("SELECT count(*) FROM progress.learning_evidence")) == 2
        assert await session.scalar(text("SELECT count(*) FROM progress.fact_invalidations")) == 2
        projection = (
            await session.execute(
                text("SELECT success_count,failure_count FROM progress.mastery_projections")
            )
        ).one()
        assert projection == (0, 1)


async def test_lexical_evidence_updates_personal_sense_facet(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempt, correction = await seed_corrected_attempt(migration_session)
    repository = SqlProgressRepository(
        runtime_factory,
        id_generator=SequenceIdGenerator(),
        clock=FrozenClock(NOW + timedelta(hours=1)),
    )
    lexical = replace(
        _observation(attempt, correction),
        target_type="lexical_sense",
        target_id=str(uid(800)),
        facet_key="target_to_support",
        modality=Modality.READING,
        operation="recall",
    )

    await repository.ingest_observations(
        actor_id=ACCOUNT_A,
        event_id=uid(380),
        observations=(lexical,),
    )

    async with runtime_factory() as session:
        await set_actor(session, ACCOUNT_A)
        row = (
            await session.execute(
                text(
                    "SELECT sense_id,modality,direction,evidence_count "
                    "FROM progress.personal_sense_facets"
                )
            )
        ).one()
        assert row == (uid(800), "reading", "target_to_support", 1)

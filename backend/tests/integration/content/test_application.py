import asyncio
from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import database_url_from_environment
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import IDS, NOW, VARIETY_ID, seed_published_catalogue_reference


class AlwaysRecentAuthentication:
    async def is_recent(
        self, *, session: AsyncSession, actor_id: UUID, session_id: UUID, now: object
    ) -> bool:
        del session, actor_id, session_id, now
        return True


class NeverRecentAuthentication:
    async def is_recent(
        self, *, session: AsyncSession, actor_id: UUID, session_id: UUID, now: object
    ) -> bool:
        del session, actor_id, session_id, now
        return False


class FailAt:
    def __init__(self, stage: str) -> None:
        self._stage = stage

    async def checkpoint(self, stage: str) -> None:
        if stage == self._stage:
            raise RuntimeError(f"injected failure at {stage}")


def _actor(actor_id: UUID, *roles: str):
    from polyglot.modules.content.application import EditorialActor

    return EditorialActor(actor_id=actor_id, roles=frozenset(roles), session_id=IDS["session"])


def _context():
    from polyglot.modules.identity.application import RequestContext

    return RequestContext(
        request_id=IDS["event"],
        correlation_id=IDS["correlation"],
        truncated_ip="127.0.0.0/24",
        origin="https://polyglot.test",
    )


def _reference():
    from polyglot.modules.content.application import ContentReference

    return ContentReference(
        reference_kind="skill_revision",
        revision_id=IDS["catalogue_revision"],
    )


def _service(factory, *, failure_injector=None):
    from polyglot.modules.content.application import ContentApplicationService

    return ContentApplicationService(
        factory,
        clock=FrozenClock(NOW),
        reauthentication_policy=AlwaysRecentAuthentication(),
        failure_injector=failure_injector,
    )


@pytest.fixture
async def factory(migration_session: AsyncSession):
    await seed_published_catalogue_reference(migration_session)
    await migration_session.commit()
    engine = create_async_engine(database_url_from_environment())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _create(service, *, key: str = "create", payload=None, references=None):
    from polyglot.modules.content.application import CreateContentDraft

    return await service.create_draft(
        CreateContentDraft(
            actor=_actor(IDS["author"], "author"),
            content_type="dialogue",
            variety_id=VARIETY_ID,
            payload=payload or {"schema_version": 1, "text": "Ciao."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=tuple(references or (_reference(),)),
            idempotency_key=key,
            context=_context(),
        )
    )


async def _validate(service, result, *, key: str, expected_version: int | None = None):
    from polyglot.modules.content.application import ValidateContentRevision

    return await service.validate_revision(
        ValidateContentRevision(
            actor=_actor(IDS["author"], "author"),
            revision_id=result.revision.content_revision_id,
            validator_set_revision_id=IDS["validator_set"],
            expected_version=expected_version or result.version,
            idempotency_key=key,
            context=_context(),
        )
    )


async def _approve(service, result, *, key: str, actor_id: UUID | None = None):
    from polyglot.modules.content.application import ApproveContentRevision

    return await service.approve_revision(
        ApproveContentRevision(
            actor=_actor(actor_id or IDS["reviewer"], "reviewer"),
            revision_id=result.revision.content_revision_id,
            expected_version=result.version,
            decision="approved",
            reason_code="reviewed.complete",
            idempotency_key=key,
            context=_context(),
        )
    )


async def _decide(service, result, *, key: str, decision: str, actor_id: UUID | None = None):
    from polyglot.modules.content.application import ApproveContentRevision

    return await service.approve_revision(
        ApproveContentRevision(
            actor=_actor(actor_id or IDS["reviewer"], "reviewer"),
            revision_id=result.revision.content_revision_id,
            expected_version=result.version,
            decision=decision,
            reason_code=f"reviewed.{decision}",
            idempotency_key=key,
            context=_context(),
        )
    )


async def _publish(service, result, *, key: str, expected_version: int | None = None):
    from polyglot.modules.content.application import PublishContentRevision

    return await service.publish_revision(
        PublishContentRevision(
            actor=_actor(IDS["reviewer"], "reviewer"),
            revision_id=result.revision.content_revision_id,
            publication_provenance_id=IDS["publication_provenance"],
            channel_code="stable",
            compatibility_range=">=2.0.0,<2.1.0",
            expected_version=expected_version or result.version,
            idempotency_key=key,
            context=_context(),
        )
    )


async def test_six_commands_are_versioned_idempotent_and_emit_exact_events(factory) -> None:
    from polyglot.modules.content.application import (
        RetireContentRevision,
        ReviseContentDraft,
    )
    from polyglot.platform.persistence.models import domain_events, outbox_messages

    service = _service(factory)
    created = await _create(service)
    replayed = await _create(service)
    with pytest.raises(DomainError) as idempotency_conflict:
        await _create(service, payload={"schema_version": 1, "text": "Diverso."})

    revised = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=created.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Buongiorno."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=1,
            idempotency_key="revise",
            context=_context(),
        )
    )
    validated = await _validate(service, revised, key="validate")
    approved = await _approve(service, validated, key="approve")
    published = await _publish(service, approved, key="publish")
    retired = await service.retire_revision(
        RetireContentRevision(
            actor=_actor(IDS["reviewer"], "reviewer"),
            content_id=published.revision.content_id,
            revision_id=published.revision.content_revision_id,
            expected_version=published.version,
            idempotency_key="retire",
            context=_context(),
        )
    )

    assert created.version == 1 and created.revision.status == "draft"
    assert (
        replayed.replayed
        and replayed.revision.content_revision_id == created.revision.content_revision_id
    )
    assert idempotency_conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert [
        revised.version,
        validated.version,
        approved.version,
        published.version,
        retired.version,
    ] == [2, 3, 4, 5, 6]
    assert retired.revision.status == "retired"

    async with factory() as session:
        events = tuple(
            (
                await session.execute(
                    select(domain_events.c.event_type).order_by(
                        domain_events.c.aggregate_version
                    )
                )
            ).scalars()
        )
        assert events == (
            "content_draft_created",
            "content_draft_revised",
            "content_validated",
            "content_approved",
            "content_published",
            "content_retired",
        )
        assert await session.scalar(select(func.count()).select_from(outbox_messages)) == 6


async def test_self_approval_human_required_rights_provenance_and_references_are_blocking(
    factory,
) -> None:
    from polyglot.modules.content.application import CreateContentDraft

    service = _service(factory)
    human = await _create(
        service,
        key="human-create",
        payload={"schema_version": 1, "text": "Ciao.", "human_required": True},
    )
    human = await _validate(service, human, key="human-validate")
    with pytest.raises(DomainError) as not_validated:
        await _approve(service, human, key="human-approve")
    assert human.revision.status == "draft"
    assert not_validated.value.code is ErrorCode.INVALID_TRANSITION

    valid = await _create(service, key="self-create")
    valid = await _validate(service, valid, key="self-validate")
    with pytest.raises(DomainError) as self_approval:
        await _approve(service, valid, key="self-approve", actor_id=IDS["author"])
    assert self_approval.value.code is ErrorCode.SELF_APPROVAL_FORBIDDEN

    with pytest.raises(DomainError) as invalid_rights:
        await service.create_draft(
            replace(
                CreateContentDraft(
                    actor=_actor(IDS["author"], "author"),
                    content_type="dialogue",
                    variety_id=VARIETY_ID,
                    payload={"schema_version": 1, "text": "Ciao."},
                    provenance_id=IDS["provenance"],
                    rights_ref="unknown-license",
                    pinned_revision_refs=(_reference(),),
                    idempotency_key="bad-rights",
                    context=_context(),
                )
            )
        )
    assert invalid_rights.value.code is ErrorCode.LICENSE_MISSING

    from polyglot.modules.content.application import ContentReference

    missing_reference = await _create(
        service,
        key="missing-reference-create",
        references=(
            ContentReference(
                reference_kind="skill_revision",
                revision_id=IDS["replacement"],
            ),
        ),
    )
    missing_reference = await _approve(
        service,
        await _validate(service, missing_reference, key="missing-reference-validate"),
        key="missing-reference-approve",
    )
    with pytest.raises(DomainError) as invalid_reference:
        await _publish(service, missing_reference, key="bad-reference")
    assert invalid_reference.value.code is ErrorCode.REFERENCE_NOT_PUBLISHABLE


async def test_rejection_is_terminal_idempotent_and_emits_exactly_one_event(factory) -> None:
    from polyglot.modules.content.application import ReviseContentDraft
    from polyglot.modules.content.persistence import content_approval_decisions
    from polyglot.platform.persistence.models import domain_events, outbox_messages

    service = _service(factory)
    validated = await _validate(
        service,
        await _create(service, key="reject-create"),
        key="reject-validate",
    )
    rejected = await _decide(
        service, validated, key="reject-decision", decision="rejected"
    )
    replayed = await _decide(
        service, validated, key="reject-decision", decision="rejected"
    )

    with pytest.raises(DomainError) as conflict:
        await _decide(service, validated, key="reject-decision", decision="approved")
    with pytest.raises(DomainError) as cannot_publish:
        await _publish(service, rejected, key="reject-publish")
    with pytest.raises(DomainError) as self_rejection:
        other = await _validate(
            service,
            await _create(service, key="self-reject-create"),
            key="self-reject-validate",
        )
        await _decide(
            service,
            other,
            key="self-reject-decision",
            decision="rejected",
            actor_id=IDS["author"],
        )

    correction = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=rejected.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Versione corretta."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=rejected.version,
            idempotency_key="reject-revise",
            context=_context(),
        )
    )

    assert rejected.revision.status == "rejected"
    assert replayed.replayed and replayed.revision.status == "rejected"
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert cannot_publish.value.code is ErrorCode.INVALID_TRANSITION
    assert self_rejection.value.code is ErrorCode.SELF_APPROVAL_FORBIDDEN
    assert correction.revision.status == "draft"
    assert correction.revision.supersedes_revision_id == rejected.revision.content_revision_id

    async with factory() as session:
        decisions = (
            await session.execute(
                select(content_approval_decisions.c.decision).where(
                    content_approval_decisions.c.content_revision_id
                    == rejected.revision.content_revision_id
                )
            )
        ).scalars().all()
        rejected_events = await session.scalar(
            select(func.count())
            .select_from(domain_events)
            .where(domain_events.c.event_type == "content_rejected")
        )
        rejected_outbox = await session.scalar(
            select(func.count())
            .select_from(outbox_messages)
            .join(domain_events, domain_events.c.event_id == outbox_messages.c.event_id)
            .where(domain_events.c.event_type == "content_rejected")
        )
    assert decisions == ["rejected"]
    assert rejected_events == rejected_outbox == 1


async def test_failure_after_event_rolls_back_editorial_state_but_finishes_receipt(factory) -> None:
    from polyglot.modules.content.persistence import content_revisions, publication_manifests
    from polyglot.platform.persistence.models import (
        command_receipts,
        domain_events,
        outbox_messages,
    )

    normal = _service(factory)
    approved = await _approve(
        normal,
        await _validate(
            normal, await _create(normal, key="failure-create"), key="failure-validate"
        ),
        key="failure-approve",
    )
    failing = _service(factory, failure_injector=FailAt("after_event"))

    with pytest.raises(RuntimeError, match="injected failure"):
        await _publish(failing, approved, key="failure-publish")

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(publication_manifests)) == 0
        assert (
            await session.scalar(
                select(content_revisions.c.status).where(
                    content_revisions.c.content_revision_id == approved.revision.content_revision_id
                )
            )
            == "approved"
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(domain_events)
                .where(domain_events.c.event_type == "content_published")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(outbox_messages)
                .join(domain_events, domain_events.c.event_id == outbox_messages.c.event_id)
                .where(domain_events.c.event_type == "content_published")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(command_receipts.c.status).where(
                    command_receipts.c.idempotency_key == "failure-publish"
                )
            )
            == "failed"
        )


async def test_spk_publish_serializes_two_first_publications_on_aggregate_lock(factory) -> None:
    from polyglot.modules.content.application import ReviseContentDraft
    from polyglot.modules.content.persistence import publication_manifests
    from polyglot.platform.persistence.models import domain_events

    service = _service(factory)
    first = await _approve(
        service,
        await _validate(service, await _create(service, key="race-create"), key="race-validate"),
        key="race-approve-first",
    )
    second = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=first.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Seconda."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=first.version,
            idempotency_key="race-revise",
            context=_context(),
        )
    )
    second = await _approve(
        service,
        await _validate(service, second, key="race-validate-second"),
        key="race-approve-second",
    )

    results = await asyncio.gather(
        _publish(
            _service(factory), first, key="race-publish-first", expected_version=second.version
        ),
        _publish(
            _service(factory), second, key="race-publish-second", expected_version=second.version
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(item, Exception) for item in results) == 1
    loser = next(item for item in results if isinstance(item, DomainError))
    assert loser.code is ErrorCode.VERSION_CONFLICT
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(publication_manifests)
                .where(publication_manifests.c.retired_at.is_(None))
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(domain_events)
                .where(domain_events.c.event_type == "content_published")
            )
            == 1
        )


async def test_replacement_manifest_and_historical_read_preserve_complete_evidence(factory) -> None:
    from polyglot.modules.content.application import RetireContentRevision, ReviseContentDraft
    from polyglot.modules.content.persistence import (
        SqlContentRepository,
        publication_manifest_entries,
    )

    service = _service(factory)
    first = await _publish(
        service,
        await _approve(
            service,
            await _validate(
                service, await _create(service, key="history-create"), key="history-validate"
            ),
            key="history-approve",
        ),
        key="history-publish",
    )
    async with factory() as session:
        repository = SqlContentRepository(session)
        await repository.record_historical_reference(
            reference_id=IDS["history"],
            content_revision_id=first.revision.content_revision_id,
            usage_type="exercise_instance",
            usage_ref="exercise:019fe003",
            context_checksum="e" * 64,
            now=NOW,
        )
        await session.commit()

    second = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=first.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Salve."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=first.version,
            idempotency_key="history-revise",
            context=_context(),
        )
    )
    second = await _publish(
        service,
        await _approve(
            service,
            await _validate(service, second, key="history-validate-second"),
            key="history-approve-second",
        ),
        key="history-publish-second",
    )
    await service.retire_revision(
        RetireContentRevision(
            actor=_actor(IDS["reviewer"], "reviewer"),
            content_id=second.revision.content_id,
            revision_id=second.revision.content_revision_id,
            expected_version=second.version,
            idempotency_key="history-retire",
            context=_context(),
        )
    )

    async with factory() as session:
        stored = await SqlContentRepository(session).get_historical_revision(
            first.revision.content_revision_id
        )
        entry = (
            (await session.execute(select(publication_manifest_entries).limit(1))).mappings().one()
        )
    assert stored.status == "superseded"
    assert stored.payload_checksum and stored.provenance_id == IDS["provenance"]
    assert stored.rights_ref == "rights:fixture:content"
    assert stored.pinned_revision_refs
    assert entry["reference_checksum"]
    assert entry["reference_provenance_id"] == IDS["provenance"]
    assert entry["reference_rights_ref"] == "CC-BY-4.0"


async def test_create_round_trips_the_requested_content_type(factory) -> None:
    from polyglot.modules.content.application import CreateContentDraft
    from polyglot.modules.content.persistence import content_items

    service = _service(factory)
    created = await service.create_draft(
        CreateContentDraft(
            actor=_actor(IDS["author"], "author"),
            content_type="grammar_note",
            variety_id=VARIETY_ID,
            payload={"schema_version": 1, "text": "Il futuro prossimo."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            idempotency_key="content-type",
            context=_context(),
        )
    )

    async with factory() as session:
        stored_type = await session.scalar(
            select(content_items.c.content_type).where(
                content_items.c.content_id == created.revision.content_id
            )
        )

    assert stored_type == "grammar_note"


async def test_publish_requires_recent_reauthentication_without_partial_effects(factory) -> None:
    from polyglot.modules.content.application import ContentApplicationService
    from polyglot.modules.content.persistence import publication_manifests
    from polyglot.platform.persistence.models import domain_events

    normal = _service(factory)
    approved = await _approve(
        normal,
        await _validate(
            normal, await _create(normal, key="reauth-create"), key="reauth-validate"
        ),
        key="reauth-approve",
    )
    expired = ContentApplicationService(
        factory,
        clock=FrozenClock(NOW),
        reauthentication_policy=NeverRecentAuthentication(),
    )

    with pytest.raises(DomainError) as rejected:
        await _publish(expired, approved, key="reauth-publish")

    assert rejected.value.code is ErrorCode.UNAUTHENTICATED
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(publication_manifests)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(domain_events)
                .where(domain_events.c.event_type == "content_published")
            )
            == 0
        )


async def test_empty_database_acceptance_flow_preserves_first_published_revision(factory) -> None:
    from polyglot.modules.content.application import RetireContentRevision, ReviseContentDraft
    from polyglot.modules.content.persistence import SqlContentRepository

    service = _service(factory)
    invalid = await _create(
        service,
        key="accept-create",
        payload={"schema_version": 1, "text": "Da correggere.", "blocking": True},
    )
    failed = await _validate(service, invalid, key="accept-validate-failed")
    assert failed.revision.status == "draft"

    corrected = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=failed.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Versione corretta."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=failed.version,
            idempotency_key="accept-revise-first",
            context=_context(),
        )
    )
    rejected = await _decide(
        service,
        await _validate(service, corrected, key="accept-validate-green"),
        key="accept-reject",
        decision="rejected",
    )
    approved_correction = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=rejected.revision.content_revision_id,
            payload={
                "schema_version": 1,
                "text": "Versione approvata dopo revisione.",
            },
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=rejected.version,
            idempotency_key="accept-revise-after-rejection",
            context=_context(),
        )
    )
    first = await _publish(
        service,
        await _approve(
            service,
            await _validate(
                service,
                approved_correction,
                key="accept-validate-after-rejection",
            ),
            key="accept-approve-first",
        ),
        key="accept-publish-first",
    )
    async with factory() as session:
        await SqlContentRepository(session).record_historical_reference(
            reference_id=IDS["history"],
            content_revision_id=first.revision.content_revision_id,
            usage_type="exercise_instance",
            usage_ref="FX-CONTENT/acceptance",
            context_checksum="e" * 64,
            now=NOW,
        )
        await session.commit()

    replacement = await service.revise_draft(
        ReviseContentDraft(
            actor=_actor(IDS["author"], "author"),
            revision_id=first.revision.content_revision_id,
            payload={"schema_version": 1, "text": "Versione sostitutiva."},
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=(_reference(),),
            expected_version=first.version,
            idempotency_key="accept-revise-replacement",
            context=_context(),
        )
    )
    replacement = await _publish(
        service,
        await _approve(
            service,
            await _validate(service, replacement, key="accept-validate-replacement"),
            key="accept-approve-replacement",
        ),
        key="accept-publish-replacement",
    )
    retired = await service.retire_revision(
        RetireContentRevision(
            actor=_actor(IDS["reviewer"], "reviewer"),
            content_id=replacement.revision.content_id,
            revision_id=replacement.revision.content_revision_id,
            expected_version=replacement.version,
            idempotency_key="accept-retire",
            context=_context(),
        )
    )

    history = await service.get_history(
        actor=_actor(IDS["reviewer"], "reviewer"),
        content_id=retired.revision.content_id,
        limit=10,
        cursor=None,
    )
    async with factory() as session:
        historical = await SqlContentRepository(session).get_historical_revision(
            first.revision.content_revision_id
        )

    assert retired.revision.status == "retired"
    assert historical.status == "superseded"
    assert historical.payload["text"] == "Versione approvata dopo revisione."
    assert {revision.status for revision in history.items} >= {
        "draft",
        "rejected",
        "superseded",
        "retired",
    }

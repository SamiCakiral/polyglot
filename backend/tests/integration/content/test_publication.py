from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import IDS, NOW, VARIETY_ID, seed_provenance


async def test_migration_enforces_immutable_published_revisions_and_single_active_publication(
    session: AsyncSession,
) -> None:
    from polyglot.modules.content.persistence import (
        content_items,
        content_revisions,
        publication_manifests,
    )

    await seed_provenance(session)
    await session.execute(
        content_items.insert().values(
            content_id=IDS["content"],
            content_type="dialogue",
            variety_id=VARIETY_ID,
            editorial_owner_id=IDS["author"],
            lineage_root_id=IDS["content"],
            parent_content_id=None,
            version=2,
            created_at=NOW,
        )
    )
    await session.execute(
        content_revisions.insert().values(
            content_revision_id=IDS["revision"],
            content_id=IDS["content"],
            revision_no=1,
            schema_version=1,
            payload={"schema_version": 1, "text": "Ciao."},
            payload_checksum="b" * 64,
            provenance_id=IDS["provenance"],
            rights_ref="rights:fixture:content",
            pinned_revision_refs=[],
            created_by_actor_id=IDS["author"],
            approved_by_actor_id=IDS["reviewer"],
            status="published",
            channel_code="stable",
            compatibility_range=">=2.0.0,<2.1.0",
            supersedes_revision_id=None,
            created_at=NOW,
            validated_at=NOW,
            approved_at=NOW,
            published_at=NOW,
            retired_at=None,
        )
    )
    await session.execute(
        publication_manifests.insert().values(
            publication_manifest_id=IDS["manifest"],
            content_id=IDS["content"],
            content_revision_id=IDS["revision"],
            channel_code="stable",
            compatibility_range=">=2.0.0,<2.1.0",
            checksum="c" * 64,
            provenance_id=IDS["provenance"],
            published_at=NOW,
            retired_at=None,
        )
    )
    await session.commit()

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await session.execute(
            content_revisions.update()
            .where(content_revisions.c.content_revision_id == IDS["revision"])
            .values(payload={"schema_version": 1, "text": "Ciao, Luca."})
        )
    await session.rollback()

    with pytest.raises(IntegrityError):
        await session.execute(
            publication_manifests.insert().values(
                publication_manifest_id=IDS["history"],
                content_id=IDS["content"],
                content_revision_id=IDS["revision"],
                channel_code="stable",
                compatibility_range=">=2.0.0,<2.1.0",
                checksum="d" * 64,
                provenance_id=IDS["provenance"],
                published_at=NOW + timedelta(seconds=1),
                retired_at=None,
            )
        )
    await session.rollback()


async def test_publish_writes_manifest_event_and_outbox_in_one_transaction(
    session: AsyncSession,
) -> None:
    from polyglot.modules.content.persistence import SqlContentPublicationRepository
    from polyglot.platform.persistence.models import domain_events, outbox_messages

    await seed_provenance(session)
    repository = SqlContentPublicationRepository(session)
    await repository.create_approved_revision(
        content_id=IDS["content"],
        content_revision_id=IDS["revision"],
        variety_id=VARIETY_ID,
        author_id=IDS["author"],
        reviewer_id=IDS["reviewer"],
        provenance_id=IDS["provenance"],
        payload={"schema_version": 1, "text": "Ciao."},
        rights_ref="rights:fixture:content",
        now=NOW,
    )

    published = await repository.publish(
        content_id=IDS["content"],
        content_revision_id=IDS["revision"],
        actor_id=IDS["reviewer"],
        command_id=IDS["command"],
        correlation_id=IDS["correlation"],
        event_id=IDS["event"],
        manifest_id=IDS["manifest"],
        channel_code="stable",
        compatibility_range=">=2.0.0,<2.1.0",
        now=NOW,
    )
    await session.commit()

    assert published.status == "published"
    assert await session.scalar(
        select(func.count()).select_from(domain_events).where(
            domain_events.c.event_type == "content_published"
        )
    ) == 1
    assert await session.scalar(
        select(func.count()).select_from(outbox_messages).where(
            outbox_messages.c.event_id == IDS["event"]
        )
    ) == 1


async def test_historical_reference_resolves_retired_revision_without_rewriting_it(
    session: AsyncSession,
) -> None:
    from polyglot.modules.content.persistence import SqlContentPublicationRepository

    await seed_provenance(session)
    repository = SqlContentPublicationRepository(session)
    await repository.create_approved_revision(
        content_id=IDS["content"],
        content_revision_id=IDS["revision"],
        variety_id=VARIETY_ID,
        author_id=IDS["author"],
        reviewer_id=IDS["reviewer"],
        provenance_id=IDS["provenance"],
        payload={"schema_version": 1, "text": "Ciao."},
        rights_ref="rights:fixture:content",
        now=NOW,
    )
    await repository.publish(
        content_id=IDS["content"],
        content_revision_id=IDS["revision"],
        actor_id=IDS["reviewer"],
        command_id=IDS["command"],
        correlation_id=IDS["correlation"],
        event_id=IDS["event"],
        manifest_id=IDS["manifest"],
        channel_code="stable",
        compatibility_range=">=2.0.0,<2.1.0",
        now=NOW,
    )
    await repository.record_historical_reference(
        reference_id=IDS["history"],
        content_revision_id=IDS["revision"],
        usage_type="fixture_usage",
        usage_ref="fixture:historical",
        context_checksum="e" * 64,
        now=NOW,
    )
    await repository.retire(
        content_revision_id=IDS["revision"],
        now=NOW + timedelta(seconds=1),
    )
    await session.commit()

    revision = await repository.get_historical_revision(IDS["revision"])

    assert revision.status == "retired"
    assert revision.payload == {"schema_version": 1, "text": "Ciao."}

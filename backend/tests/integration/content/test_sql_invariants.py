import pytest
from sqlalchemy import Table, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import IDS, NOW, VARIETY_ID, seed_provenance


async def _insert_draft(session: AsyncSession) -> None:
    from polyglot.modules.content.persistence import content_items, content_revisions

    await seed_provenance(session)
    await session.execute(
        content_items.insert().values(
            content_id=IDS["content"],
            content_type="dialogue",
            variety_id=VARIETY_ID,
            editorial_owner_id=IDS["author"],
            lineage_root_id=IDS["content"],
            parent_content_id=None,
            version=1,
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
            approved_by_actor_id=None,
            status="draft",
            channel_code=None,
            compatibility_range=None,
            supersedes_revision_id=None,
            created_at=NOW,
            validated_at=None,
            approved_at=None,
            published_at=None,
            retired_at=None,
        )
    )


async def test_revision_insert_and_updates_cannot_skip_cycle_or_self_approve(
    migration_session: AsyncSession,
) -> None:
    from polyglot.modules.content.persistence import content_revisions

    await _insert_draft(migration_session)
    await migration_session.commit()

    with pytest.raises(DBAPIError, match="invalid content revision transition"):
        await migration_session.execute(
            content_revisions.update()
            .where(content_revisions.c.content_revision_id == IDS["revision"])
            .values(
                status="approved",
                approved_by_actor_id=IDS["author"],
                validated_at=NOW,
                approved_at=NOW,
            )
        )
    await migration_session.rollback()

    values = dict(
        (
            await migration_session.execute(
                select(content_revisions).where(
                    content_revisions.c.content_revision_id == IDS["revision"]
                )
            )
        )
        .mappings()
        .one()
    )
    values["content_revision_id"] = IDS["replacement"]
    values["revision_no"] = 2
    values["status"] = "approved"
    values["approved_by_actor_id"] = IDS["reviewer"]
    values["validated_at"] = NOW
    values["approved_at"] = NOW
    with pytest.raises(DBAPIError, match="new content revision must be draft"):
        await migration_session.execute(content_revisions.insert().values(**values))
    await migration_session.rollback()


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_revision_payload_is_immutable_from_insertion(
    migration_session: AsyncSession,
    operation: str,
) -> None:
    from polyglot.modules.content.persistence import content_revisions

    await _insert_draft(migration_session)
    await migration_session.commit()

    statement = (
        content_revisions.update()
        .where(content_revisions.c.content_revision_id == IDS["revision"])
        .values(payload={"schema_version": 1, "text": "Riscritto."})
        if operation == "update"
        else content_revisions.delete().where(
            content_revisions.c.content_revision_id == IDS["revision"]
        )
    )
    with pytest.raises(DBAPIError, match="content revision is immutable"):
        await migration_session.execute(statement)
    await migration_session.rollback()


async def _insert_complete_audit_chain(session: AsyncSession) -> tuple[Table, ...]:
    from polyglot.modules.content.persistence import (
        content_approval_decisions,
        content_revisions,
        historical_content_references,
        publication_manifest_entries,
        publication_manifests,
        validation_findings,
        validation_reports,
    )

    await _insert_draft(session)
    await session.execute(
        content_revisions.update()
        .where(content_revisions.c.content_revision_id == IDS["revision"])
        .values(status="validating")
    )
    await session.execute(
        validation_reports.insert().values(
            report_id=IDS["report"],
            subject_revision_id=IDS["revision"],
            validator_set_revision_id=IDS["validator_set"],
            status="passed",
            started_at=NOW,
            completed_at=NOW,
            summary_checksum="c" * 64,
        )
    )
    await session.execute(
        validation_findings.insert().values(
            finding_id=IDS["finding"],
            report_id=IDS["report"],
            ordinal=1,
            validator_code="fixture.structure",
            severity="information",
            path="$.text",
            message_code="fixture.ok",
            redacted_value=None,
            resolved_by_revision_id=None,
        )
    )
    await session.execute(
        content_revisions.update()
        .where(content_revisions.c.content_revision_id == IDS["revision"])
        .values(status="validated", validated_at=NOW)
    )
    await session.execute(
        content_approval_decisions.insert().values(
            approval_decision_id=IDS["decision"],
            content_revision_id=IDS["revision"],
            author_id=IDS["author"],
            reviewer_id=IDS["reviewer"],
            decision="approved",
            reason_code="fixture.reviewed",
            decided_at=NOW,
        )
    )
    await session.execute(
        content_revisions.update()
        .where(content_revisions.c.content_revision_id == IDS["revision"])
        .values(
            status="approved",
            approved_by_actor_id=IDS["reviewer"],
            approved_at=NOW,
        )
    )
    await session.execute(
        publication_manifests.insert().values(
            publication_manifest_id=IDS["manifest"],
            content_id=IDS["content"],
            content_revision_id=IDS["revision"],
            channel_code="stable",
            compatibility_range=">=2.0.0,<2.1.0",
            checksum="d" * 64,
            provenance_id=IDS["provenance"],
            published_at=NOW,
            retired_at=None,
        )
    )
    await session.execute(
        publication_manifest_entries.insert().values(
            publication_manifest_id=IDS["manifest"],
            ordinal=1,
            referenced_revision_id=IDS["catalogue_revision"],
            reference_kind="skill_revision",
            reference_checksum="f" * 64,
            reference_provenance_id=IDS["provenance"],
            reference_rights_ref="CC-BY-4.0",
            reference_status="published",
        )
    )
    await session.execute(
        content_revisions.update()
        .where(content_revisions.c.content_revision_id == IDS["revision"])
        .values(
            status="published",
            channel_code="stable",
            compatibility_range=">=2.0.0,<2.1.0",
            published_at=NOW,
        )
    )
    await session.execute(
        historical_content_references.insert().values(
            reference_id=IDS["history"],
            content_revision_id=IDS["revision"],
            usage_type="fixture_usage",
            usage_ref="fixture:historical",
            context_checksum="e" * 64,
            recorded_at=NOW,
        )
    )
    return (
        validation_reports,
        validation_findings,
        content_approval_decisions,
        publication_manifests,
        publication_manifest_entries,
        historical_content_references,
    )


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_audit_proofs_are_append_only(
    migration_session: AsyncSession,
    operation: str,
) -> None:
    tables = await _insert_complete_audit_chain(migration_session)
    await migration_session.commit()

    for table in tables:
        primary_key = next(iter(table.primary_key.columns))
        value = await migration_session.scalar(select(primary_key).limit(1))
        statement = (
            table.update().where(primary_key == value).values(**{primary_key.name: value})
            if operation == "update"
            else table.delete().where(primary_key == value)
        )
        with pytest.raises(DBAPIError, match="append-only"):
            await migration_session.execute(statement)
        await migration_session.rollback()

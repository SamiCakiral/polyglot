from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.language_profiles.domain import (
    LanguageProfileStatus,
    LearnerLanguageProfile,
    LearningPhase,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.persistence.models import metadata


def _table(name: str, *columns: Any) -> Table:
    return Table(name, metadata, *columns, schema="language_profiles")


learner_language_profiles = _table(
    "learner_language_profiles",
    Column("profile_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id"),
        nullable=False,
    ),
    Column("target_variety_id", PG_UUID(as_uuid=True), nullable=False),
    Column("native_variety_id", PG_UUID(as_uuid=True), nullable=False),
    Column("status", String(24), nullable=False),
    Column("current_phase", String(24), nullable=False),
    Column("goals", JSONB, nullable=False),
    Column("interests", JSONB, nullable=False),
    Column("excluded_themes", JSONB, nullable=False),
    Column("correction_preference", JSONB, nullable=False),
    Column("availability_pattern", JSONB, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
)
support_language_authorizations = _table(
    "support_language_authorizations",
    Column("authorization_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "profile_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.learner_language_profiles.profile_id"),
        nullable=False,
    ),
    Column("variety_id", PG_UUID(as_uuid=True), nullable=False),
    Column("authorized_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
)
declared_language_experiences = _table(
    "declared_language_experiences",
    Column("experience_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "profile_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.learner_language_profiles.profile_id"),
        nullable=False,
    ),
    Column("variety_id", PG_UUID(as_uuid=True), nullable=False),
    Column("declared_level", String(120)),
    Column("years_experience", Numeric(6, 2)),
    Column("notes", String),
    Column("declared_at", DateTime(timezone=True), nullable=False),
    Column("superseded_at", DateTime(timezone=True)),
)
diagnostic_runs = _table(
    "diagnostic_runs",
    Column("diagnostic_run_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "profile_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.learner_language_profiles.profile_id"),
        nullable=False,
    ),
    Column("policy_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("pack_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("status", String(24), nullable=False),
    Column("seed", String(255), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("classification", String(24)),
    Column("confidence", Numeric(5, 4)),
    Column("stop_reason", String(120)),
    Column("version", Integer, nullable=False),
)
diagnostic_responses = _table(
    "diagnostic_responses",
    Column("response_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "diagnostic_run_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.diagnostic_runs.diagnostic_run_id"),
        nullable=False,
    ),
    Column("item_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("answer", JSONB, nullable=False),
    Column("score", Numeric(5, 4)),
    Column("confidence", Numeric(5, 4)),
    Column("evaluable", Boolean, nullable=False),
    Column("revealed", Boolean, nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
)
foundation_runs = _table(
    "foundation_runs",
    Column("foundation_run_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "profile_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.learner_language_profiles.profile_id"),
        nullable=False,
    ),
    Column("pack_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("foundation_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("status", String(24), nullable=False),
    Column("seed", String(255), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
)
foundation_run_blocks = _table(
    "foundation_run_blocks",
    Column("foundation_run_block_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "foundation_run_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.foundation_runs.foundation_run_id"),
        nullable=False,
    ),
    Column("block_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("block_code", String(120), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("session_id", PG_UUID(as_uuid=True)),
    Column("result", JSONB),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
)
foundation_gate_results = _table(
    "foundation_gate_results",
    Column("gate_result_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "foundation_run_id",
        PG_UUID(as_uuid=True),
        ForeignKey("language_profiles.foundation_runs.foundation_run_id"),
        nullable=False,
    ),
    Column("gate_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("coverage", Numeric(5, 4), nullable=False),
    Column("confidence", Numeric(5, 4), nullable=False),
    Column("reasons", JSONB, nullable=False),
    Column("details", JSONB, nullable=False),
    Column("waiver_reason", String(120)),
    Column("waiver_evidence_ids", ARRAY(PG_UUID(as_uuid=True)), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
)


def _profile_from_row(row: Mapping[str, object]) -> LearnerLanguageProfile:
    return LearnerLanguageProfile(
        profile_id=cast(UUID, row["profile_id"]),
        account_id=cast(UUID, row["account_id"]),
        target_variety_id=cast(UUID, row["target_variety_id"]),
        native_variety_id=cast(UUID, row["native_variety_id"]),
        status=LanguageProfileStatus(cast(str, row["status"])),
        current_phase=LearningPhase(cast(str, row["current_phase"])),
        goals=tuple(cast(list[str], row["goals"])),
        interests=tuple(cast(list[str], row["interests"])),
        excluded_themes=tuple(cast(list[str], row["excluded_themes"])),
        version=cast(int, row["version"]),
        created_at=cast(datetime, row["created_at"]),
        updated_at=cast(datetime, row["updated_at"]),
        archived_at=cast(datetime | None, row["archived_at"]),
        deleted_at=cast(datetime | None, row["deleted_at"]),
    )


class SqlLanguageProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_actor(self, account_id: UUID) -> None:
        await self._session.execute(
            text("SELECT set_config('app.user_id', :account_id, true)"),
            {"account_id": str(account_id)},
        )

    async def add(self, profile: LearnerLanguageProfile) -> None:
        await self.set_actor(profile.account_id)
        await self._session.execute(
            learner_language_profiles.insert().values(
                profile_id=profile.profile_id,
                account_id=profile.account_id,
                target_variety_id=profile.target_variety_id,
                native_variety_id=profile.native_variety_id,
                status=profile.status.value,
                current_phase=profile.current_phase.value,
                goals=list(profile.goals),
                interests=list(profile.interests),
                excluded_themes=list(profile.excluded_themes),
                correction_preference={},
                availability_pattern={},
                version=profile.version,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
                archived_at=profile.archived_at,
                deleted_at=profile.deleted_at,
            )
        )

    async def get_owned(self, profile_id: UUID, account_id: UUID) -> LearnerLanguageProfile:
        await self.set_actor(account_id)
        row = (
            (
                await self._session.execute(
                    select(learner_language_profiles).where(
                        learner_language_profiles.c.profile_id == profile_id,
                        learner_language_profiles.c.account_id == account_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return _profile_from_row(cast(Mapping[str, object], row))

    async def update(self, profile: LearnerLanguageProfile) -> None:
        await self.set_actor(profile.account_id)
        changed = await self._session.scalar(
            learner_language_profiles.update()
            .where(
                learner_language_profiles.c.profile_id == profile.profile_id,
                learner_language_profiles.c.account_id == profile.account_id,
                learner_language_profiles.c.version == profile.version - 1,
            )
            .values(
                status=profile.status.value,
                current_phase=profile.current_phase.value,
                goals=list(profile.goals),
                interests=list(profile.interests),
                excluded_themes=list(profile.excluded_themes),
                version=profile.version,
                updated_at=profile.updated_at,
                archived_at=profile.archived_at,
                deleted_at=profile.deleted_at,
            )
            .returning(learner_language_profiles.c.profile_id)
        )
        if changed is None:
            raise DomainError(ErrorCode.VERSION_CONFLICT)

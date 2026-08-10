from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.curriculum.application import (
    CompleteEnrollment,
    EnrollInModule,
    EnrollmentView,
    ModuleSummary,
    PauseEnrollment,
)
from polyglot.modules.curriculum.bindings import CurriculumError
from polyglot.modules.curriculum.enrollment import EnrollmentStatus, ModuleEnrollment
from polyglot.modules.identity.application import RequestContext
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt, DomainEvent
from polyglot.platform.persistence.repositories import (
    SqlCommandReceiptStore,
    SqlEventOutboxRepository,
)

RECEIPT_RETENTION = timedelta(hours=24)
EVENT_RETENTION = timedelta(days=3650)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _enrollment(row: RowMapping) -> EnrollmentView:
    return EnrollmentView(
        enrollment_id=_uuid(row["enrollment_id"]),
        profile_id=_uuid(row["profile_id"]),
        module_revision_id=_uuid(row["module_revision_id"]),
        module_code=str(row["module_code"]),
        nominal_days=int(row["nominal_days"]),
        max_days=int(row["max_days"]),
        status=str(row["status"]),
        current_day_ordinal=int(row["current_day_ordinal"]),
        started_on_pedagogical_day=row["started_on_pedagogical_day"],
        completed_at=row["completed_at"],
        terminal_at=row["terminal_at"],
        paused_at=row["paused_at"],
        waiver_refs=tuple(str(item) for item in row["waiver_refs"]),
        migration_map_revision_id=(
            None
            if row["migration_map_revision_id"] is None
            else _uuid(row["migration_map_revision_id"])
        ),
        version=int(row["version"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _aggregate(view: EnrollmentView) -> ModuleEnrollment:
    return ModuleEnrollment(
        enrollment_id=view.enrollment_id,
        profile_id=view.profile_id,
        module_revision_id=view.module_revision_id,
        nominal_days=view.nominal_days,
        max_days=view.max_days,
        status=EnrollmentStatus(view.status),
        current_day_ordinal=view.current_day_ordinal,
        started_on_pedagogical_day=view.started_on_pedagogical_day,
        completed_at=view.completed_at,
        terminal_at=view.terminal_at,
        paused_at=view.paused_at,
        waiver_refs=view.waiver_refs,
        migration_map_revision_id=view.migration_map_revision_id,
        version=view.version,
    )


class SqlCurriculumService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    async def list_modules(self, actor_id: UUID) -> tuple[ModuleSummary, ...]:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT module.module_id,module.module_code,"
                            "revision.module_revision_id,revision.primary_intention,"
                            "revision.nominal_days,revision.max_days,revision.min_minutes,"
                            "revision.max_minutes,revision.entry_profile_codes "
                            "FROM curriculum.learning_modules module "
                            "JOIN curriculum.module_revisions revision ON "
                            "revision.module_revision_id=module.current_revision_id "
                            "WHERE module.status='published' AND revision.status='published' "
                            "ORDER BY module.module_code,module.module_id"
                        )
                    )
                )
                .mappings()
                .all()
            )
            return tuple(
                ModuleSummary(
                    module_id=_uuid(row["module_id"]),
                    module_code=str(row["module_code"]),
                    module_revision_id=_uuid(row["module_revision_id"]),
                    primary_intention=str(row["primary_intention"]),
                    nominal_days=int(row["nominal_days"]),
                    max_days=int(row["max_days"]),
                    min_minutes=int(row["min_minutes"]),
                    max_minutes=int(row["max_minutes"]),
                    entry_profile_codes=tuple(str(item) for item in row["entry_profile_codes"]),
                )
                for row in rows
            )

    async def get_enrollment(self, actor_id: UUID, enrollment_id: UUID) -> EnrollmentView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view = await self._read_enrollment(session, enrollment_id)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def enroll(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: EnrollInModule,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView:
        fingerprint = canonical_json_fingerprint(
            cast(
                JsonValue,
                {
                    "profile_id": str(profile_id),
                    "enrollment_id": str(command.enrollment_id),
                    "module_revision_id": str(command.module_revision_id),
                    "pedagogical_day": command.pedagogical_day.isoformat(),
                    "waiver_refs": list(command.waiver_refs),
                },
            )
        )
        now = self._clock.now()
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay = await self._reserve(
                session,
                actor_id=actor_id,
                command_type="EnrollInModule",
                aggregate_id=command.enrollment_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                now=now,
            )
            if replay is not None:
                return replay
            owned = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                    "WHERE profile_id=:profile AND account_id=:actor AND status <> 'deleted')"
                ),
                {"profile": profile_id, "actor": actor_id},
            )
            if not owned:
                raise DomainError(ErrorCode.NOT_FOUND)
            revision = (
                (
                    await session.execute(
                        text(
                            "SELECT revision.nominal_days,revision.max_days,"
                            "revision.prerequisite_skill_revision_ids "
                            "FROM curriculum.module_revisions revision "
                            "JOIN curriculum.learning_modules module USING (module_id) "
                            "WHERE revision.module_revision_id=:revision "
                            "AND revision.status='published' AND module.status='published'"
                        ),
                        {"revision": command.module_revision_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if revision is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if revision["prerequisite_skill_revision_ids"] and not command.waiver_refs:
                raise DomainError(ErrorCode.PREREQUISITE_MISSING)
            aggregate = ModuleEnrollment.plan(
                enrollment_id=command.enrollment_id,
                profile_id=profile_id,
                module_revision_id=command.module_revision_id,
                nominal_days=int(revision["nominal_days"]),
                max_days=int(revision["max_days"]),
                waiver_refs=command.waiver_refs,
            ).start(pedagogical_day=command.pedagogical_day)
            try:
                await session.execute(
                    text(
                        "INSERT INTO curriculum.module_enrollments "
                        "(enrollment_id,profile_id,module_revision_id,nominal_days,max_days,"
                        "status,current_day_ordinal,started_on_pedagogical_day,completed_at,"
                        "terminal_at,paused_at,waiver_refs,migration_map_revision_id,version,"
                        "created_at,updated_at) VALUES "
                        "(:enrollment,:profile,:revision,:nominal,:maximum,:status,:ordinal,"
                        ":started,NULL,NULL,NULL,:waivers,NULL,:version,:now,:now)"
                    ),
                    {
                        "enrollment": aggregate.enrollment_id,
                        "profile": aggregate.profile_id,
                        "revision": aggregate.module_revision_id,
                        "nominal": aggregate.nominal_days,
                        "maximum": aggregate.max_days,
                        "status": aggregate.status.value,
                        "ordinal": aggregate.current_day_ordinal,
                        "started": aggregate.started_on_pedagogical_day,
                        "waivers": list(aggregate.waiver_refs),
                        "version": aggregate.version,
                        "now": now,
                    },
                )
            except IntegrityError as error:
                raise DomainError(ErrorCode.ACTIVE_RUN_EXISTS) from error
            view = await self._required_enrollment(session, aggregate.enrollment_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=profile_id,
                context=context,
                event_type="module_enrollment_created",
                view=view,
                now=now,
            )
            await session.commit()
            return view

    async def pause(
        self,
        actor_id: UUID,
        enrollment_id: UUID,
        command: PauseEnrollment,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView:
        return await self._transition(
            actor_id=actor_id,
            enrollment_id=enrollment_id,
            command_type="PauseModuleEnrollment",
            event_type="module_enrollment_paused",
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            occurred_at=command.paused_at,
            payload={"paused_at": command.paused_at.isoformat()},
            transition=lambda value: value.pause(paused_at=command.paused_at),
        )

    async def complete(
        self,
        actor_id: UUID,
        enrollment_id: UUID,
        command: CompleteEnrollment,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView:
        return await self._transition(
            actor_id=actor_id,
            enrollment_id=enrollment_id,
            command_type="CompleteModuleEnrollment",
            event_type="module_enrollment_completed",
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            occurred_at=command.completed_at,
            payload={
                "completed_at": command.completed_at.isoformat(),
            },
            transition=lambda value: value.complete(
                completed_at=command.completed_at,
                exit_criteria_satisfied=True,
            ),
        )

    async def _transition(
        self,
        *,
        actor_id: UUID,
        enrollment_id: UUID,
        command_type: str,
        event_type: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
        occurred_at: datetime,
        payload: dict[str, JsonValue],
        transition: Callable[[ModuleEnrollment], ModuleEnrollment],
    ) -> EnrollmentView:
        fingerprint = canonical_json_fingerprint(
            cast(
                JsonValue,
                {
                    "enrollment_id": str(enrollment_id),
                    "expected_version": expected_version,
                    **payload,
                },
            )
        )
        now = self._clock.now()
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay = await self._reserve(
                session,
                actor_id=actor_id,
                command_type=command_type,
                aggregate_id=enrollment_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay is not None:
                return replay
            before = await self._read_enrollment(session, enrollment_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            try:
                after = transition(_aggregate(before))
            except CurriculumError as error:
                code = (
                    ErrorCode.COMPLETION_CRITERIA_MISSING
                    if str(error) == "completion_criteria_missing"
                    else ErrorCode.INVALID_TRANSITION
                )
                raise DomainError(code) from error
            await session.execute(
                text(
                    "UPDATE curriculum.module_enrollments SET status=:status,"
                    "current_day_ordinal=:ordinal,completed_at=:completed,terminal_at=:terminal,"
                    "paused_at=:paused,version=:version,updated_at=:updated "
                    "WHERE enrollment_id=:enrollment"
                ),
                {
                    "status": after.status.value,
                    "ordinal": after.current_day_ordinal,
                    "completed": after.completed_at,
                    "terminal": after.terminal_at,
                    "paused": after.paused_at,
                    "version": after.version,
                    "updated": occurred_at,
                    "enrollment": enrollment_id,
                },
            )
            view = await self._required_enrollment(session, enrollment_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=view.profile_id,
                context=context,
                event_type=event_type,
                view=view,
                now=now,
            )
            await session.commit()
            return view

    async def _reserve(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        command_type: str,
        aggregate_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_version: int | None,
        now: datetime,
    ) -> tuple[CommandReceipt, EnrollmentView | None]:
        if not idempotency_key or len(idempotency_key) > 255:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        receipt = CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=actor_id,
            aggregate_type="module_enrollment",
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + RECEIPT_RETENTION,
        )
        reservation = await SqlCommandReceiptStore(session).reserve(receipt)
        if reservation.created:
            return reservation.receipt, None
        stored = reservation.receipt
        if stored.status != "succeeded" or stored.result_ref is None:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        replay = await self._read_enrollment(session, stored.result_ref)
        if replay is None:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return stored, replay

    async def _record(
        self,
        session: AsyncSession,
        *,
        receipt: CommandReceipt,
        actor_id: UUID,
        profile_id: UUID,
        context: RequestContext,
        event_type: str,
        view: EnrollmentView,
        now: datetime,
    ) -> None:
        await SqlCommandReceiptStore(session).complete(
            command_id=receipt.command_id,
            status="succeeded",
            result_ref=view.enrollment_id,
            result_payload={
                "resource_id": str(view.enrollment_id),
                "version": view.version,
            },
        )
        await SqlEventOutboxRepository(session, self._ids).add(
            DomainEvent(
                event_id=self._ids.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type="module_enrollment",
                aggregate_id=view.enrollment_id,
                aggregate_version=view.version,
                actor_type="account",
                actor_id=actor_id,
                profile_id=profile_id,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=receipt.command_id,
                privacy_class="personal",
                policy_versions={"curriculum": 1},
                payload={"resource_id": str(view.enrollment_id)},
                expires_at=now + EVENT_RETENTION,
                subject_type="profile",
                subject_id=profile_id,
            ),
            destinations=("curriculum.events",),
        )

    async def _required_enrollment(
        self, session: AsyncSession, enrollment_id: UUID
    ) -> EnrollmentView:
        view = await self._read_enrollment(session, enrollment_id)
        if view is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return view

    @staticmethod
    async def _read_enrollment(
        session: AsyncSession,
        enrollment_id: UUID,
        *,
        for_update: bool = False,
    ) -> EnrollmentView | None:
        suffix = " FOR UPDATE OF enrollment" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT enrollment.*,module.module_code "
                        "FROM curriculum.module_enrollments enrollment "
                        "JOIN curriculum.module_revisions revision USING (module_revision_id) "
                        "JOIN curriculum.learning_modules module USING (module_id) "
                        "WHERE enrollment.enrollment_id=:enrollment" + suffix
                    ),
                    {"enrollment": enrollment_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _enrollment(row)

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )


__all__ = ["SqlCurriculumService"]

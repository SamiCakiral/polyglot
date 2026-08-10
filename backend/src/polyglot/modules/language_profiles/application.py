"""Application boundary for the W03 profile, diagnostic, and foundation flows."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.catalogue.core.domain import (
    FoundationCheckerKind,
    PublishedFoundationCatalogue,
    PublishedFoundationItem,
)
from polyglot.modules.catalogue.core.service import CatalogueReader
from polyglot.modules.identity.application import RequestContext
from polyglot.modules.language_profiles.diagnostic import (
    DiagnosticPolicy,
    DiagnosticRun,
    DiagnosticTarget,
)
from polyglot.modules.language_profiles.diagnostic import (
    DiagnosticResponse as DiagnosticAnswer,
)
from polyglot.modules.language_profiles.domain import LanguageProfileStatus, LearnerLanguageProfile
from polyglot.modules.language_profiles.foundations import (
    FoundationBlock,
    FoundationCriterion,
    FoundationGate,
    FoundationMeasurement,
)
from polyglot.modules.language_profiles.persistence import (
    SqlLanguageProfileRepository,
    diagnostic_responses,
    diagnostic_runs,
    foundation_gate_results,
    foundation_measurements,
    foundation_run_blocks,
    foundation_runs,
)
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
from polyglot.platform.persistence.uow import SqlAlchemyUnitOfWork

COMMAND_RECEIPT_RETENTION = timedelta(hours=24)
PROFILE_EVENT_RETENTION = timedelta(days=180)


@dataclass(frozen=True, slots=True)
class ProfileMutationResult:
    profile: LearnerLanguageProfile
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DiagnosticRunSummary:
    diagnostic_run_id: UUID
    profile_id: UUID
    status: str
    policy_revision_id: UUID
    pack_revision_id: UUID
    started_at: datetime
    expires_at: datetime
    version: int
    completed_at: datetime | None
    classification: str | None
    confidence: float | None
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class FoundationRunSummary:
    foundation_run_id: UUID
    profile_id: UUID
    status: str
    pack_revision_id: UUID
    foundation_revision_id: UUID
    started_at: datetime
    expires_at: datetime
    version: int
    completed_at: datetime | None
    session_count: int = 0
    gate_passed: bool | None = None
    gate_reasons: tuple[str, ...] = ()


class LanguageProfileApplicationService:
    """Persists W03 state only; it deliberately has no mastery/projection dependency."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        catalogue_reader: CatalogueReader | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or Uuid7Generator(self._clock)
        self._catalogue_reader = catalogue_reader

    async def _published_foundations(self, pack_revision_id: UUID) -> PublishedFoundationCatalogue:
        if self._catalogue_reader is None:
            raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
        catalogue = await self._catalogue_reader.read_foundations(
            pack_revision_id=pack_revision_id
        )
        if catalogue is None:
            raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
        return catalogue

    @staticmethod
    def _answer_value(answer: dict[str, JsonValue]) -> str | None:
        value = answer.get("value")
        return value if isinstance(value, str) else None

    @classmethod
    def _score_item(
        cls, item: PublishedFoundationItem, answer: dict[str, JsonValue]
    ) -> tuple[float | None, bool]:
        if item.checker_kind is FoundationCheckerKind.NOT_EVALUABLE:
            return None, False
        value = cls._answer_value(answer)
        if value is None:
            return 0.0, True
        if item.checker_kind is FoundationCheckerKind.NORMALIZED_ALTERNATIVES:
            normalized = "_".join(value.casefold().strip().split())
            expected = {"_".join(item.casefold().strip().split()) for item in item.checker_values}
            return float(normalized in expected), True
        return float(value in item.checker_values), True

    @staticmethod
    def _foundation_block(code: str) -> FoundationBlock:
        return {
            "F1": FoundationBlock.F1,
            "F2": FoundationBlock.F2,
            "F3": FoundationBlock.F3,
            "F4": FoundationBlock.F4,
            "F5": FoundationBlock.F5,
        }[code]

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    @staticmethod
    def _session(uow: SqlAlchemyUnitOfWork) -> AsyncSession:
        if uow.session is None:
            raise RuntimeError("language profile unit of work is not active")
        return uow.session

    def _receipt(
        self,
        *,
        command_type: str,
        account_id: UUID,
        aggregate_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_version: int | None,
        now: datetime,
    ) -> CommandReceipt:
        if not idempotency_key or len(idempotency_key) > 255:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        return CommandReceipt(
            command_id=self._id_generator.new(),
            command_type=command_type,
            actor_id=account_id,
            aggregate_type="learner_language_profile",
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + COMMAND_RECEIPT_RETENTION,
        )

    @staticmethod
    def _replayed_error(receipt: CommandReceipt) -> None:
        if receipt.status == "started":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if receipt.status in {"rejected", "failed"}:
            payload = receipt.result_payload or {}
            raise DomainError(cast(str, payload.get("code", ErrorCode.INTERNAL_ERROR.value)))

    async def _complete(
        self,
        store: SqlCommandReceiptStore,
        receipt: CommandReceipt,
        resource_id: UUID,
        version: int,
    ) -> None:
        await store.complete(
            command_id=receipt.command_id,
            status="succeeded",
            result_ref=resource_id,
            result_payload={"resource_id": str(resource_id), "version": version},
        )

    async def _event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        profile: LearnerLanguageProfile,
        account_id: UUID,
        command_id: UUID,
        context: RequestContext,
        now: datetime,
        payload: dict[str, JsonValue],
        aggregate_type: str = "learner_language_profile",
        aggregate_id: UUID | None = None,
        aggregate_version: int | None = None,
    ) -> None:
        await SqlEventOutboxRepository(session, self._id_generator).add(
            DomainEvent(
                event_id=self._id_generator.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id or profile.profile_id,
                aggregate_version=aggregate_version or profile.version,
                actor_type="account",
                actor_id=account_id,
                profile_id=profile.profile_id,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=command_id,
                privacy_class="personal",
                policy_versions={"language_profiles": 1},
                payload=payload,
                expires_at=now + PROFILE_EVENT_RETENTION,
                subject_type="profile",
                subject_id=profile.profile_id,
            ),
            destinations=("language_profiles.events",),
        )

    async def list_profiles(self, account_id: UUID) -> tuple[LearnerLanguageProfile, ...]:
        async with self._uow() as uow:
            repository = SqlLanguageProfileRepository(self._session(uow))
            profiles = await repository.list_owned(account_id)
            await uow.commit()
            return profiles
        raise RuntimeError("profile listing was unexpectedly suppressed")

    async def get_profile(self, profile_id: UUID, account_id: UUID) -> LearnerLanguageProfile:
        async with self._uow() as uow:
            repository = SqlLanguageProfileRepository(self._session(uow))
            profile = await repository.get_owned(profile_id, account_id)
            await uow.commit()
            return profile
        raise RuntimeError("profile lookup was unexpectedly suppressed")

    async def create_profile(
        self,
        *,
        account_id: UUID,
        target_variety_id: UUID,
        native_variety_id: UUID,
        idempotency_key: str,
        context: RequestContext,
    ) -> ProfileMutationResult:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            receipt = self._receipt(
                command_type="CreateLanguageProfile",
                account_id=account_id,
                aggregate_id=account_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint(
                    {
                        "target_variety_id": str(target_variety_id),
                        "native_variety_id": str(native_variety_id),
                    }
                ),
                expected_version=None,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                profile = await repository.get_owned(
                    cast(UUID, reservation.receipt.result_ref), account_id
                )
                await uow.commit()
                return ProfileMutationResult(profile, replayed=True)
            profile = LearnerLanguageProfile.create(
                profile_id=self._id_generator.new(),
                account_id=account_id,
                target_variety_id=target_variety_id,
                native_variety_id=native_variety_id,
                now=now,
            )
            try:
                await repository.add(profile)
            except IntegrityError as error:
                await uow.rollback()
                raise DomainError(ErrorCode.PROFILE_ALREADY_EXISTS) from error
            await self._event(
                session,
                event_type="language_profile_created",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"profile_id": str(profile.profile_id), "status": profile.status.value},
            )
            await self._complete(store, receipt, profile.profile_id, profile.version)
            await uow.commit()
            return ProfileMutationResult(profile)
        raise RuntimeError("profile creation was unexpectedly suppressed")

    async def update_goals(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        goals: tuple[str, ...],
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> ProfileMutationResult:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            current = await repository.get_owned(profile_id, account_id)
            receipt = self._receipt(
                command_type="UpdateLearningGoals",
                account_id=account_id,
                aggregate_id=profile_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint({"goals": list(goals)}),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                profile = await repository.get_owned(profile_id, account_id)
                await uow.commit()
                return ProfileMutationResult(profile, replayed=True)
            profile = current.with_goals(goals, expected_version=expected_version, now=now)
            await repository.update(profile)
            await self._event(
                session,
                event_type="learning_goals_updated",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"profile_id": str(profile.profile_id), "version": profile.version},
            )
            await self._complete(store, receipt, profile.profile_id, profile.version)
            await uow.commit()
            return ProfileMutationResult(profile)
        raise RuntimeError("profile goal update was unexpectedly suppressed")

    async def transition_profile(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        status: LanguageProfileStatus,
        command_type: str,
        event_type: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> ProfileMutationResult:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            current = await repository.get_owned(profile_id, account_id)
            receipt = self._receipt(
                command_type=command_type,
                account_id=account_id,
                aggregate_id=profile_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint({"status": status.value}),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                profile = await repository.get_owned(profile_id, account_id)
                await uow.commit()
                return ProfileMutationResult(profile, replayed=True)
            if current.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            profile = current.transition(status, now=now)
            await repository.update(profile)
            await self._event(
                session,
                event_type=event_type,
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"profile_id": str(profile.profile_id), "status": profile.status.value},
            )
            await self._complete(store, receipt, profile.profile_id, profile.version)
            await uow.commit()
            return ProfileMutationResult(profile)
        raise RuntimeError("profile transition was unexpectedly suppressed")

    @staticmethod
    def _diagnostic_summary(row: object) -> DiagnosticRunSummary:
        values = cast(dict[str, object], row)
        return DiagnosticRunSummary(
            diagnostic_run_id=cast(UUID, values["diagnostic_run_id"]),
            profile_id=cast(UUID, values["profile_id"]),
            status=cast(str, values["status"]),
            policy_revision_id=cast(UUID, values["policy_revision_id"]),
            pack_revision_id=cast(UUID, values["pack_revision_id"]),
            started_at=cast(datetime, values["started_at"]),
            expires_at=cast(datetime, values["expires_at"]),
            version=cast(int, values["version"]),
            completed_at=cast(datetime | None, values["completed_at"]),
            classification=cast(str | None, values["classification"]),
            confidence=float(cast(Decimal, values["confidence"]))
            if values["confidence"] is not None
            else None,
            stop_reason=cast(str | None, values["stop_reason"]),
        )

    async def start_diagnostic(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        policy_revision_id: UUID,
        pack_revision_id: UUID,
        seed: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> DiagnosticRunSummary:
        if not seed:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        try:
            await self._published_foundations(pack_revision_id)
        except DomainError as error:
            if error.code is ErrorCode.FOUNDATION_PACK_MISSING:
                raise DomainError(ErrorCode.DIAGNOSTIC_UNAVAILABLE) from error
            raise
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            profile = await repository.get_owned(profile_id, account_id)
            if profile.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            await session.execute(
                diagnostic_runs.update()
                .where(
                    diagnostic_runs.c.profile_id == profile_id,
                    diagnostic_runs.c.status.in_(("prepared", "in_progress", "interrupted")),
                    diagnostic_runs.c.expires_at <= now,
                )
                .values(status="expired", version=diagnostic_runs.c.version + 1)
            )
            receipt = self._receipt(
                command_type="StartDiagnostic",
                account_id=account_id,
                aggregate_id=profile_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint(
                    {
                        "policy_revision_id": str(policy_revision_id),
                        "pack_revision_id": str(pack_revision_id),
                        "seed": seed,
                    }
                ),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                row = (
                    await session.execute(
                        select(diagnostic_runs).where(
                            diagnostic_runs.c.diagnostic_run_id == reservation.receipt.result_ref
                        )
                    )
                ).mappings().one()
                await uow.commit()
                return self._diagnostic_summary(dict(row))
            active = (
                await session.execute(
                    select(diagnostic_runs)
                    .where(
                        diagnostic_runs.c.profile_id == profile_id,
                        diagnostic_runs.c.status.in_(("prepared", "in_progress", "interrupted")),
                        diagnostic_runs.c.expires_at > now,
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if active is not None:
                active_summary = self._diagnostic_summary(dict(active))
                await self._complete(
                    store,
                    receipt,
                    active_summary.diagnostic_run_id,
                    active_summary.version,
                )
                await uow.commit()
                return active_summary
            run_id = self._id_generator.new()
            try:
                await session.execute(
                    diagnostic_runs.insert().values(
                        diagnostic_run_id=run_id,
                        profile_id=profile_id,
                        policy_revision_id=policy_revision_id,
                        pack_revision_id=pack_revision_id,
                        status="in_progress",
                        seed=seed,
                        started_at=now,
                        expires_at=now + timedelta(hours=24),
                        completed_at=None,
                        classification=None,
                        confidence=None,
                        stop_reason=None,
                        version=1,
                    )
                )
            except IntegrityError as error:
                raise DomainError(ErrorCode.ACTIVE_RUN_EXISTS) from error
            await self._event(
                session,
                event_type="diagnostic_started",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"profile_id": str(profile_id), "diagnostic_run_id": str(run_id)},
                aggregate_type="diagnostic_run",
                aggregate_id=run_id,
                aggregate_version=1,
            )
            await self._complete(store, receipt, run_id, 1)
            await uow.commit()
            return DiagnosticRunSummary(
                diagnostic_run_id=run_id,
                profile_id=profile_id,
                status="in_progress",
                policy_revision_id=policy_revision_id,
                pack_revision_id=pack_revision_id,
                started_at=now,
                expires_at=now + timedelta(hours=24),
                version=1,
                completed_at=None,
                classification=None,
                confidence=None,
                stop_reason=None,
            )
        raise RuntimeError("diagnostic start was unexpectedly suppressed")

    async def get_diagnostic(self, run_id: UUID, account_id: UUID) -> DiagnosticRunSummary:
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(diagnostic_runs).where(diagnostic_runs.c.diagnostic_run_id == run_id)
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            await uow.commit()
            return self._diagnostic_summary(dict(row))
        raise RuntimeError("diagnostic lookup was unexpectedly suppressed")

    async def _expire_diagnostic_response_run_if_due(
        self,
        *,
        run_id: UUID,
        account_id: UUID,
        expected_version: int,
        now: datetime,
    ) -> bool:
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(diagnostic_runs)
                    .where(diagnostic_runs.c.diagnostic_run_id == run_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            if row["status"] != "in_progress":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if cast(int, row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if now < cast(datetime, row["expires_at"]):
                await uow.commit()
                return False
            await session.execute(
                diagnostic_runs.update()
                .where(diagnostic_runs.c.diagnostic_run_id == run_id)
                .values(status="expired", version=expected_version + 1)
            )
            await uow.commit()
            return True
        raise RuntimeError("diagnostic expiry was unexpectedly suppressed")

    async def submit_diagnostic_response(
        self,
        *,
        run_id: UUID,
        account_id: UUID,
        item_revision_id: UUID,
        ordinal: int,
        answer: dict[str, JsonValue],
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> DiagnosticRunSummary:
        now = self._clock.now()
        if await self._expire_diagnostic_response_run_if_due(
            run_id=run_id,
            account_id=account_id,
            expected_version=expected_version,
            now=now,
        ):
            raise DomainError(ErrorCode.RUN_EXPIRED)
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(diagnostic_runs).where(diagnostic_runs.c.diagnostic_run_id == run_id)
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            profile = await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            if row["status"] != "in_progress":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if cast(int, row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            catalogue = await self._published_foundations(cast(UUID, row["pack_revision_id"]))
            item_context = next(
                (
                    (block, item)
                    for block in catalogue.definition.blocks
                    for item in block.items
                    if item.item_revision_id == item_revision_id
                ),
                None,
            )
            if item_context is None:
                raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
            previous_count = cast(
                int,
                await session.scalar(
                    select(func.count()).select_from(diagnostic_responses).where(
                        diagnostic_responses.c.diagnostic_run_id == run_id
                    )
                )
                or 0,
            )
            if ordinal != previous_count + 1:
                raise DomainError(ErrorCode.RESPONSE_CONFLICT)
            block, published_item = item_context
            score, evaluable = self._score_item(published_item, answer)
            target = {
                "F1": DiagnosticTarget.FOUNDATIONS,
                "F2": DiagnosticTarget.LISTENING,
                "F3": DiagnosticTarget.READING,
                "F4": DiagnosticTarget.WRITING,
                "F5": DiagnosticTarget.WRITING,
            }[block.block_code]
            receipt = self._receipt(
                command_type="SubmitDiagnosticResponse",
                account_id=account_id,
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint(
                    {
                        "item_revision_id": str(item_revision_id),
                        "ordinal": ordinal,
                    }
                ),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                await uow.commit()
                return await self.get_diagnostic(run_id, account_id)
            persisted_answer = {
                **answer,
                "_w03_target": target.value,
                "_w03_difficulty": block.ordinal,
            }
            try:
                await session.execute(
                    diagnostic_responses.insert().values(
                        response_id=self._id_generator.new(),
                        diagnostic_run_id=run_id,
                        item_revision_id=item_revision_id,
                        ordinal=ordinal,
                        answer=persisted_answer,
                        score=score,
                        confidence=1.0 if evaluable else None,
                        evaluable=evaluable,
                        revealed=False,
                        submitted_at=now,
                        idempotency_key=idempotency_key,
                    )
                )
            except IntegrityError as error:
                raise DomainError(ErrorCode.RESPONSE_CONFLICT) from error
            version = expected_version + 1
            await session.execute(
                diagnostic_runs.update()
                .where(diagnostic_runs.c.diagnostic_run_id == run_id)
                .values(version=version)
            )
            await self._event(
                session,
                event_type="diagnostic_response_recorded",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"diagnostic_run_id": str(run_id), "ordinal": ordinal},
                aggregate_type="diagnostic_run",
                aggregate_id=run_id,
                aggregate_version=version,
            )
            await self._complete(store, receipt, run_id, version)
            await uow.commit()
            return replace(self._diagnostic_summary(dict(row)), version=version)
        raise RuntimeError("diagnostic response was unexpectedly suppressed")

    async def complete_diagnostic(
        self,
        *,
        run_id: UUID,
        account_id: UUID,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> DiagnosticRunSummary:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(diagnostic_runs).where(diagnostic_runs.c.diagnostic_run_id == run_id)
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            profile = await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            if row["status"] != "in_progress" or cast(int, row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            answers = (
                await session.execute(
                    select(diagnostic_responses)
                    .where(diagnostic_responses.c.diagnostic_run_id == run_id)
                    .order_by(diagnostic_responses.c.ordinal)
                )
            ).mappings().all()
            run = DiagnosticRun.start(
                diagnostic_run_id=run_id,
                profile_id=profile.profile_id,
                policy=DiagnosticPolicy.v0(),
                seed=cast(str, row["seed"]),
                started_at=cast(datetime, row["started_at"]),
            )
            for item in answers:
                answer = cast(dict[str, object], item["answer"])
                run = run.record(
                    DiagnosticAnswer(
                        target=DiagnosticTarget(cast(str, answer["_w03_target"])),
                        score=float(item["score"] or 0),
                        confidence=float(item["confidence"] or 0),
                        evaluable=cast(bool, item["evaluable"]),
                        difficulty=cast(int, answer["_w03_difficulty"]),
                        item_revision_id=cast(UUID, item["item_revision_id"]),
                    ),
                    at=cast(datetime, item["submitted_at"]),
                )
            result = run.complete(at=now)
            receipt = self._receipt(
                command_type="CompleteDiagnostic",
                account_id=account_id,
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint({"run_id": str(run_id)}),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                await uow.commit()
                return await self.get_diagnostic(run_id, account_id)
            version = expected_version + 1
            await session.execute(
                diagnostic_runs.update()
                .where(diagnostic_runs.c.diagnostic_run_id == run_id)
                .values(
                    status="completed",
                    completed_at=now,
                    classification=result.classification.value,
                    confidence=0.0,
                    stop_reason=result.stop_reason.value,
                    version=version,
                )
            )
            next_status = LanguageProfileStatus(result.next_profile_status)
            updated_profile = profile.transition(next_status, now=now)
            await repository.update(updated_profile)
            await self._event(
                session,
                event_type="diagnostic_completed",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={
                    "diagnostic_run_id": str(run_id),
                    "classification": result.classification.value,
                },
                aggregate_type="diagnostic_run",
                aggregate_id=run_id,
                aggregate_version=version,
            )
            await self._event(
                session,
                event_type="placement_decided",
                profile=updated_profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"profile_id": str(profile.profile_id), "next_status": next_status.value},
            )
            await self._complete(store, receipt, run_id, version)
            await uow.commit()
            return replace(
                self._diagnostic_summary(dict(row)),
                status="completed",
                completed_at=now,
                classification=result.classification.value,
                confidence=0.0,
                stop_reason=result.stop_reason.value,
                version=version,
            )
        raise RuntimeError("diagnostic completion was unexpectedly suppressed")

    async def _foundation_summary(
        self, session: AsyncSession, row: object
    ) -> FoundationRunSummary:
        values = cast(dict[str, object], row)
        run_id = cast(UUID, values["foundation_run_id"])
        session_count = cast(
            int,
            await session.scalar(
                select(func.count(distinct(foundation_measurements.c.session_id))).where(
                    foundation_measurements.c.foundation_run_id == run_id
                )
            )
            or 0,
        )
        gate = (
            await session.execute(
                select(foundation_gate_results)
                .where(foundation_gate_results.c.foundation_run_id == run_id)
                .order_by(
                    foundation_gate_results.c.decided_at.desc(),
                    foundation_gate_results.c.gate_result_id.desc(),
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return FoundationRunSummary(
            foundation_run_id=run_id,
            profile_id=cast(UUID, values["profile_id"]),
            status=cast(str, values["status"]),
            pack_revision_id=cast(UUID, values["pack_revision_id"]),
            foundation_revision_id=cast(UUID, values["foundation_revision_id"]),
            started_at=cast(datetime, values["started_at"]),
            expires_at=cast(datetime, values["expires_at"]),
            version=cast(int, values["version"]),
            completed_at=cast(datetime | None, values["completed_at"]),
            session_count=session_count,
            gate_passed=cast(bool, gate["passed"]) if gate is not None else None,
            gate_reasons=tuple(cast(list[str], gate["reasons"])) if gate is not None else (),
        )

    async def get_foundation_run(self, run_id: UUID, account_id: UUID) -> FoundationRunSummary:
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(foundation_runs).where(foundation_runs.c.foundation_run_id == run_id)
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            await uow.commit()
            summary = await self._foundation_summary(session, dict(row))
            await uow.commit()
            return summary
        raise RuntimeError("foundation run lookup was unexpectedly suppressed")

    async def start_foundation_run(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        pack_revision_id: UUID,
        foundation_revision_id: UUID,
        seed: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> FoundationRunSummary:
        if not seed:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        catalogue = await self._published_foundations(pack_revision_id)
        if catalogue.definition.foundation_revision_id != foundation_revision_id:
            raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            profile = await repository.get_owned(profile_id, account_id)
            if profile.status is not LanguageProfileStatus.FOUNDATIONS:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if profile.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            await session.execute(
                foundation_runs.update()
                .where(
                    foundation_runs.c.profile_id == profile_id,
                    foundation_runs.c.status.in_(("prepared", "in_progress", "interrupted")),
                    foundation_runs.c.expires_at <= now,
                )
                .values(status="expired", version=foundation_runs.c.version + 1)
            )
            receipt = self._receipt(
                command_type="StartFoundationRun",
                account_id=account_id,
                aggregate_id=profile_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint(
                    {
                        "pack_revision_id": str(pack_revision_id),
                        "foundation_revision_id": str(foundation_revision_id),
                        "seed": seed,
                    }
                ),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                return await self.get_foundation_run(
                    cast(UUID, reservation.receipt.result_ref), account_id
                )
            run_id = self._id_generator.new()
            try:
                await session.execute(
                    foundation_runs.insert().values(
                        foundation_run_id=run_id,
                        profile_id=profile_id,
                        pack_revision_id=pack_revision_id,
                        foundation_revision_id=foundation_revision_id,
                        status="in_progress",
                        seed=seed,
                        started_at=now,
                        expires_at=now + timedelta(days=7),
                        completed_at=None,
                        version=1,
                    )
                )
            except IntegrityError as error:
                raise DomainError(ErrorCode.ACTIVE_RUN_EXISTS) from error
            for block in catalogue.definition.blocks:
                await session.execute(
                    foundation_run_blocks.insert().values(
                        foundation_run_block_id=self._id_generator.new(),
                        foundation_run_id=run_id,
                        block_revision_id=block.block_revision_id,
                        block_code=block.block_code,
                        ordinal=block.ordinal,
                        status="available",
                        session_id=None,
                        started_at=None,
                        completed_at=None,
                    )
                )
            await self._event(
                session,
                event_type="foundation_run_started",
                profile=profile,
                account_id=account_id,
                command_id=receipt.command_id,
                context=context,
                now=now,
                payload={"foundation_run_id": str(run_id)},
                aggregate_type="foundation_run",
                aggregate_id=run_id,
                aggregate_version=1,
            )
            await self._complete(store, receipt, run_id, 1)
            await uow.commit()
            return FoundationRunSummary(
                foundation_run_id=run_id,
                profile_id=profile_id,
                status="in_progress",
                pack_revision_id=pack_revision_id,
                foundation_revision_id=foundation_revision_id,
                started_at=now,
                expires_at=now + timedelta(days=7),
                version=1,
                completed_at=None,
            )
        raise RuntimeError("foundation start was unexpectedly suppressed")

    async def complete_foundation_gate(
        self,
        *,
        run_id: UUID,
        account_id: UUID,
        answers: tuple[tuple[UUID, int, dict[str, JsonValue], bool], ...],
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> FoundationRunSummary:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlLanguageProfileRepository(session)
            await repository.set_actor(account_id)
            row = (
                await session.execute(
                    select(foundation_runs).where(foundation_runs.c.foundation_run_id == run_id)
                )
            ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            profile = await repository.get_owned(cast(UUID, row["profile_id"]), account_id)
            if cast(int, row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if row["status"] not in {"in_progress", "interrupted"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if now >= cast(datetime, row["expires_at"]):
                await session.execute(
                    foundation_runs.update()
                    .where(foundation_runs.c.foundation_run_id == run_id)
                    .values(status="expired", version=expected_version + 1)
                )
                await uow.commit()
                raise DomainError(ErrorCode.RUN_EXPIRED)

            catalogue = await self._published_foundations(cast(UUID, row["pack_revision_id"]))
            definition = catalogue.definition
            if definition.foundation_revision_id != row["foundation_revision_id"]:
                raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
            published_items = {
                item.item_revision_id: (block, item)
                for block in definition.blocks
                for item in block.items
            }
            required_trials = {
                item.item_revision_id: {
                    "ITF-F1-01": 10,
                    "ITF-F1-02": 10,
                    "ITF-F5-02": 5,
                }.get(item.item_code, 1)
                for block in definition.blocks
                for item in block.items
            }
            submitted_trials = [
                (item_id, trial_ordinal) for item_id, trial_ordinal, _, _ in answers
            ]
            expected_trials = {
                (item_id, trial_ordinal)
                for item_id, total in required_trials.items()
                for trial_ordinal in range(1, total + 1)
            }
            if len(submitted_trials) != len(set(submitted_trials)) or set(
                submitted_trials
            ) != expected_trials:
                raise DomainError(ErrorCode.RESPONSE_CONFLICT)

            receipt = self._receipt(
                command_type="CompleteFoundationGate",
                account_id=account_id,
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=canonical_json_fingerprint(
                    {
                        "run_id": str(run_id),
                        "answers": [
                            {
                                "item_revision_id": str(item_id),
                                "trial_ordinal": trial_ordinal,
                                "answer": answer,
                                "revealed": revealed,
                            }
                            for item_id, trial_ordinal, answer, revealed in answers
                        ],
                    }
                ),
                expected_version=expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._replayed_error(reservation.receipt)
                await uow.commit()
                return await self.get_foundation_run(run_id, account_id)

            block_rows = {
                cast(UUID, item["block_revision_id"]): item
                for item in (
                    await session.execute(
                        select(foundation_run_blocks).where(
                            foundation_run_blocks.c.foundation_run_id == run_id
                        )
                    )
                ).mappings()
            }
            if set(block_rows) != {item.block_revision_id for item in definition.blocks}:
                raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
            session_id = self._id_generator.new()
            criteria = {
                "ITF-F1-01": FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
                "ITF-F1-02": FoundationCriterion.TARGETED_READING,
                "ITF-F5-02": FoundationCriterion.SURVIVAL_EXCHANGE,
            }
            for item_id, trial_ordinal, answer, revealed in answers:
                block, item = published_items[item_id]
                score, evaluable = self._score_item(item, answer)
                await session.execute(
                    foundation_measurements.insert().values(
                        measurement_id=self._id_generator.new(),
                        foundation_run_id=run_id,
                        foundation_run_block_id=block_rows[block.block_revision_id][
                            "foundation_run_block_id"
                        ],
                        item_revision_id=item_id,
                        session_id=session_id,
                        trial_ordinal=trial_ordinal,
                        criterion=criteria.get(item.item_code),
                        answer=answer,
                        score=score,
                        evaluable=evaluable,
                        revealed=revealed,
                        measured_at=now,
                    )
                )

            persisted = (
                await session.execute(
                    select(
                        foundation_measurements.c.session_id,
                        foundation_measurements.c.item_revision_id,
                        foundation_measurements.c.criterion,
                        foundation_measurements.c.score,
                        foundation_measurements.c.evaluable,
                        foundation_measurements.c.revealed,
                        foundation_measurements.c.measured_at,
                    ).where(foundation_measurements.c.foundation_run_id == run_id)
                )
            ).mappings().all()
            grouped: dict[tuple[UUID, str, str | None], list[object]] = {}
            item_blocks = {
                item.item_revision_id: block.block_code
                for block in definition.blocks
                for item in block.items
            }
            for measurement in persisted:
                key = (
                    cast(UUID, measurement["session_id"]),
                    item_blocks[cast(UUID, measurement["item_revision_id"])],
                    cast(str | None, measurement["criterion"]),
                )
                grouped.setdefault(key, []).append(measurement)
            gate_measurements: list[FoundationMeasurement] = []
            for (persisted_session_id, block_code, criterion), items in grouped.items():
                values = [cast(dict[str, object], item) for item in items]
                eligible = [item for item in values if cast(bool, item["evaluable"])]
                gate_measurements.append(
                    FoundationMeasurement(
                        block=self._foundation_block(block_code),
                        criterion=FoundationCriterion(criterion) if criterion is not None else None,
                        score=sum(int(cast(Decimal, item["score"])) for item in eligible),
                        maximum=max(1, len(eligible)),
                        session_id=persisted_session_id,
                        at=cast(datetime, values[0]["measured_at"]),
                        revealed=any(cast(bool, item["revealed"]) for item in eligible),
                        evaluable=bool(eligible),
                    )
                )
            gate = FoundationGate(
                gate_code=definition.gate.gate_code,
                revision=1,
                grapheme_sound_minimum=definition.gate.grapheme_sound_minimum,
                grapheme_sound_total=definition.gate.grapheme_sound_total,
                targeted_reading_minimum=definition.gate.targeted_reading_minimum,
                targeted_reading_total=definition.gate.targeted_reading_total,
                survival_exchange_minimum=definition.gate.survival_exchange_minimum,
                survival_exchange_total=definition.gate.survival_exchange_total,
                delayed_control_after=timedelta(hours=definition.gate.delayed_control_hours),
            )
            result = gate.evaluate(tuple(gate_measurements))
            deterministic = [item for item in persisted if cast(bool, item["evaluable"])]
            coverage = (
                sum(float(cast(Decimal, item["score"])) for item in deterministic)
                / len(deterministic)
                if deterministic
                else 0.0
            )
            await session.execute(
                foundation_gate_results.insert().values(
                    gate_result_id=self._id_generator.new(),
                    foundation_run_id=run_id,
                    gate_revision_id=definition.gate.gate_revision_id,
                    passed=result.passed,
                    coverage=coverage,
                    confidence=1.0 if deterministic else 0.0,
                    reasons=list(result.reasons),
                    details={
                        "session_count": len({item.session_id for item in gate_measurements}),
                        "not_evaluable_blocks": [
                            item.value for item in result.not_evaluable_blocks
                        ],
                    },
                    waiver_reason=None,
                    waiver_evidence_ids=[],
                    decided_at=now,
                )
            )
            version = expected_version + 1
            new_status = "completed" if result.passed else "interrupted"
            await session.execute(
                foundation_runs.update()
                .where(foundation_runs.c.foundation_run_id == run_id)
                .values(
                    status=new_status,
                    completed_at=now if result.passed else None,
                    version=version,
                )
            )
            await session.execute(
                foundation_run_blocks.update()
                .where(foundation_run_blocks.c.foundation_run_id == run_id)
                .values(
                    status="completed" if result.passed else "in_progress",
                    session_id=session_id,
                    result={"gate_passed": result.passed},
                    started_at=cast(datetime, row["started_at"]),
                    completed_at=now if result.passed else None,
                )
            )
            if result.passed:
                updated_profile = profile.transition(LanguageProfileStatus.ACTIVE, now=now)
                await repository.update(updated_profile)
                await self._event(
                    session,
                    event_type="foundation_gate_completed",
                    profile=updated_profile,
                    account_id=account_id,
                    command_id=receipt.command_id,
                    context=context,
                    now=now,
                    payload={
                        "foundation_run_id": str(run_id),
                        "passed": True,
                        "gate_revision_id": str(definition.gate.gate_revision_id),
                    },
                    aggregate_type="foundation_run",
                    aggregate_id=run_id,
                    aggregate_version=version,
                )
            await self._complete(store, receipt, run_id, version)
            await uow.commit()
            return FoundationRunSummary(
                foundation_run_id=run_id,
                profile_id=profile.profile_id,
                status=new_status,
                pack_revision_id=definition.pack_revision_id,
                foundation_revision_id=definition.foundation_revision_id,
                started_at=cast(datetime, row["started_at"]),
                expires_at=cast(datetime, row["expires_at"]),
                version=version,
                completed_at=now if result.passed else None,
                session_count=len({item.session_id for item in gate_measurements}),
                gate_passed=result.passed,
                gate_reasons=result.reasons,
            )
        raise RuntimeError("foundation completion was unexpectedly suppressed")

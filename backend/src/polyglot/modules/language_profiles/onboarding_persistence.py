from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.identity.application import RequestContext
from polyglot.modules.language_profiles.domain import LanguageProfileStatus
from polyglot.modules.language_profiles.onboarding import (
    EntryPath,
    OnboardingState,
    PlacementBand,
    PlacementChoice,
    SkillDimension,
    SkillEstimate,
)
from polyglot.modules.language_profiles.persistence import (
    SqlLanguageProfileRepository,
    learner_language_profiles,
    onboarding_states,
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


def _serialize_skills(skills: tuple[SkillEstimate, ...]) -> list[JsonValue]:
    return [
        {
            "dimension": item.dimension.value,
            "band": item.band.value,
            "confidence": item.confidence,
            "evidence_count": item.evidence_count,
        }
        for item in skills
    ]


def _state(row: RowMapping) -> OnboardingState:
    return OnboardingState(
        profile_id=row["profile_id"],
        account_id=row["account_id"],
        entry_path=EntryPath(row["entry_path"]),
        detected_band=(
            None if row["detected_band"] is None else PlacementBand(row["detected_band"])
        ),
        placement_confidence=(
            None if row["placement_confidence"] is None else float(row["placement_confidence"])
        ),
        skill_profile=tuple(
            SkillEstimate(
                dimension=SkillDimension(item["dimension"]),
                band=PlacementBand(item["band"]),
                confidence=float(item["confidence"]),
                evidence_count=int(item["evidence_count"]),
            )
            for item in row["skill_profile"]
        ),
        placement_choice=(
            None if row["placement_choice"] is None else PlacementChoice(row["placement_choice"])
        ),
        calibration_sessions_remaining=row["calibration_sessions_remaining"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlOnboardingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_owner(self, account_id: UUID) -> None:
        await self._session.execute(
            text("SELECT set_config('app.user_id', :account_id, true)"),
            {"account_id": str(account_id)},
        )

    async def require_profile(self, profile_id: UUID, account_id: UUID) -> None:
        await self.set_owner(account_id)
        owned = await self._session.scalar(
            select(learner_language_profiles.c.profile_id)
            .where(
                learner_language_profiles.c.profile_id == profile_id,
                learner_language_profiles.c.account_id == account_id,
                learner_language_profiles.c.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if owned is None:
            raise DomainError(ErrorCode.NOT_FOUND)

    async def get(self, profile_id: UUID, account_id: UUID) -> OnboardingState:
        await self.set_owner(account_id)
        row = (
            (
                await self._session.execute(
                    select(onboarding_states).where(
                        onboarding_states.c.profile_id == profile_id,
                        onboarding_states.c.account_id == account_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return _state(row)

    async def add(self, state: OnboardingState) -> None:
        await self.set_owner(state.account_id)
        await self._session.execute(
            onboarding_states.insert().values(
                profile_id=state.profile_id,
                account_id=state.account_id,
                entry_path=state.entry_path.value,
                detected_band=None,
                placement_confidence=None,
                skill_profile=[],
                placement_choice=None,
                calibration_sessions_remaining=state.calibration_sessions_remaining,
                version=state.version,
                created_at=state.created_at,
                updated_at=state.updated_at,
            )
        )

    async def update(self, state: OnboardingState, expected_version: int) -> None:
        await self.set_owner(state.account_id)
        updated = await self._session.scalar(
            onboarding_states.update()
            .where(
                onboarding_states.c.profile_id == state.profile_id,
                onboarding_states.c.account_id == state.account_id,
                onboarding_states.c.version == expected_version,
            )
            .values(
                entry_path=state.entry_path.value,
                detected_band=(None if state.detected_band is None else state.detected_band.value),
                placement_confidence=state.placement_confidence,
                skill_profile=_serialize_skills(state.skill_profile),
                placement_choice=(
                    None if state.placement_choice is None else state.placement_choice.value
                ),
                calibration_sessions_remaining=state.calibration_sessions_remaining,
                version=state.version,
                updated_at=state.updated_at,
            )
            .returning(onboarding_states.c.profile_id)
        )
        if updated is None:
            raise DomainError(ErrorCode.VERSION_CONFLICT)


class OnboardingApplicationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    @staticmethod
    def _session(uow: SqlAlchemyUnitOfWork) -> AsyncSession:
        if uow.session is None:
            raise RuntimeError("onboarding unit of work is not active")
        return uow.session

    def _receipt(
        self,
        *,
        command_type: str,
        account_id: UUID,
        profile_id: UUID,
        key: str,
        fingerprint: str,
        expected_version: int | None,
    ) -> CommandReceipt:
        now = self._clock.now()
        return CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=account_id,
            aggregate_type="onboarding_state",
            aggregate_id=profile_id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + timedelta(hours=24),
        )

    async def _event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        state: OnboardingState,
        command_id: UUID,
        context: RequestContext,
    ) -> None:
        now = self._clock.now()
        await SqlEventOutboxRepository(session, self._ids).add(
            DomainEvent(
                event_id=self._ids.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type="onboarding_state",
                aggregate_id=state.profile_id,
                aggregate_version=state.version,
                actor_type="account",
                actor_id=state.account_id,
                profile_id=state.profile_id,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=command_id,
                privacy_class="personal",
                policy_versions={"placement": 1},
                payload={
                    "entry_path": state.entry_path.value,
                    "detected_band": (
                        None if state.detected_band is None else state.detected_band.value
                    ),
                    "placement_choice": (
                        None if state.placement_choice is None else state.placement_choice.value
                    ),
                },
                expires_at=now + timedelta(days=180),
                subject_type="profile",
                subject_id=state.profile_id,
            ),
            destinations=("language_profiles.events",),
        )

    async def _complete(
        self, store: SqlCommandReceiptStore, receipt: CommandReceipt, state: OnboardingState
    ) -> None:
        await store.complete(
            command_id=receipt.command_id,
            status="succeeded",
            result_ref=state.profile_id,
            result_payload={"resource_id": str(state.profile_id), "version": state.version},
        )

    async def get(self, profile_id: UUID, account_id: UUID) -> OnboardingState:
        async with self._uow() as uow:
            state = await SqlOnboardingRepository(self._session(uow)).get(profile_id, account_id)
            await uow.commit()
            return state
        raise RuntimeError("onboarding lookup was suppressed")

    async def start(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        entry_path: EntryPath,
        idempotency_key: str,
        context: RequestContext,
    ) -> OnboardingState:
        receipt = self._receipt(
            command_type="StartOnboarding",
            account_id=account_id,
            profile_id=profile_id,
            key=idempotency_key,
            fingerprint=canonical_json_fingerprint({"entry_path": entry_path.value}),
            expected_version=None,
        )
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlOnboardingRepository(session)
            await repository.require_profile(profile_id, account_id)
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                result = await repository.get(profile_id, account_id)
                await uow.commit()
                return result
            try:
                existing = await repository.get(profile_id, account_id)
            except DomainError as error:
                if error.code is not ErrorCode.NOT_FOUND:
                    raise
            else:
                if existing.entry_path is not entry_path:
                    raise DomainError(ErrorCode.INVALID_TRANSITION)
                await self._complete(store, receipt, existing)
                await uow.commit()
                return existing
            state = OnboardingState.start(
                profile_id=profile_id,
                account_id=account_id,
                entry_path=entry_path,
                now=self._clock.now(),
            )
            await repository.add(state)
            await self._event(
                session,
                event_type="onboarding_started",
                state=state,
                command_id=receipt.command_id,
                context=context,
            )
            await self._complete(store, receipt, state)
            await uow.commit()
            return state
        raise RuntimeError("onboarding start was suppressed")

    async def record_placement(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        detected_band: PlacementBand,
        confidence: float,
        skills: tuple[SkillEstimate, ...],
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> OnboardingState:
        fingerprint = canonical_json_fingerprint(
            {
                "detected_band": detected_band.value,
                "confidence": confidence,
                "skills": _serialize_skills(skills),
            }
        )
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlOnboardingRepository(session)
            store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type="RecordPlacementProfile",
                account_id=account_id,
                profile_id=profile_id,
                key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
            )
            reservation = await store.reserve(receipt)
            if not reservation.created:
                result = await repository.get(profile_id, account_id)
                await uow.commit()
                return result
            state = await repository.get(profile_id, account_id)
            placed = state.record_placement(
                detected_band=detected_band,
                confidence=confidence,
                skills=skills,
                expected_version=expected_version,
                now=self._clock.now(),
            )
            await repository.update(placed, expected_version)
            await self._event(
                session,
                event_type="placement_profile_recorded",
                state=placed,
                command_id=receipt.command_id,
                context=context,
            )
            await self._complete(store, receipt, placed)
            await uow.commit()
            return placed
        raise RuntimeError("placement recording was suppressed")

    async def choose(
        self,
        *,
        profile_id: UUID,
        account_id: UUID,
        choice: PlacementChoice,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> OnboardingState:
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlOnboardingRepository(session)
            store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type="ChoosePlacement",
                account_id=account_id,
                profile_id=profile_id,
                key=idempotency_key,
                fingerprint=canonical_json_fingerprint({"choice": choice.value}),
                expected_version=expected_version,
            )
            reservation = await store.reserve(receipt)
            if not reservation.created:
                result = await repository.get(profile_id, account_id)
                await uow.commit()
                return result
            state = await repository.get(profile_id, account_id)
            chosen = state.choose(
                choice,
                expected_version=expected_version,
                now=self._clock.now(),
            )
            await repository.update(chosen, expected_version)
            profile_repository = SqlLanguageProfileRepository(session)
            profile = await profile_repository.get_owned(profile_id, account_id)
            if profile.status in {
                LanguageProfileStatus.ONBOARDING,
                LanguageProfileStatus.FOUNDATIONS,
            }:
                await profile_repository.update(
                    profile.transition(LanguageProfileStatus.ACTIVE, now=self._clock.now())
                )
            await self._event(
                session,
                event_type="placement_choice_recorded",
                state=chosen,
                command_id=receipt.command_id,
                context=context,
            )
            await self._complete(store, receipt, chosen)
            await uow.commit()
            return chosen
        raise RuntimeError("placement choice was suppressed")

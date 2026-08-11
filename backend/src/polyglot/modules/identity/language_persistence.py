from dataclasses import asdict
from datetime import timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.identity.application import RequestContext
from polyglot.modules.identity.languages import (
    AccountLanguage,
    LanguageRelationship,
    SelfAssessedBand,
)
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.persistence.models import metadata
from polyglot.platform.persistence.records import CommandReceipt, DomainEvent
from polyglot.platform.persistence.repositories import (
    SqlCommandReceiptStore,
    SqlEventOutboxRepository,
)
from polyglot.platform.persistence.uow import SqlAlchemyUnitOfWork

account_languages = Table(
    "account_languages",
    metadata,
    Column("account_language_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id"),
        nullable=False,
    ),
    Column(
        "variety_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_varieties.variety_id"),
        nullable=False,
    ),
    Column("relationship", String(24), nullable=False),
    Column("self_assessed_band", String(24), nullable=False),
    Column("use_for_explanations", Boolean, nullable=False),
    Column("use_for_contrasts", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True)),
    schema="identity",
)


def _language(row: RowMapping) -> AccountLanguage:
    return AccountLanguage(
        account_language_id=row["account_language_id"],
        account_id=row["account_id"],
        variety_id=row["variety_id"],
        relationship=LanguageRelationship(row["relationship"]),
        self_assessed_band=SelfAssessedBand(row["self_assessed_band"]),
        use_for_explanations=row["use_for_explanations"],
        use_for_contrasts=row["use_for_contrasts"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived_at=row["archived_at"],
    )


class SqlAccountLanguageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_owner(self, account_id: UUID) -> None:
        await self._session.execute(
            text("SELECT set_config('app.user_id', :account_id, true)"),
            {"account_id": str(account_id)},
        )

    async def list_owned(self, account_id: UUID) -> tuple[AccountLanguage, ...]:
        await self.set_owner(account_id)
        rows = (
            await self._session.execute(
                select(account_languages)
                .where(
                    account_languages.c.account_id == account_id,
                    account_languages.c.archived_at.is_(None),
                )
                .order_by(account_languages.c.relationship, account_languages.c.created_at)
            )
        ).mappings()
        return tuple(_language(row) for row in rows)

    async def get_owned(self, language_id: UUID, account_id: UUID) -> AccountLanguage:
        await self.set_owner(account_id)
        row = (
            (
                await self._session.execute(
                    select(account_languages).where(
                        account_languages.c.account_language_id == language_id,
                        account_languages.c.account_id == account_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return _language(row)

    async def find_active(self, account_id: UUID, variety_id: UUID) -> AccountLanguage | None:
        await self.set_owner(account_id)
        row = (
            (
                await self._session.execute(
                    select(account_languages).where(
                        account_languages.c.account_id == account_id,
                        account_languages.c.variety_id == variety_id,
                        account_languages.c.archived_at.is_(None),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _language(row)

    async def add(self, language: AccountLanguage) -> None:
        await self.set_owner(language.account_id)
        await self._session.execute(
            account_languages.insert().values(
                **{
                    **asdict(language),
                    "relationship": language.relationship.value,
                    "self_assessed_band": language.self_assessed_band.value,
                }
            )
        )

    async def update(self, language: AccountLanguage, expected_version: int) -> None:
        await self.set_owner(language.account_id)
        updated = await self._session.scalar(
            account_languages.update()
            .where(
                account_languages.c.account_language_id == language.account_language_id,
                account_languages.c.account_id == language.account_id,
                account_languages.c.version == expected_version,
            )
            .values(
                relationship=language.relationship.value,
                self_assessed_band=language.self_assessed_band.value,
                use_for_explanations=language.use_for_explanations,
                use_for_contrasts=language.use_for_contrasts,
                version=language.version,
                updated_at=language.updated_at,
                archived_at=language.archived_at,
            )
            .returning(account_languages.c.account_language_id)
        )
        if updated is None:
            raise DomainError(ErrorCode.VERSION_CONFLICT)


class AccountLanguageApplicationService:
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
            raise RuntimeError("account language unit of work is not active")
        return uow.session

    async def list_languages(self, account_id: UUID) -> tuple[AccountLanguage, ...]:
        async with self._uow() as uow:
            result = await SqlAccountLanguageRepository(self._session(uow)).list_owned(account_id)
            await uow.commit()
            return result
        raise RuntimeError("account language listing was suppressed")

    def _receipt(
        self,
        *,
        command_type: str,
        account_id: UUID,
        aggregate_id: UUID,
        key: str,
        fingerprint: str,
        expected_version: int | None,
    ) -> CommandReceipt:
        now = self._clock.now()
        return CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=account_id,
            aggregate_type="account_language",
            aggregate_id=aggregate_id,
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
        language: AccountLanguage,
        command_id: UUID,
        context: RequestContext,
    ) -> None:
        now = self._clock.now()
        await SqlEventOutboxRepository(session, self._ids).add(
            DomainEvent(
                event_id=self._ids.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type="account_language",
                aggregate_id=language.account_language_id,
                aggregate_version=language.version,
                actor_type="account",
                actor_id=language.account_id,
                profile_id=None,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=command_id,
                privacy_class="personal",
                policy_versions={"account_languages": 1},
                payload={
                    "variety_id": str(language.variety_id),
                    "relationship": language.relationship.value,
                    "grants_mastery": False,
                },
                expires_at=now + timedelta(days=180),
                subject_type="account",
                subject_id=language.account_id,
            ),
            destinations=("identity.events",),
        )

    async def create_language(
        self,
        *,
        account_id: UUID,
        variety_id: UUID,
        relationship: LanguageRelationship,
        self_assessed_band: SelfAssessedBand,
        use_for_explanations: bool,
        use_for_contrasts: bool,
        idempotency_key: str,
        context: RequestContext,
    ) -> AccountLanguage:
        now = self._clock.now()
        language_id = self._ids.new()
        fingerprint = canonical_json_fingerprint(
            {
                "variety_id": str(variety_id),
                "relationship": relationship.value,
                "self_assessed_band": self_assessed_band.value,
                "use_for_explanations": use_for_explanations,
                "use_for_contrasts": use_for_contrasts,
            }
        )
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlAccountLanguageRepository(session)
            receipt_store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type="CreateAccountLanguage",
                account_id=account_id,
                aggregate_id=account_id,
                key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
            )
            reservation = await receipt_store.reserve(receipt)
            if not reservation.created:
                stored_id = cast(UUID, reservation.receipt.result_ref)
                result = await repository.get_owned(stored_id, account_id)
                await uow.commit()
                return result
            if await repository.find_active(account_id, variety_id) is not None:
                raise DomainError(ErrorCode.IDENTITY_CONFLICT)
            language = AccountLanguage.create(
                account_language_id=language_id,
                account_id=account_id,
                variety_id=variety_id,
                relationship=relationship,
                self_assessed_band=self_assessed_band,
                use_for_explanations=use_for_explanations,
                use_for_contrasts=use_for_contrasts,
                now=now,
            )
            await repository.add(language)
            await self._event(
                session,
                event_type="account_language_declared",
                language=language,
                command_id=receipt.command_id,
                context=context,
            )
            await receipt_store.complete(
                command_id=receipt.command_id,
                status="succeeded",
                result_ref=language.account_language_id,
                result_payload={
                    "resource_id": str(language.account_language_id),
                    "version": language.version,
                },
            )
            await uow.commit()
            return language
        raise RuntimeError("account language creation was suppressed")

    async def revise_language(
        self,
        *,
        account_id: UUID,
        language_id: UUID,
        relationship: LanguageRelationship,
        self_assessed_band: SelfAssessedBand,
        use_for_explanations: bool,
        use_for_contrasts: bool,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> AccountLanguage:
        fingerprint = canonical_json_fingerprint(
            {
                "relationship": relationship.value,
                "self_assessed_band": self_assessed_band.value,
                "use_for_explanations": use_for_explanations,
                "use_for_contrasts": use_for_contrasts,
            }
        )
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlAccountLanguageRepository(session)
            receipt_store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type="ReviseAccountLanguage",
                account_id=account_id,
                aggregate_id=language_id,
                key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
            )
            reservation = await receipt_store.reserve(receipt)
            if not reservation.created:
                result = await repository.get_owned(language_id, account_id)
                await uow.commit()
                return result
            current = await repository.get_owned(language_id, account_id)
            revised = current.revise(
                relationship=relationship,
                self_assessed_band=self_assessed_band,
                use_for_explanations=use_for_explanations,
                use_for_contrasts=use_for_contrasts,
                expected_version=expected_version,
                now=self._clock.now(),
            )
            await repository.update(revised, expected_version)
            await self._event(
                session,
                event_type="account_language_revised",
                language=revised,
                command_id=receipt.command_id,
                context=context,
            )
            await receipt_store.complete(
                command_id=receipt.command_id,
                status="succeeded",
                result_ref=revised.account_language_id,
                result_payload={
                    "resource_id": str(revised.account_language_id),
                    "version": revised.version,
                },
            )
            await uow.commit()
            return revised
        raise RuntimeError("account language revision was suppressed")

    async def archive_language(
        self,
        *,
        account_id: UUID,
        language_id: UUID,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> AccountLanguage:
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlAccountLanguageRepository(session)
            receipt_store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type="ArchiveAccountLanguage",
                account_id=account_id,
                aggregate_id=language_id,
                key=idempotency_key,
                fingerprint=canonical_json_fingerprint({}),
                expected_version=expected_version,
            )
            reservation = await receipt_store.reserve(receipt)
            if not reservation.created:
                result = await repository.get_owned(language_id, account_id)
                await uow.commit()
                return result
            current = await repository.get_owned(language_id, account_id)
            archived = current.archive(
                expected_version=expected_version,
                now=self._clock.now(),
            )
            await repository.update(archived, expected_version)
            await self._event(
                session,
                event_type="account_language_archived",
                language=archived,
                command_id=receipt.command_id,
                context=context,
            )
            await receipt_store.complete(
                command_id=receipt.command_id,
                status="succeeded",
                result_ref=archived.account_language_id,
                result_payload={
                    "resource_id": str(archived.account_language_id),
                    "version": archived.version,
                },
            )
            await uow.commit()
            return archived
        raise RuntimeError("account language archive was suppressed")

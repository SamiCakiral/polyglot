from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.content.persistence import (
    ContentRevisionPage,
    SqlContentRepository,
    StoredContentRevision,
    StoredValidationReport,
)
from polyglot.modules.identity.application import RECENT_AUTHENTICATION, RequestContext
from polyglot.modules.identity.persistence import auth_sessions
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
CONTENT_EVENT_DESTINATION = "content.events"


@dataclass(frozen=True, slots=True)
class EditorialActor:
    actor_id: UUID
    roles: frozenset[str]
    session_id: UUID


@dataclass(frozen=True, slots=True)
class ContentReference:
    reference_kind: str
    revision_id: UUID

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "reference_kind": self.reference_kind,
            "revision_id": str(self.revision_id),
        }


@dataclass(frozen=True, slots=True)
class CreateContentDraft:
    actor: EditorialActor
    content_type: str
    variety_id: UUID
    payload: Mapping[str, JsonValue]
    provenance_id: UUID
    rights_ref: str
    pinned_revision_refs: tuple[ContentReference, ...]
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ReviseContentDraft:
    actor: EditorialActor
    revision_id: UUID
    payload: Mapping[str, JsonValue]
    provenance_id: UUID
    rights_ref: str
    pinned_revision_refs: tuple[ContentReference, ...]
    expected_version: int
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ValidateContentRevision:
    actor: EditorialActor
    revision_id: UUID
    validator_set_revision_id: UUID
    expected_version: int
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ApproveContentRevision:
    actor: EditorialActor
    revision_id: UUID
    expected_version: int
    reason_code: str
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class PublishContentRevision:
    actor: EditorialActor
    revision_id: UUID
    publication_provenance_id: UUID
    channel_code: str
    compatibility_range: str
    expected_version: int
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class RetireContentRevision:
    actor: EditorialActor
    content_id: UUID
    revision_id: UUID
    expected_version: int
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ContentMutationResult:
    revision: StoredContentRevision
    version: int
    replayed: bool = False
    report_id: UUID | None = None
    manifest_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator_code: str
    severity: str
    path: str
    message_code: str
    redacted_value: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: str
    findings: tuple[ValidationFinding, ...]


class ContentValidator(Protocol):
    async def validate(self, payload: Mapping[str, JsonValue]) -> ValidationResult: ...


class DeterministicContentValidator:
    async def validate(self, payload: Mapping[str, JsonValue]) -> ValidationResult:
        if payload.get("human_required") is True:
            return ValidationResult(
                "human_required",
                (
                    ValidationFinding(
                        validator_code="content.human_review",
                        severity="human_required",
                        path="$",
                        message_code="human_review.required",
                    ),
                ),
            )
        if payload.get("blocking") is True:
            return ValidationResult(
                "failed",
                (
                    ValidationFinding(
                        validator_code="content.structure",
                        severity="blocking",
                        path="$",
                        message_code="content.invalid",
                    ),
                ),
            )
        return ValidationResult("passed", ())


class ReauthenticationPolicy(Protocol):
    async def is_recent(
        self,
        *,
        session: AsyncSession,
        actor_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> bool: ...


class SqlRecentAuthenticationPolicy:
    async def is_recent(
        self,
        *,
        session: AsyncSession,
        actor_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> bool:
        authenticated_at = await session.scalar(
            select(auth_sessions.c.authenticated_at).where(
                auth_sessions.c.session_id == session_id,
                auth_sessions.c.account_id == actor_id,
                auth_sessions.c.revoked_at.is_(None),
            )
        )
        return (
            authenticated_at is not None
            and timedelta(0) <= now - authenticated_at <= RECENT_AUTHENTICATION
        )


class FailureInjector(Protocol):
    async def checkpoint(self, stage: str) -> None: ...


class NoFailureInjector:
    async def checkpoint(self, stage: str) -> None:
        del stage


class KnownRightsPolicy:
    _PREFIXES = ("rights:fixture:", "rights:human:", "rights:import:", "rights:tool:")

    def require_publishable(self, rights_ref: str) -> None:
        if not rights_ref.startswith(self._PREFIXES):
            raise DomainError(ErrorCode.LICENSE_MISSING)

    def historical_interpretable(self, rights_ref: str) -> bool:
        return rights_ref.startswith(self._PREFIXES)


CommandAction = Callable[
    [SqlContentRepository, CommandReceipt, datetime], Awaitable[ContentMutationResult]
]


class ContentApplicationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        validator: ContentValidator | None = None,
        reauthentication_policy: ReauthenticationPolicy | None = None,
        failure_injector: FailureInjector | None = None,
        rights_policy: KnownRightsPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or Uuid7Generator(self._clock)
        self._validator = validator or DeterministicContentValidator()
        self._reauthentication = reauthentication_policy or SqlRecentAuthenticationPolicy()
        self._failure_injector = failure_injector or NoFailureInjector()
        self._rights = rights_policy or KnownRightsPolicy()

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    @staticmethod
    def _session(uow: SqlAlchemyUnitOfWork) -> AsyncSession:
        if uow.session is None:
            raise RuntimeError("content unit of work is not active")
        return uow.session

    @staticmethod
    def _require_role(actor: EditorialActor, *allowed: str) -> None:
        if not actor.roles.intersection(allowed) or "worker" in actor.roles:
            raise DomainError(ErrorCode.FORBIDDEN)

    def _receipt(
        self,
        *,
        command_type: str,
        actor: EditorialActor,
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
            actor_id=actor.actor_id,
            aggregate_type="content_item",
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
    def _raise_replayed_error(receipt: CommandReceipt) -> None:
        if receipt.status == "started":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if receipt.status in {"rejected", "failed"}:
            payload = receipt.result_payload or {}
            raise DomainError(cast(str, payload.get("code", ErrorCode.INTERNAL_ERROR.value)))

    async def _execute(
        self,
        *,
        command_type: str,
        actor: EditorialActor,
        aggregate_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_version: int | None,
        action: CommandAction,
    ) -> ContentMutationResult:
        now = self._clock.now()
        async with self._uow() as uow:
            session = self._session(uow)
            repository = SqlContentRepository(session)
            store = SqlCommandReceiptStore(session)
            receipt = self._receipt(
                command_type=command_type,
                actor=actor,
                aggregate_id=aggregate_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                if reservation.receipt.result_ref is None:
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                revision = await repository.get_revision(reservation.receipt.result_ref)
                result_payload = reservation.receipt.result_payload or {}
                version = result_payload.get("version")
                if not isinstance(version, int):
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                report_id, manifest_id = await repository.get_command_proofs(
                    reservation.receipt.command_id
                )
                await uow.commit()
                return ContentMutationResult(
                    revision,
                    version,
                    replayed=True,
                    report_id=report_id,
                    manifest_id=manifest_id,
                )

            savepoint = await session.begin_nested()
            try:
                await repository.begin_command(reservation.receipt.command_id)
                result = await action(repository, reservation.receipt, now)
                await self._failure_injector.checkpoint("after_event")
                await store.complete(
                    command_id=reservation.receipt.command_id,
                    status="succeeded",
                    result_ref=result.revision.content_revision_id,
                    result_payload={
                        "resource_id": str(result.revision.content_revision_id),
                        "version": result.version,
                    },
                )
                await savepoint.commit()
            except DomainError as error:
                await savepoint.rollback()
                await store.complete(
                    command_id=reservation.receipt.command_id,
                    status="rejected",
                    result_ref=None,
                    result_payload={"code": error.code.value, "message_key": error.message_key},
                )
                await uow.commit()
                raise
            except Exception:
                await savepoint.rollback()
                await store.complete(
                    command_id=reservation.receipt.command_id,
                    status="failed",
                    result_ref=None,
                    result_payload={
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message_key": "errors.internal_error",
                    },
                )
                await uow.commit()
                raise
            await uow.commit()
            return result
        raise RuntimeError("content command was unexpectedly suppressed")

    async def _event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        content_id: UUID,
        revision_id: UUID,
        version: int,
        actor: EditorialActor,
        command_id: UUID,
        context: RequestContext,
        now: datetime,
        extra: dict[str, JsonValue] | None = None,
    ) -> None:
        payload: dict[str, JsonValue] = {
            "schema_version": 1,
            "content_revision_id": str(revision_id),
        }
        if extra:
            payload.update(extra)
        await SqlEventOutboxRepository(session, self._id_generator).add(
            DomainEvent(
                event_id=self._id_generator.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type="content_item",
                aggregate_id=content_id,
                aggregate_version=version,
                actor_type="account",
                actor_id=actor.actor_id,
                profile_id=None,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=command_id,
                privacy_class="public",
                policy_versions={"content": 1},
                payload=payload,
            ),
            destinations=(CONTENT_EVENT_DESTINATION,),
        )

    async def create_draft(self, command: CreateContentDraft) -> ContentMutationResult:
        self._require_role(command.actor, "author")
        payload = dict(command.payload)
        references = tuple(reference.as_json() for reference in command.pinned_revision_refs)
        fingerprint = canonical_json_fingerprint(
            {
                "content_type": command.content_type,
                "variety_id": str(command.variety_id),
                "payload": payload,
                "provenance_id": str(command.provenance_id),
                "rights_ref": command.rights_ref,
                "pinned_revision_refs": list(references),
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            self._rights.require_publishable(command.rights_ref)
            await repository.require_provenance(command.provenance_id)
            content_id = self._id_generator.new()
            revision_id = self._id_generator.new()
            revision = await repository.create_item_and_draft(
                content_id=content_id,
                content_revision_id=revision_id,
                content_type=command.content_type,
                variety_id=command.variety_id,
                author_id=command.actor.actor_id,
                provenance_id=command.provenance_id,
                payload=payload,
                rights_ref=command.rights_ref,
                pinned_revision_refs=references,
                now=now,
            )
            await self._event(
                repository._session,
                event_type="content_draft_created",
                content_id=content_id,
                revision_id=revision_id,
                version=1,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
            )
            return ContentMutationResult(revision, 1)

        return await self._execute(
            command_type="CreateContentDraft",
            actor=command.actor,
            aggregate_id=command.actor.actor_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=None,
            action=action,
        )

    async def revise_draft(self, command: ReviseContentDraft) -> ContentMutationResult:
        self._require_role(command.actor, "author")
        payload = dict(command.payload)
        references = tuple(reference.as_json() for reference in command.pinned_revision_refs)
        fingerprint = canonical_json_fingerprint(
            {
                "revision_id": str(command.revision_id),
                "payload": payload,
                "provenance_id": str(command.provenance_id),
                "rights_ref": command.rights_ref,
                "pinned_revision_refs": list(references),
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            item, source = await repository.lock_item_for_revision(
                command.revision_id, expected_version=command.expected_version
            )
            if item.editorial_owner_id != command.actor.actor_id:
                raise DomainError(ErrorCode.FORBIDDEN)
            if source.status in {"validating", "validated", "abandoned"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            self._rights.require_publishable(command.rights_ref)
            await repository.require_provenance(command.provenance_id)
            revision = await repository.add_revised_draft(
                source=source,
                content_revision_id=self._id_generator.new(),
                actor_id=command.actor.actor_id,
                payload=payload,
                provenance_id=command.provenance_id,
                rights_ref=command.rights_ref,
                pinned_revision_refs=references,
                now=now,
            )
            version = await repository.bump_version(item.content_id, command.expected_version)
            await self._event(
                repository._session,
                event_type="content_draft_revised",
                content_id=item.content_id,
                revision_id=revision.content_revision_id,
                version=version,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                extra={"supersedes_revision_id": str(source.content_revision_id)},
            )
            return ContentMutationResult(revision, version)

        return await self._execute(
            command_type="ReviseContentDraft",
            actor=command.actor,
            aggregate_id=command.revision_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=command.expected_version,
            action=action,
        )

    async def validate_revision(
        self, command: ValidateContentRevision
    ) -> ContentMutationResult:
        self._require_role(command.actor, "author", "reviewer")
        fingerprint = canonical_json_fingerprint(
            {
                "revision_id": str(command.revision_id),
                "validator_set_revision_id": str(command.validator_set_revision_id),
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            item, revision = await repository.lock_item_for_revision(
                command.revision_id, expected_version=command.expected_version
            )
            if (
                "reviewer" not in command.actor.roles
                and item.editorial_owner_id != command.actor.actor_id
            ):
                raise DomainError(ErrorCode.FORBIDDEN)
            if revision.status != "draft":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await repository.begin_validation(command.revision_id)
            try:
                validation = await self._validator.validate(revision.payload)
            except DomainError:
                raise
            except Exception as error:
                raise DomainError(ErrorCode.VALIDATOR_UNAVAILABLE) from error
            findings: tuple[dict[str, object], ...] = tuple(
                {
                    "finding_id": self._id_generator.new(),
                    "ordinal": ordinal,
                    "validator_code": finding.validator_code,
                    "severity": finding.severity,
                    "path": finding.path,
                    "message_code": finding.message_code,
                    "redacted_value": finding.redacted_value,
                    "resolved_by_revision_id": None,
                }
                for ordinal, finding in enumerate(validation.findings, start=1)
            )
            checksum_findings: list[JsonValue] = [
                {
                    "ordinal": ordinal,
                    "validator_code": finding.validator_code,
                    "severity": finding.severity,
                    "path": finding.path,
                    "message_code": finding.message_code,
                    "redacted_value": finding.redacted_value,
                }
                for ordinal, finding in enumerate(validation.findings, start=1)
            ]
            summary_checksum = canonical_json_fingerprint(
                {
                    "status": validation.status,
                    "findings": checksum_findings,
                }
            )
            report_id = self._id_generator.new()
            updated = await repository.complete_validation(
                content_revision_id=command.revision_id,
                report_id=report_id,
                command_id=receipt.command_id,
                validator_set_revision_id=command.validator_set_revision_id,
                status=validation.status,
                summary_checksum=summary_checksum,
                findings=findings,
                now=now,
            )
            version = await repository.bump_version(item.content_id, command.expected_version)
            event_type = "content_validated"
            if validation.status != "passed":
                event_type = "content_validation_failed"
            await self._event(
                repository._session,
                event_type=event_type,
                content_id=item.content_id,
                revision_id=command.revision_id,
                version=version,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                extra={"validation_report_id": str(report_id), "status": validation.status},
            )
            return ContentMutationResult(updated, version, report_id=report_id)

        return await self._execute(
            command_type="ValidateContentRevision",
            actor=command.actor,
            aggregate_id=command.revision_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=command.expected_version,
            action=action,
        )

    async def approve_revision(
        self, command: ApproveContentRevision
    ) -> ContentMutationResult:
        self._require_role(command.actor, "reviewer")
        fingerprint = canonical_json_fingerprint(
            {
                "revision_id": str(command.revision_id),
                "reason_code": command.reason_code,
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            item, revision = await repository.lock_item_for_revision(
                command.revision_id, expected_version=command.expected_version
            )
            if command.actor.actor_id == revision.created_by_actor_id:
                raise DomainError(ErrorCode.SELF_APPROVAL_FORBIDDEN)
            if revision.status != "validated":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            updated = await repository.approve(
                content_revision_id=command.revision_id,
                decision_id=self._id_generator.new(),
                command_id=receipt.command_id,
                author_id=revision.created_by_actor_id,
                reviewer_id=command.actor.actor_id,
                reason_code=command.reason_code,
                now=now,
            )
            version = await repository.bump_version(item.content_id, command.expected_version)
            await self._event(
                repository._session,
                event_type="content_approved",
                content_id=item.content_id,
                revision_id=command.revision_id,
                version=version,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
            )
            return ContentMutationResult(updated, version)

        return await self._execute(
            command_type="ApproveContentRevision",
            actor=command.actor,
            aggregate_id=command.revision_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=command.expected_version,
            action=action,
        )

    async def publish_revision(
        self, command: PublishContentRevision
    ) -> ContentMutationResult:
        self._require_role(command.actor, "reviewer", "admin")
        fingerprint = canonical_json_fingerprint(
            {
                "revision_id": str(command.revision_id),
                "publication_provenance_id": str(command.publication_provenance_id),
                "channel_code": command.channel_code,
                "compatibility_range": command.compatibility_range,
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            if not await self._reauthentication.is_recent(
                session=repository._session,
                actor_id=command.actor.actor_id,
                session_id=command.actor.session_id,
                now=now,
            ):
                raise DomainError(ErrorCode.UNAUTHENTICATED)
            item, revision = await repository.lock_item_for_revision(
                command.revision_id, expected_version=command.expected_version
            )
            if revision.status != "approved":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            self._rights.require_publishable(revision.rights_ref)
            await repository.require_provenance(command.publication_provenance_id)
            references = await repository.resolve_published_references(
                variety_id=item.variety_id,
                references=revision.pinned_revision_refs,
            )
            manifest_id = self._id_generator.new()
            manifest_checksum = canonical_json_fingerprint(
                {
                    "content_id": str(item.content_id),
                    "content_revision_id": str(revision.content_revision_id),
                    "payload_checksum": revision.payload_checksum,
                    "channel_code": command.channel_code,
                    "compatibility_range": command.compatibility_range,
                    "references": [
                        {
                            "revision_id": str(reference.revision_id),
                            "reference_kind": reference.reference_kind,
                            "checksum": reference.checksum,
                            "provenance_id": str(reference.provenance_id),
                            "rights_ref": reference.rights_ref,
                        }
                        for reference in references
                    ],
                }
            )
            updated = await repository.publish(
                content_id=item.content_id,
                content_revision_id=command.revision_id,
                manifest_id=manifest_id,
                command_id=receipt.command_id,
                publication_provenance_id=command.publication_provenance_id,
                channel_code=command.channel_code,
                compatibility_range=command.compatibility_range,
                manifest_checksum=manifest_checksum,
                references=references,
                now=now,
            )
            version = await repository.bump_version(item.content_id, command.expected_version)
            await self._event(
                repository._session,
                event_type="content_published",
                content_id=item.content_id,
                revision_id=command.revision_id,
                version=version,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                extra={"publication_manifest_id": str(manifest_id)},
            )
            return ContentMutationResult(updated, version, manifest_id=manifest_id)

        return await self._execute(
            command_type="PublishContentRevision",
            actor=command.actor,
            aggregate_id=command.revision_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=command.expected_version,
            action=action,
        )

    async def retire_revision(self, command: RetireContentRevision) -> ContentMutationResult:
        self._require_role(command.actor, "reviewer", "admin")
        fingerprint = canonical_json_fingerprint(
            {
                "content_id": str(command.content_id),
                "revision_id": str(command.revision_id),
            }
        )

        async def action(
            repository: SqlContentRepository, receipt: CommandReceipt, now: datetime
        ) -> ContentMutationResult:
            item, revision = await repository.lock_item_for_revision(
                command.revision_id, expected_version=command.expected_version
            )
            if item.content_id != command.content_id:
                raise DomainError(ErrorCode.NOT_FOUND)
            if revision.status != "published":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if not self._rights.historical_interpretable(revision.rights_ref):
                raise DomainError(ErrorCode.HISTORICAL_RIGHTS_CONFLICT)
            await repository.retire(content_revision_id=command.revision_id, now=now)
            updated = await repository.get_revision(command.revision_id)
            version = await repository.bump_version(item.content_id, command.expected_version)
            await self._event(
                repository._session,
                event_type="content_retired",
                content_id=item.content_id,
                revision_id=command.revision_id,
                version=version,
                actor=command.actor,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
            )
            return ContentMutationResult(updated, version)

        return await self._execute(
            command_type="RetireContentRevision",
            actor=command.actor,
            aggregate_id=command.revision_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            expected_version=command.expected_version,
            action=action,
        )

    async def list_drafts(
        self,
        *,
        actor: EditorialActor,
        limit: int,
        cursor: str | None,
    ) -> ContentRevisionPage:
        self._require_role(actor, "author", "reviewer")
        async with self._uow() as uow:
            repository = SqlContentRepository(self._session(uow))
            page = await repository.list_drafts(
                actor_id=actor.actor_id,
                reviewer="reviewer" in actor.roles,
                limit=limit,
                cursor=cursor,
            )
            await uow.commit()
            return page
        raise RuntimeError("content query was unexpectedly suppressed")

    async def get_draft(
        self,
        *,
        actor: EditorialActor,
        revision_id: UUID,
    ) -> StoredContentRevision:
        self._require_role(actor, "author", "reviewer")
        async with self._uow() as uow:
            repository = SqlContentRepository(self._session(uow))
            revision = await repository.get_draft_for_actor(
                revision_id,
                actor_id=actor.actor_id,
                reviewer="reviewer" in actor.roles,
            )
            await uow.commit()
            return revision
        raise RuntimeError("content query was unexpectedly suppressed")

    async def get_history(
        self,
        *,
        actor: EditorialActor,
        content_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> ContentRevisionPage:
        self._require_role(actor, "author", "reviewer")
        async with self._uow() as uow:
            repository = SqlContentRepository(self._session(uow))
            page = await repository.get_history_for_actor(
                content_id,
                actor_id=actor.actor_id,
                reviewer="reviewer" in actor.roles,
                limit=limit,
                cursor=cursor,
            )
            await uow.commit()
            return page
        raise RuntimeError("content query was unexpectedly suppressed")

    async def get_validation_report(
        self,
        *,
        actor: EditorialActor,
        report_id: UUID,
    ) -> StoredValidationReport:
        self._require_role(actor, "author", "reviewer")
        async with self._uow() as uow:
            repository = SqlContentRepository(self._session(uow))
            report = await repository.get_validation_report_for_actor(
                report_id,
                actor_id=actor.actor_id,
                reviewer="reviewer" in actor.roles,
            )
            await uow.commit()
            return report
        raise RuntimeError("content query was unexpectedly suppressed")

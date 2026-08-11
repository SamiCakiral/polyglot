from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_bytes
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import (
    command_receipts,
    domain_events,
    inbox_receipts,
    job_attempts,
    job_claims,
    jobs,
    outbox_messages,
)
from polyglot.platform.persistence.records import (
    CommandReceipt,
    CommandReservation,
    DomainEvent,
    InboxReceipt,
    JobClaim,
    OutboxClaim,
    RetentionPurgeResult,
)

_MAX_RECEIPT_REPLAY_BYTES = 512


def _invalid_receipt_replay() -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION_FAILED,
        field_errors=[{"location": "result_payload", "code": "invalid"}],
    )


def _validate_receipt_replay(
    *,
    status: str,
    result_ref: UUID | None,
    result_payload: dict[str, JsonValue] | None,
) -> None:
    if result_payload is None:
        raise _invalid_receipt_replay()
    try:
        if len(canonical_json_bytes(result_payload)) > _MAX_RECEIPT_REPLAY_BYTES:
            raise _invalid_receipt_replay()
    except (TypeError, ValueError):
        raise _invalid_receipt_replay() from None

    if status == "succeeded":
        version = result_payload.get("version")
        valid = (
            result_ref is not None
            and set(result_payload) == {"resource_id", "version"}
            and result_payload.get("resource_id") == str(result_ref)
            and isinstance(version, int)
            and not isinstance(version, bool)
            and version >= 1
        )
    else:
        code = result_payload.get("code")
        try:
            error_code = ErrorCode(code) if isinstance(code, str) else None
        except ValueError:
            error_code = None
        valid = (
            result_ref is None
            and set(result_payload) == {"code", "message_key"}
            and error_code is not None
            and result_payload.get("message_key") == f"errors.{error_code.value}"
        )
    if not valid:
        raise _invalid_receipt_replay()


def _stored_command_receipt(row: RowMapping) -> CommandReceipt:
    receipt = object.__new__(CommandReceipt)
    for field in CommandReceipt.__dataclass_fields__:
        object.__setattr__(receipt, field, row[field])
    return receipt


class SqlCommandReceiptStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(self, receipt: CommandReceipt) -> CommandReservation:
        receipt.validate_reservation()
        statement = (
            postgresql_insert(command_receipts)
            .values(asdict(receipt))
            .on_conflict_do_nothing(
                index_elements=("actor_id", "command_type", "idempotency_key")
            )
            .returning(command_receipts.c.command_id)
        )
        inserted_id = await self._session.scalar(statement)
        if inserted_id is not None:
            return CommandReservation(receipt=receipt, created=True)

        existing = (
            await self._session.execute(
                select(command_receipts).where(
                    command_receipts.c.actor_id == receipt.actor_id,
                    command_receipts.c.command_type == receipt.command_type,
                    command_receipts.c.idempotency_key == receipt.idempotency_key,
                )
            )
        ).mappings().one()
        immutable_identity = (
            "request_fingerprint",
            "aggregate_type",
            "aggregate_id",
            "expected_version",
        )
        if any(existing[field] != getattr(receipt, field) for field in immutable_identity):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        stored = _stored_command_receipt(existing)
        return CommandReservation(receipt=stored, created=False)

    async def complete(
        self,
        *,
        command_id: UUID,
        status: str,
        result_ref: UUID | None,
        result_payload: dict[str, JsonValue] | None,
    ) -> CommandReceipt:
        if status not in {"succeeded", "rejected", "failed"}:
            raise ValueError("command completion requires a terminal status")
        _validate_receipt_replay(
            status=status,
            result_ref=result_ref,
            result_payload=result_payload,
        )
        completed = (
            await self._session.execute(
                command_receipts.update()
                .where(
                    command_receipts.c.command_id == command_id,
                    command_receipts.c.status == "started",
                )
                .values(
                    status=status,
                    result_ref=result_ref,
                    result_payload=result_payload,
                )
                .returning(*command_receipts.c)
            )
        ).mappings().one_or_none()
        if completed is None:
            completed = (
                await self._session.execute(
                    select(command_receipts).where(command_receipts.c.command_id == command_id)
                )
            ).mappings().one_or_none()
        if completed is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if (
            completed["status"] != status
            or completed["result_ref"] != result_ref
            or completed["result_payload"] != result_payload
        ):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _stored_command_receipt(completed)


class SqlEventOutboxRepository:
    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator or Uuid7Generator()

    async def add(self, event: DomainEvent, *, destinations: tuple[str, ...]) -> None:
        if len(destinations) != 1:
            raise ValueError("each domain event requires exactly one outbox destination")
        await self._session.execute(domain_events.insert().values(asdict(event)))
        await self._session.execute(
            outbox_messages.insert().values(
                outbox_id=self._id_generator.new(),
                event_id=event.event_id,
                destination=destinations[0],
                created_at=event.recorded_at,
                published_at=None,
                attempt_count=0,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=None,
            )
        )


class SqlInboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, receipt: InboxReceipt) -> bool:
        statement = (
            postgresql_insert(inbox_receipts)
            .values(asdict(receipt))
            .on_conflict_do_nothing(index_elements=("consumer_code", "event_id"))
            .returning(inbox_receipts.c.event_id)
        )
        inserted_id = await self._session.scalar(statement)
        if inserted_id is not None:
            return True
        existing_checksum = await self._session.scalar(
            select(inbox_receipts.c.result_checksum).where(
                inbox_receipts.c.consumer_code == receipt.consumer_code,
                inbox_receipts.c.event_id == receipt.event_id,
            )
        )
        if existing_checksum != receipt.result_checksum:
            raise DomainError(ErrorCode.RESPONSE_CONFLICT)
        return False


class SqlJobStore:
    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator or Uuid7Generator()

    async def claim(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
    ) -> JobClaim | None:
        job = (
            await self._session.execute(
                select(jobs).where(jobs.c.job_id == job_id).with_for_update()
            )
        ).mappings().one_or_none()
        if job is None or job["status"] not in {"queued", "running", "retry_wait"}:
            return None
        if job["status"] == "retry_wait" and job["retry_not_before_at"] > now:
            return None

        existing = (
            await self._session.execute(
                select(job_claims).where(job_claims.c.job_id == job_id)
            )
        ).mappings().one_or_none()
        if existing is not None and existing["lease_expires_at"] > now:
            return None

        if existing is None:
            last_attempt = await self._session.scalar(
                select(func.max(job_attempts.c.attempt_no)).where(job_attempts.c.job_id == job_id)
            )
            attempt_no = (last_attempt or 0) + 1
            started_at = now
        else:
            attempt_no = existing["attempt_no"]
            started_at = existing["started_at"]

        lease_token = self._id_generator.new()
        lease_expires_at = now + lease_for
        statement = postgresql_insert(job_claims).values(
            job_id=job_id,
            attempt_no=attempt_no,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            started_at=started_at,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=("job_id",),
                set_={
                    "worker_id": worker_id,
                    "lease_token": lease_token,
                    "lease_expires_at": lease_expires_at,
                },
            )
        )
        await self._session.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(
                status="running",
                started_at=func.coalesce(jobs.c.started_at, started_at),
                retry_not_before_at=None,
                version=jobs.c.version + 1,
            )
        )
        return JobClaim(
            job_id=job_id,
            attempt_no=attempt_no,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            started_at=started_at,
        )

    async def renew(
        self,
        *,
        claim: JobClaim,
        now: datetime,
        lease_for: timedelta,
    ) -> bool:
        renewed = await self._session.scalar(
            job_claims.update()
            .where(
                job_claims.c.job_id == claim.job_id,
                job_claims.c.worker_id == claim.worker_id,
                job_claims.c.lease_token == claim.lease_token,
                job_claims.c.lease_expires_at > now,
            )
            .values(lease_expires_at=now + lease_for)
            .returning(job_claims.c.job_id)
        )
        return renewed is not None

    async def succeed(
        self,
        *,
        claim: JobClaim,
        finished_at: datetime,
        result_ref: UUID,
    ) -> bool:
        active = await self._consume_claim(claim=claim)
        if active is None:
            return False
        await self._append_attempt(
            active=active,
            status="succeeded",
            finished_at=finished_at,
            error_code=None,
            retry_not_before_at=None,
            retryable=False,
        )
        await self._session.execute(
            jobs.update()
            .where(jobs.c.job_id == claim.job_id)
            .values(
                status="succeeded",
                finished_at=finished_at,
                result_ref=result_ref,
                error_code=None,
                version=jobs.c.version + 1,
            )
        )
        return True

    async def fail(
        self,
        *,
        claim: JobClaim,
        finished_at: datetime,
        error_code: str,
        retry_not_before_at: datetime | None,
    ) -> bool:
        active = await self._consume_claim(claim=claim)
        if active is None:
            return False
        retryable = retry_not_before_at is not None
        await self._append_attempt(
            active=active,
            status="retryable_failed" if retryable else "failed",
            finished_at=finished_at,
            error_code=error_code,
            retry_not_before_at=retry_not_before_at,
            retryable=retryable,
        )
        await self._session.execute(
            jobs.update()
            .where(jobs.c.job_id == claim.job_id)
            .values(
                status="retry_wait" if retryable else "failed",
                finished_at=None if retryable else finished_at,
                retry_not_before_at=retry_not_before_at,
                error_code=error_code,
                version=jobs.c.version + 1,
            )
        )
        return True

    async def _consume_claim(
        self,
        *,
        claim: JobClaim,
    ) -> RowMapping | None:
        return (
            await self._session.execute(
                job_claims.delete()
                .where(
                    job_claims.c.job_id == claim.job_id,
                    job_claims.c.worker_id == claim.worker_id,
                    job_claims.c.lease_token == claim.lease_token,
                    job_claims.c.lease_expires_at > func.clock_timestamp(),
                )
                .returning(*job_claims.c)
            )
        ).mappings().one_or_none()

    async def _append_attempt(
        self,
        *,
        active: RowMapping,
        status: str,
        finished_at: datetime,
        error_code: str | None,
        retry_not_before_at: datetime | None,
        retryable: bool,
    ) -> None:
        await self._session.execute(
            job_attempts.insert().values(
                job_attempt_id=self._id_generator.new(),
                job_id=active["job_id"],
                attempt_no=active["attempt_no"],
                status=status,
                worker_id=active["worker_id"],
                started_at=active["started_at"],
                finished_at=finished_at,
                retry_not_before_at=retry_not_before_at,
                provider_code=None,
                operation_code=None,
                error_code=error_code,
                retryable=retryable,
            )
        )


class SqlRetentionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_expired(
        self,
        *,
        cutoff: datetime,
        audit_id: UUID,
        actor_pseudonym: str,
        reason_code: str,
        request_id: UUID,
        correlation_id: UUID,
    ) -> RetentionPurgeResult:
        row = (
            await self._session.execute(
                text(
                    "SELECT domain_event_count, security_audit_count "
                    "FROM platform.purge_expired_append_only("
                    ":cutoff, :audit_id, :actor_pseudonym, :reason_code, "
                    ":request_id, :correlation_id)"
                ),
                {
                    "cutoff": cutoff,
                    "audit_id": audit_id,
                    "actor_pseudonym": actor_pseudonym,
                    "reason_code": reason_code,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                },
            )
        ).mappings().one()
        return RetentionPurgeResult(
            audit_id=audit_id,
            domain_event_count=row["domain_event_count"],
            security_audit_count=row["security_audit_count"],
        )

    async def purge_subject_private_events(
        self,
        *,
        deletion_request_id: UUID,
        subject_type: str,
        subject_id: UUID,
        subject_fingerprint: str,
        tombstone_id: UUID,
        audit_id: UUID,
        request_id: UUID,
        correlation_id: UUID,
    ) -> RetentionPurgeResult:
        count = await self._session.scalar(
            text(
                "SELECT platform.purge_subject_private_events("
                ":deletion_request_id, :subject_type, :subject_id, "
                ":subject_fingerprint, :tombstone_id, :audit_id, "
                ":request_id, :correlation_id)"
            ),
            {
                "deletion_request_id": deletion_request_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "subject_fingerprint": subject_fingerprint,
                "tombstone_id": tombstone_id,
                "audit_id": audit_id,
                "request_id": request_id,
                "correlation_id": correlation_id,
            },
        )
        return RetentionPurgeResult(
            audit_id=audit_id,
            domain_event_count=count or 0,
            security_audit_count=0,
        )


class SqlOutboxRepository:
    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator or Uuid7Generator()

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
        limit: int,
        destination: str | None = None,
    ) -> list[OutboxClaim]:
        if limit < 1:
            return []
        conditions: list[ColumnElement[bool]] = [
            outbox_messages.c.published_at.is_(None),
            (outbox_messages.c.lease_expires_at.is_(None))
            | (outbox_messages.c.lease_expires_at <= now),
        ]
        if destination is not None:
            conditions.append(outbox_messages.c.destination == destination)
        available = (
            select(outbox_messages.c.outbox_id)
            .where(*conditions)
            .order_by(outbox_messages.c.created_at, outbox_messages.c.outbox_id)
            .limit(limit)
            .with_for_update(skip_locked=True, of=outbox_messages)
        )
        identifiers = list((await self._session.execute(available)).scalars())
        if not identifiers:
            return []
        lease_expires_at = now + lease_for
        lease_tokens = {identifier: self._id_generator.new() for identifier in identifiers}
        for identifier in identifiers:
            await self._session.execute(
                outbox_messages.update()
                .where(outbox_messages.c.outbox_id == identifier)
                .values(
                    lease_owner=worker_id,
                    lease_token=lease_tokens[identifier],
                    lease_expires_at=lease_expires_at,
                )
            )
        rows = (
            await self._session.execute(
                select(
                    outbox_messages.c.outbox_id,
                    outbox_messages.c.event_id,
                    outbox_messages.c.destination,
                    domain_events.c.correlation_id,
                    outbox_messages.c.created_at,
                    outbox_messages.c.attempt_count,
                    outbox_messages.c.lease_token,
                )
                .join(domain_events, domain_events.c.event_id == outbox_messages.c.event_id)
                .where(outbox_messages.c.outbox_id.in_(identifiers))
                .order_by(outbox_messages.c.created_at, outbox_messages.c.outbox_id)
            )
        ).mappings()
        return [
            OutboxClaim(
                **row,
                lease_owner=worker_id,
                lease_expires_at=lease_expires_at,
            )
            for row in rows
        ]

    async def mark_published(
        self,
        *,
        claim: OutboxClaim,
        published_at: datetime,
    ) -> bool:
        acknowledged = await self._session.scalar(
            outbox_messages.update()
            .where(
                outbox_messages.c.outbox_id == claim.outbox_id,
                outbox_messages.c.lease_owner == claim.lease_owner,
                outbox_messages.c.lease_token == claim.lease_token,
                outbox_messages.c.lease_expires_at > func.clock_timestamp(),
                outbox_messages.c.published_at.is_(None),
            )
            .values(
                published_at=published_at,
                attempt_count=outbox_messages.c.attempt_count + 1,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                last_error_code=None,
            )
            .returning(outbox_messages.c.outbox_id)
        )
        return acknowledged is not None

    async def mark_failed(
        self,
        *,
        claim: OutboxClaim,
        failed_at: datetime,
        error_code: str,
    ) -> bool:
        acknowledged = await self._session.scalar(
            outbox_messages.update()
            .where(
                and_(
                    outbox_messages.c.outbox_id == claim.outbox_id,
                    outbox_messages.c.lease_owner == claim.lease_owner,
                    outbox_messages.c.lease_token == claim.lease_token,
                    outbox_messages.c.lease_expires_at > func.clock_timestamp(),
                    outbox_messages.c.published_at.is_(None),
                )
            )
            .values(
                attempt_count=outbox_messages.c.attempt_count + 1,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                last_error_code=error_code,
            )
            .returning(outbox_messages.c.outbox_id)
        )
        return acknowledged is not None

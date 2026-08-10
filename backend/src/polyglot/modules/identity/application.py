import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.identity.domain import (
    Account,
    AccountStatus,
    Actor,
    AuthorizationPolicy,
    AuthSession,
    ConsentDecision,
    ConsentStatus,
    FakeOidcProvider,
    IdentityAction,
    IdentityProviderType,
    IdentityValidationError,
    LoginIdentity,
    SessionSecrets,
    UserPreferences,
    normalize_identifier,
    verify_session_csrf,
)
from polyglot.modules.identity.passwords import Argon2idPasswordHasher, PasswordPolicyError
from polyglot.modules.identity.persistence import (
    IdentityAuthentication,
    SessionAuthentication,
    SqlIdentityRepository,
)
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import security_audit_entries
from polyglot.platform.persistence.records import CommandReceipt, DomainEvent
from polyglot.platform.persistence.repositories import (
    SqlCommandReceiptStore,
    SqlEventOutboxRepository,
)
from polyglot.platform.persistence.uow import SqlAlchemyUnitOfWork

COMMAND_RECEIPT_RETENTION = timedelta(hours=24)
IDENTITY_EVENT_RETENTION = timedelta(days=180)
RECENT_AUTHENTICATION = timedelta(minutes=5)
AUDIT_RETENTION = timedelta(days=180)
_ZERO_FINGERPRINT = "0" * 64


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: UUID
    correlation_id: UUID
    truncated_ip: str


@dataclass(frozen=True, slots=True)
class RegisterAccount:
    provider_type: str
    identifier: str | None
    password: str | None
    authorization_code: str | None
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class AuthenticateSession:
    provider_type: str
    identifier: str | None
    password: str | None
    authorization_code: str | None
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class RevokeSession:
    session_token: str
    csrf_token: str
    idempotency_key: str | None
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ChangePassword:
    session_token: str
    csrf_token: str
    current_password: str
    new_password: str
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class UpdateUserPreferences:
    session_token: str
    csrf_token: str
    expected_version: int
    idempotency_key: str | None
    context: RequestContext
    interface_locale: str | None = None
    timezone: str | None = None
    preferred_sprint_minutes: int | None = None
    accessibility_preferences: dict[str, JsonValue] | None = None
    media_preferences: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class UpdateConsent:
    session_token: str
    csrf_token: str
    purpose_code: str
    status: str
    policy_revision_id: UUID
    expected_version: int
    idempotency_key: str
    context: RequestContext


@dataclass(frozen=True, slots=True)
class ResourceResult:
    resource_id: UUID
    version: int

    @property
    def account_id(self) -> UUID:
        return self.resource_id


@dataclass(frozen=True, slots=True)
class AuthenticatedSessionResult:
    session_id: UUID
    account_id: UUID
    roles: tuple[str, ...]
    session_token: str
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentSessionResult:
    session_id: UUID
    account_id: UUID
    roles: tuple[str, ...]
    session_token: str
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    preferences: UserPreferences
    consents: tuple[ConsentDecision, ...]


@dataclass(frozen=True, slots=True)
class SessionContinuation:
    session_token: str
    csrf_token: str
    rotated: bool


@dataclass(frozen=True, slots=True)
class PreferencesMutationResult:
    preferences: UserPreferences
    continuation: SessionContinuation


@dataclass(frozen=True, slots=True)
class ConsentMutationResult:
    consent: ConsentDecision
    continuation: SessionContinuation


def _fingerprint_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()


def _actor_pseudonym(account_id: UUID) -> str:
    return hashlib.sha256(str(account_id).encode()).hexdigest()


class IdentityApplicationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        password_hasher: Argon2idPasswordHasher | None = None,
        session_secrets: SessionSecrets,
        oidc_provider: FakeOidcProvider,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or Uuid7Generator(self._clock)
        self._password_hasher = password_hasher or Argon2idPasswordHasher()
        self._session_secrets = session_secrets
        self._oidc_provider = oidc_provider
        self._authorization = AuthorizationPolicy()

    def _unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    def _session(self, uow: SqlAlchemyUnitOfWork) -> AsyncSession:
        if uow.session is None:
            raise RuntimeError("identity unit of work is not active")
        return uow.session

    def _receipt(
        self,
        *,
        command_type: str,
        actor_id: UUID,
        aggregate_type: str,
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
            actor_id=actor_id,
            aggregate_type=aggregate_type,
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

    async def _complete_success(
        self,
        store: SqlCommandReceiptStore,
        receipt: CommandReceipt,
        *,
        resource_id: UUID,
        version: int,
    ) -> None:
        await store.complete(
            command_id=receipt.command_id,
            status="succeeded",
            result_ref=resource_id,
            result_payload={"resource_id": str(resource_id), "version": version},
        )

    async def _complete_rejection(
        self,
        store: SqlCommandReceiptStore,
        receipt: CommandReceipt,
        error: ErrorCode,
    ) -> None:
        await store.complete(
            command_id=receipt.command_id,
            status="rejected",
            result_ref=None,
            result_payload={"code": error.value, "message_key": f"errors.{error.value}"},
        )

    async def _append_event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        actor_id: UUID,
        command_id: UUID,
        context: RequestContext,
        now: datetime,
        payload: dict[str, JsonValue],
    ) -> None:
        event = DomainEvent(
            event_id=self._id_generator.new(),
            event_type=event_type,
            schema_version=1,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            actor_type="account",
            actor_id=actor_id,
            profile_id=None,
            occurred_at=now,
            recorded_at=now,
            correlation_id=context.correlation_id,
            causation_id=None,
            command_id=command_id,
            privacy_class="personal",
            policy_versions={"identity": 1},
            payload=payload,
            expires_at=now + IDENTITY_EVENT_RETENTION,
            subject_type="account",
            subject_id=actor_id,
        )
        await SqlEventOutboxRepository(session, self._id_generator).add(
            event,
            destinations=("identity.events",),
        )

    async def _append_audit(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID,
        result: str,
        reason: str,
        context: RequestContext,
        now: datetime,
        session_fingerprint: str = _ZERO_FINGERPRINT,
    ) -> None:
        await session.execute(
            security_audit_entries.insert().values(
                audit_id=self._id_generator.new(),
                actor_pseudonym=_actor_pseudonym(actor_id),
                action_code=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                reason_code=reason,
                occurred_at=now,
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                session_fingerprint=session_fingerprint,
                truncated_ip=context.truncated_ip,
                expires_at=now + AUDIT_RETENTION,
            )
        )

    def _registration_identity(
        self,
        command: RegisterAccount,
        *,
        account_id: UUID,
        identity_id: UUID,
        now: datetime,
    ) -> tuple[str, LoginIdentity]:
        try:
            provider_type = IdentityProviderType(command.provider_type)
            if provider_type is IdentityProviderType.LOCAL_PASSWORD:
                if command.identifier is None or command.password is None:
                    raise IdentityValidationError("local credentials are incomplete")
                normalized = normalize_identifier(command.identifier)
                password_hash = self._password_hasher.hash(command.password)
                return normalized, LoginIdentity.local(
                    identity_id=identity_id,
                    account_id=account_id,
                    identifier=normalized,
                    password_hash=password_hash,
                    created_at=now,
                )
            if command.authorization_code is None:
                raise IdentityValidationError("OIDC authorization code is required")
            assertion = self._oidc_provider.authenticate(command.authorization_code)
            lock_key = f"oidc:{assertion.issuer}:{assertion.subject}"
            return lock_key, LoginIdentity.oidc(
                identity_id=identity_id,
                account_id=account_id,
                issuer=assertion.issuer,
                subject=assertion.subject,
                created_at=now,
            )
        except (IdentityValidationError, PasswordPolicyError, ValueError) as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED) from error

    async def _find_existing_identity(
        self,
        repository: SqlIdentityRepository,
        identity: LoginIdentity,
    ) -> IdentityAuthentication | None:
        if identity.provider_type is IdentityProviderType.LOCAL_PASSWORD:
            if identity.normalized_identifier is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            return await repository.find_local_for_authentication(
                identity.normalized_identifier
            )
        if identity.issuer is None or identity.subject is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return await repository.find_oidc_for_authentication(identity.issuer, identity.subject)

    async def register_account(self, command: RegisterAccount) -> ResourceResult:
        now = self._clock.now()
        candidate_account_id = self._id_generator.new()
        lock_key, candidate_identity = self._registration_identity(
            command,
            account_id=candidate_account_id,
            identity_id=self._id_generator.new(),
            now=now,
        )
        fingerprint = canonical_json_fingerprint(
            {
                "provider_type": command.provider_type,
                "identifier": command.identifier,
                "password": command.password,
                "authorization_code": command.authorization_code,
            }
        )
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            await repository.lock_identifier(lock_key)
            existing = await self._find_existing_identity(repository, candidate_identity)
            account_id = (
                existing.account.account_id
                if existing is not None
                else candidate_account_id
            )
            receipt = self._receipt(
                command_type="RegisterAccount",
                actor_id=account_id,
                aggregate_type="account",
                aggregate_id=account_id,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                await uow.commit()
                payload = reservation.receipt.result_payload or {}
                return ResourceResult(account_id, cast(int, payload["version"]))
            if existing is not None:
                await self._complete_rejection(store, receipt, ErrorCode.IDENTITY_CONFLICT)
                await self._append_audit(
                    session,
                    actor_id=account_id,
                    action="identity.register",
                    resource_type="account",
                    resource_id=account_id,
                    result="rejected",
                    reason="identity_conflict",
                    context=command.context,
                    now=now,
                )
                await uow.commit()
                raise DomainError(ErrorCode.IDENTITY_CONFLICT)

            account = Account.new(candidate_account_id, now)
            preferences = UserPreferences.defaults(candidate_account_id, now)
            await repository.add_account(account, candidate_identity, preferences)
            await self._append_event(
                session,
                event_type="account_registered",
                aggregate_type="account",
                aggregate_id=account.account_id,
                aggregate_version=account.version,
                actor_id=account.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={
                    "account_id": str(account.account_id),
                    "provider_type": candidate_identity.provider_type.value,
                },
            )
            await self._append_audit(
                session,
                actor_id=account.account_id,
                action="identity.register",
                resource_type="account",
                resource_id=account.account_id,
                result="succeeded",
                reason="account_registered",
                context=command.context,
                now=now,
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=account.account_id,
                version=account.version,
            )
            await uow.commit()
            return ResourceResult(account.account_id, account.version)
        raise RuntimeError("identity operation was unexpectedly suppressed")

    async def _credentials(
        self,
        repository: SqlIdentityRepository,
        command: AuthenticateSession,
    ) -> IdentityAuthentication | None:
        try:
            provider_type = IdentityProviderType(command.provider_type)
        except ValueError:
            return None
        if provider_type is IdentityProviderType.LOCAL_PASSWORD:
            if command.identifier is None or command.password is None:
                return None
            try:
                normalized = normalize_identifier(command.identifier)
            except IdentityValidationError:
                return None
            identity = await repository.find_local_for_authentication(normalized)
            if identity is None or identity.identity.password_hash is None:
                return None
            try:
                valid = self._password_hasher.verify(
                    identity.identity.password_hash,
                    command.password,
                )
            except PasswordPolicyError:
                valid = False
            return identity if valid else None
        if command.authorization_code is None:
            return None
        try:
            assertion = self._oidc_provider.authenticate(command.authorization_code)
        except IdentityValidationError:
            return None
        return await repository.find_oidc_for_authentication(
            assertion.issuer,
            assertion.subject,
        )

    async def _session_result(
        self,
        repository: SqlIdentityRepository,
        session_id: UUID,
    ) -> AuthenticatedSessionResult:
        secrets = self._session_secrets.issue(session_id)
        resolved = await repository.find_session_for_authentication(
            secrets.session_fingerprint
        )
        if resolved is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return AuthenticatedSessionResult(
            session_id=session_id,
            account_id=resolved.account.account_id,
            roles=tuple(sorted(role.value for role in resolved.account.roles)),
            session_token=secrets.session_token,
            csrf_token=secrets.csrf_token,
            idle_expires_at=resolved.session.idle_expires_at,
            absolute_expires_at=resolved.session.absolute_expires_at,
        )

    async def authenticate_session(
        self,
        command: AuthenticateSession,
    ) -> AuthenticatedSessionResult:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "provider_type": command.provider_type,
                "identifier": command.identifier,
                "password": command.password,
                "authorization_code": command.authorization_code,
            }
        )
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            lookup_key = command.identifier or command.authorization_code or "invalid"
            await repository.lock_identifier(lookup_key)
            authenticated = await self._credentials(repository, command)
            if authenticated is None:
                await self._append_audit(
                    session,
                    actor_id=command.context.request_id,
                    action="identity.authenticate",
                    resource_type="authentication_request",
                    resource_id=command.context.request_id,
                    result="rejected",
                    reason="invalid_credentials",
                    context=command.context,
                    now=now,
                )
                await uow.commit()
                raise DomainError(ErrorCode.INVALID_CREDENTIALS)
            account = authenticated.account
            if account.status is AccountStatus.LOCKED:
                await self._append_audit(
                    session,
                    actor_id=account.account_id,
                    action="identity.authenticate",
                    resource_type="account",
                    resource_id=account.account_id,
                    result="rejected",
                    reason="account_locked",
                    context=command.context,
                    now=now,
                )
                await uow.commit()
                raise DomainError(ErrorCode.ACCOUNT_LOCKED)
            if account.status is not AccountStatus.ACTIVE:
                await uow.commit()
                raise DomainError(ErrorCode.INVALID_CREDENTIALS)

            receipt = self._receipt(
                command_type="AuthenticateSession",
                actor_id=account.account_id,
                aggregate_type="account",
                aggregate_id=account.account_id,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                if reservation.receipt.result_ref is None:
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                result = await self._session_result(
                    repository,
                    reservation.receipt.result_ref,
                )
                await uow.commit()
                return result

            session_id = self._id_generator.new()
            secrets = self._session_secrets.issue(session_id)
            auth_session = AuthSession.issue(
                session_id=session_id,
                account_id=account.account_id,
                session_fingerprint=secrets.session_fingerprint,
                csrf_secret_hash=secrets.csrf_secret_hash,
                roles=account.roles,
                account_session_version=account.session_version,
                now=now,
            )
            await repository.add_session(auth_session)
            await repository.update_last_authenticated(authenticated.identity.identity_id, now)
            await self._append_event(
                session,
                event_type="session_authenticated",
                aggregate_type="auth_session",
                aggregate_id=session_id,
                aggregate_version=1,
                actor_id=account.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={"session_id": str(session_id)},
            )
            await self._append_audit(
                session,
                actor_id=account.account_id,
                action="identity.authenticate",
                resource_type="auth_session",
                resource_id=session_id,
                result="succeeded",
                reason="session_authenticated",
                context=command.context,
                now=now,
                session_fingerprint=secrets.session_fingerprint,
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=session_id,
                version=1,
            )
            await uow.commit()
            return AuthenticatedSessionResult(
                session_id=session_id,
                account_id=account.account_id,
                roles=tuple(sorted(role.value for role in account.roles)),
                session_token=secrets.session_token,
                csrf_token=secrets.csrf_token,
                idle_expires_at=auth_session.idle_expires_at,
                absolute_expires_at=auth_session.absolute_expires_at,
            )
        raise RuntimeError("identity operation was unexpectedly suppressed")

    def _rotation_context(self, context: RequestContext | None) -> RequestContext:
        if context is not None:
            return context
        return RequestContext(
            request_id=self._id_generator.new(),
            correlation_id=self._id_generator.new(),
            truncated_ip="unknown",
        )

    async def _append_rotation_facts(
        self,
        session: AsyncSession,
        *,
        predecessor: AuthSession,
        replacement: AuthSession,
        account: Account,
        reason: str,
        context: RequestContext,
        now: datetime,
    ) -> None:
        await self._append_event(
            session,
            event_type="session_revoked",
            aggregate_type="auth_session",
            aggregate_id=predecessor.session_id,
            aggregate_version=2,
            actor_id=account.account_id,
            command_id=context.request_id,
            context=context,
            now=now,
            payload={
                "reason": reason,
                "replacement_session_id": str(replacement.session_id),
            },
        )
        await self._append_event(
            session,
            event_type="session_authenticated",
            aggregate_type="auth_session",
            aggregate_id=replacement.session_id,
            aggregate_version=1,
            actor_id=account.account_id,
            command_id=context.request_id,
            context=context,
            now=now,
            payload={
                "session_id": str(replacement.session_id),
                "predecessor_session_id": str(predecessor.session_id),
                "reason": reason,
            },
        )
        await self._append_audit(
            session,
            actor_id=account.account_id,
            action="identity.revoke_session",
            resource_type="auth_session",
            resource_id=predecessor.session_id,
            result="succeeded",
            reason=reason,
            context=context,
            now=now,
            session_fingerprint=predecessor.session_fingerprint,
        )
        await self._append_audit(
            session,
            actor_id=account.account_id,
            action="identity.authenticate",
            resource_type="auth_session",
            resource_id=replacement.session_id,
            result="succeeded",
            reason="session_rotated",
            context=context,
            now=now,
            session_fingerprint=replacement.session_fingerprint,
        )

    async def _resolve_session(
        self,
        session: AsyncSession,
        repository: SqlIdentityRepository,
        token: str,
        *,
        csrf_token: str | None = None,
        context: RequestContext | None = None,
    ) -> tuple[SessionAuthentication, SessionContinuation]:
        fingerprint = _fingerprint_session_token(token)
        acquired_immediately = await repository.lock_session(fingerprint)
        resolved = await repository.find_session_for_authentication(fingerprint)
        if resolved is None:
            raise DomainError(ErrorCode.UNAUTHENTICATED)
        account = resolved.account
        active = resolved.session
        now = self._clock.now()
        if account.status is AccountStatus.LOCKED:
            raise DomainError(ErrorCode.ACCOUNT_LOCKED)
        if account.status is not AccountStatus.ACTIVE:
            raise DomainError(ErrorCode.UNAUTHENTICATED)
        if csrf_token is not None and not verify_session_csrf(
            active.session_fingerprint,
            csrf_token,
            active.csrf_secret_hash,
        ):
            raise DomainError(ErrorCode.FORBIDDEN)
        if active.revoked_at is not None:
            if not acquired_immediately and active.replaced_by_session_id is not None:
                replacement_secrets = self._session_secrets.issue(
                    active.replaced_by_session_id
                )
                successor = await repository.find_session_for_authentication(
                    replacement_secrets.session_fingerprint
                )
                if successor is not None and successor.session.is_active(
                    now,
                    successor.account.session_version,
                ):
                    return successor, SessionContinuation(
                        session_token=replacement_secrets.session_token,
                        csrf_token=replacement_secrets.csrf_token,
                        rotated=True,
                    )
            raise DomainError(ErrorCode.UNAUTHENTICATED)
        if now >= active.idle_expires_at or now >= active.absolute_expires_at:
            raise DomainError(ErrorCode.UNAUTHENTICATED)

        if active.requires_rotation(now, account.session_version):
            replacement_id = self._id_generator.new()
            secrets = self._session_secrets.issue(replacement_id)
            try:
                replacement = active.rotate(
                    session_id=replacement_id,
                    session_fingerprint=secrets.session_fingerprint,
                    csrf_secret_hash=secrets.csrf_secret_hash,
                    roles=account.roles,
                    account_session_version=account.session_version,
                    now=now,
                )
            except IdentityValidationError as error:
                raise DomainError(ErrorCode.UNAUTHENTICATED) from error
            reason = (
                "role_changed"
                if active.account_session_version != account.session_version
                else "periodic_rotation"
            )
            revoked = await repository.revoke_session(
                active.session_id,
                revoked_at=now,
                reason=reason,
                replaced_by_session_id=replacement.session_id,
            )
            if not revoked:
                raise DomainError(ErrorCode.UNAUTHENTICATED)
            await repository.add_session(replacement)
            await self._append_rotation_facts(
                session,
                predecessor=active,
                replacement=replacement,
                account=account,
                reason=reason,
                context=self._rotation_context(context),
                now=now,
            )
            return SessionAuthentication(
                account=account,
                session=replacement,
            ), SessionContinuation(
                session_token=secrets.session_token,
                csrf_token=secrets.csrf_token,
                rotated=True,
            )

        touched = active.touch(now)
        await repository.touch_session(touched)
        csrf = self._session_secrets.issue(active.session_id).csrf_token
        return SessionAuthentication(
            account=account,
            session=touched,
        ), SessionContinuation(session_token=token, csrf_token=csrf, rotated=False)

    def _authorize(
        self,
        account: Account,
        action: IdentityAction,
    ) -> None:
        allowed = self._authorization.allows(
            Actor(account.account_id, account.roles),
            action=action,
            resource_type="account",
            resource_id=account.account_id,
            scope="owner",
        )
        if not allowed:
            raise DomainError(ErrorCode.FORBIDDEN)

    async def get_current_session(
        self,
        session_token: str,
        context: RequestContext | None = None,
    ) -> CurrentSessionResult:
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            resolved, continuation = await self._resolve_session(
                session,
                repository,
                session_token,
                context=context,
            )
            self._authorize(resolved.account, IdentityAction.READ_SESSION)
            preferences = await repository.get_preferences(resolved.account.account_id)
            if preferences is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            consents = await repository.get_current_consents(resolved.account.account_id)
            await uow.commit()
            return CurrentSessionResult(
                session_id=resolved.session.session_id,
                account_id=resolved.account.account_id,
                roles=tuple(sorted(role.value for role in resolved.account.roles)),
                session_token=continuation.session_token,
                csrf_token=continuation.csrf_token,
                idle_expires_at=resolved.session.idle_expires_at,
                absolute_expires_at=resolved.session.absolute_expires_at,
                preferences=preferences,
                consents=tuple(consents[purpose] for purpose in sorted(consents)),
            )
        raise RuntimeError("identity operation was unexpectedly suppressed")

    async def update_preferences(
        self,
        command: UpdateUserPreferences,
    ) -> PreferencesMutationResult:
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            resolved, continuation = await self._resolve_session(
                session,
                repository,
                command.session_token,
                csrf_token=command.csrf_token,
                context=command.context,
            )
            self._authorize(resolved.account, IdentityAction.UPDATE_PREFERENCES)
            current = await repository.get_preferences(resolved.account.account_id)
            if current is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            fingerprint = canonical_json_fingerprint(
                {
                    "interface_locale": command.interface_locale,
                    "timezone": command.timezone,
                    "preferred_sprint_minutes": command.preferred_sprint_minutes,
                    "accessibility_preferences": command.accessibility_preferences,
                    "media_preferences": command.media_preferences,
                }
            )
            receipt = self._receipt(
                command_type="UpdateUserPreferences",
                actor_id=resolved.account.account_id,
                aggregate_type="user_preferences",
                aggregate_id=resolved.account.account_id,
                idempotency_key=command.idempotency_key or str(command.context.request_id),
                fingerprint=fingerprint,
                expected_version=command.expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                replay = await repository.get_preferences(resolved.account.account_id)
                if replay is None:
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                await uow.commit()
                return PreferencesMutationResult(replay, continuation)
            try:
                updated = current.update(
                    interface_locale=command.interface_locale,
                    timezone=command.timezone,
                    preferred_sprint_minutes=command.preferred_sprint_minutes,
                    accessibility_preferences=command.accessibility_preferences,
                    media_preferences=command.media_preferences,
                    now=now,
                )
            except IdentityValidationError as error:
                raise DomainError(ErrorCode.VALIDATION_FAILED) from error
            await repository.update_preferences(
                updated,
                expected_version=command.expected_version,
            )
            await self._append_event(
                session,
                event_type="user_preferences_updated",
                aggregate_type="user_preferences",
                aggregate_id=updated.account_id,
                aggregate_version=updated.version,
                actor_id=updated.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={"version": updated.version},
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=updated.account_id,
                version=updated.version,
            )
            await uow.commit()
            return PreferencesMutationResult(updated, continuation)
        raise RuntimeError("identity operation was unexpectedly suppressed")

    async def update_consent(self, command: UpdateConsent) -> ConsentMutationResult:
        now = self._clock.now()
        try:
            status = ConsentStatus(command.status)
        except ValueError as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED) from error
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            resolved, continuation = await self._resolve_session(
                session,
                repository,
                command.session_token,
                csrf_token=command.csrf_token,
                context=command.context,
            )
            self._authorize(resolved.account, IdentityAction.UPDATE_CONSENT)
            fingerprint = canonical_json_fingerprint(
                {
                    "purpose_code": command.purpose_code,
                    "status": status.value,
                    "policy_revision_id": str(command.policy_revision_id),
                }
            )
            receipt = self._receipt(
                command_type="UpdateConsent",
                actor_id=resolved.account.account_id,
                aggregate_type="consent",
                aggregate_id=resolved.account.account_id,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                expected_version=command.expected_version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                if reservation.receipt.result_ref is None:
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                replay = await repository.get_consent(reservation.receipt.result_ref)
                if replay is None:
                    raise DomainError(ErrorCode.INTERNAL_ERROR)
                await uow.commit()
                return ConsentMutationResult(replay, continuation)
            try:
                decision = ConsentDecision.decide(
                    consent_id=self._id_generator.new(),
                    account_id=resolved.account.account_id,
                    purpose_code=command.purpose_code,
                    status=status,
                    policy_revision_id=command.policy_revision_id,
                    version=command.expected_version + 1,
                    now=now,
                )
            except IdentityValidationError as error:
                raise DomainError(ErrorCode.VALIDATION_FAILED) from error
            await repository.add_consent(decision, expected_version=command.expected_version)
            await self._append_event(
                session,
                event_type="consent_updated",
                aggregate_type="consent",
                aggregate_id=decision.consent_id,
                aggregate_version=decision.version,
                actor_id=decision.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={
                    "purpose_code": decision.purpose_code,
                    "status": decision.status.value,
                    "policy_revision_id": str(decision.policy_revision_id),
                },
            )
            await self._append_audit(
                session,
                actor_id=decision.account_id,
                action="identity.consent",
                resource_type="consent",
                resource_id=decision.consent_id,
                result="succeeded",
                reason=decision.status.value,
                context=command.context,
                now=now,
                session_fingerprint=resolved.session.session_fingerprint,
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=decision.consent_id,
                version=decision.version,
            )
            await uow.commit()
            return ConsentMutationResult(decision, continuation)
        raise RuntimeError("identity operation was unexpectedly suppressed")

    async def change_password(self, command: ChangePassword) -> ResourceResult:
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            resolved, _ = await self._resolve_session(
                session,
                repository,
                command.session_token,
                csrf_token=command.csrf_token,
                context=command.context,
            )
            self._authorize(resolved.account, IdentityAction.CHANGE_PASSWORD)
            if now - resolved.session.authenticated_at > RECENT_AUTHENTICATION:
                raise DomainError(ErrorCode.UNAUTHENTICATED)
            identity = await repository.get_local_identity(resolved.account.account_id)
            if identity is None or identity.password_hash is None:
                raise DomainError(ErrorCode.IDENTITY_PROVIDER_MISMATCH)
            if not self._password_hasher.verify(identity.password_hash, command.current_password):
                raise DomainError(ErrorCode.INVALID_CREDENTIALS)
            try:
                replacement_hash = self._password_hasher.hash(command.new_password)
            except PasswordPolicyError as error:
                raise DomainError(ErrorCode.VALIDATION_FAILED) from error
            fingerprint = canonical_json_fingerprint(
                {
                    "current_password": command.current_password,
                    "new_password": command.new_password,
                }
            )
            receipt = self._receipt(
                command_type="ChangePassword",
                actor_id=resolved.account.account_id,
                aggregate_type="account",
                aggregate_id=resolved.account.account_id,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                expected_version=resolved.account.version,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                payload = reservation.receipt.result_payload or {}
                await uow.commit()
                return ResourceResult(
                    resolved.account.account_id,
                    cast(int, payload["version"]),
                )
            await repository.update_password(
                identity.identity_id,
                password_hash=replacement_hash,
                now=now,
            )
            new_session_version = await repository.revoke_all_sessions(
                resolved.account.account_id,
                now=now,
                reason="password_changed",
            )
            new_account_version = resolved.account.version + 1
            await self._append_event(
                session,
                event_type="password_changed",
                aggregate_type="account_security",
                aggregate_id=resolved.account.account_id,
                aggregate_version=new_account_version,
                actor_id=resolved.account.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={"account_id": str(resolved.account.account_id)},
            )
            await self._append_event(
                session,
                event_type="sessions_revoked",
                aggregate_type="account_sessions",
                aggregate_id=resolved.account.account_id,
                aggregate_version=new_session_version,
                actor_id=resolved.account.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={"reason": "security_change"},
            )
            await self._append_audit(
                session,
                actor_id=resolved.account.account_id,
                action="identity.change_credential",
                resource_type="account",
                resource_id=resolved.account.account_id,
                result="succeeded",
                reason="security_change",
                context=command.context,
                now=now,
                session_fingerprint=resolved.session.session_fingerprint,
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=resolved.account.account_id,
                version=new_account_version,
            )
            await uow.commit()
            return ResourceResult(resolved.account.account_id, new_account_version)
        raise RuntimeError("identity operation was unexpectedly suppressed")

    async def revoke_session(self, command: RevokeSession) -> ResourceResult:
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            session = self._session(uow)
            repository = SqlIdentityRepository(session, self._id_generator)
            resolved, _ = await self._resolve_session(
                session,
                repository,
                command.session_token,
                csrf_token=command.csrf_token,
                context=command.context,
            )
            self._authorize(resolved.account, IdentityAction.REVOKE_SESSION)
            fingerprint = canonical_json_fingerprint(
                {"session_id": str(resolved.session.session_id)}
            )
            receipt = self._receipt(
                command_type="RevokeSession",
                actor_id=resolved.account.account_id,
                aggregate_type="auth_session",
                aggregate_id=resolved.session.session_id,
                idempotency_key=command.idempotency_key or str(command.context.request_id),
                fingerprint=fingerprint,
                expected_version=1,
                now=now,
            )
            store = SqlCommandReceiptStore(session)
            reservation = await store.reserve(receipt)
            if not reservation.created:
                self._raise_replayed_error(reservation.receipt)
                await uow.commit()
                return ResourceResult(resolved.session.session_id, 2)
            await repository.revoke_session(
                resolved.session.session_id,
                revoked_at=now,
                reason="logout",
            )
            await self._append_event(
                session,
                event_type="session_revoked",
                aggregate_type="auth_session",
                aggregate_id=resolved.session.session_id,
                aggregate_version=2,
                actor_id=resolved.account.account_id,
                command_id=receipt.command_id,
                context=command.context,
                now=now,
                payload={"reason": "logout"},
            )
            await self._append_audit(
                session,
                actor_id=resolved.account.account_id,
                action="identity.revoke_session",
                resource_type="auth_session",
                resource_id=resolved.session.session_id,
                result="succeeded",
                reason="logout",
                context=command.context,
                now=now,
                session_fingerprint=resolved.session.session_fingerprint,
            )
            await self._complete_success(
                store,
                receipt,
                resource_id=resolved.session.session_id,
                version=2,
            )
            await uow.commit()
            return ResourceResult(resolved.session.session_id, 2)
        raise RuntimeError("identity operation was unexpectedly suppressed")

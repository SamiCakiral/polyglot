from dataclasses import asdict, dataclass
from datetime import time
from typing import cast
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    and_,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.identity.domain import (
    Account,
    AccountRole,
    AccountStatus,
    AuthSession,
    ConsentDecision,
    ConsentStatus,
    IdentityProviderType,
    LoginIdentity,
    UserPreferences,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import metadata

accounts = Table(
    "accounts",
    metadata,
    Column("account_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("status", String(32), nullable=False),
    Column("security_version", Integer, nullable=False),
    Column("session_version", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("security_last_activity_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True)),
    CheckConstraint("identity.is_uuid7(account_id)", name="ck_account_uuid7"),
    CheckConstraint(
        "status IN ('active', 'locked', 'pending_deletion', 'deleted')",
        name="ck_account_status",
    ),
    CheckConstraint(
        "security_version >= 1 AND session_version >= 1 AND version >= 1",
        name="ck_account_versions",
    ),
    CheckConstraint(
        "(status = 'deleted') = (deleted_at IS NOT NULL)",
        name="ck_account_deleted_shape",
    ),
    schema="identity",
)

login_identities = Table(
    "login_identities",
    metadata,
    Column("identity_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("provider_type", String(32), nullable=False),
    Column("normalized_identifier", String(320)),
    Column("password_hash", Text),
    Column("issuer", String(500)),
    Column("subject", String(500)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_authenticated_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    CheckConstraint(
        "identity.is_uuid7(identity_id) AND identity.is_uuid7(account_id)",
        name="ck_identity_uuid7",
    ),
    CheckConstraint(
        "provider_type IN ('local_password', 'oidc')",
        name="ck_identity_provider_type",
    ),
    CheckConstraint(
        "((provider_type = 'local_password' AND normalized_identifier IS NOT NULL "
        "AND password_hash LIKE '$argon2id$%' AND issuer IS NULL AND subject IS NULL) "
        "OR (provider_type = 'oidc' AND normalized_identifier IS NULL "
        "AND password_hash IS NULL AND issuer IS NOT NULL AND subject IS NOT NULL))",
        name="ck_identity_provider_shape",
    ),
    schema="identity",
)
Index(
    "uq_login_identity_local_active",
    login_identities.c.normalized_identifier,
    unique=True,
    postgresql_where=and_(
        login_identities.c.provider_type == "local_password",
        login_identities.c.revoked_at.is_(None),
    ),
)
Index(
    "uq_login_identity_oidc_active",
    login_identities.c.issuer,
    login_identities.c.subject,
    unique=True,
    postgresql_where=and_(
        login_identities.c.provider_type == "oidc",
        login_identities.c.revoked_at.is_(None),
    ),
)
Index("ix_login_identities_account_id", login_identities.c.account_id)

account_roles = Table(
    "account_roles",
    metadata,
    Column("role_grant_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("role", String(32), nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("granted_by_actor_id", PG_UUID(as_uuid=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    CheckConstraint(
        "identity.is_uuid7(role_grant_id) AND identity.is_uuid7(account_id) "
        "AND identity.is_uuid7(granted_by_actor_id)",
        name="ck_account_role_uuid7",
    ),
    CheckConstraint(
        "role IN ('learner', 'author', 'reviewer', 'support', 'admin', 'worker')",
        name="ck_account_role",
    ),
    CheckConstraint(
        "revoked_at IS NULL OR revoked_at >= granted_at",
        name="ck_account_role_revoke_order",
    ),
    schema="identity",
)
Index(
    "uq_account_role_active",
    account_roles.c.account_id,
    account_roles.c.role,
    unique=True,
    postgresql_where=account_roles.c.revoked_at.is_(None),
)
Index("ix_account_roles_account_id", account_roles.c.account_id)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("session_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("session_fingerprint", String(64), nullable=False, unique=True),
    Column("csrf_secret_hash", String(64), nullable=False),
    Column("roles_snapshot", ARRAY(String(32)), nullable=False),
    Column("account_session_version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("authenticated_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True), nullable=False),
    Column("idle_expires_at", DateTime(timezone=True), nullable=False),
    Column("absolute_expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revoke_reason", String(120)),
    CheckConstraint(
        "identity.is_uuid7(session_id) AND identity.is_uuid7(account_id)",
        name="ck_session_uuid7",
    ),
    CheckConstraint(
        "session_fingerprint ~ '^[0-9a-f]{64}$' "
        "AND csrf_secret_hash ~ '^[0-9a-f]{64}$'",
        name="ck_session_fingerprints",
    ),
    CheckConstraint(
        "cardinality(roles_snapshot) >= 1 "
        "AND NOT roles_snapshot && ARRAY['worker']::varchar[] "
        "AND roles_snapshot <@ ARRAY["
        "'learner', 'author', 'reviewer', 'support', 'admin']::varchar[]",
        name="ck_session_roles",
    ),
    CheckConstraint("account_session_version >= 1", name="ck_session_version"),
    CheckConstraint(
        "created_at <= authenticated_at AND authenticated_at <= last_seen_at "
        "AND created_at <= rotated_at AND last_seen_at < idle_expires_at "
        "AND idle_expires_at <= absolute_expires_at "
        "AND absolute_expires_at <= created_at + interval '7 days'",
        name="ck_session_expiry_order",
    ),
    CheckConstraint(
        "(revoked_at IS NULL AND revoke_reason IS NULL) "
        "OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)",
        name="ck_session_revoke_shape",
    ),
    schema="identity",
)
Index("ix_auth_sessions_account_id", auth_sessions.c.account_id)
Index("ix_auth_sessions_idle_expires_at", auth_sessions.c.idle_expires_at)
Index("ix_auth_sessions_absolute_expires_at", auth_sessions.c.absolute_expires_at)
Index(
    "ix_auth_sessions_open_account",
    auth_sessions.c.account_id,
    auth_sessions.c.created_at,
    postgresql_where=auth_sessions.c.revoked_at.is_(None),
)

user_preferences = Table(
    "user_preferences",
    metadata,
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("interface_locale", String(35), nullable=False),
    Column("timezone", String(120), nullable=False),
    Column("day_cutover_local_time", Time, nullable=False),
    Column("preferred_sprint_minutes", Integer, nullable=False),
    Column("accessibility_preferences", JSONB, nullable=False),
    Column("media_preferences", JSONB, nullable=False),
    Column("preferred_voice_id", PG_UUID(as_uuid=True)),
    Column("voice_catalog_revision_id", PG_UUID(as_uuid=True)),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("identity.is_uuid7(account_id)", name="ck_preferences_uuid7"),
    CheckConstraint(
        "preferred_sprint_minutes BETWEEN 10 AND 60 "
        "AND preferred_sprint_minutes % 5 = 0",
        name="ck_preferences_sprint_minutes",
    ),
    CheckConstraint(
        "jsonb_typeof(accessibility_preferences) = 'object' "
        "AND accessibility_preferences->>'schema_version' = '1' "
        "AND jsonb_typeof(media_preferences) = 'object' "
        "AND media_preferences->>'schema_version' = '1'",
        name="ck_preferences_json",
    ),
    CheckConstraint(
        "(preferred_voice_id IS NULL) = (voice_catalog_revision_id IS NULL) "
        "AND (preferred_voice_id IS NULL OR (identity.is_uuid7(preferred_voice_id) "
        "AND identity.is_uuid7(voice_catalog_revision_id)))",
        name="ck_preferences_voice_pair",
    ),
    CheckConstraint("version >= 1", name="ck_preferences_version"),
    CheckConstraint("updated_at >= created_at", name="ck_preferences_update_order"),
    schema="identity",
)

consent_purposes = Table(
    "consent_purposes",
    metadata,
    Column("purpose_code", String(64), primary_key=True),
    Column("active", Boolean, nullable=False),
    CheckConstraint(
        "purpose_code ~ '^[a-z][a-z0-9_]{2,63}$'",
        name="ck_consent_purpose_code",
    ),
    schema="identity",
)

consent_grants = Table(
    "consent_grants",
    metadata,
    Column("consent_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "purpose_code",
        String(64),
        ForeignKey("identity.consent_purposes.purpose_code", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("status", String(32), nullable=False),
    Column("policy_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("withdrawn_at", DateTime(timezone=True)),
    CheckConstraint(
        "identity.is_uuid7(consent_id) AND identity.is_uuid7(account_id) "
        "AND identity.is_uuid7(policy_revision_id)",
        name="ck_consent_uuid7",
    ),
    CheckConstraint("status IN ('granted', 'withdrawn')", name="ck_consent_status"),
    CheckConstraint(
        "(status = 'granted' AND withdrawn_at IS NULL) "
        "OR (status = 'withdrawn' AND withdrawn_at = decided_at)",
        name="ck_consent_withdrawal_shape",
    ),
    CheckConstraint("version >= 1", name="ck_consent_version"),
    UniqueConstraint(
        "account_id",
        "purpose_code",
        "version",
        name="uq_consent_account_purpose_version",
    ),
    schema="identity",
)
Index(
    "ix_consent_grants_account_purpose_decided",
    consent_grants.c.account_id,
    consent_grants.c.purpose_code,
    consent_grants.c.decided_at.desc(),
)


@dataclass(frozen=True, slots=True)
class IdentityAuthentication:
    account: Account
    identity: LoginIdentity
    preferences: UserPreferences


@dataclass(frozen=True, slots=True)
class SessionAuthentication:
    account: Account
    session: AuthSession


def _account_from_row(row: RowMapping, *, session_lookup: bool = False) -> Account:
    prefix = "current_" if session_lookup else ""
    return Account(
        account_id=row["account_id"],
        status=AccountStatus(row["account_status"] if "account_status" in row else row["status"]),
        security_version=row[f"{prefix}security_version"],
        session_version=row[f"{prefix}session_version"],
        version=row["account_version"] if "account_version" in row else row["version"],
        roles=frozenset(AccountRole(role) for role in row["current_roles"]),
        created_at=row["account_created_at"] if "account_created_at" in row else row["created_at"],
        security_last_activity_at=row["security_last_activity_at"],
        deleted_at=row["deleted_at"],
    )


def _preferences_from_row(row: RowMapping) -> UserPreferences:
    return UserPreferences(
        account_id=row["account_id"],
        interface_locale=row["interface_locale"],
        timezone=row["timezone"],
        day_cutover_local_time=cast(time, row["day_cutover_local_time"]),
        preferred_sprint_minutes=row["preferred_sprint_minutes"],
        accessibility_preferences=cast(dict[str, JsonValue], row["accessibility_preferences"]),
        media_preferences=cast(dict[str, JsonValue], row["media_preferences"]),
        preferred_voice_id=row["preferred_voice_id"],
        voice_catalog_revision_id=row["voice_catalog_revision_id"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _consent_from_row(row: RowMapping) -> ConsentDecision:
    return ConsentDecision(
        consent_id=row["consent_id"],
        account_id=row["account_id"],
        purpose_code=row["purpose_code"],
        status=ConsentStatus(row["status"]),
        policy_revision_id=row["policy_revision_id"],
        version=row["version"],
        decided_at=row["decided_at"],
        withdrawn_at=row["withdrawn_at"],
    )


class SqlIdentityRepository:
    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator or Uuid7Generator()

    async def set_actor(self, account_id: UUID) -> None:
        await self._session.execute(
            text("SELECT set_config('app.user_id', :account_id, true)"),
            {"account_id": str(account_id)},
        )

    async def lock_identifier(self, identifier: str) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identifier, 0))"),
            {"identifier": identifier},
        )

    async def add_account(
        self,
        account: Account,
        identity: LoginIdentity,
        preferences: UserPreferences,
    ) -> None:
        await self.set_actor(account.account_id)
        await self._session.execute(
            accounts.insert().values(
                account_id=account.account_id,
                status=account.status.value,
                security_version=account.security_version,
                session_version=account.session_version,
                version=account.version,
                created_at=account.created_at,
                security_last_activity_at=account.security_last_activity_at,
                deleted_at=account.deleted_at,
            )
        )
        await self._session.execute(
            login_identities.insert().values(
                identity_id=identity.identity_id,
                account_id=identity.account_id,
                provider_type=identity.provider_type.value,
                normalized_identifier=identity.normalized_identifier,
                password_hash=identity.password_hash,
                issuer=identity.issuer,
                subject=identity.subject,
                created_at=identity.created_at,
                last_authenticated_at=identity.last_authenticated_at,
                revoked_at=None,
            )
        )
        for role in sorted(account.roles, key=lambda item: item.value):
            await self._session.execute(
                account_roles.insert().values(
                    role_grant_id=self._id_generator.new(),
                    account_id=account.account_id,
                    role=role.value,
                    granted_at=account.created_at,
                    granted_by_actor_id=account.account_id,
                    revoked_at=None,
                )
            )
        await self._session.execute(
            user_preferences.insert().values(
                account_id=preferences.account_id,
                interface_locale=preferences.interface_locale,
                timezone=preferences.timezone,
                day_cutover_local_time=preferences.day_cutover_local_time,
                preferred_sprint_minutes=preferences.preferred_sprint_minutes,
                accessibility_preferences=preferences.accessibility_preferences,
                media_preferences=preferences.media_preferences,
                preferred_voice_id=preferences.preferred_voice_id,
                voice_catalog_revision_id=preferences.voice_catalog_revision_id,
                version=preferences.version,
                created_at=preferences.created_at,
                updated_at=preferences.updated_at,
            )
        )

    async def get_account(self, account_id: UUID) -> Account | None:
        row = (
            await self._session.execute(
                select(accounts).where(accounts.c.account_id == account_id)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        roles = (
            await self._session.execute(
                select(account_roles.c.role).where(
                    account_roles.c.account_id == account_id,
                    account_roles.c.revoked_at.is_(None),
                )
            )
        ).scalars()
        values = dict(row)
        values["current_roles"] = list(roles)
        return _account_from_row(cast(RowMapping, values))

    async def find_local_for_authentication(
        self,
        normalized_identifier: str,
    ) -> IdentityAuthentication | None:
        row = (
            await self._session.execute(
                text("SELECT * FROM identity.lookup_local_identity(:identifier)"),
                {"identifier": normalized_identifier},
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        await self.set_actor(row["account_id"])
        preferences = await self.get_preferences(row["account_id"])
        if preferences is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        identity = LoginIdentity(
            identity_id=row["identity_id"],
            account_id=row["account_id"],
            provider_type=IdentityProviderType.LOCAL_PASSWORD,
            normalized_identifier=normalized_identifier,
            password_hash=row["password_hash"],
            issuer=None,
            subject=None,
            created_at=row["account_created_at"],
            last_authenticated_at=row["last_authenticated_at"],
        )
        return IdentityAuthentication(
            account=_account_from_row(row),
            identity=identity,
            preferences=preferences,
        )

    async def add_session(self, session: AuthSession) -> None:
        await self.set_actor(session.account_id)
        await self._session.execute(
            auth_sessions.insert().values(
                session_id=session.session_id,
                account_id=session.account_id,
                session_fingerprint=session.session_fingerprint,
                csrf_secret_hash=session.csrf_secret_hash,
                roles_snapshot=[
                    role.value
                    for role in sorted(session.roles, key=lambda role: role.value)
                ],
                account_session_version=session.account_session_version,
                created_at=session.created_at,
                authenticated_at=session.authenticated_at,
                last_seen_at=session.last_seen_at,
                rotated_at=session.rotated_at,
                idle_expires_at=session.idle_expires_at,
                absolute_expires_at=session.absolute_expires_at,
                revoked_at=session.revoked_at,
                revoke_reason=session.revoke_reason,
            )
        )

    async def find_session_for_authentication(
        self,
        fingerprint: str,
    ) -> SessionAuthentication | None:
        row = (
            await self._session.execute(
                text("SELECT * FROM identity.lookup_session(:fingerprint)"),
                {"fingerprint": fingerprint},
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        await self.set_actor(row["account_id"])
        account = _account_from_row(row, session_lookup=True)
        session = AuthSession(
            session_id=row["session_id"],
            account_id=row["account_id"],
            session_fingerprint=row["session_fingerprint"],
            csrf_secret_hash=row["csrf_secret_hash"],
            roles=frozenset(AccountRole(role) for role in row["roles_snapshot"]),
            account_session_version=row["account_session_version"],
            created_at=row["created_at"],
            authenticated_at=row["authenticated_at"],
            last_seen_at=row["last_seen_at"],
            rotated_at=row["rotated_at"],
            idle_expires_at=row["idle_expires_at"],
            absolute_expires_at=row["absolute_expires_at"],
            revoked_at=row["revoked_at"],
            revoke_reason=row["revoke_reason"],
        )
        return SessionAuthentication(account=account, session=session)

    async def get_preferences(self, account_id: UUID) -> UserPreferences | None:
        row = (
            await self._session.execute(
                select(user_preferences).where(user_preferences.c.account_id == account_id)
            )
        ).mappings().one_or_none()
        return None if row is None else _preferences_from_row(row)

    async def update_preferences(
        self,
        preferences: UserPreferences,
        *,
        expected_version: int,
    ) -> None:
        updated_id = await self._session.scalar(
            user_preferences.update()
            .where(
                user_preferences.c.account_id == preferences.account_id,
                user_preferences.c.version == expected_version,
            )
            .values(
                interface_locale=preferences.interface_locale,
                timezone=preferences.timezone,
                day_cutover_local_time=preferences.day_cutover_local_time,
                preferred_sprint_minutes=preferences.preferred_sprint_minutes,
                accessibility_preferences=preferences.accessibility_preferences,
                media_preferences=preferences.media_preferences,
                preferred_voice_id=preferences.preferred_voice_id,
                voice_catalog_revision_id=preferences.voice_catalog_revision_id,
                version=preferences.version,
                updated_at=preferences.updated_at,
            )
            .returning(user_preferences.c.account_id)
        )
        if updated_id is None:
            raise DomainError(ErrorCode.VERSION_CONFLICT)

    async def add_consent(
        self,
        decision: ConsentDecision,
        *,
        expected_version: int,
    ) -> None:
        current_version = await self._session.scalar(
            select(func.max(consent_grants.c.version)).where(
                consent_grants.c.account_id == decision.account_id,
                consent_grants.c.purpose_code == decision.purpose_code,
            )
        )
        if (current_version or 0) != expected_version or decision.version != expected_version + 1:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        known = await self._session.scalar(
            select(consent_purposes.c.active).where(
                consent_purposes.c.purpose_code == decision.purpose_code
            )
        )
        if known is not True:
            raise DomainError(ErrorCode.CONSENT_PURPOSE_UNKNOWN)
        await self._session.execute(
            consent_grants.insert().values(asdict(decision) | {"status": decision.status.value})
        )

    async def get_current_consents(
        self,
        account_id: UUID,
    ) -> dict[str, ConsentDecision]:
        rows = (
            await self._session.execute(
                select(consent_grants)
                .where(consent_grants.c.account_id == account_id)
                .order_by(consent_grants.c.purpose_code, consent_grants.c.version.desc())
            )
        ).mappings()
        latest: dict[str, ConsentDecision] = {}
        for row in rows:
            latest.setdefault(row["purpose_code"], _consent_from_row(row))
        return latest

    async def revoke_session(
        self,
        session_id: UUID,
        *,
        revoked_at: object,
        reason: str,
    ) -> bool:
        updated = await self._session.scalar(
            auth_sessions.update()
            .where(
                auth_sessions.c.session_id == session_id,
                auth_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revoke_reason=reason)
            .returning(auth_sessions.c.session_id)
        )
        return updated is not None

    async def revoke_all_sessions(
        self,
        account_id: UUID,
        *,
        now: object,
        reason: str,
    ) -> int:
        new_version = await self._session.scalar(
            accounts.update()
            .where(accounts.c.account_id == account_id)
            .values(
                security_version=accounts.c.security_version + 1,
                session_version=accounts.c.session_version + 1,
                version=accounts.c.version + 1,
                security_last_activity_at=now,
            )
            .returning(accounts.c.session_version)
        )
        if new_version is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        await self._session.execute(
            auth_sessions.update()
            .where(
                auth_sessions.c.account_id == account_id,
                auth_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason=reason)
        )
        return cast(int, new_version)

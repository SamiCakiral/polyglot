import base64
import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from polyglot.platform.json_types import JsonValue

LEARNER_IDLE_TIMEOUT = timedelta(hours=12)
AUTHORING_IDLE_TIMEOUT = timedelta(minutes=30)
ABSOLUTE_SESSION_TIMEOUT = timedelta(days=7)
SESSION_ROTATION_INTERVAL = timedelta(hours=24)

_AUTHORING_ROLES: frozenset["AccountRole"]
_PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ACCESSIBILITY_KEYS = frozenset({"schema_version", "reduced_motion", "high_contrast"})
_MEDIA_KEYS = frozenset({"schema_version", "autoplay_audio"})


class IdentityValidationError(ValueError):
    pass


class InvalidIdentityTransition(IdentityValidationError):
    pass


class InvalidOidcAssertion(IdentityValidationError):
    pass


class AccountStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    PENDING_DELETION = "pending_deletion"
    DELETED = "deleted"


class AccountRole(StrEnum):
    LEARNER = "learner"
    AUTHOR = "author"
    REVIEWER = "reviewer"
    SUPPORT = "support"
    ADMIN = "admin"
    WORKER = "worker"


_AUTHORING_ROLES = frozenset(
    {
        AccountRole.AUTHOR,
        AccountRole.REVIEWER,
        AccountRole.SUPPORT,
        AccountRole.ADMIN,
    }
)


class IdentityProviderType(StrEnum):
    LOCAL_PASSWORD = "local_password"
    OIDC = "oidc"


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class IdentityAction(StrEnum):
    READ_SESSION = "read_session"
    REVOKE_SESSION = "revoke_session"
    CHANGE_PASSWORD = "change_password"
    UPDATE_PREFERENCES = "update_preferences"
    UPDATE_CONSENT = "update_consent"


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IdentityValidationError(f"{field} must be timezone-aware")


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise IdentityValidationError(f"{field} must be UUIDv7")


def _require_sha256(value: str, field: str) -> None:
    if _HEX_SHA256_PATTERN.fullmatch(value) is None:
        raise IdentityValidationError(f"{field} must be a SHA-256 fingerprint")


def normalize_identifier(identifier: str) -> str:
    normalized = unicodedata.normalize("NFKC", identifier).strip().casefold()
    contains_space = any(character.isspace() for character in normalized)
    if not normalized or len(normalized) > 320 or contains_space:
        raise IdentityValidationError("identifier is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class LoginIdentity:
    identity_id: UUID
    account_id: UUID
    provider_type: IdentityProviderType
    normalized_identifier: str | None
    password_hash: str | None
    issuer: str | None
    subject: str | None
    created_at: datetime
    last_authenticated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_uuid7(self.identity_id, "identity_id")
        _require_uuid7(self.account_id, "account_id")
        _require_aware(self.created_at, "created_at")
        if self.last_authenticated_at is not None:
            _require_aware(self.last_authenticated_at, "last_authenticated_at")
        local_shape = (
            self.normalized_identifier is not None
            and self.password_hash is not None
            and self.password_hash.startswith("$argon2id$")
            and self.issuer is None
            and self.subject is None
        )
        oidc_shape = (
            self.normalized_identifier is None
            and self.password_hash is None
            and bool(self.issuer)
            and bool(self.subject)
        )
        if self.provider_type is IdentityProviderType.LOCAL_PASSWORD and not local_shape:
            raise IdentityValidationError("local identity fields are invalid")
        if self.provider_type is IdentityProviderType.OIDC and not oidc_shape:
            raise IdentityValidationError("OIDC identity fields are invalid")

    @classmethod
    def local(
        cls,
        *,
        identity_id: UUID,
        account_id: UUID,
        identifier: str,
        password_hash: str,
        created_at: datetime,
    ) -> "LoginIdentity":
        return cls(
            identity_id=identity_id,
            account_id=account_id,
            provider_type=IdentityProviderType.LOCAL_PASSWORD,
            normalized_identifier=normalize_identifier(identifier),
            password_hash=password_hash,
            issuer=None,
            subject=None,
            created_at=created_at,
        )

    @classmethod
    def oidc(
        cls,
        *,
        identity_id: UUID,
        account_id: UUID,
        issuer: str,
        subject: str,
        created_at: datetime,
    ) -> "LoginIdentity":
        return cls(
            identity_id=identity_id,
            account_id=account_id,
            provider_type=IdentityProviderType.OIDC,
            normalized_identifier=None,
            password_hash=None,
            issuer=issuer.strip(),
            subject=subject.strip(),
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class Account:
    account_id: UUID
    status: AccountStatus
    security_version: int
    session_version: int
    version: int
    roles: frozenset[AccountRole]
    created_at: datetime
    security_last_activity_at: datetime
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_uuid7(self.account_id, "account_id")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.security_last_activity_at, "security_last_activity_at")
        if self.deleted_at is not None:
            _require_aware(self.deleted_at, "deleted_at")
        if not self.roles or min(self.security_version, self.session_version, self.version) < 1:
            raise IdentityValidationError("account versions and roles are required")
        if (self.status is AccountStatus.DELETED) != (self.deleted_at is not None):
            raise IdentityValidationError("deleted account state is inconsistent")

    @classmethod
    def new(cls, account_id: UUID, now: datetime) -> "Account":
        return cls(
            account_id=account_id,
            status=AccountStatus.ACTIVE,
            security_version=1,
            session_version=1,
            version=1,
            roles=frozenset({AccountRole.LEARNER}),
            created_at=now,
            security_last_activity_at=now,
        )

    def _security_transition(
        self,
        *,
        status: AccountStatus,
        now: datetime,
        deleted_at: datetime | None = None,
    ) -> "Account":
        if self.status is AccountStatus.DELETED:
            raise InvalidIdentityTransition("deleted account is terminal")
        return replace(
            self,
            status=status,
            security_version=self.security_version + 1,
            session_version=self.session_version + 1,
            version=self.version + 1,
            security_last_activity_at=now,
            deleted_at=deleted_at,
        )

    def lock(self, now: datetime) -> "Account":
        if self.status not in {AccountStatus.ACTIVE, AccountStatus.LOCKED}:
            raise InvalidIdentityTransition("account cannot be locked")
        if self.status is AccountStatus.LOCKED:
            return self
        return self._security_transition(status=AccountStatus.LOCKED, now=now)

    def request_deletion(self, now: datetime) -> "Account":
        if self.status not in {AccountStatus.ACTIVE, AccountStatus.LOCKED}:
            raise InvalidIdentityTransition("account cannot request deletion")
        return self._security_transition(status=AccountStatus.PENDING_DELETION, now=now)

    def mark_deleted(self, now: datetime) -> "Account":
        if self.status is not AccountStatus.PENDING_DELETION:
            raise InvalidIdentityTransition("only pending deletion can become deleted")
        return self._security_transition(status=AccountStatus.DELETED, now=now, deleted_at=now)

    def replace_roles(self, roles: frozenset[AccountRole], now: datetime) -> "Account":
        if not roles:
            raise IdentityValidationError("an account requires at least one role")
        if roles == self.roles:
            return self
        return replace(
            self,
            roles=roles,
            security_version=self.security_version + 1,
            session_version=self.session_version + 1,
            version=self.version + 1,
            security_last_activity_at=now,
        )


@dataclass(frozen=True, slots=True)
class AuthSession:
    session_id: UUID
    account_id: UUID
    session_fingerprint: str
    csrf_secret_hash: str
    roles: frozenset[AccountRole]
    account_session_version: int
    created_at: datetime
    authenticated_at: datetime
    last_seen_at: datetime
    rotated_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None

    @classmethod
    def issue(
        cls,
        *,
        session_id: UUID,
        account_id: UUID,
        session_fingerprint: str,
        csrf_secret_hash: str,
        roles: frozenset[AccountRole],
        account_session_version: int,
        now: datetime,
    ) -> "AuthSession":
        _require_uuid7(session_id, "session_id")
        _require_uuid7(account_id, "account_id")
        _require_sha256(session_fingerprint, "session_fingerprint")
        _require_sha256(csrf_secret_hash, "csrf_secret_hash")
        _require_aware(now, "now")
        if not roles or AccountRole.WORKER in roles or account_session_version < 1:
            raise IdentityValidationError("interactive session roles are invalid")
        idle_timeout = (
            AUTHORING_IDLE_TIMEOUT if roles & _AUTHORING_ROLES else LEARNER_IDLE_TIMEOUT
        )
        return cls(
            session_id=session_id,
            account_id=account_id,
            session_fingerprint=session_fingerprint,
            csrf_secret_hash=csrf_secret_hash,
            roles=roles,
            account_session_version=account_session_version,
            created_at=now,
            authenticated_at=now,
            last_seen_at=now,
            rotated_at=now,
            idle_expires_at=now + idle_timeout,
            absolute_expires_at=now + ABSOLUTE_SESSION_TIMEOUT,
        )

    def is_active(self, now: datetime, current_session_version: int) -> bool:
        return (
            self.revoked_at is None
            and self.account_session_version == current_session_version
            and now < self.idle_expires_at
            and now < self.absolute_expires_at
        )

    def requires_rotation(self, now: datetime, current_session_version: int) -> bool:
        return (
            self.account_session_version != current_session_version
            or now >= self.rotated_at + SESSION_ROTATION_INTERVAL
        )

    def touch(self, now: datetime) -> "AuthSession":
        idle_timeout = (
            AUTHORING_IDLE_TIMEOUT if self.roles & _AUTHORING_ROLES else LEARNER_IDLE_TIMEOUT
        )
        return replace(
            self,
            last_seen_at=now,
            idle_expires_at=min(now + idle_timeout, self.absolute_expires_at),
        )

    def revoke(self, now: datetime, reason: str) -> "AuthSession":
        if self.revoked_at is not None:
            return self
        if not reason.strip():
            raise IdentityValidationError("revoke reason is required")
        return replace(self, revoked_at=now, revoke_reason=reason.strip())


@dataclass(frozen=True, slots=True)
class IssuedSessionSecrets:
    session_token: str
    csrf_token: str
    session_fingerprint: str
    csrf_secret_hash: str


class SessionSecrets:
    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise IdentityValidationError("session secret key must be at least 32 bytes")
        self._key = key

    @classmethod
    def from_key(cls, key: bytes) -> "SessionSecrets":
        return cls(key)

    def _derive(self, label: bytes, session_id: UUID) -> str:
        digest = hmac.digest(self._key, label + b":" + session_id.bytes, "sha256")
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def issue(self, session_id: UUID) -> IssuedSessionSecrets:
        _require_uuid7(session_id, "session_id")
        session_token = self._derive(b"session", session_id)
        csrf_token = self._derive(b"csrf", session_id)
        fingerprint = hashlib.sha256(session_token.encode("ascii")).hexdigest()
        return IssuedSessionSecrets(
            session_token=session_token,
            csrf_token=csrf_token,
            session_fingerprint=fingerprint,
            csrf_secret_hash=_csrf_hash(fingerprint, csrf_token),
        )


def _csrf_hash(session_fingerprint: str, csrf_token: str) -> str:
    return hashlib.sha256(f"{session_fingerprint}:{csrf_token}".encode()).hexdigest()


def verify_session_csrf(
    session_fingerprint: str,
    csrf_token: str,
    expected_hash: str,
) -> bool:
    if _HEX_SHA256_PATTERN.fullmatch(expected_hash) is None:
        return False
    return hmac.compare_digest(_csrf_hash(session_fingerprint, csrf_token), expected_hash)


def _validated_preferences(
    values: dict[str, JsonValue],
    allowed: frozenset[str],
) -> dict[str, JsonValue]:
    if set(values) - allowed or values.get("schema_version") != 1:
        raise IdentityValidationError("preference document is not a closed version 1 schema")
    return dict(values)


@dataclass(frozen=True, slots=True)
class UserPreferences:
    account_id: UUID
    interface_locale: str
    timezone: str
    day_cutover_local_time: time
    preferred_sprint_minutes: int
    accessibility_preferences: dict[str, JsonValue]
    media_preferences: dict[str, JsonValue]
    preferred_voice_id: UUID | None
    voice_catalog_revision_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def defaults(cls, account_id: UUID, now: datetime) -> "UserPreferences":
        return cls(
            account_id=account_id,
            interface_locale="en",
            timezone="UTC",
            day_cutover_local_time=time(4),
            preferred_sprint_minutes=20,
            accessibility_preferences={"schema_version": 1},
            media_preferences={"schema_version": 1},
            preferred_voice_id=None,
            voice_catalog_revision_id=None,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def __post_init__(self) -> None:
        _require_uuid7(self.account_id, "account_id")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if not self.interface_locale.strip() or len(self.interface_locale) > 35:
            raise IdentityValidationError("interface locale is invalid")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise IdentityValidationError("timezone is invalid") from None
        if not 10 <= self.preferred_sprint_minutes <= 60:
            raise IdentityValidationError("preferred sprint duration is out of range")
        if self.preferred_sprint_minutes % 5:
            raise IdentityValidationError("preferred sprint duration must use five-minute steps")
        _validated_preferences(self.accessibility_preferences, _ACCESSIBILITY_KEYS)
        _validated_preferences(self.media_preferences, _MEDIA_KEYS)
        if (self.preferred_voice_id is None) != (self.voice_catalog_revision_id is None):
            raise IdentityValidationError("voice preference references must be paired")
        if self.version < 1:
            raise IdentityValidationError("preference version is invalid")

    def update(
        self,
        *,
        interface_locale: str | None = None,
        timezone: str | None = None,
        day_cutover_local_time: time | None = None,
        preferred_sprint_minutes: int | None = None,
        accessibility_preferences: dict[str, JsonValue] | None = None,
        media_preferences: dict[str, JsonValue] | None = None,
        now: datetime,
    ) -> "UserPreferences":
        return replace(
            self,
            interface_locale=interface_locale or self.interface_locale,
            timezone=timezone or self.timezone,
            day_cutover_local_time=day_cutover_local_time or self.day_cutover_local_time,
            preferred_sprint_minutes=(
                preferred_sprint_minutes
                if preferred_sprint_minutes is not None
                else self.preferred_sprint_minutes
            ),
            accessibility_preferences=(
                _validated_preferences(accessibility_preferences, _ACCESSIBILITY_KEYS)
                if accessibility_preferences is not None
                else self.accessibility_preferences
            ),
            media_preferences=(
                _validated_preferences(media_preferences, _MEDIA_KEYS)
                if media_preferences is not None
                else self.media_preferences
            ),
            version=self.version + 1,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class ConsentDecision:
    consent_id: UUID
    account_id: UUID
    purpose_code: str
    status: ConsentStatus
    policy_revision_id: UUID
    version: int
    decided_at: datetime
    withdrawn_at: datetime | None

    @classmethod
    def decide(
        cls,
        *,
        consent_id: UUID,
        account_id: UUID,
        purpose_code: str,
        status: ConsentStatus,
        policy_revision_id: UUID,
        version: int,
        now: datetime,
    ) -> "ConsentDecision":
        normalized_purpose = purpose_code.strip().casefold()
        if _PURPOSE_PATTERN.fullmatch(normalized_purpose) is None:
            raise IdentityValidationError("consent purpose code is invalid")
        return cls(
            consent_id=consent_id,
            account_id=account_id,
            purpose_code=normalized_purpose,
            status=status,
            policy_revision_id=policy_revision_id,
            version=version,
            decided_at=now,
            withdrawn_at=now if status is ConsentStatus.WITHDRAWN else None,
        )

    def __post_init__(self) -> None:
        _require_uuid7(self.consent_id, "consent_id")
        _require_uuid7(self.account_id, "account_id")
        _require_uuid7(self.policy_revision_id, "policy_revision_id")
        _require_aware(self.decided_at, "decided_at")
        if self.withdrawn_at is not None:
            _require_aware(self.withdrawn_at, "withdrawn_at")
        if (self.status is ConsentStatus.WITHDRAWN) != (self.withdrawn_at is not None):
            raise IdentityValidationError("consent withdrawal state is inconsistent")
        if self.version < 1:
            raise IdentityValidationError("consent version is invalid")

    def next(
        self,
        *,
        consent_id: UUID,
        status: ConsentStatus,
        policy_revision_id: UUID,
        now: datetime,
    ) -> "ConsentDecision":
        return self.decide(
            consent_id=consent_id,
            account_id=self.account_id,
            purpose_code=self.purpose_code,
            status=status,
            policy_revision_id=policy_revision_id,
            version=self.version + 1,
            now=now,
        )


@dataclass(frozen=True, slots=True)
class Actor:
    account_id: UUID
    roles: frozenset[AccountRole]


class AuthorizationPolicy:
    _OWNER_ACTIONS = frozenset(IdentityAction)

    def allows(
        self,
        actor: Actor,
        *,
        action: IdentityAction | str,
        resource_type: str,
        resource_id: UUID,
        scope: str,
    ) -> bool:
        try:
            canonical_action = IdentityAction(action)
        except ValueError:
            return False
        return (
            AccountRole.LEARNER in actor.roles
            and canonical_action in self._OWNER_ACTIONS
            and resource_type == "account"
            and resource_id == actor.account_id
            and scope == "owner"
        )


@dataclass(frozen=True, slots=True)
class OidcAssertion:
    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if not self.issuer.startswith("https://") or not self.subject:
            raise InvalidOidcAssertion("OIDC assertion is invalid")


class FakeOidcProvider:
    def __init__(self, assertions: dict[str, OidcAssertion]) -> None:
        self._assertions = MappingProxyType(dict(assertions))

    def authenticate(self, authorization_code: str) -> OidcAssertion:
        try:
            return self._assertions[authorization_code]
        except KeyError:
            raise InvalidOidcAssertion("OIDC assertion is invalid") from None

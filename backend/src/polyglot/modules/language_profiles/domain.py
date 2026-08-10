from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class LanguageProfileStatus(StrEnum):
    ONBOARDING = "onboarding"
    FOUNDATIONS = "foundations"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DELETING = "deleting"
    DELETED = "deleted"


class LearningPhase(StrEnum):
    DIAGNOSTIC = "diagnostic"
    FOUNDATIONS = "foundations"
    MODULE_LEARNING = "module_learning"
    PAUSED = "paused"
    ARCHIVED = "archived"


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class LearnerLanguageProfile:
    profile_id: UUID
    account_id: UUID
    target_variety_id: UUID
    native_variety_id: UUID
    status: LanguageProfileStatus
    current_phase: LearningPhase
    goals: tuple[str, ...]
    interests: tuple[str, ...]
    excluded_themes: tuple[str, ...]
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        profile_id: UUID,
        account_id: UUID,
        target_variety_id: UUID,
        native_variety_id: UUID,
        now: datetime,
    ) -> "LearnerLanguageProfile":
        return cls(
            profile_id=profile_id,
            account_id=account_id,
            target_variety_id=target_variety_id,
            native_variety_id=native_variety_id,
            status=LanguageProfileStatus.ONBOARDING,
            current_phase=LearningPhase.DIAGNOSTIC,
            goals=(),
            interests=(),
            excluded_themes=(),
            version=1,
            created_at=now,
            updated_at=now,
        )

    def __post_init__(self) -> None:
        for field, value in (
            ("profile_id", self.profile_id),
            ("account_id", self.account_id),
            ("target_variety_id", self.target_variety_id),
            ("native_variety_id", self.native_variety_id),
        ):
            if value.version != 7:
                raise _invalid(f"{field} must be UUIDv7")
        if self.target_variety_id == self.native_variety_id:
            raise _invalid("target and native varieties must differ")
        if self.version < 1:
            raise _invalid("profile version must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise _invalid("profile timestamps must be timezone-aware")
        if self.created_at > self.updated_at:
            raise _invalid("profile timestamps are unordered")
        if (self.status is LanguageProfileStatus.ARCHIVED) != (self.archived_at is not None):
            raise _invalid("archived timestamp must match status")
        if (self.status is LanguageProfileStatus.DELETED) != (self.deleted_at is not None):
            raise _invalid("deleted timestamp must match status")

    def with_goals(
        self,
        goals: tuple[str, ...],
        *,
        expected_version: int,
        now: datetime,
    ) -> "LearnerLanguageProfile":
        if expected_version != self.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        if self.status in {LanguageProfileStatus.DELETING, LanguageProfileStatus.DELETED}:
            raise DomainError(ErrorCode.PROFILE_DELETED)
        return replace(self, goals=goals, version=self.version + 1, updated_at=now)

    def transition(
        self,
        status: LanguageProfileStatus,
        *,
        now: datetime,
    ) -> "LearnerLanguageProfile":
        allowed = {
            LanguageProfileStatus.ONBOARDING: {
                LanguageProfileStatus.FOUNDATIONS,
                LanguageProfileStatus.ACTIVE,
            },
            LanguageProfileStatus.FOUNDATIONS: {LanguageProfileStatus.ACTIVE},
            LanguageProfileStatus.ACTIVE: {
                LanguageProfileStatus.PAUSED,
                LanguageProfileStatus.ARCHIVED,
            },
            LanguageProfileStatus.PAUSED: {
                LanguageProfileStatus.ACTIVE,
                LanguageProfileStatus.ARCHIVED,
            },
            LanguageProfileStatus.ARCHIVED: {
                LanguageProfileStatus.ACTIVE,
                LanguageProfileStatus.DELETING,
            },
            LanguageProfileStatus.DELETING: {LanguageProfileStatus.DELETED},
            LanguageProfileStatus.DELETED: set(),
        }
        if status not in allowed[self.status]:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        phase = {
            LanguageProfileStatus.FOUNDATIONS: LearningPhase.FOUNDATIONS,
            LanguageProfileStatus.ACTIVE: LearningPhase.MODULE_LEARNING,
            LanguageProfileStatus.PAUSED: LearningPhase.PAUSED,
            LanguageProfileStatus.ARCHIVED: LearningPhase.ARCHIVED,
        }.get(status, self.current_phase)
        return replace(
            self,
            status=status,
            current_phase=phase,
            version=self.version + 1,
            updated_at=now,
            archived_at=now if status is LanguageProfileStatus.ARCHIVED else None,
            deleted_at=now if status is LanguageProfileStatus.DELETED else None,
        )

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class LanguageRelationship(StrEnum):
    NATIVE = "native"
    FLUENT = "fluent"
    STUDIED = "studied"
    READING_ONLY = "reading_only"


class SelfAssessedBand(StrEnum):
    NEW = "new"
    FAMILIAR = "familiar"
    FUNCTIONAL = "functional"
    INDEPENDENT = "independent"
    ADVANCED = "advanced"


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class AccountLanguage:
    account_language_id: UUID
    account_id: UUID
    variety_id: UUID
    relationship: LanguageRelationship
    self_assessed_band: SelfAssessedBand
    use_for_explanations: bool
    use_for_contrasts: bool
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        account_language_id: UUID,
        account_id: UUID,
        variety_id: UUID,
        relationship: LanguageRelationship,
        self_assessed_band: SelfAssessedBand,
        use_for_explanations: bool,
        use_for_contrasts: bool,
        now: datetime,
    ) -> "AccountLanguage":
        return cls(
            account_language_id=account_language_id,
            account_id=account_id,
            variety_id=variety_id,
            relationship=relationship,
            self_assessed_band=self_assessed_band,
            use_for_explanations=use_for_explanations,
            use_for_contrasts=use_for_contrasts,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def __post_init__(self) -> None:
        for field, value in (
            ("account_language_id", self.account_language_id),
            ("account_id", self.account_id),
            ("variety_id", self.variety_id),
        ):
            if value.version != 7:
                raise _invalid(f"{field} must be UUIDv7")
        if self.version < 1:
            raise _invalid("account language version must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise _invalid("account language timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise _invalid("account language timestamps are unordered")

    @property
    def grants_mastery(self) -> bool:
        return False

    def revise(
        self,
        *,
        relationship: LanguageRelationship,
        self_assessed_band: SelfAssessedBand,
        use_for_explanations: bool,
        use_for_contrasts: bool,
        expected_version: int,
        now: datetime,
    ) -> "AccountLanguage":
        if expected_version != self.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        return replace(
            self,
            relationship=relationship,
            self_assessed_band=self_assessed_band,
            use_for_explanations=use_for_explanations,
            use_for_contrasts=use_for_contrasts,
            version=self.version + 1,
            updated_at=now,
        )

    def archive(self, *, expected_version: int, now: datetime) -> "AccountLanguage":
        if expected_version != self.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        if self.archived_at is not None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(
            self,
            version=self.version + 1,
            updated_at=now,
            archived_at=now,
        )

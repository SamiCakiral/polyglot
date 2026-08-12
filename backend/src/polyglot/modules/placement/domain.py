from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite
from uuid import UUID

from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.platform.errors import DomainError, ErrorCode

MIN_LEVEL = 0
MAX_LEVEL = 8


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _validate_level(value: int | None, field: str) -> None:
    if value is not None and not MIN_LEVEL <= value <= MAX_LEVEL:
        raise _invalid(f"{field} must be between zero and eight")


class SkillDimension(StrEnum):
    SCRIPT = "script"
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"
    VOCABULARY = "vocabulary"
    GRAMMAR_FUNCTIONS = "grammar_functions"
    INTERACTION_REPAIR = "interaction_repair"
    PRAGMATICS_REGISTER = "pragmatics_register"


class ObservationStatus(StrEnum):
    NOT_OBSERVED = "not_observed"
    PRIOR_ONLY = "prior_only"
    PROVISIONAL = "provisional"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"


class PlacementStatus(StrEnum):
    ACTIVE = "active"
    COMPLETE = "complete"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class ScoringKind(StrEnum):
    DETERMINISTIC = "deterministic"
    STRUCTURED = "structured"
    STRUCTURED_LM = "structured_lm"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class SkillEstimate:
    skill_ref: str
    status: ObservationStatus
    lower_bound: int | None
    probable_level: int | None
    upper_bound: int | None
    confidence: float
    independent_evidence_count: int
    confirmed_success_level: int | None
    confirmed_failure_level: int | None
    unresolved_contradiction_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not self.skill_ref.strip():
            raise _invalid("skill reference is required")
        for field in (
            "lower_bound",
            "probable_level",
            "upper_bound",
            "confirmed_success_level",
            "confirmed_failure_level",
        ):
            _validate_level(getattr(self, field), field)
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise _invalid("confidence must be between zero and one")
        if self.independent_evidence_count < 0:
            raise _invalid("independent evidence count must be non-negative")
        bounds = (self.lower_bound, self.probable_level, self.upper_bound)
        if self.status is ObservationStatus.NOT_OBSERVED and any(x is not None for x in bounds):
            raise _invalid("an unobserved skill cannot have an estimated level")
        if any(x is None for x in bounds) and any(x is not None for x in bounds):
            raise _invalid("estimated bounds must be all present or all absent")
        if all(x is not None for x in bounds):
            lower, probable, upper = bounds
            assert lower is not None and probable is not None and upper is not None
            if not lower <= probable <= upper:
                raise _invalid("skill estimate bounds are unordered")

    @classmethod
    def unobserved(cls, skill_ref: str) -> "SkillEstimate":
        return cls(skill_ref, ObservationStatus.NOT_OBSERVED, None, None, None, 0, 0, None, None)

    @classmethod
    def prior(cls, skill_ref: str, probable: int) -> "SkillEstimate":
        return cls(
            skill_ref,
            ObservationStatus.PRIOR_ONLY,
            0,
            probable,
            MAX_LEVEL,
            0,
            0,
            None,
            None,
        )

    @classmethod
    def observed(
        cls,
        skill_ref: str,
        *,
        lower: int,
        probable: int,
        upper: int,
        confidence: float,
        independent_evidence_count: int = 1,
        confirmed_success_level: int | None = None,
        confirmed_failure_level: int | None = None,
    ) -> "SkillEstimate":
        return cls(
            skill_ref,
            ObservationStatus.PROVISIONAL,
            lower,
            probable,
            upper,
            confidence,
            independent_evidence_count,
            confirmed_success_level,
            confirmed_failure_level,
        )


@dataclass(frozen=True, slots=True)
class PlacementCandidate:
    variant_revision_id: UUID
    variant_pool_id: str
    primitive_ref: str
    primary_skill_ref: str
    level: int
    estimated_seconds: int
    scoring_kind: ScoringKind
    secondary_skill_refs: tuple[str, ...] = ()
    prerequisite_skill_refs: tuple[str, ...] = ()
    requires_script: bool = False
    requires_media: bool = False
    is_foundation: bool = False
    scorer_available: bool = True
    media_available: bool = True

    def __post_init__(self) -> None:
        if self.variant_revision_id.version != 7:
            raise _invalid("candidate identifier must be UUIDv7")
        _validate_level(self.level, "level")
        if self.estimated_seconds <= 0:
            raise _invalid("estimated duration must be positive")
        if not self.variant_pool_id or not self.primitive_ref or not self.primary_skill_ref:
            raise _invalid("candidate references are required")


@dataclass(frozen=True, slots=True)
class PlacementObservation:
    item_instance_id: UUID
    variant_pool_id: str
    primitive_ref: str
    skill_ref: str
    level: int
    score: float | None
    confidence: float
    elapsed_seconds: int
    scoring_kind: ScoringKind
    evaluable: bool
    independent: bool = True

    def __post_init__(self) -> None:
        if self.item_instance_id.version != 7:
            raise _invalid("observation identifier must be UUIDv7")
        _validate_level(self.level, "level")
        if self.evaluable != (self.score is not None):
            raise _invalid("evaluable observations require a score")
        if self.score is not None and (not isfinite(self.score) or not 0 <= self.score <= 1):
            raise _invalid("score must be between zero and one")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise _invalid("confidence must be between zero and one")
        if self.elapsed_seconds < 0:
            raise _invalid("elapsed time must be non-negative")


@dataclass(frozen=True, slots=True)
class PlacementState:
    entry_path: EntryPath
    estimates: tuple[SkillEstimate, ...]
    observations: tuple[PlacementObservation, ...] = ()
    used_variant_pool_ids: tuple[str, ...] = ()
    status: PlacementStatus = PlacementStatus.ACTIVE

    def estimate_for(self, skill_ref: str) -> SkillEstimate:
        return next(item for item in self.estimates if item.skill_ref == skill_ref)

    def replace_estimate(self, estimate: SkillEstimate) -> "PlacementState":
        estimates = tuple(
            estimate if item.skill_ref == estimate.skill_ref else item for item in self.estimates
        )
        return replace(self, estimates=estimates)


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    candidate: PlacementCandidate | None
    reason: str


@dataclass(frozen=True, slots=True)
class StopDecision:
    should_stop: bool
    status: PlacementStatus
    reason: str

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class EntryPath(StrEnum):
    COMPLETE_BEGINNER = "complete_beginner"
    ALREADY_STARTED = "already_started"
    ADVANCED = "advanced"


class PlacementBand(StrEnum):
    FOUNDATIONS = "foundations"
    EMERGING = "emerging"
    FUNCTIONAL = "functional"
    INDEPENDENT = "independent"
    ADVANCED = "advanced"


class PlacementChoice(StrEnum):
    ACCEPT = "accept"
    START_EASIER = "start_easier"
    CHALLENGE = "challenge"
    START_NOW = "start_now"


class SkillDimension(StrEnum):
    SCRIPT = "script"
    READING = "reading"
    LISTENING = "listening"
    VOCABULARY = "vocabulary"
    PRODUCTION = "production"
    GRAMMAR_FUNCTIONS = "grammar_functions"


def _band_for_score(score: float) -> PlacementBand:
    if score < 0.3:
        return PlacementBand.FOUNDATIONS
    if score < 0.5:
        return PlacementBand.EMERGING
    if score < 0.75:
        return PlacementBand.FUNCTIONAL
    if score < 0.9:
        return PlacementBand.INDEPENDENT
    return PlacementBand.ADVANCED


def skill_profile_from_diagnostic(
    *,
    scores: dict[str, float | None],
    confidences: dict[str, float | None],
    evidence_counts: dict[str, int],
) -> tuple[PlacementBand, float, tuple["SkillEstimate", ...]]:
    evaluated_scores = [value for value in scores.values() if value is not None]
    overall_score = sum(evaluated_scores) / len(evaluated_scores) if evaluated_scores else 0.0
    overall_band = _band_for_score(overall_score)
    sources = {
        SkillDimension.SCRIPT: ("foundations",),
        SkillDimension.READING: ("reading",),
        SkillDimension.LISTENING: ("listening",),
        SkillDimension.VOCABULARY: ("reading",),
        SkillDimension.PRODUCTION: ("writing", "speaking"),
        SkillDimension.GRAMMAR_FUNCTIONS: ("foundations",),
    }
    estimates: list[SkillEstimate] = []
    for dimension, targets in sources.items():
        target_scores = [scores.get(target) for target in targets]
        available_scores = [value for value in target_scores if value is not None]
        target_confidences = [confidences.get(target) for target in targets]
        available_confidences = [value for value in target_confidences if value is not None]
        evidence_count = sum(evidence_counts.get(target, 0) for target in targets)
        estimates.append(
            SkillEstimate(
                dimension=dimension,
                band=(
                    _band_for_score(sum(available_scores) / len(available_scores))
                    if available_scores
                    else overall_band
                ),
                confidence=(
                    sum(available_confidences) / len(available_confidences)
                    if available_confidences
                    else 0.0
                ),
                evidence_count=evidence_count,
            )
        )
    overall_confidence = sum(item.confidence for item in estimates) / len(SkillDimension)
    return overall_band, overall_confidence, tuple(estimates)


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class SkillEstimate:
    dimension: SkillDimension
    band: PlacementBand
    confidence: float
    evidence_count: int

    def __post_init__(self) -> None:
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise _invalid("skill confidence must be between zero and one")
        if self.evidence_count < 0:
            raise _invalid("skill evidence count must be non-negative")


@dataclass(frozen=True, slots=True)
class OnboardingState:
    profile_id: UUID
    account_id: UUID
    entry_path: EntryPath
    detected_band: PlacementBand | None
    placement_confidence: float | None
    skill_profile: tuple[SkillEstimate, ...]
    placement_choice: PlacementChoice | None
    calibration_sessions_remaining: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def start(
        cls,
        *,
        profile_id: UUID,
        account_id: UUID,
        entry_path: EntryPath,
        now: datetime,
    ) -> "OnboardingState":
        return cls(
            profile_id=profile_id,
            account_id=account_id,
            entry_path=entry_path,
            detected_band=None,
            placement_confidence=None,
            skill_profile=(),
            placement_choice=None,
            calibration_sessions_remaining=3,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def __post_init__(self) -> None:
        if self.profile_id.version != 7 or self.account_id.version != 7:
            raise _invalid("onboarding identifiers must be UUIDv7")
        if self.version < 1:
            raise _invalid("onboarding version must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise _invalid("onboarding timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise _invalid("onboarding timestamps are unordered")
        if not 0 <= self.calibration_sessions_remaining <= 3:
            raise _invalid("calibration sessions must be between zero and three")
        if self.placement_confidence is not None and (
            not isfinite(self.placement_confidence) or not 0 <= self.placement_confidence <= 1
        ):
            raise _invalid("placement confidence must be between zero and one")
        dimensions = tuple(item.dimension for item in self.skill_profile)
        if len(dimensions) != len(set(dimensions)):
            raise _invalid("skill dimensions must be unique")

    @property
    def can_train(self) -> bool:
        return True

    @property
    def is_provisional(self) -> bool:
        return self.placement_choice is None or (
            self.placement_choice is PlacementChoice.START_NOW and self.detected_band is None
        )

    @property
    def resolved_band(self) -> PlacementBand:
        detected = self.detected_band
        if detected is None:
            return (
                PlacementBand.FOUNDATIONS
                if self.entry_path is EntryPath.COMPLETE_BEGINNER
                else PlacementBand.EMERGING
            )
        order = tuple(PlacementBand)
        index = order.index(detected)
        if self.placement_choice is PlacementChoice.START_EASIER:
            return order[max(0, index - 1)]
        if self.placement_choice is PlacementChoice.CHALLENGE:
            return order[min(len(order) - 1, index + 1)]
        return detected

    def record_placement(
        self,
        *,
        detected_band: PlacementBand,
        confidence: float,
        skills: tuple[SkillEstimate, ...],
        expected_version: int,
        now: datetime,
    ) -> "OnboardingState":
        self._require_version(expected_version)
        if {item.dimension for item in skills} != set(SkillDimension):
            raise _invalid("placement must describe every skill dimension")
        return replace(
            self,
            detected_band=detected_band,
            placement_confidence=confidence,
            skill_profile=skills,
            version=self.version + 1,
            updated_at=now,
        )

    def choose(
        self,
        choice: PlacementChoice,
        *,
        expected_version: int,
        now: datetime,
    ) -> "OnboardingState":
        self._require_version(expected_version)
        if choice is not PlacementChoice.START_NOW and self.detected_band is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(
            self,
            placement_choice=choice,
            version=self.version + 1,
            updated_at=now,
        )

    def register_calibration_session(
        self, *, expected_version: int, now: datetime
    ) -> "OnboardingState":
        self._require_version(expected_version)
        if self.calibration_sessions_remaining == 0:
            return self
        return replace(
            self,
            calibration_sessions_remaining=self.calibration_sessions_remaining - 1,
            version=self.version + 1,
            updated_at=now,
        )

    def _require_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)

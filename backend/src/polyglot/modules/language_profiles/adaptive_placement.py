from collections import Counter
from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from polyglot.modules.language_profiles.onboarding import EntryPath, SkillDimension
from polyglot.platform.errors import DomainError, ErrorCode


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class PlacementCandidate:
    item_revision_id: UUID
    dimension: SkillDimension
    difficulty: int
    estimated_seconds: int
    requires_script: bool = False
    is_foundation: bool = False

    def __post_init__(self) -> None:
        if self.item_revision_id.version != 7:
            raise _invalid("placement candidate id must be UUIDv7")
        if not 1 <= self.difficulty <= 5:
            raise _invalid("placement difficulty must be between one and five")
        if not 15 <= self.estimated_seconds <= 180:
            raise _invalid("placement duration must be between 15 and 180 seconds")


@dataclass(frozen=True, slots=True)
class PlacementObservation:
    item_revision_id: UUID
    dimension: SkillDimension
    score: float
    confidence: float
    elapsed_seconds: int

    def __post_init__(self) -> None:
        if self.item_revision_id.version != 7:
            raise _invalid("placement observation id must be UUIDv7")
        for field, value in (("score", self.score), ("confidence", self.confidence)):
            if not isfinite(value) or not 0 <= value <= 1:
                raise _invalid(f"{field} must be between zero and one")
        if self.elapsed_seconds < 0:
            raise _invalid("placement elapsed time must be non-negative")


class AdaptivePlacementPlanner:
    minimum_seconds = 300
    maximum_seconds = 600

    def __init__(self, entry_path: EntryPath) -> None:
        self._initial_difficulty = {
            EntryPath.COMPLETE_BEGINNER: 1,
            EntryPath.ALREADY_STARTED: 2,
            EntryPath.ADVANCED: 4,
        }[entry_path]

    def next_item(
        self,
        candidates: tuple[PlacementCandidate, ...],
        history: tuple[PlacementObservation, ...],
    ) -> PlacementCandidate | None:
        elapsed = sum(item.elapsed_seconds for item in history)
        if elapsed >= self.maximum_seconds:
            return None
        coverage = Counter(item.dimension for item in history)
        if elapsed >= self.minimum_seconds and all(
            coverage[dimension] > 0 for dimension in SkillDimension
        ):
            return None

        used = {item.item_revision_id for item in history}
        available = [item for item in candidates if item.item_revision_id not in used]
        script_scores = [item.score for item in history if item.dimension is SkillDimension.SCRIPT]
        script_ready = not script_scores or sum(script_scores) / len(script_scores) >= 0.4
        if not script_ready:
            accessible = [item for item in available if not item.requires_script]
            foundations = [item for item in accessible if item.is_foundation]
            available = foundations or accessible
        if not available:
            return None

        minimum_coverage = min(coverage[item.dimension] for item in available)
        least_observed = [
            item for item in available if coverage[item.dimension] == minimum_coverage
        ]
        desired_difficulty = self._desired_difficulty(history)
        return min(
            least_observed,
            key=lambda item: (
                abs(item.difficulty - desired_difficulty),
                item.difficulty,
                str(item.item_revision_id),
            ),
        )

    def _desired_difficulty(self, history: tuple[PlacementObservation, ...]) -> int:
        if not history:
            return self._initial_difficulty
        recent = history[-2:]
        score = sum(item.score for item in recent) / len(recent)
        adjustment = 1 if score >= 0.8 else -1 if score <= 0.35 else 0
        return max(1, min(5, self._initial_difficulty + adjustment))

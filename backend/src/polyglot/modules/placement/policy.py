from dataclasses import replace
from hashlib import sha256
from typing import ClassVar

from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.modules.placement.domain import (
    MAX_LEVEL,
    ObservationStatus,
    PlacementCandidate,
    PlacementObservation,
    PlacementState,
    PlacementStatus,
    ScoringKind,
    SelectionDecision,
    SkillEstimate,
    StopDecision,
)


class PlacementPolicyV1:
    minimum_seconds = 480
    target_seconds = 720
    maximum_seconds = 1200

    _priors: ClassVar[dict[EntryPath, int]] = {
        EntryPath.COMPLETE_BEGINNER: 1,
        EntryPath.ALREADY_STARTED: 3,
        EntryPath.ADVANCED: 6,
    }

    def initial_state(self, entry_path: EntryPath, skill_refs: tuple[str, ...]) -> PlacementState:
        prior = self._priors[entry_path]
        return PlacementState(
            entry_path,
            tuple(SkillEstimate.prior(ref, prior) for ref in skill_refs),
        )

    def update(self, state: PlacementState, observation: PlacementObservation) -> PlacementState:
        observations = (*state.observations, observation)
        pools = (*state.used_variant_pool_ids, observation.variant_pool_id)
        if not observation.evaluable or observation.score is None:
            return replace(state, observations=observations, used_variant_pool_ids=pools)
        current = state.estimate_for(observation.skill_ref)
        lower = current.lower_bound if current.lower_bound is not None else 0
        upper = current.upper_bound if current.upper_bound is not None else MAX_LEVEL
        success = current.confirmed_success_level
        failure = current.confirmed_failure_level
        count = current.independent_evidence_count + int(observation.independent)
        closes_bound = observation.scoring_kind in {
            ScoringKind.DETERMINISTIC,
            ScoringKind.STRUCTURED,
        }
        if observation.score >= 0.8:
            success = max(success or 0, observation.level)
            lower = max(lower, observation.level)
        elif observation.score <= 0.35 and closes_bound:
            failure = min(failure if failure is not None else MAX_LEVEL, observation.level)
            upper = min(upper, observation.level)
        if lower > upper:
            lower, upper = min(lower, upper), max(lower, upper)
        probable = min(upper, max(lower, round((lower + upper) / 2)))
        confidence = min(1.0, count / 4)
        status = ObservationStatus.CORROBORATED if count >= 2 else ObservationStatus.PROVISIONAL
        estimate = SkillEstimate(
            skill_ref=current.skill_ref,
            status=status,
            lower_bound=lower,
            probable_level=probable,
            upper_bound=upper,
            confidence=confidence,
            independent_evidence_count=count,
            confirmed_success_level=success,
            confirmed_failure_level=failure,
        )
        return replace(
            state.replace_estimate(estimate),
            observations=observations,
            used_variant_pool_ids=pools,
        )

    def select(
        self,
        state: PlacementState,
        candidates: tuple[PlacementCandidate, ...],
        *,
        seconds_remaining: int,
        seed: str,
    ) -> SelectionDecision:
        available = tuple(
            item
            for item in candidates
            if item.variant_pool_id not in state.used_variant_pool_ids
            and item.estimated_seconds <= seconds_remaining
            and item.scorer_available
            and (not item.requires_media or item.media_available)
        )
        if not available:
            return SelectionDecision(None, "no_accessible_candidate")

        def priority(item: PlacementCandidate) -> tuple[int, int, str, str]:
            estimate = state.estimate_for(item.primary_skill_ref)
            evidence = estimate.independent_evidence_count
            distance = abs((estimate.probable_level or 0) - item.level)
            digest = sha256(f"{seed}:{item.variant_revision_id}".encode()).hexdigest()
            return evidence, distance, digest, str(item.variant_revision_id)

        return SelectionDecision(min(available, key=priority), "lowest_evidence_near_boundary")

    def should_stop(
        self,
        state: PlacementState,
        *,
        elapsed_seconds: int,
        provider_failure_count: int = 0,
    ) -> StopDecision:
        if provider_failure_count >= 2:
            return StopDecision(True, PlacementStatus.PARTIAL, "provider_unavailable")
        if elapsed_seconds >= self.maximum_seconds:
            return StopDecision(True, PlacementStatus.PARTIAL, "maximum_duration_reached")
        observed = tuple(item for item in state.estimates if item.independent_evidence_count > 0)
        confirmed_beginner = (
            state.entry_path is EntryPath.COMPLETE_BEGINNER
            and len(observed) == len(state.estimates)
            and all(
                item.independent_evidence_count >= 2
                and item.upper_bound is not None
                and item.upper_bound <= 1
                for item in observed
            )
        )
        if confirmed_beginner:
            return StopDecision(True, PlacementStatus.COMPLETE, "confirmed_absolute_beginner")
        if elapsed_seconds >= self.minimum_seconds and all(
            item.independent_evidence_count >= 2 for item in state.estimates
        ):
            return StopDecision(True, PlacementStatus.COMPLETE, "sufficient_skill_coverage")
        return StopDecision(False, PlacementStatus.ACTIVE, "more_evidence_required")

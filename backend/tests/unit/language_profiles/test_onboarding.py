from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.modules.language_profiles.onboarding import (
    EntryPath,
    OnboardingState,
    PlacementBand,
    PlacementChoice,
    SkillDimension,
    SkillEstimate,
    skill_profile_from_diagnostic,
)
from polyglot.platform.errors import DomainError

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
PROFILE_ID = UUID("019f0000-0000-7000-8000-000000000401")
ACCOUNT_ID = UUID("019f0000-0000-7000-8000-000000000402")


def estimates(band: PlacementBand = PlacementBand.FUNCTIONAL) -> tuple[SkillEstimate, ...]:
    return tuple(
        SkillEstimate(dimension, band, confidence=0.8, evidence_count=2)
        for dimension in SkillDimension
    )


def test_onboarding_preserves_training_access_before_placement() -> None:
    state = OnboardingState.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ALREADY_STARTED,
        now=NOW,
    )

    assert state.can_train is True
    assert state.is_provisional is True
    assert state.calibration_sessions_remaining == 3


def test_placement_is_descriptive_and_user_can_start_easier() -> None:
    state = OnboardingState.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ALREADY_STARTED,
        now=NOW,
    ).record_placement(
        detected_band=PlacementBand.FUNCTIONAL,
        confidence=0.8,
        skills=estimates(),
        expected_version=1,
        now=NOW,
    )
    chosen = state.choose(
        PlacementChoice.START_EASIER,
        expected_version=2,
        now=NOW,
    )

    assert chosen.resolved_band is PlacementBand.EMERGING
    assert chosen.is_provisional is False
    assert {item.dimension for item in chosen.skill_profile} == set(SkillDimension)


def test_start_now_works_without_diagnostic_and_calibrates_three_sessions() -> None:
    state = OnboardingState.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.COMPLETE_BEGINNER,
        now=NOW,
    ).choose(PlacementChoice.START_NOW, expected_version=1, now=NOW)

    for expected in (2, 3, 4):
        state = state.register_calibration_session(expected_version=expected, now=NOW)

    assert state.resolved_band is PlacementBand.FOUNDATIONS
    assert state.calibration_sessions_remaining == 0


def test_accept_requires_a_placement_result() -> None:
    state = OnboardingState.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ADVANCED,
        now=NOW,
    )

    with pytest.raises(DomainError):
        state.choose(PlacementChoice.ACCEPT, expected_version=1, now=NOW)


def test_diagnostic_mapping_keeps_untested_skills_explicit() -> None:
    band, confidence, profile = skill_profile_from_diagnostic(
        scores={"foundations": 0.9, "reading": 0.7, "writing": 0.55},
        confidences={"foundations": 0.8, "reading": 0.7, "writing": 0.6},
        evidence_counts={"foundations": 2, "reading": 2, "writing": 2},
    )

    by_dimension = {item.dimension: item for item in profile}
    assert band is PlacementBand.FUNCTIONAL
    assert confidence == pytest.approx(0.6)
    assert by_dimension[SkillDimension.LISTENING].evidence_count == 0
    assert by_dimension[SkillDimension.LISTENING].confidence == 0

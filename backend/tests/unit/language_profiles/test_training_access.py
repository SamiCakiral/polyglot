from datetime import UTC, datetime
from uuid import UUID

from polyglot.modules.language_profiles.domain import (
    LanguageProfileStatus,
    LearnerLanguageProfile,
    TrainingAccess,
)


def _profile() -> LearnerLanguageProfile:
    return LearnerLanguageProfile.create(
        profile_id=UUID("019f0000-0000-7000-8000-000000000101"),
        account_id=UUID("019f0000-0000-7000-8000-000000000102"),
        target_variety_id=UUID("019f0000-0000-7000-8000-000000000103"),
        native_variety_id=UUID("019f0000-0000-7000-8000-000000000104"),
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_onboarding_and_foundations_adapt_training_instead_of_blocking_it() -> None:
    onboarding = _profile()
    foundations = onboarding.transition(
        LanguageProfileStatus.FOUNDATIONS,
        now=datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
    )

    assert onboarding.training_access is TrainingAccess.ADAPTED
    assert foundations.training_access is TrainingAccess.ADAPTED


def test_active_profile_has_full_training_access() -> None:
    active = _profile().transition(
        LanguageProfileStatus.ACTIVE,
        now=datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
    )

    assert active.training_access is TrainingAccess.FULL

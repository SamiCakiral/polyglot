from datetime import UTC, datetime
from uuid import UUID

from polyglot.modules.identity.languages import (
    AccountLanguage,
    LanguageRelationship,
    SelfAssessedBand,
)


def test_account_language_is_context_not_mastery_evidence() -> None:
    language = AccountLanguage.create(
        account_language_id=UUID("019f0000-0000-7000-8000-000000000201"),
        account_id=UUID("019f0000-0000-7000-8000-000000000202"),
        variety_id=UUID("019f0000-0000-7000-8000-000000000203"),
        relationship=LanguageRelationship.FLUENT,
        self_assessed_band=SelfAssessedBand.INDEPENDENT,
        use_for_explanations=True,
        use_for_contrasts=True,
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert language.relationship is LanguageRelationship.FLUENT
    assert language.grants_mastery is False
    assert language.version == 1


def test_native_language_can_be_excluded_from_explanations() -> None:
    language = AccountLanguage.create(
        account_language_id=UUID("019f0000-0000-7000-8000-000000000201"),
        account_id=UUID("019f0000-0000-7000-8000-000000000202"),
        variety_id=UUID("019f0000-0000-7000-8000-000000000203"),
        relationship=LanguageRelationship.NATIVE,
        self_assessed_band=SelfAssessedBand.ADVANCED,
        use_for_explanations=False,
        use_for_contrasts=True,
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert language.use_for_explanations is False


def test_language_revision_and_archive_are_versioned() -> None:
    language = AccountLanguage.create(
        account_language_id=UUID("019f0000-0000-7000-8000-000000000201"),
        account_id=UUID("019f0000-0000-7000-8000-000000000202"),
        variety_id=UUID("019f0000-0000-7000-8000-000000000203"),
        relationship=LanguageRelationship.STUDIED,
        self_assessed_band=SelfAssessedBand.FAMILIAR,
        use_for_explanations=True,
        use_for_contrasts=True,
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )
    revised = language.revise(
        relationship=LanguageRelationship.FLUENT,
        self_assessed_band=SelfAssessedBand.INDEPENDENT,
        use_for_explanations=True,
        use_for_contrasts=True,
        expected_version=1,
        now=datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
    )
    archived = revised.archive(
        expected_version=2,
        now=datetime(2026, 8, 11, 0, 2, tzinfo=UTC),
    )

    assert revised.version == 2
    assert archived.version == 3
    assert archived.archived_at is not None

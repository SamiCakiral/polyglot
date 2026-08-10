from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
AUTHOR_ID = UUID("019fe001-0000-7000-8000-000000000001")
REVIEWER_ID = UUID("019fe001-0000-7000-8000-000000000002")
CONTENT_ID = UUID("019fe001-0000-7000-8000-000000000003")
REVISION_ID = UUID("019fe001-0000-7000-8000-000000000004")
NEXT_REVISION_ID = UUID("019fe001-0000-7000-8000-000000000005")
PROVENANCE_ID = UUID("019fe001-0000-7000-8000-000000000006")
VARIETY_ID = UUID("019fe001-0000-7000-8000-000000000007")
VALIDATOR_SET_ID = UUID("019fe001-0000-7000-8000-000000000008")


def draft():
    from polyglot.modules.content.domain import ContentRevision

    return ContentRevision.create_draft(
        content_id=CONTENT_ID,
        content_revision_id=REVISION_ID,
        revision_no=1,
        variety_id=VARIETY_ID,
        created_by_actor_id=AUTHOR_ID,
        provenance_id=PROVENANCE_ID,
        rights_ref="rights:fixture:content",
        payload={"schema_version": 1, "kind": "dialogue", "text": "Ciao."},
        now=NOW,
    )


def test_revising_a_draft_creates_a_new_immutable_revision() -> None:
    original = draft()

    revised = original.revise(
        content_revision_id=NEXT_REVISION_ID,
        revision_no=2,
        actor_id=AUTHOR_ID,
        payload={"schema_version": 1, "kind": "dialogue", "text": "Buongiorno."},
        provenance_id=PROVENANCE_ID,
        rights_ref="rights:fixture:content",
        now=NOW,
    )

    assert original.payload["text"] == "Ciao."
    assert revised.payload["text"] == "Buongiorno."
    assert revised.supersedes_revision_id == original.content_revision_id
    assert revised.status.value == "draft"
    assert revised.revision_no == 2


def test_author_cannot_approve_own_validated_revision_even_with_reviewer_role() -> None:
    from polyglot.modules.content.domain import ValidationOutcome

    validated = (
        draft()
        .start_validation()
        .complete_validation(
            outcome=ValidationOutcome.passed(VALIDATOR_SET_ID),
            now=NOW,
        )
    )

    with pytest.raises(DomainError) as rejected:
        validated.approve(actor_id=AUTHOR_ID, now=NOW)

    assert rejected.value.code is ErrorCode.SELF_APPROVAL_FORBIDDEN


def test_human_required_validation_cannot_transition_to_approval() -> None:
    from polyglot.modules.content.domain import ValidationOutcome

    pending_human_review = (
        draft()
        .start_validation()
        .complete_validation(
            outcome=ValidationOutcome.human_required(VALIDATOR_SET_ID),
            now=NOW,
        )
    )

    with pytest.raises(DomainError) as rejected:
        pending_human_review.approve(actor_id=REVIEWER_ID, now=NOW)

    assert rejected.value.code is ErrorCode.INVALID_TRANSITION


def test_published_revision_can_spawn_a_draft_but_cannot_be_republished() -> None:
    from polyglot.modules.content.domain import ValidationOutcome

    published = (
        draft()
        .start_validation()
        .complete_validation(ValidationOutcome.passed(VALIDATOR_SET_ID), now=NOW)
        .approve(actor_id=REVIEWER_ID, now=NOW)
        .publish(now=NOW)
    )

    correction = published.revise(
        content_revision_id=NEXT_REVISION_ID,
        revision_no=2,
        actor_id=AUTHOR_ID,
        payload={"schema_version": 1, "kind": "dialogue", "text": "Ciao."},
        provenance_id=PROVENANCE_ID,
        rights_ref="rights:fixture:content",
        now=NOW,
    )
    with pytest.raises(DomainError) as publish_rejected:
        published.publish(now=NOW)

    assert published.status.value == "published"
    assert correction.status.value == "draft"
    assert correction.supersedes_revision_id == published.content_revision_id
    assert publish_rejected.value.code is ErrorCode.INVALID_TRANSITION


def test_validation_models_every_transition_without_skipping_validating() -> None:
    from polyglot.modules.content.domain import ContentRevisionStatus, ValidationOutcome

    with pytest.raises(DomainError) as skipped:
        draft().complete_validation(ValidationOutcome.passed(VALIDATOR_SET_ID), now=NOW)

    validating = draft().start_validation()
    failed = validating.complete_validation(ValidationOutcome.failed(VALIDATOR_SET_ID), now=NOW)
    passed = validating.complete_validation(ValidationOutcome.passed(VALIDATOR_SET_ID), now=NOW)

    assert skipped.value.code is ErrorCode.INVALID_TRANSITION
    assert validating.status is ContentRevisionStatus.VALIDATING
    assert failed.status is ContentRevisionStatus.DRAFT
    assert passed.status is ContentRevisionStatus.VALIDATED


def test_draft_can_be_abandoned_and_validated_revision_can_be_rejected() -> None:
    from polyglot.modules.content.domain import ContentRevisionStatus, ValidationOutcome

    abandoned = draft().abandon(now=NOW)
    rejected = (
        draft()
        .start_validation()
        .complete_validation(ValidationOutcome.passed(VALIDATOR_SET_ID), now=NOW)
        .reject(now=NOW)
    )

    assert abandoned.status is ContentRevisionStatus.ABANDONED
    assert rejected.status is ContentRevisionStatus.REJECTED

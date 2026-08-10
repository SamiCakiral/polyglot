from datetime import UTC, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
AUTHOR_ID = UUID("019fe002-0000-7000-8000-000000000001")
REVIEWER_ID = UUID("019fe002-0000-7000-8000-000000000002")
CONTENT_ID = UUID("019fe002-0000-7000-8000-000000000003")
PROVENANCE_ID = UUID("019fe002-0000-7000-8000-000000000004")
VARIETY_ID = UUID("019fe002-0000-7000-8000-000000000005")
VALIDATOR_SET_ID = UUID("019fe002-0000-7000-8000-000000000006")


def identifier(offset: int) -> UUID:
    return UUID(int=(0x019FE002 << 96) | (0x7000 << 64) | (0x8000 << 48) | offset)


@given(st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=8))
def test_revision_chain_preserves_each_payload_and_monotonic_numbers(texts: list[str]) -> None:
    from polyglot.modules.content.domain import ContentRevision

    revision = ContentRevision.create_draft(
        content_id=CONTENT_ID,
        content_revision_id=identifier(1),
        revision_no=1,
        variety_id=VARIETY_ID,
        created_by_actor_id=AUTHOR_ID,
        provenance_id=PROVENANCE_ID,
        rights_ref="rights:fixture:content",
        payload={"schema_version": 1, "text": texts[0]},
        now=NOW,
    )
    revisions = [revision]
    for revision_no, text in enumerate(texts[1:], start=2):
        revision = revision.revise(
            content_revision_id=identifier(revision_no),
            revision_no=revision_no,
            actor_id=AUTHOR_ID,
            payload={"schema_version": 1, "text": text},
            provenance_id=PROVENANCE_ID,
            rights_ref="rights:fixture:content",
            now=NOW,
        )
        revisions.append(revision)

    assert [item.revision_no for item in revisions] == list(range(1, len(texts) + 1))
    assert [item.payload["text"] for item in revisions] == texts


def test_same_actor_is_never_an_approver() -> None:
    from polyglot.modules.content.domain import ContentRevision, ValidationOutcome

    revision = ContentRevision.create_draft(
        content_id=CONTENT_ID,
        content_revision_id=identifier(9),
        revision_no=1,
        variety_id=VARIETY_ID,
        created_by_actor_id=AUTHOR_ID,
        provenance_id=PROVENANCE_ID,
        rights_ref="rights:fixture:content",
        payload={"schema_version": 1, "text": "Ciao."},
        now=NOW,
    ).complete_validation(ValidationOutcome.passed(VALIDATOR_SET_ID), now=NOW)

    with pytest.raises(DomainError) as rejected:
        revision.approve(actor_id=AUTHOR_ID, now=NOW)

    assert rejected.value.code is ErrorCode.SELF_APPROVAL_FORBIDDEN

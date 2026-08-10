from __future__ import annotations

from uuid import UUID

import pytest

from polyglot.modules.lexicon.exchange.lists import ListAssociation
from polyglot.platform.errors import DomainError, ErrorCode


@pytest.mark.parametrize(
    "target_type",
    (
        "module_revision",
        "module_day_revision",
        "session_plan",
        "exercise_definition_revision",
    ),
)
def test_association_targets_are_closed_and_never_award_evidence(target_type: str) -> None:
    association = ListAssociation.create(
        target_type=target_type,
        target_id=UUID("019bfcc0-7cf1-7000-8000-000000000010"),
        role="target",
    )

    assert association.target_type == target_type
    assert not hasattr(association, "mastery")
    assert not hasattr(association, "evidence")


def test_association_rejects_unknown_target() -> None:
    with pytest.raises(DomainError) as rejected:
        ListAssociation.create(
            target_type="sprint_run",
            target_id=UUID("019bfcc0-7cf1-7000-8000-000000000010"),
            role="target",
        )
    assert rejected.value.code is ErrorCode.VALIDATION_FAILED

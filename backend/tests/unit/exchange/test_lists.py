from __future__ import annotations

from uuid import UUID

import pytest

from polyglot.modules.lexicon.exchange.lists import (
    DynamicListPolicy,
    ListDefinition,
    ListStatus,
    archive_list,
    snapshot_checksum,
)
from polyglot.platform.errors import DomainError, ErrorCode

PROFILE = UUID("019bfcc0-7cf1-7000-8000-000000000001")
SENSE_A = UUID("019bfcc0-7cf1-7000-8000-000000000002")
SENSE_B = UUID("019bfcc0-7cf1-7000-8000-000000000003")


def test_manual_dynamic_and_editorial_lists_have_closed_rules() -> None:
    manual = ListDefinition.create("manual", None, actor_roles=("learner",))
    dynamic = ListDefinition.create(
        "dynamic",
        {"all": [{"tag_in": ["voyage"]}, {"has_due_prompt": True}]},
        actor_roles=("learner",),
    )
    editorial = ListDefinition.create("editorial", None, actor_roles=("author",))

    assert manual.query_definition is None
    assert dynamic.query_definition is not None
    assert editorial.list_type == "editorial"

    with pytest.raises(DomainError) as missing_query:
        ListDefinition.create("dynamic", None, actor_roles=("learner",))
    with pytest.raises(DomainError) as learner_editorial:
        ListDefinition.create("editorial", None, actor_roles=("learner",))
    assert missing_query.value.code is ErrorCode.VALIDATION_FAILED
    assert learner_editorial.value.code is ErrorCode.FORBIDDEN


def test_dynamic_ast_rejects_unknown_predicates_depth_and_large_values() -> None:
    policy = DynamicListPolicy(max_depth=2, max_predicates=2, max_values=2)

    for query in (
        {"sql": "SELECT *"},
        {"not": {"not": {"tag_in": ["x"]}}},
        {"sense_id_in": [str(SENSE_A), str(SENSE_B), str(PROFILE)]},
    ):
        with pytest.raises(DomainError) as rejected:
            policy.validate(query)
        assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_snapshot_checksum_canonicalizes_only_unordered_lists() -> None:
    ordered_ab = snapshot_checksum(PROFILE, (SENSE_A, SENSE_B), ordered=True)
    ordered_ba = snapshot_checksum(PROFILE, (SENSE_B, SENSE_A), ordered=True)
    unordered_ab = snapshot_checksum(PROFILE, (SENSE_A, SENSE_B), ordered=False)
    unordered_ba = snapshot_checksum(PROFILE, (SENSE_B, SENSE_A), ordered=False)

    assert ordered_ab != ordered_ba
    assert unordered_ab == unordered_ba
    assert ordered_ab != unordered_ab


@pytest.mark.parametrize(
    "query",
    (
        {"not": [{"tag_in": ["x"]}]},
        {"all": {"tag_in": ["x"]}},
        {"has_due_prompt": "yes"},
        {"tag_in": []},
    ),
)
def test_dynamic_ast_validates_operator_and_predicate_shapes(
    query: dict[str, object],
) -> None:
    with pytest.raises(DomainError) as rejected:
        DynamicListPolicy().validate(query)
    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_archiving_changes_status_without_mutating_historical_revision() -> None:
    archived = archive_list(ListStatus.ACTIVE, version=4)

    assert archived.status is ListStatus.ARCHIVED
    assert archived.version == 5
    with pytest.raises(DomainError) as duplicate:
        archive_list(ListStatus.ARCHIVED, version=5)
    assert duplicate.value.code is ErrorCode.INVALID_TRANSITION

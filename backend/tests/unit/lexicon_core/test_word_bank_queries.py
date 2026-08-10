from uuid import UUID

import pytest

from polyglot.modules.lexicon.core.queries import (
    GraphEdge,
    WordBankItem,
    bounded_neighborhood,
    paginate_word_bank,
)
from polyglot.platform.errors import DomainError, ErrorCode


def uid(number: int) -> UUID:
    return UUID(f"019feb40-0000-7000-8000-{number:012x}")


def items(size: int = 10) -> tuple[WordBankItem, ...]:
    return tuple(
        WordBankItem(uid(index), f"mot-{index:02d}", index, (f"source-{index}",))
        for index in range(1, size + 1)
    )


def test_keyset_pagination_is_stable_and_has_no_duplicate() -> None:
    first = paginate_word_bank(items(), limit=4, cursor=None)
    second = paginate_word_bank(items(), limit=4, cursor=first.next_cursor)
    third = paginate_word_bank(items(), limit=4, cursor=second.next_cursor)

    seen = first.items + second.items + third.items
    assert seen == items()
    assert len({item.sense_id for item in seen}) == 10


def test_cursor_rejects_tampering_and_wrong_reference_revision() -> None:
    page = paginate_word_bank(items(), limit=4, cursor=None, reference_revision="freq-it-v1")

    with pytest.raises(DomainError) as error:
        paginate_word_bank(
            items(),
            limit=4,
            cursor=page.next_cursor,
            reference_revision="freq-it-v2",
        )

    assert error.value.code is ErrorCode.CURSOR_INVALID


def test_neighborhood_requires_edge_types_and_hard_bounds() -> None:
    edges = tuple(
        GraphEdge(uid(index), uid(index + 1), "confusable") for index in range(1, 800)
    )

    result = bounded_neighborhood(
        uid(1), edges, depth=2, edge_types=frozenset({"confusable"}), max_nodes=500
    )

    assert result.nodes == (uid(1), uid(2), uid(3))
    assert len(result.nodes) <= 500
    with pytest.raises(DomainError):
        bounded_neighborhood(uid(1), edges, depth=3, edge_types=frozenset({"confusable"}))
    with pytest.raises(DomainError):
        bounded_neighborhood(uid(1), edges, depth=2, edge_types=frozenset())

from __future__ import annotations

from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.lexicon.exchange.domain import (
    ImportCandidate,
    ImportStrategy,
    create_preview,
)

VARIETY = UUID("019bfcc0-7cf1-7000-8000-000000000001")


@given(
    st.lists(
        st.text(
            alphabet=st.characters(categories=("Ll", "Lu")),
            min_size=1,
            max_size=24,
        ),
        min_size=1,
        max_size=40,
        unique=True,
    )
)
def test_conflict_free_preview_is_deterministic_and_preserves_line_order(
    forms: list[str],
) -> None:
    rows = tuple(
        ImportCandidate(
            line_no=index,
            source_key=f"line-{index}",
            variety_id=VARIETY,
            unit_type="word",
            normalized_form=form,
            semantic_key=f"sense-{index}",
            prompt_key=None,
            external_identity=None,
            external_revision=None,
            visibility="private",
            payload_checksum=f"{index:064x}",
        )
        for index, form in enumerate(forms, 1)
    )

    first = create_preview(rows, (), ImportStrategy.INTERACTIVE, "catalogue:17")
    second = create_preview(rows, (), ImportStrategy.INTERACTIVE, "catalogue:17")

    assert first == second
    assert tuple(line.line_no for line in first.lines) == tuple(range(1, len(rows) + 1))

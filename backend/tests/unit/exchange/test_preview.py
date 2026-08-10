from __future__ import annotations

from uuid import UUID

import pytest

from polyglot.modules.lexicon.exchange.domain import (
    ConflictClass,
    ExistingLexicalCandidate,
    ImportCandidate,
    ImportStrategy,
    PreviewDecision,
    classify_candidate,
    create_preview,
)
from polyglot.platform.errors import DomainError, ErrorCode

VARIETY = UUID("019bfcc0-7cf1-7000-8000-000000000001")


def candidate(**changes: object) -> ImportCandidate:
    values: dict[str, object] = {
        "line_no": 1,
        "source_key": "line-1",
        "variety_id": VARIETY,
        "unit_type": "word",
        "normalized_form": "pesca",
        "semantic_key": "fruit.peach",
        "prompt_key": None,
        "external_identity": None,
        "external_revision": None,
        "visibility": "private",
        "payload_checksum": "a" * 64,
    }
    values.update(changes)
    return ImportCandidate(**values)  # type: ignore[arg-type]


def existing(**changes: object) -> ExistingLexicalCandidate:
    values: dict[str, object] = {
        "entity_ref": "sense:peach",
        "variety_id": VARIETY,
        "unit_type": "word",
        "normalized_form": "pesca",
        "semantic_key": "fruit.peach",
        "prompt_key": None,
        "external_identity": None,
        "external_revision": None,
        "visibility": "shared",
        "payload_checksum": "a" * 64,
    }
    values.update(changes)
    return ExistingLexicalCandidate(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("incoming", "known", "expected"),
    (
        (
            candidate(external_identity="lex:1", external_revision="4"),
            existing(external_identity="lex:1", external_revision="4"),
            ConflictClass.EXACT_IDENTITY,
        ),
        (
            candidate(external_identity="lex:1", external_revision="5"),
            existing(external_identity="lex:1", external_revision="4"),
            ConflictClass.CONTENT_REVISION_CONFLICT,
        ),
        (candidate(), existing(), ConflictClass.SAME_SENSE),
        (
            candidate(semantic_key="sport.fishing"),
            existing(),
            ConflictClass.SAME_FORM_OTHER_SENSE,
        ),
        (
            candidate(prompt_key="p:it-fr"),
            existing(prompt_key="p:it-fr"),
            ConflictClass.SAME_PROMPT,
        ),
        (
            candidate(semantic_key=None),
            existing(semantic_key=None),
            ConflictClass.PRIVATE_PUBLIC_COLLISION,
        ),
        (
            candidate(normalized_form="andare via", unit_type="multiword_expression"),
            existing(
                normalized_form="andare via",
                unit_type="multiword_expression",
                semantic_key=None,
                visibility="private",
            ),
            ConflictClass.AMBIGUOUS,
        ),
    ),
)
def test_candidate_classification_is_semantic_not_string_only(
    incoming: ImportCandidate,
    known: ExistingLexicalCandidate,
    expected: ConflictClass,
) -> None:
    assert classify_candidate(incoming, known).conflict_class is expected


def test_preview_is_stable_and_does_not_mutate_candidates() -> None:
    rows = (
        candidate(),
        candidate(
            line_no=2,
            source_key="line-2",
            normalized_form="treno",
            semantic_key="transport.train",
        ),
    )
    known = (existing(),)

    first = create_preview(rows, known, ImportStrategy.INTERACTIVE, "catalogue:17")
    second = create_preview(rows, known, ImportStrategy.INTERACTIVE, "catalogue:17")

    assert first == second
    assert first.checksum == second.checksum
    assert first.lines[0].decision is PreviewDecision.CONFLICT
    assert first.lines[1].decision is PreviewDecision.CREATE
    assert rows[0].semantic_key == "fruit.peach"


def test_fail_on_conflict_rejects_the_whole_preview() -> None:
    with pytest.raises(DomainError) as caught:
        create_preview(
            (candidate(),),
            (existing(),),
            ImportStrategy.FAIL_ON_CONFLICT,
            "catalogue:17",
        )

    assert caught.value.code is ErrorCode.UNRESOLVED_CONFLICT


def test_reuse_exact_never_reuses_an_ambiguous_homonym() -> None:
    preview = create_preview(
        (candidate(semantic_key="sport.fishing"),),
        (existing(),),
        ImportStrategy.REUSE_EXACT,
        "catalogue:17",
    )

    assert preview.lines[0].decision is PreviewDecision.CONFLICT
    assert preview.lines[0].allowed_actions == ("create_distinct", "reject")

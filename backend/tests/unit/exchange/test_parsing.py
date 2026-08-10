from __future__ import annotations

import json
from uuid import UUID

import pytest

from polyglot.modules.lexicon.exchange.parsing import ParseLimits, parse_import
from polyglot.platform.errors import DomainError, ErrorCode

VARIETY = "019bfcc0-7cf1-7000-8000-000000000001"


def test_lexicon_json_parses_to_versioned_intermediate_rows() -> None:
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "andare-via",
                    "variety_id": VARIETY,
                    "unit_type": "multiword_expression",
                    "form": "Andare via",
                    "semantic_key": "motion.leave",
                    "visibility": "private",
                }
            ],
        }
    ).encode()

    parsed = parse_import(payload, "polyglot.lexicon.bundle/v1", "utf-8", ParseLimits())

    assert parsed.schema_version == 1
    assert parsed.rows[0].normalized_form == "andare via"
    assert parsed.rows[0].variety_id == UUID(VARIETY)


def test_generic_qa_csv_requires_declared_columns_and_is_deterministic() -> None:
    payload = (
        f"question,answer,variety_id\n"
        f"Dov'è la stazione?,Où est la gare ? ,{VARIETY}\n"
    ).encode()

    first = parse_import(payload, "polyglot.generic.qa/v1", "utf-8", ParseLimits())
    second = parse_import(payload, "polyglot.generic.qa/v1", "utf-8", ParseLimits())

    assert first == second
    assert first.rows[0].prompt_key is not None


@pytest.mark.parametrize(
    ("payload", "format_id", "code"),
    (
        (b"{}", "unknown/v1", ErrorCode.UNSUPPORTED_IMPORT_FORMAT),
        (b"\xff", "polyglot.lexicon.bundle/v1", ErrorCode.VALIDATION_FAILED),
        (
            json.dumps({"format": "polyglot.lexicon.bundle/v1", "entries": []}).encode(),
            "polyglot.lexicon.bundle/v1",
            ErrorCode.VALIDATION_FAILED,
        ),
    ),
)
def test_parser_rejects_unsupported_or_malformed_input(
    payload: bytes,
    format_id: str,
    code: ErrorCode,
) -> None:
    with pytest.raises(DomainError) as caught:
        parse_import(payload, format_id, "utf-8", ParseLimits())
    assert caught.value.code is code


def test_parser_enforces_row_and_depth_limits_before_preview() -> None:
    too_many = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [{"x": index} for index in range(3)],
        }
    ).encode()
    nested: object = "end"
    for _ in range(8):
        nested = {"nested": nested}

    with pytest.raises(DomainError) as rows_error:
        parse_import(
            too_many,
            "polyglot.lexicon.bundle/v1",
            "utf-8",
            ParseLimits(max_rows=2),
        )
    with pytest.raises(DomainError) as depth_error:
        parse_import(
            json.dumps(
                {
                    "format": "polyglot.lexicon.bundle/v1",
                    "schema_version": 1,
                    "entries": [nested],
                }
            ).encode(),
            "polyglot.lexicon.bundle/v1",
            "utf-8",
            ParseLimits(max_depth=5),
        )

    assert rows_error.value.code is ErrorCode.SIZE_LIMIT_EXCEEDED
    assert depth_error.value.code is ErrorCode.SIZE_LIMIT_EXCEEDED

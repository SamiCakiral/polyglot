from __future__ import annotations

import csv
import hashlib
import io
import json
import unicodedata
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from polyglot.modules.lexicon.exchange.domain import ImportCandidate
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue

SUPPORTED_FORMATS = frozenset(
    {
        "polyglot.lexicon.bundle/v1",
        "polyglot.memory.prompts/v1",
        "polyglot.generic.qa/v1",
        "polyglot.authoring.bundle/v1",
        "polyglot.user.export/v1",
    }
)


@dataclass(frozen=True, slots=True)
class ParseLimits:
    max_bytes: int = 20 * 1024 * 1024
    max_rows: int = 100_000
    max_depth: int = 32
    max_string_length: int = 32 * 1024


@dataclass(frozen=True, slots=True)
class ParsedImport:
    format_id: str
    schema_version: int
    rows: tuple[ImportCandidate, ...]
    source_checksum: str


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _validate_tree(value: JsonValue, limits: ParseLimits) -> None:
    stack: list[tuple[JsonValue, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > limits.max_depth:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        if isinstance(current, str) and len(current) > limits.max_string_length:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        if isinstance(current, dict):
            stack.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)


def _required_text(row: dict[str, Any], name: str) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            field_errors=[{"location": name, "code": "required"}],
        )
    return value.strip()


def _uuid(row: dict[str, Any], name: str) -> UUID:
    try:
        value = UUID(_required_text(row, name))
    except ValueError as error:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"invalid {name}") from error
    if value.version != 7:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"invalid {name}")
    return value


def _candidate(row: dict[str, Any], line_no: int) -> ImportCandidate:
    form = _required_text(row, "form")
    serializable = json.loads(json.dumps(row))
    return ImportCandidate(
        line_no=line_no,
        source_key=_required_text(row, "source_key"),
        variety_id=_uuid(row, "variety_id"),
        unit_type=str(row.get("unit_type", "word")),
        normalized_form=_normalize(form),
        semantic_key=(
            value.strip()
            if isinstance((value := row.get("semantic_key")), str) and value.strip()
            else None
        ),
        prompt_key=(
            value.strip()
            if isinstance((value := row.get("prompt_key")), str) and value.strip()
            else None
        ),
        external_identity=(
            value.strip()
            if isinstance((value := row.get("external_identity")), str) and value.strip()
            else None
        ),
        external_revision=(
            value.strip()
            if isinstance((value := row.get("external_revision")), str) and value.strip()
            else None
        ),
        visibility=str(row.get("visibility", "private")),
        payload_checksum=canonical_json_fingerprint(serializable),
    )


def _qa_candidate(row: dict[str, Any], line_no: int) -> ImportCandidate:
    question = _required_text(row, "question")
    answer = _required_text(row, "answer")
    variety_id = _uuid(row, "variety_id")
    identity: dict[str, JsonValue] = {
        "question": _normalize(question),
        "answer": _normalize(answer),
        "variety_id": str(variety_id),
    }
    checksum = canonical_json_fingerprint(identity)
    return ImportCandidate(
        line_no=line_no,
        source_key=str(row.get("source_key") or f"qa:{line_no}"),
        variety_id=variety_id,
        unit_type="lexicalized_construction",
        normalized_form=_normalize(question),
        semantic_key=None,
        prompt_key=f"qa:{checksum}",
        external_identity=None,
        external_revision=None,
        visibility="private",
        payload_checksum=checksum,
    )


def _json_rows(
    payload: bytes,
    format_id: str,
    limits: ParseLimits,
) -> tuple[int, list[dict[str, Any]]]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid JSON import") from error
    if not isinstance(document, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    _validate_tree(document, limits)
    if document.get("format") != format_id or document.get("schema_version") != 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    key = {
        "polyglot.lexicon.bundle/v1": "entries",
        "polyglot.memory.prompts/v1": "prompts",
        "polyglot.generic.qa/v1": "items",
        "polyglot.authoring.bundle/v1": "artifacts",
        "polyglot.user.export/v1": "entries",
    }[format_id]
    rows = document.get(key)
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    if len(rows) > limits.max_rows:
        raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
    return 1, rows


def _csv_rows(payload: bytes, limits: ParseLimits) -> list[dict[str, Any]]:
    try:
        source = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid CSV encoding") from error
    reader = csv.DictReader(io.StringIO(source), dialect="excel")
    required = {"question", "answer", "variety_id"}
    if reader.fieldnames is None or not required <= set(reader.fieldnames):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="missing CSV columns")
    rows: list[dict[str, Any]] = []
    for row in reader:
        if len(rows) >= limits.max_rows:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        rows.append(dict(row))
    if not rows:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    _validate_tree(cast(JsonValue, rows), limits)
    return rows


def parse_import(
    payload: bytes,
    format_id: str,
    encoding: str,
    limits: ParseLimits,
) -> ParsedImport:
    if format_id not in SUPPORTED_FORMATS:
        raise DomainError(ErrorCode.UNSUPPORTED_IMPORT_FORMAT)
    if encoding.lower().replace("_", "-") not in {"utf-8", "utf-8-sig"}:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unsupported encoding")
    if len(payload) > limits.max_bytes:
        raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
    is_csv = format_id == "polyglot.generic.qa/v1" and not payload.lstrip().startswith((b"{", b"["))
    if is_csv:
        rows = _csv_rows(payload, limits)
        candidates = tuple(_qa_candidate(row, index) for index, row in enumerate(rows, 1))
        schema_version = 1
    else:
        schema_version, rows = _json_rows(payload, format_id, limits)
        converter = _qa_candidate if format_id == "polyglot.generic.qa/v1" else _candidate
        candidates = tuple(converter(row, index) for index, row in enumerate(rows, 1))
    return ParsedImport(
        format_id=format_id,
        schema_version=schema_version,
        rows=candidates,
        source_checksum=canonical_json_fingerprint(
            {
                "format_id": format_id,
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
    )

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


class ImportStrategy(StrEnum):
    FAIL_ON_CONFLICT = "fail_on_conflict"
    REUSE_EXACT = "reuse_exact"
    CREATE_DISTINCT = "create_distinct"
    INTERACTIVE = "interactive"


class ConflictClass(StrEnum):
    EXACT_IDENTITY = "exact_identity"
    SAME_SENSE = "same_sense"
    SAME_FORM_OTHER_SENSE = "same_form_other_sense"
    SAME_PROMPT = "same_prompt"
    CONTENT_REVISION_CONFLICT = "content_revision_conflict"
    PRIVATE_PUBLIC_COLLISION = "private_public_collision"
    AMBIGUOUS = "ambiguous"


class PreviewDecision(StrEnum):
    CREATE = "create"
    REUSE = "reuse"
    CREATE_DISTINCT = "create_distinct"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    line_no: int
    source_key: str
    variety_id: UUID
    unit_type: str
    normalized_form: str
    semantic_key: str | None
    prompt_key: str | None
    external_identity: str | None
    external_revision: str | None
    visibility: str
    payload_checksum: str

    def __post_init__(self) -> None:
        if self.line_no < 1 or not self.source_key or not self.normalized_form:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if self.unit_type not in {
            "word",
            "multiword_expression",
            "proper_name",
            "lexicalized_construction",
        }:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if self.visibility not in {"private", "shared"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if len(self.payload_checksum) != 64:
            raise DomainError(ErrorCode.VALIDATION_FAILED)


@dataclass(frozen=True, slots=True)
class ExistingLexicalCandidate:
    entity_ref: str
    variety_id: UUID
    unit_type: str
    normalized_form: str
    semantic_key: str | None
    prompt_key: str | None
    external_identity: str | None
    external_revision: str | None
    visibility: str
    payload_checksum: str


@dataclass(frozen=True, slots=True)
class CandidateConflict:
    conflict_class: ConflictClass
    candidate_ref: str
    allowed_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreviewLine:
    line_no: int
    source_key: str
    decision: PreviewDecision
    conflict_class: ConflictClass | None
    candidate_ref: str | None
    allowed_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportPreview:
    strategy: ImportStrategy
    catalogue_version: str
    lines: tuple[PreviewLine, ...]
    checksum: str


_ACTIONS: dict[ConflictClass, tuple[str, ...]] = {
    ConflictClass.EXACT_IDENTITY: ("reuse_exact", "reject"),
    ConflictClass.SAME_SENSE: ("reuse_exact", "enrich", "create_distinct", "reject"),
    ConflictClass.SAME_FORM_OTHER_SENSE: ("create_distinct", "reject"),
    ConflictClass.SAME_PROMPT: ("merge_intent", "reject"),
    ConflictClass.CONTENT_REVISION_CONFLICT: ("create_revision", "reject"),
    ConflictClass.PRIVATE_PUBLIC_COLLISION: (
        "link_shared",
        "keep_private",
        "review",
        "reject",
    ),
    ConflictClass.AMBIGUOUS: ("review", "reject"),
}


def classify_candidate(
    incoming: ImportCandidate,
    known: ExistingLexicalCandidate,
) -> CandidateConflict | None:
    if incoming.variety_id != known.variety_id:
        return None
    if incoming.external_identity and incoming.external_identity == known.external_identity:
        conflict_class = (
            ConflictClass.EXACT_IDENTITY
            if incoming.external_revision == known.external_revision
            and incoming.payload_checksum == known.payload_checksum
            else ConflictClass.CONTENT_REVISION_CONFLICT
        )
    elif incoming.prompt_key and incoming.prompt_key == known.prompt_key:
        conflict_class = ConflictClass.SAME_PROMPT
    elif incoming.semantic_key and incoming.semantic_key == known.semantic_key:
        conflict_class = ConflictClass.SAME_SENSE
    elif (
        incoming.normalized_form == known.normalized_form
        and incoming.unit_type == known.unit_type
        and incoming.semantic_key
        and known.semantic_key
        and incoming.semantic_key != known.semantic_key
    ):
        conflict_class = ConflictClass.SAME_FORM_OTHER_SENSE
    elif incoming.normalized_form != known.normalized_form or incoming.unit_type != known.unit_type:
        return None
    elif incoming.visibility != known.visibility:
        conflict_class = ConflictClass.PRIVATE_PUBLIC_COLLISION
    else:
        conflict_class = ConflictClass.AMBIGUOUS
    return CandidateConflict(conflict_class, known.entity_ref, _ACTIONS[conflict_class])


def _decision(
    conflict: CandidateConflict | None,
    strategy: ImportStrategy,
) -> PreviewDecision:
    if conflict is None:
        return PreviewDecision.CREATE
    if strategy is ImportStrategy.REUSE_EXACT and conflict.conflict_class in {
        ConflictClass.EXACT_IDENTITY,
        ConflictClass.SAME_SENSE,
    }:
        return PreviewDecision.REUSE
    if (
        strategy is ImportStrategy.CREATE_DISTINCT
        and "create_distinct" in conflict.allowed_actions
    ):
        return PreviewDecision.CREATE_DISTINCT
    return PreviewDecision.CONFLICT


def create_preview(
    rows: tuple[ImportCandidate, ...],
    known_candidates: tuple[ExistingLexicalCandidate, ...],
    strategy: ImportStrategy,
    catalogue_version: str,
) -> ImportPreview:
    if not catalogue_version or len({row.line_no for row in rows}) != len(rows):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    lines: list[PreviewLine] = []
    for row in sorted(rows, key=lambda item: item.line_no):
        conflicts = tuple(
            conflict
            for known in known_candidates
            if (conflict := classify_candidate(row, known)) is not None
        )
        conflict = conflicts[0] if len(conflicts) == 1 else None
        if len(conflicts) > 1:
            conflict = CandidateConflict(
                ConflictClass.AMBIGUOUS,
                "multiple",
                _ACTIONS[ConflictClass.AMBIGUOUS],
            )
        decision = _decision(conflict, strategy)
        lines.append(
            PreviewLine(
                line_no=row.line_no,
                source_key=row.source_key,
                decision=decision,
                conflict_class=None if conflict is None else conflict.conflict_class,
                candidate_ref=None if conflict is None else conflict.candidate_ref,
                allowed_actions=() if conflict is None else conflict.allowed_actions,
            )
        )
    if strategy is ImportStrategy.FAIL_ON_CONFLICT and any(
        line.conflict_class is not None for line in lines
    ):
        raise DomainError(ErrorCode.UNRESOLVED_CONFLICT)
    fingerprint_rows: list[JsonValue] = [
        {
            "line_no": line.line_no,
            "source_key": line.source_key,
            "decision": line.decision.value,
            "conflict_class": (
                None if line.conflict_class is None else line.conflict_class.value
            ),
            "candidate_ref": line.candidate_ref,
            "allowed_actions": list(line.allowed_actions),
        }
        for line in lines
    ]
    checksum = canonical_json_fingerprint(
        {
            "strategy": strategy.value,
            "catalogue_version": catalogue_version,
            "lines": fingerprint_rows,
        }
    )
    return ImportPreview(strategy, catalogue_version, tuple(lines), checksum)


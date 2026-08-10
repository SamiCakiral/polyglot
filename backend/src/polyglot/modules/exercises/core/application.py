from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.exercises.core.domain import AnswerKind, CorrectionResult, HintLevel
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class ExerciseInstanceView:
    instance_id: UUID
    definition_revision_id: UUID
    language_pack_revision_id: UUID
    primitive_id: str
    response_kinds: tuple[AnswerKind, ...]
    stimulus_revision_ids: tuple[UUID, ...]
    target_bindings: tuple[JsonValue, ...]
    lexical_bindings: tuple[JsonValue, ...]
    grammar_bindings: tuple[JsonValue, ...]
    seed: int


@dataclass(frozen=True, slots=True)
class AttemptView:
    attempt_id: UUID
    profile_id: UUID
    instance_id: UUID
    attempt_no: int
    status: str
    terminal_reason: str
    answer_kind: AnswerKind | None
    raw_answer: JsonValue
    input_method: str | None
    input_locale: str | None
    submitted_at: datetime | None
    active_duration_ms: int
    correction_reviewed_at: datetime | None
    version: int
    started_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectionView:
    correction_id: UUID
    attempt_id: UUID
    revision_no: int
    verdict: str
    confidence: float
    target_coverage: float
    strategy: str
    proposed_answer: JsonValue
    alternatives: tuple[str, ...]
    explanation: str
    error_codes: tuple[str, ...]
    criterion_scores: dict[str, float]
    requires_review: bool
    supersedes_correction_id: UUID | None
    is_current: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectionCaseView:
    case_id: UUID
    attempt_id: UUID
    status: str
    reason_code: str
    user_comment: str | None
    resolution_correction_id: UUID | None
    version: int
    opened_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class OpenAttempt:
    attempt_id: UUID
    profile_id: UUID
    attempt_no: int
    started_at: datetime


@dataclass(frozen=True, slots=True)
class SaveDraft:
    draft_payload: dict[str, JsonValue]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UseHint:
    hint_use_id: UUID
    hint_definition_revision_id: UUID
    level: HintLevel
    reason: str
    answer_state_checksum: str
    effect_policy_revision_id: UUID
    shown_at: datetime


@dataclass(frozen=True, slots=True)
class SubmitAttempt:
    kind: AnswerKind
    raw_value: JsonValue
    input_method: str
    input_locale: str
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class ContestCorrection:
    case_id: UUID
    reason_code: str
    user_comment: str | None
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class MarkCorrectionRead:
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class ResolveCorrectionCase:
    case_review_id: UUID
    correction_id: UUID
    decision: str
    rationale: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectAttempt:
    correction_id: UUID
    result: CorrectionResult
    provenance_id: UUID
    rubric_revision_id: UUID | None
    proposed_answer: JsonValue
    requires_review: bool
    created_at: datetime


class ExerciseApplicationService(Protocol):
    async def get_instance(self, actor_id: UUID, instance_id: UUID) -> ExerciseInstanceView: ...

    async def get_attempt(self, actor_id: UUID, attempt_id: UUID) -> AttemptView: ...

    async def get_correction(self, actor_id: UUID, correction_id: UUID) -> CorrectionView: ...

    async def get_correction_case(
        self, actor_id: UUID, case_id: UUID
    ) -> CorrectionCaseView: ...

    async def open_attempt(
        self,
        actor_id: UUID,
        instance_id: UUID,
        command: OpenAttempt,
        *,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def save_draft(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: SaveDraft,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def use_hint(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: UseHint,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def submit_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: SubmitAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def correct_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: CorrectAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def contest_correction(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: ContestCorrection,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> CorrectionCaseView: ...

    async def mark_correction_read(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: MarkCorrectionRead,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView: ...

    async def resolve_correction_case(
        self,
        actor_id: UUID,
        case_id: UUID,
        command: ResolveCorrectionCase,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> CorrectionCaseView: ...


__all__ = [
    "AttemptView",
    "ContestCorrection",
    "CorrectAttempt",
    "CorrectionCaseView",
    "CorrectionView",
    "ExerciseApplicationService",
    "ExerciseInstanceView",
    "MarkCorrectionRead",
    "OpenAttempt",
    "ResolveCorrectionCase",
    "SaveDraft",
    "SubmitAttempt",
    "UseHint",
]

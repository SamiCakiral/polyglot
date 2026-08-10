from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.assessments.domain import AssessmentModality
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class AssessmentItemView:
    item_id: UUID
    section_id: UUID
    ordinal: int
    item_kind: str
    answer_kind: str
    weight: float
    coverage_targets: tuple[str, ...]
    prompt: dict[str, JsonValue]
    media_ref: str | None
    max_plays: int | None
    answer: dict[str, JsonValue] | None
    response_version: int
    saved_at: datetime | None


@dataclass(frozen=True, slots=True)
class AssessmentSectionView:
    section_id: UUID
    ordinal: int
    section_type: str
    title: str
    instructions: str
    weight: float
    status: str
    items: tuple[AssessmentItemView, ...]


@dataclass(frozen=True, slots=True)
class AssessmentResultView:
    result_id: UUID
    modality: str
    status: str
    score: float | None
    band: str | None
    confidence: float
    coverage: float
    integrity_factor: float
    limiting_criteria: tuple[str, ...]
    policy_revision: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AssessmentRunView:
    run_id: UUID
    profile_id: UUID
    modality: str
    status: str
    protocol_code: str
    form_code: str
    time_limit_ms: int
    pause_allowed: bool
    prepared_at: datetime
    started_at: datetime | None
    deadline_at: datetime | None
    paused_at: datetime | None
    remaining_time_ms: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    server_now: datetime
    sections: tuple[AssessmentSectionView, ...]
    result: AssessmentResultView | None
    version: int


@dataclass(frozen=True, slots=True)
class PrepareAssessment:
    run_id: UUID
    modality: AssessmentModality
    seed: str
    target_snapshot: dict[str, JsonValue]
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SaveAssessmentResponse:
    answer: dict[str, JsonValue]
    expected_response_version: int


@dataclass(frozen=True, slots=True)
class ResolveAssessmentReview:
    rubric_revision: str
    criterion_scores: dict[str, JsonValue]
    annotations: tuple[dict[str, JsonValue], ...] = ()


class AssessmentApplicationService(Protocol):
    async def prepare(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: PrepareAssessment,
        *,
        idempotency_key: str,
    ) -> AssessmentRunView: ...

    async def get_run(self, actor_id: UUID, run_id: UUID) -> AssessmentRunView: ...

    async def start(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView: ...

    async def save_response(
        self,
        actor_id: UUID,
        run_id: UUID,
        item_id: UUID,
        command: SaveAssessmentResponse,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AssessmentRunView: ...

    async def pause(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView: ...

    async def resume(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView: ...

    async def submit(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView: ...

    async def resolve_review(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: ResolveAssessmentReview,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AssessmentRunView: ...

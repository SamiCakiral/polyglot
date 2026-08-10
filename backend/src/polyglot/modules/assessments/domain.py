from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from polyglot.platform.json_types import JsonValue


class AssessmentDomainError(ValueError):
    pass


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise AssessmentDomainError(f"{field}_must_be_uuid7")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AssessmentDomainError(f"{field}_must_be_timezone_aware")


class AssessmentModality(StrEnum):
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class AssessmentRunStatus(StrEnum):
    PREPARED = "prepared"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    SCORING = "scoring"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssessmentResultStatus(StrEnum):
    VALID = "valid"
    INDICATIVE = "indicative"
    NOT_EVALUABLE = "not_evaluable"


class AssessmentBand(StrEnum):
    ASSESS_B0 = "assess_b0"
    ASSESS_B1 = "assess_b1"
    ASSESS_B2 = "assess_b2"
    ASSESS_B3 = "assess_b3"
    ASSESS_B4 = "assess_b4"


@dataclass(frozen=True, slots=True)
class AssessmentResponse:
    item_id: UUID
    answer: Mapping[str, JsonValue]
    version: int
    saved_at: datetime

    def __post_init__(self) -> None:
        _require_uuid7(self.item_id, "item_id")
        _require_aware(self.saved_at, "saved_at")
        if self.version < 1 or not self.answer:
            raise AssessmentDomainError("answer_shape_invalid")
        object.__setattr__(self, "answer", MappingProxyType(dict(self.answer)))


@dataclass(frozen=True, slots=True)
class AssessmentRun:
    run_id: UUID
    profile_id: UUID
    assessment_revision_id: UUID
    form_id: UUID
    modality: AssessmentModality
    item_ids: tuple[UUID, ...]
    time_limit_ms: int
    pause_allowed: bool
    resume_window_ms: int
    status: AssessmentRunStatus
    prepared_at: datetime
    started_at: datetime | None = None
    deadline_at: datetime | None = None
    paused_at: datetime | None = None
    remaining_time_ms: int | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    responses: tuple[AssessmentResponse, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        for field in ("run_id", "profile_id", "assessment_revision_id", "form_id"):
            _require_uuid7(getattr(self, field), field)
        for item_id in self.item_ids:
            _require_uuid7(item_id, "item_id")
        _require_aware(self.prepared_at, "prepared_at")
        for field in ("started_at", "deadline_at", "paused_at", "submitted_at", "completed_at"):
            value = getattr(self, field)
            if value is not None:
                _require_aware(value, field)
        if not self.item_ids or len(set(self.item_ids)) != len(self.item_ids):
            raise AssessmentDomainError("invalid_assessment_items")
        if self.time_limit_ms < 60_000 or self.resume_window_ms < 0 or self.version < 1:
            raise AssessmentDomainError("invalid_assessment_policy")
        if len({response.item_id for response in self.responses}) != len(self.responses):
            raise AssessmentDomainError("duplicate_assessment_response")

    @classmethod
    def prepare(
        cls,
        *,
        run_id: UUID,
        profile_id: UUID,
        assessment_revision_id: UUID,
        form_id: UUID,
        modality: AssessmentModality,
        item_ids: tuple[UUID, ...],
        time_limit_ms: int,
        pause_allowed: bool,
        resume_window_ms: int,
        prepared_at: datetime,
    ) -> AssessmentRun:
        return cls(
            run_id=run_id,
            profile_id=profile_id,
            assessment_revision_id=assessment_revision_id,
            form_id=form_id,
            modality=modality,
            item_ids=item_ids,
            time_limit_ms=time_limit_ms,
            pause_allowed=pause_allowed,
            resume_window_ms=resume_window_ms,
            status=AssessmentRunStatus.PREPARED,
            prepared_at=prepared_at,
        )

    def start(self, now: datetime) -> AssessmentRun:
        _require_aware(now, "now")
        if self.status is not AssessmentRunStatus.PREPARED:
            raise AssessmentDomainError("invalid_transition")
        return replace(
            self,
            status=AssessmentRunStatus.IN_PROGRESS,
            started_at=now,
            deadline_at=now + timedelta(milliseconds=self.time_limit_ms),
            remaining_time_ms=self.time_limit_ms,
            version=self.version + 1,
        )

    def pause(self, now: datetime) -> AssessmentRun:
        _require_aware(now, "now")
        current = self.expire_if_due(now)
        if current.status is AssessmentRunStatus.EXPIRED:
            raise AssessmentDomainError("assessment_expired")
        if current.status is not AssessmentRunStatus.IN_PROGRESS:
            raise AssessmentDomainError("invalid_transition")
        if not current.pause_allowed:
            raise AssessmentDomainError("pause_not_allowed")
        assert current.deadline_at is not None
        remaining = max(int((current.deadline_at - now).total_seconds() * 1000), 0)
        return replace(
            current,
            status=AssessmentRunStatus.PAUSED,
            paused_at=now,
            remaining_time_ms=remaining,
            version=current.version + 1,
        )

    def resume(self, now: datetime) -> AssessmentRun:
        _require_aware(now, "now")
        if self.status is not AssessmentRunStatus.PAUSED:
            raise AssessmentDomainError("invalid_transition")
        assert self.paused_at is not None and self.remaining_time_ms is not None
        if now > self.paused_at + timedelta(milliseconds=self.resume_window_ms):
            raise AssessmentDomainError("assessment_expired")
        return replace(
            self,
            status=AssessmentRunStatus.IN_PROGRESS,
            deadline_at=now + timedelta(milliseconds=self.remaining_time_ms),
            paused_at=None,
            version=self.version + 1,
        )

    def save_response(
        self,
        item_id: UUID,
        answer: Mapping[str, JsonValue],
        expected_response_version: int,
        now: datetime,
    ) -> AssessmentRun:
        _require_aware(now, "now")
        current = self.expire_if_due(now)
        if current.status not in {AssessmentRunStatus.IN_PROGRESS, AssessmentRunStatus.PAUSED}:
            code = (
                "response_conflict"
                if current.status
                in {
                    AssessmentRunStatus.SUBMITTED,
                    AssessmentRunStatus.EXPIRED,
                    AssessmentRunStatus.SCORING,
                    AssessmentRunStatus.REVIEW_REQUIRED,
                    AssessmentRunStatus.COMPLETED,
                }
                else "invalid_transition"
            )
            raise AssessmentDomainError(code)
        if item_id not in current.item_ids:
            raise AssessmentDomainError("not_found")
        responses = {response.item_id: response for response in current.responses}
        existing = responses.get(item_id)
        actual_version = existing.version if existing is not None else 0
        if expected_response_version != actual_version:
            raise AssessmentDomainError("response_stale")
        responses[item_id] = AssessmentResponse(
            item_id=item_id,
            answer=answer,
            version=actual_version + 1,
            saved_at=now,
        )
        return replace(
            current,
            responses=tuple(responses[item] for item in current.item_ids if item in responses),
            version=current.version + 1,
        )

    def submit(self, now: datetime) -> AssessmentRun:
        _require_aware(now, "now")
        if self.status in {
            AssessmentRunStatus.SUBMITTED,
            AssessmentRunStatus.SCORING,
            AssessmentRunStatus.REVIEW_REQUIRED,
            AssessmentRunStatus.COMPLETED,
        }:
            return self
        current = self.expire_if_due(now)
        if current.status is AssessmentRunStatus.EXPIRED:
            return current
        if current.status not in {AssessmentRunStatus.IN_PROGRESS, AssessmentRunStatus.PAUSED}:
            raise AssessmentDomainError("invalid_transition")
        return replace(
            current,
            status=AssessmentRunStatus.SUBMITTED,
            submitted_at=now,
            version=current.version + 1,
        )

    def expire_if_due(self, now: datetime) -> AssessmentRun:
        _require_aware(now, "now")
        if self.status is AssessmentRunStatus.IN_PROGRESS:
            assert self.deadline_at is not None
            if now >= self.deadline_at:
                return replace(
                    self,
                    status=AssessmentRunStatus.EXPIRED,
                    submitted_at=self.deadline_at,
                    remaining_time_ms=0,
                    version=self.version + 1,
                )
        if self.status is AssessmentRunStatus.PAUSED:
            assert self.paused_at is not None
            if now > self.paused_at + timedelta(milliseconds=self.resume_window_ms):
                return replace(
                    self,
                    status=AssessmentRunStatus.EXPIRED,
                    submitted_at=self.paused_at
                    + timedelta(milliseconds=self.resume_window_ms),
                    version=self.version + 1,
                )
        return self

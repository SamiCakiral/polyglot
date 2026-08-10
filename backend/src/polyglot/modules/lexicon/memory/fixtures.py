from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from polyglot.modules.lexicon.memory.application import (
    CreateMemoryPrompt,
    MemoryLifecycle,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.policy import (
    HintLevel,
    ReviewVerdict,
    SchedulerPolicy,
)
from polyglot.modules.lexicon.memory.ports import MemoryRating
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import (
    MemoryReplayBinding,
    StaticMemoryReplayResolver,
    rebuild_schedule,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class MemoryFixtureReport:
    history_count: int
    replay_count: int
    final_due_at: datetime
    directions_independent: bool
    non_evaluable_suppressed: bool


def _uuid(index: int) -> UUID:
    return UUID(f"018f0000-0000-7000-8000-{index:012x}")


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    return value


def load_and_run_memory_fixture(root: Path) -> MemoryFixtureReport:
    payload = cast(JsonValue, json.loads((root / "memory.json").read_text()))
    document = _object(payload)
    scheduler_data = _object(document["scheduler"])
    directions = document["directions"]
    history = document["history"]
    expected = _object(document["expected_projection"])
    if not isinstance(directions, list) or len(directions) != 2:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    if not isinstance(history, list) or not history:
        raise DomainError(ErrorCode.VALIDATION_FAILED)

    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    if (
        scheduler.identity.kind != scheduler_data["kind"]
        or scheduler.identity.version != scheduler_data["version"]
        or scheduler.identity.parameter_set_id != scheduler_data["parameter_set_id"]
        or policy.revision != scheduler_data["policy_revision"]
        or str(policy.desired_retention) != scheduler_data["desired_retention"]
    ):
        raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)

    lifecycle = MemoryLifecycle(scheduler)
    prompts = []
    for raw_direction in directions:
        direction = _object(raw_direction)
        prompts.append(
            lifecycle.create(
                CreateMemoryPrompt(
                    prompt_id=UUID(str(direction["prompt_id"])),
                    profile_id=UUID(str(document["profile_id"])),
                    target_ref=UUID(str(document["target_ref"])),
                    target_revision_id=UUID(str(document["target_revision_id"])),
                    direction=str(direction["direction"]),
                    modality="written",
                    operation="recall",
                    protocol_id="certified-recall-v1",
                    protocol_revision=1,
                    rating_semantics_id="polyglot-recall-v1",
                    scheduler_policy_id=_uuid(5),
                    created_at=datetime.fromisoformat(
                        str(_object(history[0])["reviewed_at"])
                    ),
                ),
                policy,
            )
        )

    forward = prompts[0]
    for index, raw_review in enumerate(history):
        review_data = _object(raw_review)
        rating = MemoryRating(str(review_data["rating"]))
        reviewed_at = datetime.fromisoformat(str(review_data["reviewed_at"]))
        decision = lifecycle.submit_review(
            forward,
            SubmitMemoryReview(
                review_id=_uuid(1000 + index),
                opportunity_id=_uuid(2000 + index),
                attempt_id=None,
                response_ref=None,
                correction_ref=None,
                verdict=(
                    ReviewVerdict.INCORRECT
                    if rating is MemoryRating.AGAIN
                    else ReviewVerdict.CORRECT
                ),
                highest_hint=HintLevel.H0,
                rating=rating,
                certified_recall=True,
                answer_revealed=False,
                exposure_only=False,
                incidental_production=False,
                self_reported=False,
                active_duration_ms=1_000,
                scheduled_at=reviewed_at,
                reviewed_at=reviewed_at,
                idempotency_key=f"fixture-review-{index}",
                certification_ref="fixture:certified-recall-v1",
                certified_operation="recall",
                certified_protocol_id="certified-recall-v1",
                certified_protocol_revision=1,
                certified_target_revision_id=forward.prompt.target_revision_id,
            ),
            policy,
        )
        if not decision.review_created:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        forward = decision.aggregate

    schedule = forward.schedule
    actual = {
        "state": schedule.state.value,
        "difficulty": str(schedule.difficulty),
        "stability": str(schedule.stability),
        "due_at": schedule.due_at.isoformat(),
        "reps": schedule.reps,
        "lapses": schedule.lapses,
        "last_rating": None if schedule.last_rating is None else schedule.last_rating.value,
        "projection_version": schedule.projection_version,
    }
    if actual != expected:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture projection drift")

    resolver = StaticMemoryReplayResolver((MemoryReplayBinding(scheduler, policy),))
    replays = tuple(rebuild_schedule(forward, resolver) for _ in range(100))
    if any(replay != schedule for replay in replays):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture replay drift")

    reverse = prompts[1]
    revealed = lifecycle.submit_review(
        reverse,
        SubmitMemoryReview(
            review_id=_uuid(3000),
            opportunity_id=_uuid(3001),
            attempt_id=None,
            response_ref=None,
            correction_ref=None,
            verdict=ReviewVerdict.CORRECT,
            highest_hint=HintLevel.H4,
            rating=MemoryRating.AGAIN,
            certified_recall=True,
            answer_revealed=True,
            exposure_only=False,
            incidental_production=False,
            self_reported=False,
            active_duration_ms=1_000,
            scheduled_at=schedule.computed_at,
            reviewed_at=schedule.computed_at,
            idempotency_key="fixture-revealed",
            certification_ref="fixture:revealed",
            certified_operation="recall",
            certified_protocol_id="certified-recall-v1",
            certified_protocol_revision=1,
            certified_target_revision_id=reverse.prompt.target_revision_id,
        ),
        policy,
    )
    return MemoryFixtureReport(
        history_count=len(forward.reviews),
        replay_count=len(replays),
        final_due_at=schedule.due_at,
        directions_independent=reverse.schedule == prompts[1].schedule,
        non_evaluable_suppressed=not revealed.review_created and revealed.aggregate == reverse,
    )

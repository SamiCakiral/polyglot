from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from polyglot.modules.exercises.core.domain import (
    CORE_PRIMITIVE_IDS,
    Answer,
    AnswerKind,
    Attempt,
    CorrectionResult,
    CorrectionStrategy,
    CorrectionVerdict,
    ExerciseBlockRun,
    ExerciseDefinition,
    ExerciseInstance,
    HintLevel,
    TerminalReason,
    primitive_spec,
)
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

_REQUIRED_CASES = frozenset(
    {
        "positive",
        "negative",
        "ambiguous",
        "not_evaluable",
        "unavailable",
        "h0",
        "h1",
        "h2",
        "h3",
        "h4",
        "replay",
        "skip",
        "abandon",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Manifest(_StrictModel):
    id: Literal["FX-PRIMITIVES"]
    kind: Literal["positive"]
    expected_status: Literal["accepted"]


class _Metadata(_StrictModel):
    schema_version: Literal[1]
    synthetic: Literal[True]
    seed: int
    clock: datetime
    payloads: dict[str, str]
    oracles: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: Literal["pending_human"]


class _CorrectionOracle(_StrictModel):
    verdict: CorrectionVerdict
    answer: str | None = None
    expected: str | None = None
    credit: float | None = None


class _A11yOracle(_StrictModel):
    keyboard: Literal[True]
    screen_reader: Literal[True]
    untimed: Literal[True]


class _AnswerSample(_StrictModel):
    kind: AnswerKind
    raw_value: JsonValue


class _PrimitiveFixture(_StrictModel):
    primitive_id: str
    answer_kinds: tuple[AnswerKind, ...]
    sample: _AnswerSample
    case_ids: tuple[str, ...]
    a11y: _A11yOracle


class _PrimitivePayload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: Literal["FX-PRIMITIVES"]
    seed: int
    clock: datetime
    correction_oracles: dict[str, _CorrectionOracle]
    hint_oracles: dict[str, float]
    expected_replay_order: tuple[str, ...]
    primitives: tuple[_PrimitiveFixture, ...]


@dataclass(frozen=True, slots=True)
class PrimitiveFixtureReport:
    primitive_ids: tuple[str, ...]
    case_counts: tuple[tuple[str, int], ...]
    a11y_certified: tuple[str, ...]
    replay_without_duplicates: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    replay_order: tuple[str, ...]
    expected_replay_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FixedIds:
    value: UUID

    def new(self) -> UUID:
        return self.value


def _validation_failed(detail: str = "FX-PRIMITIVES is invalid") -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _fixture_uuid(index: int, suffix: int) -> UUID:
    return UUID(f"019fe009-{index:04x}-7000-8000-{suffix:012x}")


def _load(root: Path) -> tuple[_Metadata, _PrimitivePayload]:
    try:
        manifest = _Manifest.model_validate_json((root / "manifest.json").read_text())
        metadata = _Metadata.model_validate_json((root / "fixture-metadata.json").read_text())
        payload_bytes = (root / "primitives.json").read_bytes()
        payload = _PrimitivePayload.model_validate_json(payload_bytes)
    except (OSError, ValidationError, ValueError) as error:
        raise _validation_failed() from error
    if manifest.id != payload.fixture_id or metadata.seed != payload.seed:
        raise _validation_failed("fixture identity, seed, and metadata must agree")
    if metadata.clock != payload.clock or metadata.network_dependencies:
        raise _validation_failed("fixture clock must be frozen and network dependencies empty")
    if set(metadata.payloads) != {"primitives.json"}:
        raise _validation_failed("fixture payload manifest is not closed")
    checksum = f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}"
    if metadata.payloads["primitives.json"] != checksum:
        raise _validation_failed("fixture payload checksum does not match")
    return metadata, payload


def _validate_closed_contract(payload: _PrimitivePayload) -> None:
    primitive_ids = tuple(item.primitive_id for item in payload.primitives)
    if primitive_ids != CORE_PRIMITIVE_IDS or len(set(primitive_ids)) != len(primitive_ids):
        raise _validation_failed("fixture must cover every core primitive exactly once")
    if payload.expected_replay_order != CORE_PRIMITIVE_IDS:
        raise _validation_failed("fixture replay order must be explicit and canonical")
    if set(payload.correction_oracles) != {
        "positive",
        "negative",
        "ambiguous",
        "not_evaluable",
    }:
        raise _validation_failed("correction oracles are incomplete")
    if payload.hint_oracles != {
        "h0": 1.0,
        "h1": 0.85,
        "h2": 0.6,
        "h3": 0.25,
        "h4": 0.0,
    }:
        raise _validation_failed("hint oracles must declare H0 through H4")
    for item in payload.primitives:
        spec = primitive_spec(item.primitive_id)
        if item.answer_kinds != spec.answer_kinds or item.sample.kind not in item.answer_kinds:
            raise _validation_failed(f"{item.primitive_id} answer contract does not match")
        if set(item.case_ids) != _REQUIRED_CASES or len(item.case_ids) != len(_REQUIRED_CASES):
            raise _validation_failed(f"{item.primitive_id} executable cases are incomplete")


def _definition(item: _PrimitiveFixture, index: int) -> ExerciseDefinition:
    return ExerciseDefinition.published(
        definition_id=_fixture_uuid(index, 1),
        revision_id=_fixture_uuid(index, 2),
        revision_no=1,
        primitive_id=item.primitive_id,
        response_kinds=item.answer_kinds,
        language_certification_ids=(_fixture_uuid(index, 3),),
        modes=("fixture",),
        target_weights=(("fixture:target", 1.0),),
        correction_policy_id="fixture:correction:v1",
        hint_policy_id="fixture:hints:v1",
        observation_policy_id="fixture:observation:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )


def _attempt(item: _PrimitiveFixture, index: int, clock: FrozenClock) -> tuple[Attempt, Answer]:
    definition = _definition(item, index)
    instance = ExerciseInstance.create(
        instance_id=_fixture_uuid(index, 4),
        definition=definition,
        language_pack_revision_id=_fixture_uuid(index, 5),
        seed=9009,
        stimulus_revision_ids=(_fixture_uuid(index, 6),),
    )
    answer = Answer.create(
        kind=item.sample.kind,
        raw_value=item.sample.raw_value,
        input_method="fixture",
        submitted_at=clock.now(),
    )
    attempt = Attempt.start(
        instance=instance,
        profile_id=_fixture_uuid(index, 7),
        attempt_no=1,
        clock=clock,
        ids=_FixedIds(_fixture_uuid(index, 8)),
    )
    return attempt, answer


def _run_correction_oracles(payload: _PrimitivePayload, operation_cap: float) -> None:
    positive = payload.correction_oracles["positive"]
    negative = payload.correction_oracles["negative"]
    if not positive.expected or positive.answer is None:
        raise _validation_failed("positive oracle is not executable")
    if not negative.expected or negative.answer is None:
        raise _validation_failed("negative oracle is not executable")
    positive_result = CorrectionStrategy.exact_normalized(positive.expected).correct(
        positive.answer
    )
    negative_result = CorrectionStrategy.exact_normalized(negative.expected).correct(
        negative.answer
    )
    ambiguous = CorrectionResult.ambiguous("fixture ambiguity")
    not_evaluable = CorrectionResult.not_evaluable("fixture unavailable")
    actual = {
        "positive": positive_result.verdict,
        "negative": negative_result.verdict,
        "ambiguous": ambiguous.verdict,
        "not_evaluable": not_evaluable.verdict,
    }
    if any(
        actual[name] is not oracle.verdict for name, oracle in payload.correction_oracles.items()
    ):
        raise _validation_failed("a correction oracle did not produce its literal verdict")
    if (
        ambiguous.credit_value(operation_cap=operation_cap, target_weight=1.0, hint_level="h0")
        is not None
        or not_evaluable.credit_value(
            operation_cap=operation_cap, target_weight=1.0, hint_level="h0"
        )
        is not None
    ):
        raise _validation_failed("ambiguous and unavailable corrections must not produce credit")
    for level, multiplier in payload.hint_oracles.items():
        credit = positive_result.credit_value(
            operation_cap=operation_cap,
            target_weight=1.0,
            hint_level=level,
        )
        if credit is None or abs(credit - operation_cap * multiplier) > 1e-12:
            raise _validation_failed(f"{level} credit oracle failed")


def _run_replay_oracles(item: _PrimitiveFixture, index: int, clock: FrozenClock) -> None:
    attempt, answer = _attempt(item, index, clock)
    hinted = attempt.use_hint(
        HintLevel.H2,
        reason="fixture hint",
        clock=clock,
        idempotency_key=f"hint-{index}",
    )
    if (
        hinted.use_hint(
            HintLevel.H2,
            reason="fixture hint",
            clock=clock,
            idempotency_key=f"hint-{index}",
        )
        != hinted
    ):
        raise _validation_failed("hint replay changed the aggregate")
    submitted = hinted.submit(answer=answer, idempotency_key=f"submit-{index}")
    corrected = submitted.start_correction().complete_correction(
        correction_id=_fixture_uuid(index, 9),
        result=CorrectionResult.correct(confidence=1.0),
        clock=clock,
        idempotency_key=f"correct-{index}",
    )
    if corrected.submit(answer=answer, idempotency_key=f"submit-{index}") != corrected:
        raise _validation_failed("submission replay changed the terminal aggregate")
    if (
        corrected.complete_correction(
            correction_id=_fixture_uuid(index, 9),
            result=CorrectionResult.correct(confidence=1.0),
            clock=clock,
            idempotency_key=f"correct-{index}",
        )
        != corrected
        or len(corrected.corrections) != 1
    ):
        raise _validation_failed("correction replay duplicated an effect")
    forced = attempt.force_submit(
        reason=TerminalReason.ANSWER_INVALID,
        idempotency_key=f"force-{index}",
    )
    if (
        forced.force_submit(
            reason=TerminalReason.ANSWER_INVALID,
            idempotency_key=f"force-{index}",
        )
        != forced
    ):
        raise _validation_failed("forced submission replay changed the aggregate")
    available = ExerciseBlockRun.create(block_id=_fixture_uuid(index, 10)).make_available()
    skipped = available.skip(reason="fixture skip", idempotency_key=f"skip-{index}")
    if skipped.skip(reason="fixture skip", idempotency_key=f"skip-{index}") != skipped:
        raise _validation_failed("skip replay changed the aggregate")
    abandoned = available.start().abandon(idempotency_key=f"abandon-{index}")
    if abandoned.abandon(idempotency_key=f"abandon-{index}") != abandoned:
        raise _validation_failed("abandon replay changed the aggregate")
    unavailable = available.mark_unavailable(
        reason="fixture unavailable",
        idempotency_key=f"unavailable-{index}",
    )
    if (
        unavailable.mark_unavailable(
            reason="fixture unavailable",
            idempotency_key=f"unavailable-{index}",
        )
        != unavailable
    ):
        raise _validation_failed("unavailable replay changed the aggregate")


def load_and_run_primitive_fixture(root: Path) -> PrimitiveFixtureReport:
    metadata, payload = _load(root)
    _validate_closed_contract(payload)
    counts = {case_id: 0 for case_id in _REQUIRED_CASES}
    certified: list[str] = []
    replayed: list[str] = []
    clock = FrozenClock(payload.clock)
    for index, item in enumerate(payload.primitives, start=1):
        _run_correction_oracles(payload, primitive_spec(item.primitive_id).operation_cap)
        _run_replay_oracles(item, index, clock)
        for case_id in item.case_ids:
            counts[case_id] += 1
        certified.append(item.primitive_id)
        replayed.append(item.primitive_id)
    replay_order = tuple(item.primitive_id for item in payload.primitives)
    return PrimitiveFixtureReport(
        primitive_ids=replay_order,
        case_counts=tuple(sorted(counts.items())),
        a11y_certified=tuple(certified),
        replay_without_duplicates=tuple(replayed),
        network_dependencies=metadata.network_dependencies,
        replay_order=replay_order,
        expected_replay_order=payload.expected_replay_order,
    )

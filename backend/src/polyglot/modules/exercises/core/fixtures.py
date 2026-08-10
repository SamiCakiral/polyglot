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
_HINT_ORACLES = {"h0": 1.0, "h1": 0.85, "h2": 0.6, "h3": 0.25, "h4": 0.0}


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
    oracle_id: str
    strategy: Literal[
        "exact_value",
        "accepted_set",
        "exact_normalized",
        "structural_constraints",
    ]
    negative_value: JsonValue
    positive_verdict: Literal[CorrectionVerdict.CORRECT]
    negative_verdict: Literal[CorrectionVerdict.INCORRECT]
    ambiguous_verdict: Literal[CorrectionVerdict.AMBIGUOUS]
    not_evaluable_verdict: Literal[CorrectionVerdict.NOT_EVALUABLE]


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
    correction_oracle: _CorrectionOracle
    case_ids: tuple[str, ...]
    a11y: _A11yOracle


class _PrimitivePayload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: Literal["FX-PRIMITIVES"]
    seed: int
    clock: datetime
    hint_oracles: dict[str, float]
    expected_replay_order: tuple[str, ...]
    primitives: tuple[_PrimitiveFixture, ...]


@dataclass(frozen=True, slots=True)
class PrimitiveOracleEvidence:
    oracle_id: str
    primitive_id: str
    sample_kind: str
    strategy: str
    sample_used: bool
    verdicts: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class PrimitiveFixtureReport:
    primitive_ids: tuple[str, ...]
    case_counts: tuple[tuple[str, int], ...]
    a11y_certified: tuple[str, ...]
    replay_without_duplicates: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    replay_order: tuple[str, ...]
    expected_replay_order: tuple[str, ...]
    instance_seeds: tuple[int, ...]
    primitive_oracles: tuple[PrimitiveOracleEvidence, ...]


@dataclass(frozen=True, slots=True)
class _FixedIds:
    value: UUID

    def new(self) -> UUID:
        return self.value


def _validation_failed(detail: str = "FX-PRIMITIVES is invalid") -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _fixture_uuid(index: int, suffix: int) -> UUID:
    return UUID(f"019fe009-{index:04x}-7000-8000-{suffix:012x}")


def _seeded_replay_order(primitive_ids: tuple[str, ...], seed: int) -> tuple[str, ...]:
    return tuple(
        sorted(
            primitive_ids,
            key=lambda primitive_id: hashlib.sha256(
                f"{seed}:{primitive_id}".encode()
            ).digest(),
        )
    )


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
    if payload.expected_replay_order != _seeded_replay_order(CORE_PRIMITIVE_IDS, payload.seed):
        raise _validation_failed("fixture replay order must match its declared seed")
    if payload.hint_oracles != _HINT_ORACLES:
        raise _validation_failed("hint oracles must declare H0 through H4")
    for item in payload.primitives:
        spec = primitive_spec(item.primitive_id)
        if item.answer_kinds != spec.answer_kinds or item.sample.kind not in item.answer_kinds:
            raise _validation_failed(f"{item.primitive_id} answer contract does not match")
        if item.correction_oracle.oracle_id != f"{item.primitive_id}:oracle":
            raise _validation_failed(f"{item.primitive_id} oracle identity is not unique")
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


def _attempt(
    item: _PrimitiveFixture, index: int, clock: FrozenClock, seed: int
) -> tuple[Attempt, Answer]:
    definition = _definition(item, index)
    instance = ExerciseInstance.create(
        instance_id=_fixture_uuid(index, 4),
        definition=definition,
        language_pack_revision_id=_fixture_uuid(index, 5),
        seed=seed,
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


def _exact_value_result(actual: JsonValue, expected: JsonValue) -> CorrectionResult:
    matched = actual == expected
    return CorrectionResult(
        CorrectionVerdict.CORRECT if matched else CorrectionVerdict.INCORRECT,
        1.0,
        float(matched),
        "exact fixture value",
        "exact_value",
    )


def _strategy_results(item: _PrimitiveFixture) -> tuple[CorrectionResult, CorrectionResult]:
    sample = item.sample.raw_value
    negative = item.correction_oracle.negative_value
    strategy = item.correction_oracle.strategy
    if strategy == "exact_value":
        return _exact_value_result(sample, sample), _exact_value_result(negative, sample)
    if not isinstance(sample, str) or not isinstance(negative, str):
        raise _validation_failed(f"{item.primitive_id} strategy requires text samples")
    if strategy == "accepted_set":
        correction = CorrectionStrategy.accepted_set((sample,))
    elif strategy == "exact_normalized":
        correction = CorrectionStrategy.exact_normalized(sample)
    elif strategy == "structural_constraints":
        correction = CorrectionStrategy.structural_constraints(
            required_tokens=tuple(sample.casefold().split()), ordered=True
        )
    else:
        raise _validation_failed(f"{item.primitive_id} strategy is not executable")
    return correction.correct(sample), correction.correct(negative)


def _run_correction_oracle(
    item: _PrimitiveFixture, operation_cap: float, clock: FrozenClock
) -> PrimitiveOracleEvidence:
    Answer.create(
        kind=item.sample.kind,
        raw_value=item.correction_oracle.negative_value,
        input_method="fixture-negative",
        submitted_at=clock.now(),
    )
    positive_result, negative_result = _strategy_results(item)
    ambiguous = CorrectionResult.ambiguous("fixture ambiguity")
    not_evaluable = CorrectionResult.not_evaluable("fixture unavailable")
    oracle = item.correction_oracle
    verdicts = (
        positive_result.verdict,
        negative_result.verdict,
        ambiguous.verdict,
        not_evaluable.verdict,
    )
    expected = (
        oracle.positive_verdict,
        oracle.negative_verdict,
        oracle.ambiguous_verdict,
        oracle.not_evaluable_verdict,
    )
    if verdicts != expected:
        raise _validation_failed(f"{item.primitive_id} correction oracle failed")
    if (
        ambiguous.credit_value(operation_cap=operation_cap, target_weight=1.0, hint_level="h0")
        is not None
        or not_evaluable.credit_value(
            operation_cap=operation_cap, target_weight=1.0, hint_level="h0"
        )
        is not None
    ):
        raise _validation_failed("ambiguous and unavailable corrections must not produce credit")
    for level, multiplier in _HINT_ORACLES.items():
        credit = positive_result.credit_value(
            operation_cap=operation_cap,
            target_weight=1.0,
            hint_level=level,
        )
        if credit is None or abs(credit - operation_cap * multiplier) > 1e-12:
            raise _validation_failed(f"{level} credit oracle failed")
    return PrimitiveOracleEvidence(
        oracle_id=oracle.oracle_id,
        primitive_id=item.primitive_id,
        sample_kind=item.sample.kind,
        strategy=oracle.strategy,
        sample_used=True,
        verdicts=(
            verdicts[0].value,
            verdicts[1].value,
            verdicts[2].value,
            verdicts[3].value,
        ),
    )


def _run_replay_oracles(
    item: _PrimitiveFixture, index: int, clock: FrozenClock, seed: int
) -> int:
    attempt, answer = _attempt(item, index, clock, seed)
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
    return attempt.instance.seed


def load_and_run_primitive_fixture(root: Path) -> PrimitiveFixtureReport:
    metadata, payload = _load(root)
    _validate_closed_contract(payload)
    counts = {case_id: 0 for case_id in _REQUIRED_CASES}
    certified: list[str] = []
    replayed: list[str] = []
    instance_seeds: list[int] = []
    primitive_oracles: list[PrimitiveOracleEvidence] = []
    clock = FrozenClock(payload.clock)
    by_id = {item.primitive_id: item for item in payload.primitives}
    replay_order = _seeded_replay_order(CORE_PRIMITIVE_IDS, payload.seed)
    for index, primitive_id in enumerate(replay_order, start=1):
        item = by_id[primitive_id]
        primitive_oracles.append(
            _run_correction_oracle(
                item,
                primitive_spec(item.primitive_id).operation_cap,
                clock,
            )
        )
        instance_seeds.append(_run_replay_oracles(item, index, clock, payload.seed))
        for case_id in item.case_ids:
            counts[case_id] += 1
        certified.append(item.primitive_id)
        replayed.append(item.primitive_id)
    return PrimitiveFixtureReport(
        primitive_ids=replay_order,
        case_counts=tuple(sorted(counts.items())),
        a11y_certified=tuple(certified),
        replay_without_duplicates=tuple(replayed),
        network_dependencies=metadata.network_dependencies,
        replay_order=replay_order,
        expected_replay_order=payload.expected_replay_order,
        instance_seeds=tuple(instance_seeds),
        primitive_oracles=tuple(primitive_oracles),
    )

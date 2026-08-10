from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from polyglot.platform.clock import Clock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import IdGenerator
from polyglot.platform.json_types import JsonValue


class AnswerKind(StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    SINGLE_CHOICE = "single_choice"
    GRADED_CHOICE = "graded_choice"
    SELECTION = "selection"
    PAIRING = "pairing"
    GROUPING = "grouping"
    ORDERED_ITEMS = "ordered_items"
    CELLS = "cells"
    SPANS = "spans"
    TOKENS = "tokens"
    TEXT = "text"
    SHORT_TEXT = "short_text"
    AUDIO_REF = "audio_ref"
    SELF_GRADE = "self_grade"
    SELF_ASSESSMENT = "self_assessment"
    NO_ANSWER = "no_answer"


class HintLevel(StrEnum):
    H0 = "h0"
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4"


class AttemptStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CORRECTING = "correcting"
    CORRECTED = "corrected"
    NOT_EVALUABLE = "not_evaluable"


class TerminalReason(StrEnum):
    NONE = "none"
    CORRECTION_UNAVAILABLE = "correction_unavailable"
    CORRECTION_AMBIGUOUS = "correction_ambiguous"
    ANSWER_INVALID = "answer_invalid"
    USER_CANCELLED = "user_cancelled"


class CorrectionVerdict(StrEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
    AMBIGUOUS = "ambiguous"
    INVALID_ANSWER = "invalid_answer"
    NOT_EVALUABLE = "not_evaluable"


class CorrectionStrategyKind(StrEnum):
    EXACT_NORMALIZED = "exact_normalized"
    ACCEPTED_SET = "accepted_set"
    MORPHOLOGICAL = "morphological"
    STRUCTURAL_CONSTRAINTS = "structural_constraints"
    RUBRIC = "rubric"


class BlockStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ABANDONED = "abandoned"
    UNAVAILABLE = "unavailable"


class CorrectionCaseStatus(StrEnum):
    CLOSED = "closed"
    CONTESTED = "contested"
    REVIEW_PENDING = "review_pending"
    RESOLVED = "resolved"


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(f"{field} must be UUIDv7")


def _freeze(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)  # type: ignore[return-value]
    return value


@dataclass(frozen=True, slots=True)
class IdempotencyReceipt:
    key: str
    command: str
    payload: tuple[object, ...]

    def __post_init__(self) -> None:
        if not self.key:
            raise _invalid("idempotent commands require a key")
        object.__setattr__(self, "payload", tuple(self.payload))


def _is_replay(
    receipts: tuple[IdempotencyReceipt, ...],
    *,
    key: str,
    command: str,
    payload: tuple[object, ...],
) -> bool:
    if not key:
        raise _invalid("idempotent commands require a key")
    for receipt in receipts:
        if receipt.key != key:
            continue
        if receipt.command == command and receipt.payload == payload:
            return True
        raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return False


def _receipt(
    receipts: tuple[IdempotencyReceipt, ...],
    *,
    key: str,
    command: str,
    payload: tuple[object, ...],
) -> tuple[IdempotencyReceipt, ...]:
    return (*receipts, IdempotencyReceipt(key, command, payload))


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().strip().split()).rstrip(".,;:!?")


@dataclass(frozen=True, slots=True)
class PrimitiveSpec:
    primitive_id: str
    answer_kinds: tuple[AnswerKind, ...]
    operation_cap: float


_SPECS = (
    PrimitiveSpec("EX-EXPOSE-01", (AnswerKind.ACKNOWLEDGEMENT,), 0.0),
    PrimitiveSpec("EX-DISC-01", (AnswerKind.SELECTION, AnswerKind.SHORT_TEXT), 0.35),
    PrimitiveSpec("EX-DISC-02", (AnswerKind.PAIRING,), 0.35),
    PrimitiveSpec("EX-DISC-03", (AnswerKind.GROUPING,), 0.35),
    PrimitiveSpec("EX-DISC-04", (AnswerKind.SINGLE_CHOICE,), 0.35),
    PrimitiveSpec("EX-DISC-06", (AnswerKind.SPANS,), 0.35),
    PrimitiveSpec("EX-RECALL-01", (AnswerKind.SELF_GRADE,), 0.55),
    PrimitiveSpec("EX-RECALL-02", (AnswerKind.TOKENS,), 0.55),
    PrimitiveSpec("EX-RECALL-03", (AnswerKind.SHORT_TEXT, AnswerKind.AUDIO_REF), 0.55),
    PrimitiveSpec("EX-RECALL-04", (AnswerKind.TEXT,), 0.55),
    PrimitiveSpec("EX-RECALL-05", (AnswerKind.TOKENS,), 0.55),
    PrimitiveSpec("EX-RECALL-06", (AnswerKind.CELLS,), 0.55),
    PrimitiveSpec("EX-RECALL-07", (AnswerKind.ORDERED_ITEMS,), 0.55),
    PrimitiveSpec("EX-TRANSFORM-01", (AnswerKind.TEXT, AnswerKind.AUDIO_REF), 0.65),
    PrimitiveSpec(
        "EX-COMP-01", (AnswerKind.SINGLE_CHOICE, AnswerKind.SPANS, AnswerKind.SHORT_TEXT), 0.35
    ),
    PrimitiveSpec(
        "EX-COMP-02", (AnswerKind.SINGLE_CHOICE, AnswerKind.SPANS, AnswerKind.SHORT_TEXT), 0.35
    ),
    PrimitiveSpec("EX-COMP-03", (AnswerKind.TEXT,), 0.55),
    PrimitiveSpec("EX-PROD-01", (AnswerKind.TEXT, AnswerKind.AUDIO_REF), 0.75),
    PrimitiveSpec("EX-PROD-02", (AnswerKind.TEXT, AnswerKind.AUDIO_REF), 0.75),
    PrimitiveSpec("EX-PROD-03", (AnswerKind.TEXT, AnswerKind.AUDIO_REF), 0.85),
    PrimitiveSpec("EX-ORAL-01", (AnswerKind.SELF_ASSESSMENT, AnswerKind.AUDIO_REF), 0.25),
    PrimitiveSpec("EX-REPAIR-01", (AnswerKind.TEXT, AnswerKind.AUDIO_REF), 0.75),
)
_SPEC_BY_ID = {spec.primitive_id: spec for spec in _SPECS}
CORE_PRIMITIVE_IDS = tuple(spec.primitive_id for spec in _SPECS)
_HELP_MULTIPLIERS = {
    HintLevel.H0: 1.0,
    HintLevel.H1: 0.85,
    HintLevel.H2: 0.60,
    HintLevel.H3: 0.25,
    HintLevel.H4: 0.0,
}


def primitive_spec(primitive_id: str) -> PrimitiveSpec:
    try:
        return _SPEC_BY_ID[primitive_id]
    except KeyError as error:
        raise DomainError(ErrorCode.PRIMITIVE_UNKNOWN) from error


@dataclass(frozen=True, slots=True)
class ExerciseDefinition:
    definition_id: UUID
    revision_id: UUID
    revision_no: int
    primitive_id: str
    response_kinds: tuple[AnswerKind, ...]
    language_certification_ids: tuple[UUID, ...]
    modes: tuple[str, ...]
    target_weights: tuple[tuple[str, float], ...]
    correction_policy_id: str
    hint_policy_id: str
    observation_policy_id: str
    accessibility_features: tuple[str, ...]
    status: str = "published"

    def __post_init__(self) -> None:
        object.__setattr__(self, "response_kinds", tuple(self.response_kinds))
        object.__setattr__(
            self, "language_certification_ids", tuple(self.language_certification_ids)
        )
        object.__setattr__(self, "modes", tuple(self.modes))
        object.__setattr__(
            self,
            "target_weights",
            tuple((str(target), float(weight)) for target, weight in self.target_weights),
        )
        object.__setattr__(self, "accessibility_features", tuple(self.accessibility_features))
        _require_uuid7(self.definition_id, "definition_id")
        _require_uuid7(self.revision_id, "revision_id")
        if self.revision_no < 1 or self.status != "published":
            raise _invalid("only a positive published definition can create an instance")
        spec = primitive_spec(self.primitive_id)
        if not self.response_kinds or not set(self.response_kinds).issubset(spec.answer_kinds):
            raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
        if not self.language_certification_ids or not self.modes or not self.target_weights:
            raise _invalid("definition contract is incomplete")
        for certification_id in self.language_certification_ids:
            _require_uuid7(certification_id, "language_certification_ids")
        if not {"keyboard", "screen_reader", "untimed"}.issubset(self.accessibility_features):
            raise _invalid("core primitive accessibility contract is incomplete")
        for target, weight in self.target_weights:
            if not target or not 0.0 <= weight <= 1.0:
                raise _invalid("target weights must be explicit and bounded")
        if not all((self.correction_policy_id, self.hint_policy_id, self.observation_policy_id)):
            raise _invalid("policy revisions are required")

    @classmethod
    def published(cls, **values: Any) -> ExerciseDefinition:
        return cls(**values)

    @property
    def spec(self) -> PrimitiveSpec:
        return primitive_spec(self.primitive_id)


@dataclass(frozen=True, slots=True)
class ExerciseInstance:
    instance_id: UUID
    definition: ExerciseDefinition
    language_pack_revision_id: UUID
    seed: int
    stimulus_revision_ids: tuple[UUID, ...]
    session_plan_revision_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stimulus_revision_ids", tuple(self.stimulus_revision_ids))
        _require_uuid7(self.instance_id, "instance_id")
        _require_uuid7(self.language_pack_revision_id, "language_pack_revision_id")
        if self.session_plan_revision_id is not None:
            _require_uuid7(self.session_plan_revision_id, "session_plan_revision_id")
        if not self.stimulus_revision_ids:
            raise _invalid("instance must pin stimulus revisions")
        for revision_id in self.stimulus_revision_ids:
            _require_uuid7(revision_id, "stimulus_revision_ids")

    @classmethod
    def create(cls, **values: Any) -> ExerciseInstance:
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Answer:
    kind: AnswerKind
    raw_value: JsonValue
    input_method: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not self.input_method or self.submitted_at.tzinfo is None:
            raise _invalid("answer input method and timezone-aware timestamp are required")
        if not _valid_answer_shape(self.kind, self.raw_value):
            raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
        object.__setattr__(self, "raw_value", _freeze(self.raw_value))

    @classmethod
    def create(cls, **values: Any) -> Answer:
        return cls(**values)


def _valid_answer_shape(kind: AnswerKind, raw_value: JsonValue) -> bool:
    if kind is AnswerKind.NO_ANSWER:
        return raw_value is None
    if kind is AnswerKind.ACKNOWLEDGEMENT:
        return raw_value in (None, True)
    if kind in {AnswerKind.SINGLE_CHOICE, AnswerKind.GRADED_CHOICE, AnswerKind.AUDIO_REF}:
        return isinstance(raw_value, str) and bool(raw_value)
    if kind in {AnswerKind.TEXT, AnswerKind.SHORT_TEXT}:
        return isinstance(raw_value, str) and (kind is AnswerKind.TEXT or len(raw_value) <= 500)
    if kind is AnswerKind.SELF_GRADE:
        return raw_value in {"again", "hard", "good", "easy"}
    if kind in {AnswerKind.SELECTION, AnswerKind.TOKENS, AnswerKind.ORDERED_ITEMS}:
        return isinstance(raw_value, list) and all(
            isinstance(value, str) and value for value in raw_value
        )
    if kind is AnswerKind.SPANS:
        return isinstance(raw_value, list) and all(_valid_span(value) for value in raw_value)
    if kind in {
        AnswerKind.PAIRING,
        AnswerKind.GROUPING,
        AnswerKind.CELLS,
        AnswerKind.SELF_ASSESSMENT,
    }:
        return isinstance(raw_value, dict) and bool(raw_value)
    return False


def _valid_span(value: JsonValue) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    start, end = value
    return isinstance(start, int) and isinstance(end, int) and 0 <= start <= end


@dataclass(frozen=True, slots=True)
class HintUse:
    level: HintLevel
    reason: str
    shown_at: datetime

    def __post_init__(self) -> None:
        if not self.reason or self.shown_at.tzinfo is None:
            raise _invalid("hint use requires a reason and timestamp")


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    verdict: CorrectionVerdict
    confidence: float
    target_coverage: float
    explanation: str
    strategy: str = "manual"
    criteria_scores: tuple[tuple[str, float], ...] = ()
    alternatives: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "criteria_scores",
            tuple((str(criterion), float(score)) for criterion, score in self.criteria_scores),
        )
        object.__setattr__(self, "alternatives", tuple(self.alternatives))
        object.__setattr__(self, "errors", tuple(self.errors))
        if not 0.0 <= self.confidence <= 1.0 or not 0.0 <= self.target_coverage <= 1.0:
            raise _invalid("correction confidence and coverage must be bounded")

    @classmethod
    def correct(cls, *, confidence: float, target_coverage: float = 1.0) -> CorrectionResult:
        if confidence < 0.60:
            return cls.not_evaluable("automatic correction confidence is below review threshold")
        return cls(CorrectionVerdict.CORRECT, confidence, target_coverage, "correct")

    @classmethod
    def ambiguous(cls, explanation: str) -> CorrectionResult:
        return cls(CorrectionVerdict.AMBIGUOUS, 0.0, 0.0, explanation)

    @classmethod
    def not_evaluable(cls, explanation: str) -> CorrectionResult:
        return cls(CorrectionVerdict.NOT_EVALUABLE, 0.0, 0.0, explanation)

    def credit_value(
        self, *, operation_cap: float, target_weight: float, hint_level: str
    ) -> float | None:
        if self.verdict in {
            CorrectionVerdict.AMBIGUOUS,
            CorrectionVerdict.INVALID_ANSWER,
            CorrectionVerdict.NOT_EVALUABLE,
        }:
            return None
        try:
            help_multiplier = _HELP_MULTIPLIERS[HintLevel(hint_level)]
        except ValueError as error:
            raise _invalid("hint level is not canonical") from error
        signed_outcome = {
            CorrectionVerdict.CORRECT: 1.0,
            CorrectionVerdict.PARTIALLY_CORRECT: 0.35,
            CorrectionVerdict.INCORRECT: -1.0,
        }[self.verdict]
        value = signed_outcome * min(operation_cap, target_weight) * help_multiplier
        value *= self.confidence * self.target_coverage
        if self.confidence < 0.80:
            value = max(-0.25, min(0.25, value))
        return max(-1.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class CorrectionStrategy:
    kind: CorrectionStrategyKind
    expected: tuple[str, ...] = ()
    expected_traits: tuple[tuple[str, str], ...] = ()
    required_tokens: tuple[str, ...] = ()
    ordered: bool = False
    required_criteria: tuple[str, ...] = ()
    passing_score: float = 1.0
    always_ambiguous: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", tuple(self.expected))
        object.__setattr__(
            self,
            "expected_traits",
            tuple((str(name), str(value)) for name, value in self.expected_traits),
        )
        object.__setattr__(self, "required_tokens", tuple(self.required_tokens))
        object.__setattr__(self, "required_criteria", tuple(self.required_criteria))

    @classmethod
    def exact_normalized(cls, expected: str) -> CorrectionStrategy:
        return cls(CorrectionStrategyKind.EXACT_NORMALIZED, expected=(expected,))

    @classmethod
    def accepted_set(cls, accepted: tuple[str, ...]) -> CorrectionStrategy:
        return cls(CorrectionStrategyKind.ACCEPTED_SET, expected=accepted)

    @classmethod
    def morphological(
        cls, *, expected: str, expected_traits: Mapping[str, str]
    ) -> CorrectionStrategy:
        return cls(
            CorrectionStrategyKind.MORPHOLOGICAL,
            expected=(expected,),
            expected_traits=tuple(sorted(expected_traits.items())),
        )

    @classmethod
    def structural_constraints(
        cls, *, required_tokens: tuple[str, ...], ordered: bool
    ) -> CorrectionStrategy:
        return cls(
            CorrectionStrategyKind.STRUCTURAL_CONSTRAINTS,
            required_tokens=required_tokens,
            ordered=ordered,
        )

    @classmethod
    def rubric(
        cls, *, required_criteria: tuple[str, ...], passing_score: float
    ) -> CorrectionStrategy:
        return cls(
            CorrectionStrategyKind.RUBRIC,
            required_criteria=required_criteria,
            passing_score=passing_score,
        )

    @classmethod
    def ambiguous(cls) -> CorrectionStrategy:
        return cls(CorrectionStrategyKind.RUBRIC, always_ambiguous=True)

    def correct(
        self, value: str | Mapping[str, float], *, observed_traits: Mapping[str, str] | None = None
    ) -> CorrectionResult:
        if self.always_ambiguous:
            return CorrectionResult.ambiguous(
                "the correction policy declares multiple plausible readings"
            )
        if self.kind in {
            CorrectionStrategyKind.EXACT_NORMALIZED,
            CorrectionStrategyKind.ACCEPTED_SET,
        }:
            if not isinstance(value, str):
                return CorrectionResult(
                    CorrectionVerdict.INVALID_ANSWER, 1.0, 0.0, "text required", self.kind
                )
            accepted = {_normalize(candidate) for candidate in self.expected}
            verdict = (
                CorrectionVerdict.CORRECT
                if _normalize(value) in accepted
                else CorrectionVerdict.INCORRECT
            )
            return CorrectionResult(
                verdict,
                1.0,
                1.0 if verdict is CorrectionVerdict.CORRECT else 0.0,
                "exact",
                self.kind,
            )
        if self.kind is CorrectionStrategyKind.MORPHOLOGICAL:
            matches_form = isinstance(value, str) and _normalize(value) == _normalize(
                self.expected[0]
            )
            matches_traits = tuple(sorted((observed_traits or {}).items())) == self.expected_traits
            verdict = (
                CorrectionVerdict.CORRECT
                if matches_form and matches_traits
                else CorrectionVerdict.INCORRECT
            )
            return CorrectionResult(
                verdict, 1.0, float(matches_form and matches_traits), "morphology", self.kind
            )
        if self.kind is CorrectionStrategyKind.STRUCTURAL_CONSTRAINTS:
            if not isinstance(value, str):
                return CorrectionResult(
                    CorrectionVerdict.INVALID_ANSWER, 1.0, 0.0, "text required", self.kind
                )
            tokens = _normalize(value).split()
            ordered_tokens = list(self.required_tokens)
            matched = all(token in tokens for token in ordered_tokens)
            if matched and self.ordered:
                matched = [token for token in tokens if token in ordered_tokens] == ordered_tokens
            return CorrectionResult(
                CorrectionVerdict.CORRECT if matched else CorrectionVerdict.INCORRECT,
                1.0,
                float(matched),
                "constraints",
                self.kind,
            )
        if not isinstance(value, Mapping) or not self.required_criteria:
            return CorrectionResult(
                CorrectionVerdict.NOT_EVALUABLE, 0.0, 0.0, "rubric data missing", self.kind
            )
        scores: list[float] = []
        for criterion in self.required_criteria:
            item = value.get(criterion)
            if not isinstance(item, (int, float)):
                return CorrectionResult(
                    CorrectionVerdict.NOT_EVALUABLE,
                    0.0,
                    0.0,
                    "rubric data incomplete",
                    self.kind,
                )
            scores.append(float(item))
        score = min(scores)
        verdict = (
            CorrectionVerdict.CORRECT
            if score >= self.passing_score
            else CorrectionVerdict.PARTIALLY_CORRECT
        )
        return CorrectionResult(verdict, 1.0, max(0.0, min(1.0, score)), "rubric", self.kind)


@dataclass(frozen=True, slots=True)
class Attempt:
    attempt_id: UUID
    instance: ExerciseInstance
    profile_id: UUID
    attempt_no: int
    status: AttemptStatus
    started_at: datetime
    answer: Answer | None = None
    hint_uses: tuple[HintUse, ...] = ()
    corrections: tuple[tuple[UUID, CorrectionResult], ...] = ()
    terminal_reason: TerminalReason = TerminalReason.NONE
    idempotency_key: str | None = None
    idempotency_receipts: tuple[IdempotencyReceipt, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hint_uses", tuple(self.hint_uses))
        object.__setattr__(
            self,
            "corrections",
            tuple((correction_id, result) for correction_id, result in self.corrections),
        )
        object.__setattr__(self, "idempotency_receipts", tuple(self.idempotency_receipts))
        _require_uuid7(self.attempt_id, "attempt_id")
        _require_uuid7(self.profile_id, "profile_id")
        if self.attempt_no < 1 or self.started_at.tzinfo is None:
            raise _invalid("attempt number and timestamp are required")
        if (self.status is AttemptStatus.NOT_EVALUABLE) != (
            self.terminal_reason is not TerminalReason.NONE
        ):
            raise _invalid("terminal reason must be explicit exactly for non-evaluable attempts")

    @classmethod
    def start(
        cls,
        *,
        instance: ExerciseInstance,
        profile_id: UUID,
        attempt_no: int,
        clock: Clock,
        ids: IdGenerator,
    ) -> Attempt:
        return cls(ids.new(), instance, profile_id, attempt_no, AttemptStatus.DRAFT, clock.now())

    def use_hint(
        self, level: HintLevel, *, reason: str, clock: Clock, idempotency_key: str
    ) -> Attempt:
        payload = (level, reason)
        if _is_replay(
            self.idempotency_receipts,
            key=idempotency_key,
            command="use_hint",
            payload=payload,
        ):
            return self
        if self.status is not AttemptStatus.DRAFT:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(
            self,
            hint_uses=(*self.hint_uses, HintUse(level, reason, clock.now())),
            idempotency_receipts=_receipt(
                self.idempotency_receipts,
                key=idempotency_key,
                command="use_hint",
                payload=payload,
            ),
        )

    def reveal(self, *, reason: str, clock: Clock, idempotency_key: str) -> Attempt:
        return self.use_hint(
            HintLevel.H4,
            reason=reason,
            clock=clock,
            idempotency_key=idempotency_key,
        )

    def submit(self, *, answer: Answer, idempotency_key: str) -> Attempt:
        payload = (answer,)
        if _is_replay(
            self.idempotency_receipts,
            key=idempotency_key,
            command="submit",
            payload=payload,
        ):
            return self
        if self.status is AttemptStatus.SUBMITTED:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if self.status is not AttemptStatus.DRAFT:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if answer.kind not in self.instance.definition.response_kinds:
            raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
        return replace(
            self,
            status=AttemptStatus.SUBMITTED,
            answer=answer,
            idempotency_key=idempotency_key,
            idempotency_receipts=_receipt(
                self.idempotency_receipts,
                key=idempotency_key,
                command="submit",
                payload=payload,
            ),
        )

    def force_submit(self, *, reason: TerminalReason, idempotency_key: str) -> Attempt:
        payload = (reason,)
        if _is_replay(
            self.idempotency_receipts,
            key=idempotency_key,
            command="force_submit",
            payload=payload,
        ):
            return self
        if reason is TerminalReason.NONE or self.status is not AttemptStatus.DRAFT:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(
            self,
            status=AttemptStatus.NOT_EVALUABLE,
            terminal_reason=reason,
            idempotency_key=idempotency_key,
            idempotency_receipts=_receipt(
                self.idempotency_receipts,
                key=idempotency_key,
                command="force_submit",
                payload=payload,
            ),
        )

    def start_correction(self) -> Attempt:
        if self.status is not AttemptStatus.SUBMITTED:
            raise DomainError(ErrorCode.ATTEMPT_NOT_SUBMITTED)
        return replace(self, status=AttemptStatus.CORRECTING)

    def complete_correction(
        self,
        *,
        correction_id: UUID,
        result: CorrectionResult,
        clock: Clock,
        idempotency_key: str,
    ) -> Attempt:
        _require_uuid7(correction_id, "correction_id")
        payload = (correction_id, result)
        if _is_replay(
            self.idempotency_receipts,
            key=idempotency_key,
            command="complete_correction",
            payload=payload,
        ):
            return self
        if self.status is not AttemptStatus.CORRECTING:
            if self.corrections:
                raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        receipts = _receipt(
            self.idempotency_receipts,
            key=idempotency_key,
            command="complete_correction",
            payload=payload,
        )
        if result.verdict is CorrectionVerdict.AMBIGUOUS:
            return replace(
                self,
                status=AttemptStatus.NOT_EVALUABLE,
                terminal_reason=TerminalReason.CORRECTION_AMBIGUOUS,
                corrections=(*self.corrections, (correction_id, result)),
                idempotency_receipts=receipts,
            )
        if result.verdict is CorrectionVerdict.NOT_EVALUABLE:
            return replace(
                self,
                status=AttemptStatus.NOT_EVALUABLE,
                terminal_reason=TerminalReason.CORRECTION_UNAVAILABLE,
                corrections=(*self.corrections, (correction_id, result)),
                idempotency_receipts=receipts,
            )
        if result.verdict is CorrectionVerdict.INVALID_ANSWER:
            return replace(
                self,
                status=AttemptStatus.NOT_EVALUABLE,
                terminal_reason=TerminalReason.ANSWER_INVALID,
                corrections=(*self.corrections, (correction_id, result)),
                idempotency_receipts=receipts,
            )
        return replace(
            self,
            status=AttemptStatus.CORRECTED,
            corrections=(*self.corrections, (correction_id, result)),
            idempotency_receipts=receipts,
        )

    def current_credit(self, *, operation_cap: float, target_weight: float) -> float | None:
        if not self.corrections:
            return None
        highest_hint = max(
            self.hint_uses, key=lambda hint: _HELP_MULTIPLIERS[hint.level], default=None
        )
        hint_level = (
            HintLevel.H0
            if highest_hint is None
            else min(
                (hint.level for hint in self.hint_uses), key=lambda level: _HELP_MULTIPLIERS[level]
            )
        )
        result = self.corrections[-1][1]
        return result.credit_value(
            operation_cap=operation_cap, target_weight=target_weight, hint_level=hint_level
        )


@dataclass(frozen=True, slots=True)
class ExerciseBlockRun:
    block_id: UUID
    status: BlockStatus = BlockStatus.PENDING
    reason: str | None = None
    idempotency_receipts: tuple[IdempotencyReceipt, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "idempotency_receipts", tuple(self.idempotency_receipts))
        _require_uuid7(self.block_id, "block_id")

    @classmethod
    def create(cls, *, block_id: UUID) -> ExerciseBlockRun:
        return cls(block_id)

    def make_available(self) -> ExerciseBlockRun:
        return self._transition(BlockStatus.PENDING, BlockStatus.AVAILABLE)

    def start(self) -> ExerciseBlockRun:
        return self._transition(BlockStatus.AVAILABLE, BlockStatus.IN_PROGRESS)

    def complete(self) -> ExerciseBlockRun:
        return self._transition(BlockStatus.IN_PROGRESS, BlockStatus.COMPLETED)

    def skip(self, *, reason: str, idempotency_key: str) -> ExerciseBlockRun:
        return self._idempotent_transition(
            BlockStatus.AVAILABLE,
            BlockStatus.SKIPPED,
            command="skip",
            key=idempotency_key,
            reason=reason,
        )

    def abandon(self, *, idempotency_key: str) -> ExerciseBlockRun:
        return self._idempotent_transition(
            BlockStatus.IN_PROGRESS,
            BlockStatus.ABANDONED,
            command="abandon",
            key=idempotency_key,
        )

    def mark_unavailable(self, *, reason: str, idempotency_key: str) -> ExerciseBlockRun:
        return self._idempotent_transition(
            BlockStatus.AVAILABLE,
            BlockStatus.UNAVAILABLE,
            command="mark_unavailable",
            key=idempotency_key,
            reason=reason,
        )

    def _idempotent_transition(
        self,
        source: BlockStatus,
        target: BlockStatus,
        *,
        command: str,
        key: str,
        reason: str | None = None,
    ) -> ExerciseBlockRun:
        payload = (reason,)
        if _is_replay(
            self.idempotency_receipts,
            key=key,
            command=command,
            payload=payload,
        ):
            return self
        transitioned = self._transition(source, target, reason)
        return replace(
            transitioned,
            idempotency_receipts=_receipt(
                self.idempotency_receipts,
                key=key,
                command=command,
                payload=payload,
            ),
        )

    def _transition(
        self, source: BlockStatus, target: BlockStatus, reason: str | None = None
    ) -> ExerciseBlockRun:
        if self.status is not source:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=target, reason=reason)


@dataclass(frozen=True, slots=True)
class CorrectionCase:
    case_id: UUID
    attempt_id: UUID
    correction_history: tuple[UUID, ...]
    status: CorrectionCaseStatus
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "correction_history", tuple(self.correction_history))
        for field, value in (("case_id", self.case_id), ("attempt_id", self.attempt_id)):
            _require_uuid7(value, field)
        if not self.correction_history:
            raise _invalid("correction case needs an original correction")
        for correction_id in self.correction_history:
            _require_uuid7(correction_id, "correction_history")

    @classmethod
    def closed(cls, *, case_id: UUID, attempt_id: UUID, correction_id: UUID) -> CorrectionCase:
        return cls(case_id, attempt_id, (correction_id,), CorrectionCaseStatus.CLOSED)

    def contest(self, *, reason: str, at: datetime) -> CorrectionCase:
        if self.status is not CorrectionCaseStatus.CLOSED or not reason or at.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=CorrectionCaseStatus.CONTESTED, reason=reason)

    def queue_review(self, *, at: datetime) -> CorrectionCase:
        if self.status is not CorrectionCaseStatus.CONTESTED or at.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=CorrectionCaseStatus.REVIEW_PENDING)

    def resolve(self, *, correction_id: UUID, at: datetime) -> CorrectionCase:
        _require_uuid7(correction_id, "correction_id")
        if self.status is not CorrectionCaseStatus.REVIEW_PENDING or at.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(
            self,
            correction_history=(*self.correction_history, correction_id),
            status=CorrectionCaseStatus.RESOLVED,
        )

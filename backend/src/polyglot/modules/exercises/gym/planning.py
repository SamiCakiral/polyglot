from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from polyglot.modules.exercises.core.domain import ExerciseDefinition, ExerciseInstance
from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


def _uuid7_from(parts: tuple[object, ...]) -> UUID:
    value = bytearray(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:16])
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(value))


def _seed_from(seed: int, case_id: str) -> int:
    digest = hashlib.sha256(f"gym:{seed}:{case_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _order_key(seed: int, case: TransformationCase) -> bytes:
    return hashlib.sha256(f"gym-order:{seed}:{case.case_id}".encode()).digest()


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be UUIDv7")


@dataclass(frozen=True, slots=True)
class GymStep:
    ordinal: int
    case_id: str
    operation_id: str
    instance_seed: int
    instance: ExerciseInstance

    def __post_init__(self) -> None:
        if self.ordinal < 1 or self.instance_seed < 0:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym step is invalid")
        if self.instance.seed != self.instance_seed:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym step seed is not pinned")


@dataclass(frozen=True, slots=True)
class GymPlan:
    plan_id: UUID
    revision_id: UUID
    profile_id: UUID
    grammar_target_revision_id: UUID
    policy_revision_id: UUID
    language_pack_revision_id: UUID
    lexical_support_snapshot_id: UUID
    seed: int
    invariants: tuple[str, ...]
    exit_evidence_spec: str
    steps: tuple[GymStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "invariants", tuple(self.invariants))
        object.__setattr__(self, "steps", tuple(self.steps))
        for field in (
            "plan_id",
            "revision_id",
            "profile_id",
            "grammar_target_revision_id",
            "policy_revision_id",
            "language_pack_revision_id",
            "lexical_support_snapshot_id",
        ):
            _require_uuid7(getattr(self, field), field)
        if self.seed < 0 or not self.invariants or not self.exit_evidence_spec:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym plan is incomplete")
        if not 1 <= len(self.steps) <= 3:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym plan requires 1 to 3 steps")
        if tuple(step.ordinal for step in self.steps) != tuple(range(1, len(self.steps) + 1)):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym step ordinals are invalid")
        if len({step.case_id for step in self.steps}) != len(self.steps):
            raise DomainError(ErrorCode.DUPLICATE_CANDIDATE)


def compose_gym_plan(
    *,
    plan_id: UUID,
    revision_id: UUID,
    profile_id: UUID,
    grammar_target_revision_id: UUID,
    policy_revision_id: UUID,
    language_pack_revision_id: UUID,
    lexical_support_snapshot_id: UUID,
    seed: int,
    definition: ExerciseDefinition,
    candidates: Sequence[TransformationCase],
    grants: Sequence[PrerequisiteGrant],
    invariants: Sequence[str],
    exit_evidence_spec: str,
) -> GymPlan:
    frozen_candidates = tuple(candidates)
    frozen_grants = tuple(grants)
    if definition.primitive_id != "EX-TRANSFORM-01":
        raise DomainError(
            ErrorCode.BLUEPRINT_MISMATCH,
            detail="Gym steps require EX-TRANSFORM-01",
        )
    if not 1 <= len(frozen_candidates) <= 3:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            detail="G1 requires one to three transformations",
        )
    case_ids = tuple(case.case_id for case in frozen_candidates)
    if len(set(case_ids)) != len(case_ids):
        raise DomainError(ErrorCode.DUPLICATE_CANDIDATE)

    granted_ids = {grant.prerequisite_id for grant in frozen_grants}
    missing = sorted(
        {
            prerequisite_id
            for case in frozen_candidates
            for prerequisite_id in case.required_prerequisites
            if prerequisite_id not in granted_ids
        }
    )
    if missing:
        missing_details = [cast(JsonValue, item) for item in missing]
        raise DomainError(
            ErrorCode.PREREQUISITE_MISSING,
            details={"missing": missing_details},
        )

    ordered = sorted(frozen_candidates, key=lambda case: _order_key(seed, case))
    steps = tuple(
        GymStep(
            ordinal=ordinal,
            case_id=case.case_id,
            operation_id=case.operation_id,
            instance_seed=_seed_from(seed, case.case_id),
            instance=ExerciseInstance.create(
                instance_id=_uuid7_from(("gym-instance", revision_id, seed, case.case_id)),
                definition=definition,
                language_pack_revision_id=language_pack_revision_id,
                seed=_seed_from(seed, case.case_id),
                stimulus_revision_ids=(
                    _uuid7_from(("gym-case-revision", case.revision_id)),
                ),
            ),
        )
        for ordinal, case in enumerate(ordered, start=1)
    )
    return GymPlan(
        plan_id=plan_id,
        revision_id=revision_id,
        profile_id=profile_id,
        grammar_target_revision_id=grammar_target_revision_id,
        policy_revision_id=policy_revision_id,
        language_pack_revision_id=language_pack_revision_id,
        lexical_support_snapshot_id=lexical_support_snapshot_id,
        seed=seed,
        invariants=tuple(invariants),
        exit_evidence_spec=exit_evidence_spec,
        steps=steps,
    )

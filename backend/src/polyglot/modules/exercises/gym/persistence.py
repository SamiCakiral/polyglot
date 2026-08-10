from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.exercises.gym.planning import GymPlan
from polyglot.platform.errors import DomainError, ErrorCode


def _step_id(plan_revision_id: UUID, ordinal: int, case_revision_id: str) -> UUID:
    payload = f"gym-step:{plan_revision_id}:{ordinal}:{case_revision_id}".encode()
    value = bytearray(hashlib.sha256(payload).digest()[:16])
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(value))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SqlGymPlanRepository:
    """Gym-owned persistence; catalogue, lexicon and exercise reads stay behind ports."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def add(
        self,
        actor_id: UUID,
        plan: GymPlan,
        *,
        provenance_id: UUID,
        created_at: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.user_id',:actor,true)"),
                {"actor": str(actor_id)},
            )
            try:
                await session.execute(
                    text(
                        "INSERT INTO exercises.gym_plans "
                        "(gym_plan_id,profile_id,status,version,created_at,updated_at) "
                        "VALUES (:plan,:profile,'ready',1,:created,:created)"
                    ),
                    {
                        "plan": plan.plan_id,
                        "profile": plan.profile_id,
                        "created": created_at,
                    },
                )
                await session.execute(
                    text(
                        "INSERT INTO exercises.gym_plan_revisions "
                        "(gym_plan_revision_id,gym_plan_id,profile_id,revision_no,"
                        "grammar_target_revision_id,policy_revision_id,language_pack_revision_id,"
                        "lexical_support_snapshot_id,seed,invariants,exit_evidence_spec,"
                        "provenance_id,created_at) VALUES "
                        "(:revision,:plan,:profile,1,:grammar,:policy,:pack,:snapshot,:seed,"
                        "CAST(:invariants AS jsonb),CAST(:exit_spec AS jsonb),:provenance,:created)"
                    ),
                    {
                        "revision": plan.revision_id,
                        "plan": plan.plan_id,
                        "profile": plan.profile_id,
                        "grammar": plan.grammar_target_revision_id,
                        "policy": plan.policy_revision_id,
                        "pack": plan.language_pack_revision_id,
                        "snapshot": plan.lexical_support_snapshot_id,
                        "seed": plan.seed,
                        "invariants": _json(plan.invariants),
                        "exit_spec": _json({"criterion": plan.exit_evidence_spec}),
                        "provenance": provenance_id,
                        "created": created_at,
                    },
                )
                for step in plan.steps:
                    await session.execute(
                        text(
                            "INSERT INTO exercises.gym_steps "
                            "(gym_step_id,gym_plan_revision_id,gym_plan_id,profile_id,ordinal,"
                            "case_revision_ref,gym_operation,instance_id,instance_seed,created_at) "
                            "VALUES (:step,:revision,:plan,:profile,:ordinal,:case_revision,"
                            ":operation,:instance,:instance_seed,:created)"
                        ),
                        {
                            "step": _step_id(
                                plan.revision_id, step.ordinal, step.case_revision_id
                            ),
                            "revision": plan.revision_id,
                            "plan": plan.plan_id,
                            "profile": plan.profile_id,
                            "ordinal": step.ordinal,
                            "case_revision": step.case_revision_id,
                            "operation": step.operation_id,
                            "instance": step.instance.instance_id,
                            "instance_seed": step.instance_seed,
                            "created": created_at,
                        },
                    )
                await session.execute(
                    text(
                        "UPDATE exercises.gym_plans SET current_revision_id=:revision "
                        "WHERE gym_plan_id=:plan"
                    ),
                    {"revision": plan.revision_id, "plan": plan.plan_id},
                )
            except IntegrityError as error:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail="Gym plan persistence rejected inconsistent references",
                ) from error


__all__ = ["SqlGymPlanRepository"]

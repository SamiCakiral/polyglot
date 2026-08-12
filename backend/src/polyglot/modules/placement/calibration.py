from dataclasses import dataclass

from polyglot.modules.placement.domain import PlacementObservation


@dataclass(frozen=True, slots=True)
class PlacementCalibrationCycle:
    phase: str
    completed_daily_runs: int
    priority_skill_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalibrationSessionContext:
    run_kind: str
    budget_minutes: int
    theme_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalibrationProbeRequest:
    skill_ref: str
    reason: str


@dataclass(frozen=True, slots=True)
class CalibrationAdvance:
    cycle: PlacementCalibrationCycle
    explanation_codes: tuple[str, ...]


class CalibrationPolicyV1:
    def requests_for(
        self,
        cycle: PlacementCalibrationCycle,
        session_context: CalibrationSessionContext,
    ) -> tuple[CalibrationProbeRequest, ...]:
        if session_context.run_kind != "daily" or cycle.phase == "complete":
            return ()
        reason = {
            "P0": "confirm_general_difficulty",
            "P1": "resolve_priority_uncertainty",
            "P2": "confirm_curriculum_prerequisite",
        }.get(cycle.phase, "confirm_transfer")
        return tuple(
            CalibrationProbeRequest(skill, reason)
            for skill in cycle.priority_skill_refs[:2]
        )

    def advance(
        self,
        cycle: PlacementCalibrationCycle,
        observations: tuple[PlacementObservation, ...],
        *,
        run_kind: str,
    ) -> CalibrationAdvance:
        if run_kind != "daily":
            return CalibrationAdvance(cycle, ())
        completed = min(3, cycle.completed_daily_runs + 1)
        phase = ("P1", "P2", "P3")[completed - 1]
        return CalibrationAdvance(
            PlacementCalibrationCycle(phase, completed, cycle.priority_skill_refs),
            ("daily_evidence_added",) if observations else ("daily_session_completed",),
        )

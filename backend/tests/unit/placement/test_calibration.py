from polyglot.modules.placement.calibration import (
    CalibrationPolicyV1,
    CalibrationSessionContext,
    PlacementCalibrationCycle,
)


def test_daily_sprint_contains_at_most_two_calibration_probes() -> None:
    cycle = PlacementCalibrationCycle("P0", 0, ("listening", "writing", "reading"))
    requests = CalibrationPolicyV1().requests_for(
        cycle, CalibrationSessionContext("daily", 30, ("travel",))
    )
    assert len(requests) <= 2


def test_free_practice_does_not_advance_p0_p3_cycle() -> None:
    cycle = PlacementCalibrationCycle("P0", 0, ("listening",))
    assert CalibrationPolicyV1().advance(cycle, (), run_kind="free").cycle == cycle

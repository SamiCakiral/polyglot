from datetime import UTC, datetime
from importlib import import_module


def test_frozen_clock_returns_the_injected_utc_instant() -> None:
    clock_module = import_module("polyglot.platform.clock")
    instant = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)

    clock = clock_module.FrozenClock(instant)

    assert clock.now() == instant


def test_frozen_clock_rejects_a_naive_datetime() -> None:
    clock_module = import_module("polyglot.platform.clock")

    try:
        clock_module.FrozenClock(datetime(2026, 8, 9, 12, 30))
    except ValueError as error:
        assert str(error) == "clock instant must be timezone-aware"
    else:
        raise AssertionError("naive datetime was accepted")


def test_system_clock_returns_an_aware_utc_instant() -> None:
    clock_module = import_module("polyglot.platform.clock")

    instant = clock_module.SystemClock().now()

    assert instant.tzinfo is UTC


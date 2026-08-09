from datetime import UTC, datetime
from importlib import import_module
from uuid import RFC_4122


def test_uuid7_generator_uses_the_injected_clock_and_entropy() -> None:
    clock_module = import_module("polyglot.platform.clock")
    ids_module = import_module("polyglot.platform.ids")
    clock = clock_module.FrozenClock(datetime(2026, 8, 9, 12, 30, tzinfo=UTC))
    generator = ids_module.Uuid7Generator(clock=clock, random_bytes=lambda size: bytes(range(size)))

    identifier = generator.new()

    assert identifier.version == 7
    assert identifier.variant == RFC_4122
    assert identifier.hex == "019fe6805d4070018203040506070809"


def test_uuid7_generator_produces_unique_identifiers_with_new_entropy() -> None:
    clock_module = import_module("polyglot.platform.clock")
    ids_module = import_module("polyglot.platform.ids")
    clock = clock_module.FrozenClock(datetime(2026, 8, 9, 12, 30, tzinfo=UTC))
    entropy = iter((b"\x00" * 10, b"\x01" * 10))
    generator = ids_module.Uuid7Generator(clock=clock, random_bytes=lambda _: next(entropy))

    identifiers = {generator.new(), generator.new()}

    assert len(identifiers) == 2

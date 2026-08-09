from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from polyglot.platform.clock import FrozenClock
from polyglot.platform.ids import Uuid7Generator


@given(st.binary(min_size=10, max_size=10))
def test_uuid7_always_sets_version_and_variant_bits(entropy: bytes) -> None:
    generator = Uuid7Generator(
        clock=FrozenClock(datetime(2026, 8, 9, tzinfo=UTC)),
        random_bytes=lambda _: entropy,
    )

    identifier = generator.new()

    assert identifier.version == 7
    assert identifier.variant == "specified in RFC 4122"

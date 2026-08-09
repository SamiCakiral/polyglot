import os
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from polyglot.platform.clock import Clock, SystemClock


class IdGenerator(Protocol):
    def new(self) -> UUID: ...


class Uuid7Generator:
    def __init__(
        self,
        clock: Clock | None = None,
        random_bytes: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self._clock = clock or SystemClock()
        self._random_bytes = random_bytes

    def new(self) -> UUID:
        unix_ms = int(self._clock.now().timestamp() * 1000)
        if not 0 <= unix_ms < 1 << 48:
            raise ValueError("UUIDv7 timestamp is outside the 48-bit range")
        entropy = self._random_bytes(10)
        if len(entropy) != 10:
            raise ValueError("UUIDv7 entropy source must return exactly 10 bytes")
        value = bytearray(unix_ms.to_bytes(6, "big") + entropy)
        value[6] = (value[6] & 0x0F) | 0x70
        value[8] = (value[8] & 0x3F) | 0x80
        return UUID(bytes=bytes(value))

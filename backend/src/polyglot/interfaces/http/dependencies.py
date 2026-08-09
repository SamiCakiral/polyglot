from typing import Protocol
from uuid import UUID


class ReadinessCheck(Protocol):
    @property
    def name(self) -> str: ...

    async def check(self) -> bool: ...


def valid_correlation_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        identifier = UUID(value)
    except ValueError:
        return None
    canonical = str(identifier)
    return canonical if canonical == value.lower() else None

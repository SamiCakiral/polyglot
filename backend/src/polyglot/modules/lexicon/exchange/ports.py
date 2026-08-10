from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class AssociationTargetPort(Protocol):
    async def verify(
        self,
        target_type: str,
        target_id: UUID,
        profile_id: UUID,
    ) -> bool: ...


class DynamicListQueryPort(Protocol):
    async def evaluate(
        self,
        profile_id: UUID,
        query_definition: dict[str, object],
        cutoff_at: datetime,
        limit: int,
    ) -> tuple[UUID, ...]: ...

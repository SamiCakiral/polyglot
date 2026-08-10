from __future__ import annotations

from typing import Protocol
from uuid import UUID


class AssociationTargetPort(Protocol):
    async def verify(
        self,
        target_type: str,
        target_id: UUID,
        profile_id: UUID,
    ) -> bool: ...

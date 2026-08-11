from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

from polyglot.modules.lexicon.exchange.persistence import SqlExchangeService


def uid(value: int) -> UUID:
    return UUID(int=value)


class MappingRows:
    def __init__(self, rows: list[dict[str, UUID]]) -> None:
        self._rows = rows

    def mappings(self) -> MappingRows:
        return self

    def all(self) -> list[dict[str, UUID]]:
        return self._rows


async def test_snapshot_members_resolve_to_latest_published_sense_revisions() -> None:
    session = AsyncMock()
    session.execute.return_value = MappingRows(
        [
            {"sense_id": uid(1), "sense_revision_id": uid(101)},
            {"sense_id": uid(2), "sense_revision_id": uid(202)},
        ]
    )

    resolved = await SqlExchangeService._published_sense_revisions(
        session,
        uid(900),
        (uid(2), uid(3), uid(1)),
    )

    assert resolved == (uid(202), uid(3), uid(101))
    _, parameters = session.execute.await_args.args
    assert parameters == {"senses": [uid(2), uid(3), uid(1)], "variety": uid(900)}

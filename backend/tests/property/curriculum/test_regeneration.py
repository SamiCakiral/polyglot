from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.curriculum import ArcType
from polyglot.modules.curriculum.revisioning import build_successor_revision
from tests.unit.curriculum.test_module_contract import day, revision, uid


@given(st.integers(min_value=0, max_value=2))
def test_regeneration_replay_is_deterministic(executed_through: int) -> None:
    source = revision(days=(day(1), day(2, arc=ArcType.GUIDED_USE), day(3, arc=ArcType.TRANSFER)))
    values = {
        build_successor_revision(
            source,
            successor_revision_id=uid(70),
            candidate_days=source.days,
            executed_through_ordinal=executed_through,
            expected_revision_no=1,
        ).payload_checksum
        for _ in range(100)
    }
    assert len(values) == 1

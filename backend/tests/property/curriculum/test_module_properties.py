from __future__ import annotations

from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.curriculum import ArcType, LearningModuleRevision, ModuleDay, ModuleStatus


def uid(suffix: int) -> UUID:
    return UUID(f"019fe112-0000-7000-8000-{suffix:012d}")


def day(ordinal: int) -> ModuleDay:
    return ModuleDay(
        uid(100 + ordinal),
        ordinal,
        ArcType.DISCOVERY,
        (f"o-{ordinal}",),
        (("written_production", "produce"),),
        (f"skill:{ordinal}",),
        (f"skill:{ordinal}",),
        (f"skill:{ordinal}",),
        10,
        3.0,
        ("explanation", "practice", "production"),
    )


def revision(*, days: tuple[ModuleDay, ...]) -> LearningModuleRevision:
    return LearningModuleRevision(
        uid(1),
        uid(2),
        1,
        ModuleStatus.DRAFT,
        uid(3),
        uid(4),
        (uid(5),),
        "autonomous exchange",
        uid(6),
        ("P-ABS", "P-FAUX", "P-INT"),
        len(days),
        len(days),
        (uid(7),),
        tuple(uid(20 + item.ordinal) for item in days),
        uid(8),
        uid(9),
        "prov:test",
        ("rights:test",),
        uid(10),
        1,
        ">=1,<2",
        days,
    )


@given(st.permutations(("a", "b", "c", "d")))
def test_semantically_unordered_inputs_have_a_stable_checksum(values: list[str]) -> None:
    days = list((day(1), day(2), day(3)))
    module = revision(days=tuple(days))
    baseline = module.payload_checksum

    object.__setattr__(module, "entry_profile_codes", tuple(values))
    normalized = module.recanonicalized()

    object.__setattr__(module, "entry_profile_codes", tuple(reversed(values)))
    assert module.recanonicalized().payload_checksum == normalized.payload_checksum
    assert baseline != ""

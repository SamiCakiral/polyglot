from __future__ import annotations

from hypothesis import given, strategies as st

from tests.unit.curriculum.test_module_contract import day, revision


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

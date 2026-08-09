from hypothesis import given
from hypothesis import strategies as st

from polyglot.platform.fingerprint import canonical_json_fingerprint

json_scalars = st.none() | st.booleans() | st.integers() | st.text()


@given(st.dictionaries(st.text(), json_scalars, max_size=20))
def test_fingerprint_is_independent_of_mapping_insertion_order(
    payload: dict[str, bool | int | str | None],
) -> None:
    reversed_payload = dict(reversed(list(payload.items())))

    assert canonical_json_fingerprint(payload) == canonical_json_fingerprint(reversed_payload)


@given(st.text())
def test_fingerprint_is_deterministic_for_unicode(value: str) -> None:
    payload = {"value": value}

    assert canonical_json_fingerprint(payload) == canonical_json_fingerprint(payload)

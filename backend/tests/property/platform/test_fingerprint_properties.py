from hypothesis import given
from hypothesis import strategies as st

from polyglot.platform.fingerprint import canonical_json_fingerprint

json_scalars = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53) + 1, max_value=2**53 - 1)
    | st.floats(allow_nan=False, allow_infinity=False, width=64)
    | st.text()
)
json_values = st.recursive(
    json_scalars,
    lambda children: st.lists(children, max_size=5)
    | st.dictionaries(st.text(), children, max_size=5),
    max_leaves=20,
)


@given(st.dictionaries(st.text(), json_values, max_size=10))
def test_fingerprint_is_independent_of_mapping_insertion_order(
    payload: dict[str, object],
) -> None:
    reversed_payload = dict(reversed(list(payload.items())))

    assert canonical_json_fingerprint(payload) == canonical_json_fingerprint(reversed_payload)


@given(st.text())
def test_fingerprint_is_deterministic_for_unicode(value: str) -> None:
    payload = {"value": value}

    assert canonical_json_fingerprint(payload) == canonical_json_fingerprint(payload)

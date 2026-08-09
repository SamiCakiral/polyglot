from importlib import import_module


def test_fingerprint_uses_canonical_json_key_ordering() -> None:
    fingerprint_module = import_module("polyglot.platform.fingerprint")

    first = fingerprint_module.canonical_json_fingerprint({"b": 2, "a": 1})
    second = fingerprint_module.canonical_json_fingerprint({"a": 1, "b": 2})

    assert first == "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    assert second == first


def test_fingerprint_rejects_non_json_values() -> None:
    fingerprint_module = import_module("polyglot.platform.fingerprint")

    try:
        fingerprint_module.canonical_json_fingerprint({"unsupported": {1, 2}})
    except TypeError:
        pass
    else:
        raise AssertionError("non-JSON value was accepted")


def test_canonical_json_matches_independent_rfc8785_number_vector() -> None:
    fingerprint_module = import_module("polyglot.platform.fingerprint")
    payload = {
        "numbers": [
            333333333.33333329,
            1e30,
            4.50,
            2e-3,
            0.000000000000000000000000001,
        ]
    }

    assert fingerprint_module.canonical_json_bytes(payload) == (
        b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    )


def test_json_integer_and_equivalent_float_have_one_cross_runtime_fingerprint() -> None:
    fingerprint_module = import_module("polyglot.platform.fingerprint")

    assert fingerprint_module.canonical_json_fingerprint({"value": 1}) == (
        fingerprint_module.canonical_json_fingerprint({"value": 1.0})
    )

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


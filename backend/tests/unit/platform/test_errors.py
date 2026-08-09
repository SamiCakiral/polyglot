import json
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_domain_error_accepts_every_canonical_error_code() -> None:
    errors_module = import_module("polyglot.platform.errors")
    registry = json.loads((ROOT / "contracts/registry/errors.yaml").read_text())

    mapped_codes = {code.value for code in errors_module.ErrorCode}

    assert mapped_codes == set(registry["errors"])


def test_domain_error_rejects_an_unregistered_code() -> None:
    errors_module = import_module("polyglot.platform.errors")

    try:
        errors_module.DomainError("invented_error")
    except ValueError:
        pass
    else:
        raise AssertionError("unregistered domain error was accepted")


def test_domain_error_exposes_stable_problem_metadata() -> None:
    errors_module = import_module("polyglot.platform.errors")

    error = errors_module.DomainError(
        errors_module.ErrorCode.IDEMPOTENCY_CONFLICT,
        detail="The idempotency key was already used with another request.",
    )

    assert error.http_status == 409
    assert error.retryable is False
    assert error.type_uri == "https://polyglot.example/problems/idempotency-conflict"
    assert error.message_key == "errors.idempotency_conflict"

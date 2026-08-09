from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st


def domain() -> object:
    try:
        return import_module("polyglot.modules.identity.domain")
    except ModuleNotFoundError:
        pytest.fail("identity domain is not implemented")


@given(st.text(min_size=1).filter(lambda value: value.strip() != ""))
def test_normalized_identifiers_are_idempotent(identifier: str) -> None:
    module = domain()

    try:
        normalized = module.normalize_identifier(identifier)
    except module.IdentityValidationError:
        return

    assert module.normalize_identifier(normalized) == normalized


@given(st.sampled_from(["active", "locked", "pending_deletion", "deleted"]))
def test_account_status_values_round_trip(status: str) -> None:
    module = domain()

    assert module.AccountStatus(status).value == status


def test_session_secret_derivation_is_stable_for_replay() -> None:
    module = domain()
    session_id = UUID("019fe900-0000-7000-8000-000000000006")
    secrets = module.SessionSecrets.from_key(b"z" * 32)

    assert secrets.issue(session_id) == secrets.issue(session_id)
    assert datetime.now(UTC).tzinfo is UTC

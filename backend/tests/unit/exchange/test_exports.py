from __future__ import annotations

import pytest

from polyglot.modules.lexicon.exchange.exports import (
    require_encrypted_artifact,
    validate_export_scope,
)
from polyglot.platform.errors import DomainError, ErrorCode


def test_export_scope_is_closed_boolean_and_non_empty() -> None:
    assert validate_export_scope(
        {"vocabulary_lists": True, "word_bank": True, "memory_prompts": False}
    ) == ("vocabulary_lists", "word_bank")
    for invalid in (
        {},
        {"word_bank": False},
        {"word_bank": "yes"},
        {"secrets": True},
    ):
        with pytest.raises(DomainError) as rejected:
            validate_export_scope(invalid)
        assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_export_artifact_must_attest_real_encryption_and_checksum() -> None:
    require_encrypted_artifact("aes-256-gcm/v1", "a" * 64)
    for scheme, checksum in (
        ("none", "a" * 64),
        ("plaintext", "a" * 64),
        ("aes-256-gcm/v1", "invalid"),
    ):
        with pytest.raises(DomainError) as rejected:
            require_encrypted_artifact(scheme, checksum)
        assert rejected.value.code is ErrorCode.VALIDATION_FAILED

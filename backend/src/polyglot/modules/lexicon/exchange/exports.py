from __future__ import annotations

from typing import Any

from polyglot.platform.errors import DomainError, ErrorCode

ALLOWED_EXPORT_SCOPES = frozenset(
    {
        "word_bank",
        "vocabulary_lists",
        "memory_prompts",
        "learning_history",
        "placement_history",
    }
)
FORBIDDEN_ENCRYPTION_SCHEMES = frozenset({"", "none", "plaintext", "identity"})


def validate_export_scope(scope: dict[str, Any]) -> tuple[str, ...]:
    if not scope or not set(scope) <= ALLOWED_EXPORT_SCOPES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid export scope")
    if any(not isinstance(value, bool) for value in scope.values()):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="export scope must be boolean")
    selected = tuple(sorted(name for name, enabled in scope.items() if enabled))
    if not selected:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="empty export scope")
    return selected


def require_encrypted_artifact(encryption_scheme: str, checksum_sha256: str) -> None:
    if encryption_scheme.strip().casefold() in FORBIDDEN_ENCRYPTION_SCHEMES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="export encryption is required")
    if len(checksum_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in checksum_sha256
    ):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid artifact checksum")

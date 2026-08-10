from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint

PREDICATES = frozenset(
    {
        "sense_id_in",
        "tag_in",
        "encountered_between",
        "declared_familiarity_is",
        "learning_preference_is",
        "has_due_prompt",
        "provenance_in",
    }
)
OPERATORS = frozenset({"all", "any", "not"})
TARGET_TYPES = frozenset(
    {
        "module_revision",
        "module_day_revision",
        "session_plan",
        "exercise_definition_revision",
    }
)


@dataclass(frozen=True, slots=True)
class DynamicListPolicy:
    max_depth: int = 8
    max_predicates: int = 64
    max_values: int = 100

    def validate(self, query: dict[str, Any]) -> None:
        predicates = 0
        stack: list[tuple[Any, int]] = [(query, 1)]
        while stack:
            node, depth = stack.pop()
            if depth > self.max_depth or not isinstance(node, dict) or len(node) != 1:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            key, value = next(iter(node.items()))
            if key in OPERATORS:
                if key == "not":
                    if not isinstance(value, dict):
                        raise DomainError(ErrorCode.VALIDATION_FAILED)
                    children = [value]
                elif not isinstance(value, list) or not value:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                else:
                    children = value
                stack.extend((child, depth + 1) for child in children)
            elif key in PREDICATES:
                predicates += 1
                if key == "has_due_prompt":
                    valid = isinstance(value, bool)
                elif key == "encountered_between":
                    valid = isinstance(value, list) and len(value) == 2
                else:
                    valid = (
                        isinstance(value, list)
                        and 1 <= len(value) <= self.max_values
                    )
                if not valid:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
            else:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            if predicates > self.max_predicates:
                raise DomainError(ErrorCode.VALIDATION_FAILED)


@dataclass(frozen=True, slots=True)
class ListDefinition:
    list_type: str
    query_definition: dict[str, Any] | None

    @classmethod
    def create(
        cls,
        list_type: str,
        query: dict[str, Any] | None,
        *,
        actor_roles: tuple[str, ...],
    ) -> ListDefinition:
        if list_type not in {"manual", "dynamic", "editorial"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if list_type == "dynamic":
            if query is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            DynamicListPolicy().validate(query)
        elif query is not None:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if list_type == "editorial" and not {"author", "reviewer", "admin"} & set(actor_roles):
            raise DomainError(ErrorCode.FORBIDDEN)
        return cls(list_type, query)


class ListStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ArchivedList:
    status: ListStatus
    version: int


def archive_list(status: ListStatus, *, version: int) -> ArchivedList:
    if status is not ListStatus.ACTIVE:
        raise DomainError(ErrorCode.INVALID_TRANSITION)
    return ArchivedList(ListStatus.ARCHIVED, version + 1)


def snapshot_checksum(
    list_id: UUID,
    members: tuple[UUID, ...],
    *,
    ordered: bool,
) -> str:
    values = members if ordered else tuple(sorted(members))
    return canonical_json_fingerprint(
        {
            "list_id": str(list_id),
            "ordered": ordered,
            "members": [str(value) for value in values],
        }
    )


@dataclass(frozen=True, slots=True)
class ListAssociation:
    target_type: str
    target_id: UUID
    role: str

    @classmethod
    def create(cls, *, target_type: str, target_id: UUID, role: str) -> ListAssociation:
        if target_type not in TARGET_TYPES or not role.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        return cls(target_type, target_id, role)

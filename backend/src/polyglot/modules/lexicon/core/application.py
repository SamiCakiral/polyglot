from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class EncounterFact:
    encounter_id: UUID
    profile_id: UUID
    mention_id: UUID
    exact_surface: str
    context_fingerprint: str
    context_private: str | None
    occurred_at: datetime
    context_deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.context_fingerprint) != 64:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid context fingerprint")
        if self.occurred_at.tzinfo is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="occurred_at must be aware")
        if self.context_deleted_at is not None:
            if self.context_private is not None or self.context_deleted_at < self.occurred_at:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid context redaction")


@dataclass(frozen=True, slots=True)
class ResolutionFact:
    resolution_id: UUID
    profile_id: UUID
    mention_id: UUID
    sense_id: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="created_at must be aware")


@dataclass(frozen=True, slots=True)
class LexiconProjection:
    encounters: Mapping[UUID, EncounterFact]
    current_sense_by_mention: Mapping[UUID, UUID]
    unresolved_mentions: tuple[UUID, ...]


class LexiconProjector:
    @staticmethod
    def rebuild(facts: tuple[EncounterFact | ResolutionFact, ...]) -> LexiconProjection:
        encounters: dict[UUID, EncounterFact] = {}
        resolutions: dict[UUID, ResolutionFact] = {}
        for fact in sorted(
            facts,
            key=lambda item: (
                item.occurred_at if isinstance(item, EncounterFact) else item.created_at,
                item.encounter_id if isinstance(item, EncounterFact) else item.resolution_id,
            ),
        ):
            if isinstance(fact, EncounterFact):
                existing = encounters.get(fact.encounter_id)
                if existing is not None and existing != fact:
                    raise DomainError(
                        ErrorCode.IDENTITY_CONFLICT,
                        detail="encounter identifier has conflicting immutable facts",
                    )
                encounters[fact.encounter_id] = fact
                continue
            current = resolutions.get(fact.mention_id)
            if current is None or (fact.created_at, fact.resolution_id) > (
                current.created_at,
                current.resolution_id,
            ):
                resolutions[fact.mention_id] = fact

        mention_ids = {item.mention_id for item in encounters.values()}
        current_senses = {
            mention_id: resolution.sense_id
            for mention_id, resolution in resolutions.items()
            if mention_id in mention_ids
        }
        return LexiconProjection(
            encounters=MappingProxyType(dict(sorted(encounters.items()))),
            current_sense_by_mention=MappingProxyType(dict(sorted(current_senses.items()))),
            unresolved_mentions=tuple(sorted(mention_ids - current_senses.keys())),
        )


def redact_private_context(fact: EncounterFact, *, deleted_at: datetime) -> EncounterFact:
    if deleted_at.tzinfo is None or deleted_at < fact.occurred_at:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid deletion timestamp")
    if fact.context_deleted_at is not None:
        return fact
    return replace(fact, context_private=None, context_deleted_at=deleted_at)


class IdempotencyLedger:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[str, UUID]] = {}

    @property
    def effect_count(self) -> int:
        return len(self._entries)

    def apply(
        self,
        command_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        resource_id: UUID,
    ) -> UUID:
        key = (command_name, idempotency_key)
        existing = self._entries.get(key)
        if existing is not None:
            existing_fingerprint, existing_resource_id = existing
            if existing_fingerprint != request_fingerprint:
                raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return existing_resource_id
        self._entries[key] = (request_fingerprint, resource_id)
        return resource_id


@dataclass(frozen=True, slots=True)
class CaptureLexicalGap:
    profile_id: UUID
    attempt_id: UUID
    intended_support_text: str
    minimal_context: str | None
    support_language_tag: str

    def __post_init__(self) -> None:
        if not self.intended_support_text.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="gap intention is required")
        if len(self.intended_support_text) > 500 or (
            self.minimal_context is not None and len(self.minimal_context) > 2_000
        ):
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)

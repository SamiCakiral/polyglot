from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from polyglot.modules.placement.domain import ScoringKind
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class PublishedPlacementVariant:
    variant_revision_id: UUID
    payload: dict[str, JsonValue]
    answer_key: dict[str, JsonValue] | None
    media_required: bool = False
    checksum: str = ""


@dataclass(frozen=True, slots=True)
class PublishedPlacementBlueprint:
    blueprint_revision_id: UUID
    primitive_revision_id: UUID
    primary_skill_ref: str
    secondary_skill_refs: tuple[str, ...]
    editorial_difficulty: int
    expected_duration_seconds: int
    checker_kind: ScoringKind
    variant_pool_id: str
    variants: tuple[PublishedPlacementVariant, ...]
    prerequisite_skill_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishedPlacementPack:
    pack_revision_id: UUID
    blueprints: tuple[PublishedPlacementBlueprint, ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


class PlacementCatalogueReader(Protocol):
    async def read_pack(self, pack_revision_id: UUID) -> PublishedPlacementPack | None: ...


def validate_pack(pack: PublishedPlacementPack) -> ValidationReport:
    errors: list[str] = []
    checksums: set[str] = set()
    skill_refs = {item.primary_skill_ref for item in pack.blueprints}
    for blueprint in pack.blueprints:
        if not blueprint.primary_skill_ref:
            errors.append("primary_skill_required")
        if not 0 <= blueprint.editorial_difficulty <= 8:
            errors.append("difficulty_out_of_range")
        for prerequisite in blueprint.prerequisite_skill_refs:
            if prerequisite not in skill_refs:
                errors.append("unresolved_prerequisite")
        for variant in blueprint.variants:
            if blueprint.primary_skill_ref == "listening" and not variant.media_required:
                errors.append("listening_media_required")
            if variant.checksum and variant.checksum in checksums:
                errors.append("duplicate_variant_checksum")
            checksums.add(variant.checksum)
            if blueprint.checker_kind is ScoringKind.STRUCTURED_LM and variant.answer_key is None:
                errors.append("rubric_required")
    return ValidationReport(tuple(dict.fromkeys(errors)))

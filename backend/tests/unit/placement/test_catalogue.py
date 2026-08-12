from uuid import UUID

from polyglot.modules.placement.catalogue import (
    PublishedPlacementBlueprint,
    PublishedPlacementPack,
    PublishedPlacementVariant,
    validate_pack,
)
from polyglot.modules.placement.domain import ScoringKind


def _id(value: int) -> UUID:
    return UUID(f"0194f7c0-7b00-7000-8000-{value:012d}")


def test_listening_without_media_is_rejected() -> None:
    blueprint = PublishedPlacementBlueprint(
        _id(1), _id(2), "listening", (), 2, 30, ScoringKind.DETERMINISTIC, "pool-a",
        (PublishedPlacementVariant(_id(3), {"prompt": "?"}, {"value": "a"}),),
    )
    report = validate_pack(PublishedPlacementPack(_id(4), (blueprint,)))
    assert "listening_media_required" in report.errors

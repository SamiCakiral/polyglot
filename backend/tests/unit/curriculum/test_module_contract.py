from __future__ import annotations

from uuid import UUID

import pytest

from polyglot.modules.curriculum import (
    ArcType,
    CurriculumError,
    LearningModuleRevision,
    ModuleDay,
    ModuleStatus,
)


def uid(suffix: int) -> UUID:
    return UUID(f"019fe110-0000-7000-8000-{suffix:012d}")


def day(ordinal: int, *, arc: ArcType = ArcType.DISCOVERY) -> ModuleDay:
    return ModuleDay(
        module_day_id=uid(100 + ordinal),
        ordinal=ordinal,
        arc_type=arc,
        objective_codes=(f"objective-{ordinal}",),
        modality_objectives=(("written_production", f"produce-{ordinal}"),),
        primary_target_refs=(f"skill:{ordinal}",),
        encountered_target_refs=(f"skill:{ordinal}",),
        output_target_refs=(f"skill:{ordinal}",),
        minimum_useful_minutes=10,
        novelty_budget=4.0 if arc is not ArcType.TRANSFER else 0.0,
        required_block_roles=("explanation", "practice", "production"),
    )


def revision(*, days: tuple[ModuleDay, ...]) -> LearningModuleRevision:
    return LearningModuleRevision(
        module_revision_id=uid(1),
        module_id=uid(2),
        revision_no=1,
        status=ModuleStatus.DRAFT,
        pack_revision_id=uid(3),
        target_variety_id=uid(4),
        support_variety_ids=(uid(5),),
        primary_intention="complete a first autonomous exchange",
        final_mission_revision_id=uid(6),
        entry_profile_codes=("P-ABS", "P-FAUX", "P-INT"),
        nominal_days=len(days),
        max_days=max(3, len(days)),
        prerequisite_skill_revision_ids=(uid(7),),
        target_skill_revision_ids=tuple(uid(20 + item.ordinal) for item in days),
        exit_policy_revision_id=uid(8),
        recall_policy_revision_id=uid(9),
        provenance_id="prov:pilot-it",
        rights_refs=("rights:cc-by-4.0",),
        validator_set_revision_id=uid(10),
        schema_version=1,
        compatibility_range=">=1,<2",
        days=days,
    )


def test_module_revision_requires_three_to_thirty_contiguous_days() -> None:
    with pytest.raises(CurriculumError, match="module_duration_out_of_range"):
        revision(days=(day(1), day(2)))

    with pytest.raises(CurriculumError, match="module_day_ordinal_gap"):
        revision(days=(day(1), day(3), day(4)))


def test_module_revision_is_deeply_immutable_and_has_stable_checksum() -> None:
    source = [day(1), day(2, arc=ArcType.GUIDED_USE), day(3, arc=ArcType.TRANSFER)]
    module = revision(days=tuple(source))
    checksum = module.payload_checksum

    source.append(day(4))

    assert tuple(item.ordinal for item in module.days) == (1, 2, 3)
    assert module.payload_checksum == checksum
    with pytest.raises((AttributeError, TypeError)):
        module.days[0].objective_codes += ("mutated",)  # type: ignore[misc]


def test_transfer_day_cannot_spend_novelty() -> None:
    with pytest.raises(CurriculumError, match="module_novelty_budget_exceeded"):
        day(3, arc=ArcType.TRANSFER).__class__(
            **{**day(3, arc=ArcType.TRANSFER).as_dict(), "novelty_budget": 0.5}
        )

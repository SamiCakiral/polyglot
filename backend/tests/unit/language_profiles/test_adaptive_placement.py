from uuid import UUID

from polyglot.modules.language_profiles.adaptive_placement import (
    AdaptivePlacementPlanner,
    PlacementCandidate,
    PlacementObservation,
)
from polyglot.modules.language_profiles.onboarding import EntryPath, SkillDimension


def candidate(
    suffix: int,
    dimension: SkillDimension,
    difficulty: int,
    *,
    requires_script: bool = False,
    foundation: bool = False,
) -> PlacementCandidate:
    return PlacementCandidate(
        item_revision_id=UUID(f"019f0000-0000-7000-8000-{suffix:012d}"),
        dimension=dimension,
        difficulty=difficulty,
        estimated_seconds=55,
        requires_script=requires_script,
        is_foundation=foundation,
    )


def test_entry_path_changes_initial_difficulty() -> None:
    candidates = tuple(
        candidate(index, SkillDimension.READING, difficulty)
        for index, difficulty in enumerate((1, 2, 4), start=1)
    )

    beginner = AdaptivePlacementPlanner(EntryPath.COMPLETE_BEGINNER).next_item(candidates, ())
    advanced = AdaptivePlacementPlanner(EntryPath.ADVANCED).next_item(candidates, ())

    assert beginner is not None and beginner.difficulty == 1
    assert advanced is not None and advanced.difficulty == 4


def test_inaccessible_script_task_is_replaced_by_foundation() -> None:
    blocked = candidate(
        10,
        SkillDimension.READING,
        3,
        requires_script=True,
    )
    fallback = candidate(
        11,
        SkillDimension.SCRIPT,
        1,
        foundation=True,
    )
    history = (
        PlacementObservation(
            item_revision_id=UUID("019f0000-0000-7000-8000-000000000012"),
            dimension=SkillDimension.SCRIPT,
            score=0.1,
            confidence=1.0,
            elapsed_seconds=50,
        ),
    )

    selected = AdaptivePlacementPlanner(EntryPath.ALREADY_STARTED).next_item(
        (blocked, fallback), history
    )

    assert selected == fallback


def test_planner_stops_after_ten_minutes_and_never_repeats_an_item() -> None:
    used = candidate(20, SkillDimension.VOCABULARY, 2)
    fresh = candidate(21, SkillDimension.VOCABULARY, 2)
    history = tuple(
        PlacementObservation(
            item_revision_id=(
                used.item_revision_id
                if index == 0
                else UUID(f"019f0000-0000-7000-8000-{100 + index:012d}")
            ),
            dimension=SkillDimension.VOCABULARY,
            score=0.7,
            confidence=0.8,
            elapsed_seconds=100,
        )
        for index in range(6)
    )
    planner = AdaptivePlacementPlanner(EntryPath.ALREADY_STARTED)

    assert planner.next_item((used, fresh), history) is None
    assert planner.next_item((used, fresh), history[:1]) == fresh

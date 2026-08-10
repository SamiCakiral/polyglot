import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import seed
from zoneinfo import ZoneInfo

import fsrs
import pytest

ROOT = Path(__file__).resolve().parents[4]
START = datetime(2026, 1, 5, 9, tzinfo=UTC)


def _review(
    scheduler: fsrs.Scheduler,
    card: fsrs.Card,
    at: datetime,
    fuzz_seed: int,
) -> fsrs.Card:
    seed(fuzz_seed)
    return scheduler.review_card(card, fsrs.Rating.Good, at, 1_200)[0]


def _snapshot(card: fsrs.Card) -> dict[str, int | str | None]:
    return {
        "difficulty": str(card.difficulty),
        "due": card.due.isoformat(),
        "last_review": None if card.last_review is None else card.last_review.isoformat(),
        "stability": str(card.stability),
        "state": card.state.value,
        "step": card.step,
    }


def test_early_late_and_timezone_histories_match_frozen_goldens() -> None:
    scheduler = fsrs.Scheduler(desired_retention=0.9, enable_fuzzing=True)
    base = fsrs.Card(card_id=201, due=START)
    base = _review(scheduler, base, START, 9_000)
    base = _review(scheduler, base, START + timedelta(minutes=10), 9_001)
    assert base.due == datetime(2026, 1, 7, 9, 10, tzinfo=UTC)

    early_at = START + timedelta(days=1, minutes=10)
    late_at = START + timedelta(days=20, minutes=10)
    early = _review(scheduler, deepcopy(base), early_at, 9_002)
    late = _review(scheduler, deepcopy(base), late_at, 9_002)
    assert early_at < base.due < late_at

    rome_at = datetime(2026, 3, 29, 9, tzinfo=ZoneInfo("Europe/Rome"))
    with pytest.raises(ValueError, match="UTC"):
        _review(scheduler, fsrs.Card(card_id=202, due=rome_at), rome_at, 9_010)
    normalized_at = rome_at.astimezone(UTC)
    timezone_card = _review(
        scheduler,
        fsrs.Card(card_id=202, due=normalized_at),
        normalized_at,
        9_010,
    )

    actual = {
        "early": _snapshot(early),
        "late": _snapshot(late),
        "timezone": {
            "input": rome_at.isoformat(),
            "normalized": normalized_at.isoformat(),
            "card": _snapshot(timezone_card),
        },
    }
    evidence = json.loads((ROOT / "docs/evidence/W07/spk-fsrs-raw.json").read_text())

    assert actual == evidence["temporal_cases"]

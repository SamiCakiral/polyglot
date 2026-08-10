from datetime import UTC, datetime, timedelta
from random import seed

import fsrs

START = datetime(2026, 1, 5, 9, tzinfo=UTC)


def _review(
    scheduler: fsrs.Scheduler,
    card: fsrs.Card,
    rating: fsrs.Rating,
    at: datetime,
    fuzz_seed: int,
) -> fsrs.Card:
    seed(fuzz_seed)
    return scheduler.review_card(card, rating, at, 1_200)[0]


def test_golden_history_and_two_directions_are_stable() -> None:
    scheduler = fsrs.Scheduler(desired_retention=0.9, enable_fuzzing=True)
    ratings = (fsrs.Rating.Again, fsrs.Rating.Good, fsrs.Rating.Good, fsrs.Rating.Easy)
    times = (
        START,
        START + timedelta(minutes=10),
        START + timedelta(days=1),
        START + timedelta(days=8),
    )
    results = []

    for card_id in (101, 102):
        card = fsrs.Card(card_id=card_id, due=START)
        for index, (rating, at) in enumerate(zip(ratings, times, strict=True)):
            card = _review(scheduler, card, rating, at, 4_242 + index)
        results.append(card)

    assert results[0].due == datetime(2026, 1, 20, 9, tzinfo=UTC)
    assert results[0].state is fsrs.State.Review
    assert results[0].difficulty == results[1].difficulty == 5.170190465277389
    assert results[0].stability == results[1].stability == 7.48411760536693
    assert results[0].card_id != results[1].card_id


def test_same_day_reset_merge_and_utc_provider_rules_are_explicit() -> None:
    scheduler = fsrs.Scheduler(desired_retention=0.9, enable_fuzzing=True)
    card = fsrs.Card(card_id=104, due=START)
    card = _review(scheduler, card, fsrs.Rating.Good, START, 6_000)
    card = _review(scheduler, card, fsrs.Rating.Good, START + timedelta(minutes=5), 6_001)

    assert card.due == datetime(2026, 1, 7, 9, 5, tzinfo=UTC)
    reset = fsrs.Card(card_id=104, due=START + timedelta(days=2))
    assert reset.stability is None and reset.last_review is None

    logs = [
        fsrs.ReviewLog(107, fsrs.Rating.Again, START, 1_000),
        fsrs.ReviewLog(107, fsrs.Rating.Again, START + timedelta(minutes=1), 1_000),
        fsrs.ReviewLog(107, fsrs.Rating.Good, START + timedelta(minutes=10), 1_000),
        fsrs.ReviewLog(107, fsrs.Rating.Good, START + timedelta(minutes=11), 1_000),
    ]
    seed(7_070)
    merged = scheduler.reschedule_card(fsrs.Card(card_id=107, due=START), logs)
    assert merged.last_review == START + timedelta(minutes=11)
    assert merged.due == datetime(2026, 1, 6, 9, 11, tzinfo=UTC)

    try:
        scheduler.review_card(fsrs.Card(), fsrs.Rating.Good, START.replace(tzinfo=None))
    except ValueError as error:
        assert "UTC" in str(error)
    else:
        raise AssertionError("fsrs must reject naive datetimes")

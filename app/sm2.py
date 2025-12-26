"""
SM-2 (SuperMemo 2) Spaced Repetition Algorithm

This is the same algorithm used by Anki for scheduling flashcard reviews.
Based on the original SM-2 algorithm by Piotr Wozniak.

Quality ratings:
    0 - Complete blackout, no recall at all
    1 - Incorrect, but upon seeing the answer, remembered
    2 - Incorrect, but the answer seemed easy to recall
    3 - Correct, but with serious difficulty
    4 - Correct, after some hesitation
    5 - Perfect response, instant recall
"""

from datetime import datetime, timedelta


def calculate_sm2(quality: int, easiness: float, interval: int, repetitions: int) -> tuple:
    """
    Calculate the next review parameters using the SM-2 algorithm.
    
    Args:
        quality: Response quality (0-5)
        easiness: Current easiness factor (E-Factor), minimum 1.3
        interval: Current interval in days
        repetitions: Number of successful repetitions
    
    Returns:
        tuple: (new_easiness, new_interval, new_repetitions, next_review_date)
    """
    # Validate quality
    quality = max(0, min(5, quality))
    
    # If quality < 3, reset the card (failed recall)
    if quality < 3:
        new_repetitions = 0
        new_interval = 1
        new_easiness = easiness  # Keep the same easiness
    else:
        # Calculate new easiness factor
        # EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
        new_easiness = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_easiness = max(1.3, new_easiness)  # Minimum easiness is 1.3
        
        # Calculate new interval
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_easiness)
        
        new_repetitions = repetitions + 1
    
    # Calculate next review date
    next_review = datetime.utcnow() + timedelta(days=new_interval)
    
    return (new_easiness, new_interval, new_repetitions, next_review)


def get_review_buttons(card) -> list:
    """
    Get the review button options with their labels and intervals.
    Similar to Anki's "Again", "Hard", "Good", "Easy" buttons.
    
    Returns a list of dicts with:
        - quality: The quality rating (0-5)
        - label: Button label in French
        - interval: Expected interval after pressing
    """
    easiness = card.easiness
    interval = card.interval
    repetitions = card.repetitions
    
    buttons = []
    
    # Again (quality = 1) - Reset
    _, again_interval, _, _ = calculate_sm2(1, easiness, interval, repetitions)
    buttons.append({
        'quality': 1,
        'label': 'À revoir',
        'interval': again_interval,
        'interval_label': format_interval(again_interval)
    })
    
    # Hard (quality = 3)
    _, hard_interval, _, _ = calculate_sm2(3, easiness, interval, repetitions)
    buttons.append({
        'quality': 3,
        'label': 'Difficile',
        'interval': hard_interval,
        'interval_label': format_interval(hard_interval)
    })
    
    # Good (quality = 4)
    _, good_interval, _, _ = calculate_sm2(4, easiness, interval, repetitions)
    buttons.append({
        'quality': 4,
        'label': 'Bien',
        'interval': good_interval,
        'interval_label': format_interval(good_interval)
    })
    
    # Easy (quality = 5)
    _, easy_interval, _, _ = calculate_sm2(5, easiness, interval, repetitions)
    buttons.append({
        'quality': 5,
        'label': 'Facile',
        'interval': easy_interval,
        'interval_label': format_interval(easy_interval)
    })
    
    return buttons


def format_interval(days: int) -> str:
    """Format interval in days to a human-readable string in French."""
    if days < 1:
        return "< 1 jour"
    elif days == 1:
        return "1 jour"
    elif days < 30:
        return f"{days} jours"
    elif days < 365:
        months = days // 30
        return f"{months} mois" if months > 1 else "1 mois"
    else:
        years = days // 365
        return f"{years} ans" if years > 1 else "1 an"

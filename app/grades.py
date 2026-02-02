"""
Grade System for Flashcards

Converts SM-2 algorithm values (repetitions, interval, easiness) into
letter grades (E to A+) for better visualization of mastery level.

Grade Scale (based primarily on successful repetitions):
    E   - Never reviewed (0 reps)
    E+  - First correct answer (1 rep)
    D   - Learning started (2 reps)
    D+  - Making progress (3 reps)
    C   - Getting familiar (4 reps)
    C+  - Good recall (5 reps)
    B   - Strong recall (6 reps)
    B+  - Very strong (7 reps)
    A   - Excellent (8 reps)
    A+  - Mastered (9+ reps)
"""

from typing import Tuple, Dict, List, Optional
from datetime import datetime


# Grade definitions: (grade, min_reps, min_interval, color, description)
# Simplified: mainly based on repetitions, interval as secondary check
GRADES = [
    ('A+', 9, 0,  '#10b981', 'Maîtrisé'),      # 9+ correct answers
    ('A',  8, 0,  '#22c55e', 'Excellent'),     # 8 correct answers
    ('B+', 7, 0,  '#84cc16', 'Très bien'),     # 7 correct answers
    ('B',  6, 0,  '#a3e635', 'Bien'),          # 6 correct answers
    ('C+', 5, 0,  '#fbbf24', 'Correct'),       # 5 correct answers
    ('C',  4, 0,  '#f59e0b', 'Moyen'),         # 4 correct answers
    ('D+', 3, 0,  '#fb923c', 'En cours'),      # 3 correct answers
    ('D',  2, 0,  '#f97316', 'Débutant'),      # 2 correct answers
    ('E+', 1, 0,  '#ef4444', 'Vu 1x'),         # 1 correct answer
    ('E',  0, 0,  '#dc2626', 'Nouveau'),       # Never reviewed
]

# For quick lookups
GRADE_INFO = {g[0]: {'min_reps': g[1], 'min_interval': g[2], 'color': g[3], 'description': g[4]} for g in GRADES}
GRADE_ORDER = [g[0] for g in GRADES]  # A+ first (best)


def calculate_grade(repetitions: int, interval: int, easiness: float = 2.5) -> str:
    """
    Calculate a letter grade based on SM-2 values.
    
    Args:
        repetitions: Number of successful repetitions
        interval: Current interval in days
        easiness: Easiness factor (used as tiebreaker)
    
    Returns:
        Letter grade string (E to A+)
    """
    # Go through grades from best to worst
    for grade, min_reps, min_interval, _, _ in GRADES:
        if repetitions >= min_reps and interval >= min_interval:
            return grade
    
    # Default to E if nothing matches
    return 'E'


def get_grade_color(grade: str) -> str:
    """Get the color for a grade."""
    return GRADE_INFO.get(grade, {}).get('color', '#6b7280')


def get_grade_description(grade: str) -> str:
    """Get the description for a grade."""
    return GRADE_INFO.get(grade, {}).get('description', 'Inconnu')


def get_grade_info(grade: str) -> Dict:
    """Get full info for a grade."""
    info = GRADE_INFO.get(grade, {})
    return {
        'grade': grade,
        'color': info.get('color', '#6b7280'),
        'description': info.get('description', 'Inconnu'),
        'min_reps': info.get('min_reps', 0),
        'min_interval': info.get('min_interval', 0)
    }


def is_high_grade(grade: str) -> bool:
    """Check if a grade is considered 'high' (A or A+)."""
    return grade in ('A', 'A+')


def is_passing_grade(grade: str) -> bool:
    """Check if a grade is considered 'passing' (C or above)."""
    return grade in ('A+', 'A', 'B+', 'B', 'C+', 'C')


def grade_to_numeric(grade: str) -> float:
    """Convert grade to numeric value for averaging (0-10 scale)."""
    grade_values = {
        'A+': 10, 'A': 9, 'B+': 8, 'B': 7,
        'C+': 6, 'C': 5, 'D+': 4, 'D': 3,
        'E+': 2, 'E': 1
    }
    return grade_values.get(grade, 0)


def numeric_to_grade(value: float) -> str:
    """Convert numeric value back to grade."""
    if value >= 9.5: return 'A+'
    if value >= 8.5: return 'A'
    if value >= 7.5: return 'B+'
    if value >= 6.5: return 'B'
    if value >= 5.5: return 'C+'
    if value >= 4.5: return 'C'
    if value >= 3.5: return 'D+'
    if value >= 2.5: return 'D'
    if value >= 1.5: return 'E+'
    return 'E'


def calculate_average_grade(grades: List[str]) -> Tuple[str, float]:
    """
    Calculate average grade from a list of grades.
    
    Returns:
        Tuple of (average_grade_letter, average_numeric_value)
    """
    if not grades:
        return 'E', 1.0
    
    numeric_values = [grade_to_numeric(g) for g in grades]
    avg = sum(numeric_values) / len(numeric_values)
    return numeric_to_grade(avg), avg


def get_grade_distribution(cards, direction: str = None) -> Dict[str, int]:
    """
    Get distribution of grades for a list of cards.
    
    Args:
        cards: List of Card objects
        direction: 'fb', 'bf', or None for legacy
    
    Returns:
        Dict mapping grade to count
    """
    distribution = {g[0]: 0 for g in GRADES}
    
    for card in cards:
        if direction == 'fb':
            reps = card.fb_repetitions
            interval = card.fb_interval
        elif direction == 'bf':
            reps = card.bf_repetitions
            interval = card.bf_interval
        else:
            reps = card.repetitions
            interval = card.interval
        
        grade = calculate_grade(reps, interval)
        distribution[grade] += 1
    
    return distribution


def get_cards_by_grade_filter(cards, min_grade: str = None, max_grade: str = None, 
                               direction: str = None) -> List:
    """
    Filter cards by grade range.
    
    Args:
        cards: List of Card objects
        min_grade: Minimum grade (inclusive), e.g., 'E'
        max_grade: Maximum grade (inclusive), e.g., 'B'
        direction: 'fb', 'bf', or None for legacy
    
    Returns:
        Filtered list of cards
    """
    if min_grade is None and max_grade is None:
        return list(cards)
    
    min_numeric = grade_to_numeric(min_grade) if min_grade else 0
    max_numeric = grade_to_numeric(max_grade) if max_grade else 10
    
    filtered = []
    for card in cards:
        if direction == 'fb':
            reps = card.fb_repetitions
            interval = card.fb_interval
        elif direction == 'bf':
            reps = card.bf_repetitions
            interval = card.bf_interval
        else:
            reps = card.repetitions
            interval = card.interval
        
        grade = calculate_grade(reps, interval)
        grade_numeric = grade_to_numeric(grade)
        
        if min_numeric <= grade_numeric <= max_numeric:
            filtered.append(card)
    
    return filtered


def calculate_deck_progress(cards, direction: str = None) -> Dict:
    """
    Calculate overall progress for a deck based on grades.
    
    Returns dict with:
        - average_grade: Letter grade
        - average_score: Numeric score (1-10)
        - progress_percent: 0-100% based on grades
        - grade_distribution: Dict of grade -> count
        - passing_count: Cards with C or above
        - mastered_count: Cards with A or A+
    """
    if not cards:
        return {
            'average_grade': 'E',
            'average_score': 1.0,
            'progress_percent': 0,
            'grade_distribution': {g[0]: 0 for g in GRADES},
            'passing_count': 0,
            'mastered_count': 0,
            'total_cards': 0
        }
    
    grades = []
    for card in cards:
        if direction == 'fb':
            reps = card.fb_repetitions
            interval = card.fb_interval
        elif direction == 'bf':
            reps = card.bf_repetitions
            interval = card.bf_interval
        else:
            reps = card.repetitions
            interval = card.interval
        
        grades.append(calculate_grade(reps, interval))
    
    avg_grade, avg_score = calculate_average_grade(grades)
    distribution = {g[0]: 0 for g in GRADES}
    for g in grades:
        distribution[g] += 1
    
    passing = sum(1 for g in grades if is_passing_grade(g))
    mastered = sum(1 for g in grades if is_high_grade(g))
    
    # Progress: 0-100% where E=0%, A+=100%
    progress = ((avg_score - 1) / 9) * 100
    
    return {
        'average_grade': avg_grade,
        'average_score': round(avg_score, 2),
        'progress_percent': round(progress, 1),
        'grade_distribution': distribution,
        'passing_count': passing,
        'mastered_count': mastered,
        'total_cards': len(cards)
    }

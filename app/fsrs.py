"""
FSRS-4.5 (Free Spaced Repetition Scheduler) Algorithm

Based on the open-spaced-repetition project.
https://github.com/open-spaced-repetition/fsrs4anki

Memory State Variables:
- D (Difficulty): How hard is the card (1-10)
- S (Stability): Days until R drops to 90% (0.1 - 36500)
- R (Retrievability): Probability of recall NOW (0-1)

Grades:
- 1 = Again (forgot)
- 2 = Hard
- 3 = Good  
- 4 = Easy
"""

import math
from datetime import datetime, timedelta
from typing import Tuple, Dict

# FSRS-4.5 Default Parameters
W = [
    0.4872,   # w0: S_0(1) - initial stability for Again
    1.4003,   # w1: S_0(2) - initial stability for Hard  
    3.7145,   # w2: S_0(3) - initial stability for Good
    13.8206,  # w3: S_0(4) - initial stability for Easy
    5.1618,   # w4: D_0(3) - initial difficulty for Good rating
    1.2298,   # w5: D_0 grade multiplier
    0.8975,   # w6: D update factor
    0.031,    # w7: D mean reversion factor
    1.6474,   # w8: S increase base
    0.1367,   # w9: S decay rate
    1.0461,   # w10: R influence on S increase
    2.1072,   # w11: S fail base
    0.0793,   # w12: S fail D influence
    0.3246,   # w13: S fail S influence
    1.587,    # w14: S fail R influence
    0.2272,   # w15: hard penalty
    2.8755,   # w16: easy bonus
]

# Forgetting curve parameters (FSRS-4.5)
DECAY = -0.5
FACTOR = 19 / 81  # ≈ 0.2346


def calculate_retrievability(t: float, S: float) -> float:
    """
    Calculate retrievability (probability of recall) at time t.
    
    Args:
        t: Days since last review
        S: Current stability (days until R drops to 90%)
    
    Returns:
        Retrievability between 0 and 1
    """
    if S <= 0:
        return 0.0
    if t <= 0:
        return 1.0
    
    # R(t,S) = (1 + FACTOR * t / S) ^ DECAY
    R = math.pow(1 + FACTOR * t / S, DECAY)
    return max(0.0, min(1.0, R))


def calculate_initial_stability(grade: int) -> float:
    """
    Calculate initial stability for a new card after first review.
    
    Args:
        grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    Returns:
        Initial stability in days
    """
    grade = max(1, min(4, grade))
    return W[grade - 1]


def calculate_initial_difficulty(grade: int) -> float:
    """
    Calculate initial difficulty for a new card after first review.
    
    Args:
        grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    Returns:
        Initial difficulty (1-10)
    """
    # D_0(G) = w[4] - (G-3) * w[5]
    D = W[4] - (grade - 3) * W[5]
    return max(1.0, min(10.0, D))


def calculate_new_difficulty(D: float, grade: int) -> float:
    """
    Calculate new difficulty after a review.
    
    Args:
        D: Current difficulty
        grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    Returns:
        New difficulty (1-10)
    """
    # Linear damping: ΔD = -w[6] * (G - 3)
    delta_D = -W[6] * (grade - 3)
    
    # Apply with linear damping toward edges
    D_prime = D + delta_D * ((10 - D) / 9)
    
    # Mean reversion toward D_0(3)
    D_0_3 = W[4]  # D_0(3) = w[4]
    D_new = W[7] * D_0_3 + (1 - W[7]) * D_prime
    
    return max(1.0, min(10.0, D_new))


def calculate_new_stability(D: float, S: float, R: float, grade: int) -> float:
    """
    Calculate new stability after a review.
    
    Args:
        D: Current difficulty
        S: Current stability
        R: Current retrievability (at time of review)
        grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    Returns:
        New stability in days
    """
    if grade == 1:
        # Failed review - stability decreases significantly
        # S' = w[11] * D^(-w[12]) * ((S+1)^w[13] - 1) * e^(w[14]*(1-R))
        S_new = (W[11] * 
                 math.pow(D, -W[12]) * 
                 (math.pow(S + 1, W[13]) - 1) * 
                 math.exp(W[14] * (1 - R)))
    else:
        # Successful review - stability increases
        # For same-day reviews (R close to 1), ensure minimum increase
        # This allows "cramming" to still show progress
        
        effective_R = min(R, 0.95)  # Cap R at 95% for calculation
        
        # SInc = e^(w[8]) * (11-D) * S^(-w[9]) * (e^(w[10]*(1-R)) - 1)
        S_inc = (math.exp(W[8]) * 
                 (11 - D) * 
                 math.pow(S, -W[9]) * 
                 (math.exp(W[10] * (1 - effective_R)) - 1))
        
        # Minimum increase of 5% for same-day reviews
        S_inc = max(S_inc, 0.05)
        
        # Apply hard penalty or easy bonus
        if grade == 2:  # Hard
            S_inc *= W[15]
        elif grade == 4:  # Easy
            S_inc *= W[16]
        
        S_new = S * (1 + S_inc)
    
    # Clamp stability to reasonable range
    return max(0.1, min(36500.0, S_new))


def calculate_next_state(D: float, S: float, t: float, grade: int) -> Tuple[float, float, float]:
    """
    Calculate the next memory state after a review.
    
    Args:
        D: Current difficulty (0 for new card)
        S: Current stability (0 for new card)
        t: Days since last review (0 for new card)
        grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    Returns:
        Tuple of (new_D, new_S, current_R)
    """
    # New card - first review
    if S <= 0:
        new_D = calculate_initial_difficulty(grade)
        new_S = calculate_initial_stability(grade)
        current_R = 1.0  # First time seeing it
    else:
        # Existing card
        current_R = calculate_retrievability(t, S)
        new_D = calculate_new_difficulty(D, grade)
        new_S = calculate_new_stability(D, S, current_R, grade)
    
    return new_D, new_S, current_R


def calculate_optimal_interval(S: float, desired_retention: float = 0.9) -> float:
    """
    Calculate the optimal interval for the next review.
    
    Args:
        S: Current stability
        desired_retention: Target retention rate (default 90%)
    
    Returns:
        Optimal interval in days
    """
    if S <= 0:
        return 1.0
    
    # I(r,S) = S/FACTOR * (r^(1/DECAY) - 1)
    interval = (S / FACTOR) * (math.pow(desired_retention, 1 / DECAY) - 1)
    return max(1.0, min(36500.0, interval))


def retrievability_to_grade_letter(R: float) -> str:
    """
    Convert retrievability to a letter grade.
    DEPRECATED: Use stability_to_grade_letter instead.
    """
    R_percent = R * 100
    
    if R_percent >= 95:
        return 'A+'
    elif R_percent >= 90:
        return 'A'
    elif R_percent >= 80:
        return 'B+'
    elif R_percent >= 70:
        return 'B'
    elif R_percent >= 60:
        return 'C+'
    elif R_percent >= 50:
        return 'C'
    elif R_percent >= 40:
        return 'D+'
    elif R_percent >= 30:
        return 'D'
    elif R_percent >= 15:
        return 'E+'
    else:
        return 'E'


def stability_to_grade_letter(S: float) -> str:
    """
    Convert stability to a letter grade.
    Stability (S) = days until R drops to 90%.
    Higher S = better long-term memory.
    
    Grade scale based on how long you can remember:
    - A+: 180+ days (6 months) - Truly mastered
    - A:  90+ days (3 months) - Excellent
    - B+: 60+ days (2 months) - Very good
    - B:  30+ days (1 month) - Good
    - C+: 14+ days (2 weeks) - Decent
    - C:  7+ days (1 week) - Learning
    - D+: 3+ days - Started
    - D:  1+ day - Just seen
    - E+: < 1 day - Very new
    - E:  0 - Never reviewed
    """
    if S <= 0:
        return 'E'
    elif S < 1:
        return 'E+'
    elif S < 3:
        return 'D'
    elif S < 7:
        return 'D+'
    elif S < 14:
        return 'C'
    elif S < 30:
        return 'C+'
    elif S < 60:
        return 'B'
    elif S < 90:
        return 'B+'
    elif S < 180:
        return 'A'
    else:
        return 'A+'


def get_grade_color_from_R(R: float) -> str:
    """Get color based on retrievability."""
    grade = retrievability_to_grade_letter(R)
    colors = {
        'A+': '#10b981',
        'A': '#22c55e',
        'B+': '#84cc16',
        'B': '#a3e635',
        'C+': '#fbbf24',
        'C': '#f59e0b',
        'D+': '#fb923c',
        'D': '#f97316',
        'E+': '#ef4444',
        'E': '#dc2626',
    }
    return colors.get(grade, '#6b7280')


def get_grade_description_from_R(R: float) -> str:
    """Get description based on retrievability. DEPRECATED."""
    grade = retrievability_to_grade_letter(R)
    descriptions = {
        'A+': 'Maîtrisé',
        'A': 'Excellent',
        'B+': 'Très bien',
        'B': 'Bien',
        'C+': 'Correct',
        'C': 'Moyen',
        'D+': 'Faible',
        'D': 'Difficile',
        'E+': 'À revoir',
        'E': 'Oublié',
    }
    return descriptions.get(grade, 'Inconnu')


def get_grade_color_from_S(S: float) -> str:
    """Get color based on stability."""
    grade = stability_to_grade_letter(S)
    colors = {
        'A+': '#10b981',
        'A': '#22c55e',
        'B+': '#84cc16',
        'B': '#a3e635',
        'C+': '#fbbf24',
        'C': '#f59e0b',
        'D+': '#fb923c',
        'D': '#f97316',
        'E+': '#ef4444',
        'E': '#dc2626',
    }
    return colors.get(grade, '#6b7280')


def get_grade_description_from_S(S: float) -> str:
    """Get description based on stability."""
    grade = stability_to_grade_letter(S)
    descriptions = {
        'A+': 'Maîtrisé (6+ mois)',
        'A': 'Excellent (3+ mois)',
        'B+': 'Très bien (2 mois)',
        'B': 'Bien (1 mois)',
        'C+': 'Correct (2 sem)',
        'C': 'En cours (1 sem)',
        'D+': 'Débutant (3j)',
        'D': 'Vu (1j)',
        'E+': 'Nouveau',
        'E': 'Jamais vu',
    }
    return descriptions.get(grade, 'Inconnu')


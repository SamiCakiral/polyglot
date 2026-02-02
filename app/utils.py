"""
Utility functions for card management including duplicate detection.
"""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Normalize text for duplicate comparison.
    - Lowercase
    - Remove accents
    - Normalize whitespace (spaces, tabs, newlines -> single space)
    - Remove common punctuation variations (-, _, ', etc.)
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Remove accents (é -> e, ü -> u, etc.)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Normalize whitespace and common separators
    text = re.sub(r'[\s\-_\'\"\.\,\;\:\!]+', ' ', text)
    
    # Strip and collapse multiple spaces
    text = ' '.join(text.split())
    
    return text


def similarity_score(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts (0.0 to 1.0).
    Uses simple character-level comparison after normalization.
    """
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 1.0
    
    if not norm1 or not norm2:
        return 0.0
    
    # Check if one is a prefix/suffix of the other (catches "chat" vs "chats")
    if norm1.startswith(norm2) or norm2.startswith(norm1):
        longer = max(len(norm1), len(norm2))
        shorter = min(len(norm1), len(norm2))
        return shorter / longer
    
    # Simple Levenshtein-like ratio
    # Count matching characters
    matches = sum(1 for a, b in zip(norm1, norm2) if a == b)
    total = max(len(norm1), len(norm2))
    
    return matches / total if total > 0 else 0.0


def find_duplicates(front: str, back: str, existing_cards, threshold: float = 0.85):
    """
    Find potential duplicate cards.
    
    Args:
        front: The front text of the new card
        back: The back text of the new card
        existing_cards: List of Card objects to check against
        threshold: Similarity threshold (0.0 to 1.0) to consider as duplicate
    
    Returns:
        List of (card, match_type, score) tuples for potential duplicates
    """
    duplicates = []
    norm_front = normalize_text(front)
    norm_back = normalize_text(back)
    
    for card in existing_cards:
        card_norm_front = normalize_text(card.front)
        card_norm_back = normalize_text(card.back)
        
        # Exact match on front (normalized)
        if norm_front == card_norm_front:
            duplicates.append((card, 'exact_front', 1.0))
            continue
        
        # Exact match on both (normalized)
        if norm_front == card_norm_front and norm_back == card_norm_back:
            duplicates.append((card, 'exact', 1.0))
            continue
        
        # Similar front
        front_score = similarity_score(front, card.front)
        if front_score >= threshold:
            duplicates.append((card, 'similar_front', front_score))
            continue
        
        # Check if front/back are swapped
        if norm_front == card_norm_back and norm_back == card_norm_front:
            duplicates.append((card, 'swapped', 1.0))
            continue
    
    # Sort by score descending
    duplicates.sort(key=lambda x: x[2], reverse=True)
    
    return duplicates


def check_import_duplicates(cards_data: list, existing_cards, threshold: float = 0.85):
    """
    Check a list of card data for duplicates against existing cards.
    
    Args:
        cards_data: List of dicts with 'front' and 'back' keys
        existing_cards: Existing Card objects in the deck
        threshold: Similarity threshold
    
    Returns:
        Dict with:
            - 'clean': cards with no duplicates
            - 'duplicates': cards with potential duplicates and their matches
            - 'internal_duplicates': duplicates within the import itself
    """
    result = {
        'clean': [],
        'duplicates': [],
        'internal_duplicates': []
    }
    
    # Check for internal duplicates in the import
    seen_fronts = {}
    for i, card_data in enumerate(cards_data):
        front = card_data.get('front', card_data.get('question', ''))
        norm_front = normalize_text(front)
        
        if norm_front in seen_fronts:
            result['internal_duplicates'].append({
                'card': card_data,
                'duplicate_of_index': seen_fronts[norm_front]
            })
        else:
            seen_fronts[norm_front] = i
    
    # Check against existing cards
    for card_data in cards_data:
        front = card_data.get('front', card_data.get('question', ''))
        back = card_data.get('back', card_data.get('answer', ''))
        
        duplicates = find_duplicates(front, back, existing_cards, threshold)
        
        if duplicates:
            result['duplicates'].append({
                'card': card_data,
                'matches': [
                    {
                        'id': card.id,
                        'front': card.front,
                        'back': card.back,
                        'type': match_type,
                        'score': round(score * 100)
                    }
                    for card, match_type, score in duplicates[:3]  # Top 3 matches
                ]
            })
        else:
            result['clean'].append(card_data)
    
    return result

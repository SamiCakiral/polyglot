import re
import random
from app.models import Card, TrainingProgram, Category


# Global conjugation cache (simplified for now, ideally in DB or JSON)
# We need to map "Io" -> "mangio", "Noi" -> "mangiamo"
# Since cards are stored as "Io (Mangiare)", we can query by Front content.

SUBJECTS = ["Io", "Tu", "Lui/Lei", "Noi", "Voi", "Loro"]

MODALS = {
    "DOVERE": {"Io": "devo", "Tu": "devi", "Lui/Lei": "deve", "Noi": "dobbiamo", "Voi": "dovete", "Loro": "devono"},
    "POTERE": {"Io": "posso", "Tu": "puoi", "Lui/Lei": "può", "Noi": "possiamo", "Voi": "potete", "Loro": "possono"},
    "VOLERE": {"Io": "voglio", "Tu": "vuoi", "Lui/Lei": "vuole", "Noi": "vogliamo", "Voi": "volete", "Loro": "vogliono"}
}

def generate_lego_sentence(program: TrainingProgram, template: dict):
    """
    Generate a Lego sentence with semantic coherence and subject variation.
    """
    
    # 1. Parse pattern
    pattern = template.get('pattern', '')
    if not pattern:
        return None
        
    slots_found = re.findall(r'\[([A-Z0-9_]+)\]', pattern)
    
    # 2. Context holder for inter-slot dependencies
    context = {}
    chosen_cards = {}
    deck_id = program.deck_id
    
    # 3. Process slots
    # We sort slots to ensure dependencies are met (e.g. Sujet -> Modal -> Verbe)
    
    def get_slot_priority(name):
        if 'SUJET' in name: return 0
        if name in MODALS: return 1
        if 'VERBE' in name: return 2
        return 3
        
    ordered_slots = sorted(slots_found, key=get_slot_priority)
    
    for slot_name in ordered_slots:
        slot_config = template.get('slots', {}).get(slot_name, {})
        
        # --- CASE 1: SUBJECT ---
        if slot_name == "SUJET" or slot_config.get('type') == 'subject':
            # Pick a random subject
            subject = random.choice(SUBJECTS)
            context['subject'] = subject
            chosen_cards[slot_name] = subject
            continue
            
        # --- CASE 1.5: FIXED STRINGS ---
        if slot_config.get('type') == 'fixed':
            chosen_cards[slot_name] = slot_config.get('value', '')
            continue
            
        # --- CASE 1.6: MODALS (Hardcoded logic) ---
        if slot_name in MODALS:
            subject = context.get('subject', 'Io')
            conjugation = MODALS[slot_name].get(subject, "???")
            chosen_cards[slot_name] = conjugation
            continue

        # --- CASE 2: VERB ---
        if slot_name == "VERBE" or slot_config.get('type') == 'verb':
            # We need to find a Verb that matches tags
            # And then find the CARD that matches the Subject + Verb
            
            # A. Select a Verb Infinitive (Concept)
            tags = slot_config.get('tags', [])
            verb_candidates = find_cards_by_tags(deck_id, tags, card_type='Infinitif')
            
            if not verb_candidates:
                # Fallback to any verb if no semantic tag found
                verb_candidates = find_cards_by_tags(deck_id, [], card_type='Infinitif')
                
            if not verb_candidates:
                chosen_cards[slot_name] = "???"
                continue
                
            selected_verb_card = random.choice(verb_candidates)
            verb_infinitive = selected_verb_card.front # "Mangiare"
            
            # Save semantic tags for Object matching
            # We look at the categories of the selected verb to find logic tags
            # e.g. Mangiare might have Tag:NeedsFood (if we added it)
            # For now, we'll map manually or rely on `match_context` logic in future
            context['verb'] = verb_infinitive
            context['verb_tags'] = [c.name for c in selected_verb_card.categories]
            
            # B. Find the Conjugated Card (if not Infinitive required)
            # Sometimes pattern is: "deve [VERBE]" -> Here VERBE should be Infinitive!
            # If previous word was a Modal, we usually want Infinitive.
            # But the user asked for: "[SUJET] non può [VERBE] perché deve [VERBE2] [OBJET]"
            # In Italian: "Io non posso mangiare" -> Infinitive.
            # But "Io mangio" -> Conjugated.
            
            # How to decide?
            # 1. Look at template. If it says "conjugate": true (or defaults).
            # 2. Heuristic: if pattern has a Modal before it? Hard to know parsing regex.
            
            # Let's check our templates.
            # "[SUJET] deve [VERBE] [OBJET]" -> Modal 'deve' requires Infinitive.
            
            # If the slot name is "VERBE_INF" or has config `form: infinitif`.
            # OR if we detect a Modal in `chosen_cards`.
            
            has_modal = any(k in MODALS for k in chosen_cards)
            
            if has_modal:
                 # Use Infinitive
                 chosen_cards[slot_name] = selected_verb_card # The card itself (Front=Mangiare usually if logic correct... wait Infinitive card Front=Mangiare?)
                 # In Deck 3, Infinitif card Front="Mangiare" (or "Essere", "Avere").
                 # So returning the card is fine.
            else:
                # Use Conjugation
                subject = context.get('subject', 'Io')
                target_front_start = f"{subject} ({verb_infinitive})"
                
                conjugated_card = Card.query.filter(
                    Card.deck_id == deck_id,
                    Card.front.like(f"{target_front_start}%")
                ).first()
                
                if conjugated_card:
                    chosen_cards[slot_name] = conjugated_card
                else:
                    chosen_cards[slot_name] = f"{subject} {verb_infinitive} (missing)"
            
            continue
            
        # --- CASE 3: OBJECT / OTHER ---
        # "match_context": "VERBE" -> implies we should look at Verb's requirements
        # For this iteration, we implemented logic: 
        # Mangiare -> Tag:Food
        # Bere -> Tag:Drink
        # Pulire -> Tag:Place/Object
        
        required_tags = slot_config.get('tags', [])
        
        # DYNAMIC LOGIC MAPPING
        # If the verb is known, strict filtering
        verb = context.get('verb', '')
        if verb == 'Mangiare':
            required_tags.append('Tag:Food')
        elif verb == 'Bere':
            required_tags.append('Tag:Drink')
        elif verb == 'Leggere':
            required_tags.append('Tag:Readable')
        elif verb == 'Aprire' or verb == 'Chiudere':
            required_tags.append('Tag:Openable')
            
        # Default to Tag:Object if no specific requirements and it's an OBJET slot
        if not required_tags and (slot_name == "OBJET" or slot_config.get('type') == 'object'):
            required_tags.append('Tag:Object')
            
        candidates = find_cards_by_tags(deck_id, required_tags)
        
        if candidates:
            chosen_cards[slot_name] = random.choice(candidates)
        else:
            chosen_cards[slot_name] = "<brique manquante>"

    # 4. Assemble
    raw_sentence = pattern
    used_cards = []
    blocks = []
    
    # We maintain the order of blocks corresponding to the pattern if we iterate key-value?
    # No, keys are unordered. But we want blocks to match the sentence structure?
    # Wait, raw_sentence.replace uses the key.
    # The `blocks` list should probably match the sentence order?
    # If the frontend displays them randomly, fine.
    # If frontend displays them in order for user to pick, it should probably be random.
    # But for now, let's just collect them.
    
    for slot_name, content in chosen_cards.items():
        text = str(content)
        if isinstance(content, Card):
            # If Content is a Card, use Front or Back?
            
            if "VERBE" in slot_name:
                # Check categories for Infinitif
                cats = [c.name for c in content.categories]
                if "Infinitif" in cats:
                     text = content.front # "Mangiare"
                else:
                     # It's a conjugated card (e.g. Front: "Noi (Mantenere)", Back: "Manteniamo")
                     # We WANT the Back for the sentence.
                     text = content.back 
                    
            elif slot_name == "OBJET":
                text = content.front
            else:
                text = content.front # Default
                
            used_cards.append(content)
        
        blocks.append(text)
            
        raw_sentence = raw_sentence.replace(f"[{slot_name}]", text)
        
    return {
        "raw_sentence": raw_sentence,
        "used_cards": [c.to_dict() if hasattr(c, 'to_dict') else str(c) for c in used_cards],
        "blocks": blocks,
        "template": template
    }


def find_cards_by_tags(deck_id, tags, card_type=None):
    """
    Find cards that match ALL tags (AND logic) or at least ONE if loose?
    Let's go with OR logic for tags list, but AND with card_type.
    """
    query = Card.query.filter(Card.deck_id == deck_id)
    
    # Join categories
    if tags:
        # We want cards that have AT LEAST ONE of the tags? 
        # Or ALL? Usually "Tag:Food" is enough.
        # If multiple tags provided ["Tag:Food", "Tag:Edible"], maybe OR is better.
        
        # Filter where card.categories.any(Category.name.in_(tags))
        query = query.join(Card.categories).filter(Category.name.in_(tags))
        
    if card_type:
        # Check if "Infinitif" is in categories
        # We need an alias or separate exists join if we already joined
        # Simpler: just filter by string match in categories if possible, 
        # or use multiple joins.
        # Since SQLAlchemy `any` creates a subquery, we can chain them.
        query = query.filter(Card.categories.any(Category.name == card_type))
        
    return query.all()


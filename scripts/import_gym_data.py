
import json
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app, db
from app.models import User, Deck, Card, Category

def import_gym_vocab():
    app = create_app()
    with app.app_context():
        # Load vocab file
        vocab_path = 'card_sets/gym_vocabulary.json'
        if not os.path.exists(vocab_path):
            print(f"Error: {vocab_path} not found")
            return

        with open(vocab_path, 'r', encoding='utf-8') as f:
            cards_data = json.load(f)

        # Get the Main Deck
        user = User.query.first()
        if not user:
            print("No user found.")
            return

        # Target the main deck used by the program
        target_deck_name = "Conjugaison Italien" 
        # Fallback to finding ANY deck if specific name not found? 
        # Better to be specific.
        
        deck = Deck.query.filter_by(user_id=user.id, name=target_deck_name).first()
        
        if not deck:
            print(f"Deck '{target_deck_name}' not found. Falling back to creating/using 'Italien - Vocabulaire Gym'")
            target_deck_name = "Italien - Vocabulaire Gym"
            deck = Deck.query.filter_by(user_id=user.id, name=target_deck_name).first()
            if not deck:
                deck = Deck(user_id=user.id, name=target_deck_name)
                db.session.add(deck)
                db.session.commit()

        print(f"Targeting deck: {deck.name}")

        # 1. Import Nouns
        existing_cards = {c.front: c for c in deck.cards}
        count_new = 0
        count_updated = 0
        
        for item in cards_data:
            front = item['front']
            back = item['back']
            categories = item.get('categories', [])
            
            card = existing_cards.get(front)
            
            if not card:
                card = Card(
                    deck_id=deck.id,
                    front=front,
                    back=back,
                    slot_type='VOCAB' 
                )
                db.session.add(card)
                count_new += 1
            else:
                card.back = back 
                count_updated += 1
            
            # Add Categories (Tags)
            ensure_categories(deck, card, categories)
        
        # 2. Tag Existing Verbs (Crucial for Lego)
        # We look for cards with 'Infinitif' category or just known verbs
        print("Tagging existing verbs...")
        count_verbs = 0
        
        # List of verbs to tag as Action (could be broader)
        verbs_to_tag = [
            # Standard Actions
            "Mangiare", "Bere", "Parlare", "Leggere", "Scrivere", 
            "Camminare", "Correre", "Dormire", "Guardare", "Ascoltare",
            "Aprire", "Chiudere", "Comprare", "Pagare", "Cercare", "Trovare",
            "Prendere", "Mettere", "Fare", "Dire"
        ]
        
        # Specific semantic tags
        semantic_map = {
            "Mangiare": ["Tag:Action", "Tag:NeedsFood"],
            "Bere": ["Tag:Action", "Tag:NeedsDrink"],
            "Leggere": ["Tag:Action", "Tag:NeedsReadable"],
            "Scrivere": ["Tag:Action", "Tag:NeedsWritable"],
            "Aprire": ["Tag:Action", "Tag:NeedsOpenable"],
            "Chiudere": ["Tag:Action", "Tag:NeedsOpenable"]
        }
        
        all_cards = Card.query.filter_by(deck_id=deck.id).all()
        
        for card in all_cards:
            # Check if it's a verb definition (Infinitif)
            # Strategy: Logic from update_deck_json.py - check categorization
            cats = [c.name for c in card.categories]
            
            if "Infinitif" in cats:
                verb_name = card.front
                
                # Default Action tag
                tags_to_add = ["Tag:Action"]
                
                # Specific tags
                if verb_name in semantic_map:
                    tags_to_add = semantic_map[verb_name]
                
                ensure_categories(deck, card, tags_to_add)
                count_verbs += 1

        db.session.commit()
        print(f"Import complete. Nouns New/Updated: {count_new}/{count_updated}. Verbs Tagged: {count_verbs}")

def ensure_categories(deck, card, category_names):
    current_cat_names = [c.name for c in card.categories]
    for cat_name in category_names:
        if cat_name not in current_cat_names:
            category = Category.query.filter_by(deck_id=deck.id, name=cat_name).first()
            if not category:
                category = Category(
                    deck_id=deck.id, 
                    name=cat_name, 
                    color='#9CA3AF'
                )
                db.session.add(category)
            
            if category not in card.categories:
                card.categories.append(category)

if __name__ == '__main__':
    import_gym_vocab()

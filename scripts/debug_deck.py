
import os
import sys

sys.path.append(os.getcwd())

from app import create_app, db
from app.models import User, Deck, Card

app = create_app()
with app.app_context():
    deck = Deck.query.get(3) # Conjugaison Italien
    print(f"Deck: {deck.name}")
    print(f"Total Cards: {len(deck.cards)}")
    
    print("\n--- First 20 Cards ---")
    for i, card in enumerate(deck.cards[:20]):
        cats = [c.name for c in card.categories]
        print(f"[{i}] Front: {card.front} | Cats: {cats}")
        
    # Check for "Infinitif" category existence
    from app.models import Category
    inf_cat = Category.query.filter_by(deck_id=1, name="Infinitif").first()
    if inf_cat:
        print(f"\nCategory 'Infinitif' exists with {len(inf_cat.cards)} cards.")
    else:
        print("\nCategory 'Infinitif' DOES NOT EXIST.")

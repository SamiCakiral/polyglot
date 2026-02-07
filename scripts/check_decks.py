
import os
import sys

sys.path.append(os.getcwd())

from app import create_app, db
from app.models import User, Deck, TrainingProgram

app = create_app()
with app.app_context():
    user = User.query.first()
    print(f"User: {user.username} (ID: {user.id})")
    
    decks = Deck.query.filter_by(user_id=user.id).all()
    print("\n--- Decks ---")
    for d in decks:
        print(f"ID: {d.id} | Name: '{d.name}'")
        
    print("\n--- Programs ---")
    program = TrainingProgram.query.filter_by(user_id=user.id).first()
    if program:
        print(f"Program ID: {program.id}")
        print(f"Linked Deck ID: {program.deck_id}")
        linked_deck = Deck.query.get(program.deck_id)
        if linked_deck:
            print(f"Linked Deck Name: '{linked_deck.name}'")
    else:
        print("No program found.")


import os
import sys

sys.path.append(os.getcwd())

from app import create_app, db
from app.models import TrainingProgram

app = create_app()
with app.app_context():
    program = TrainingProgram.query.first()
    if program:
        print(f"Updating Program ID {program.id}...")
        print(f"Old Deck ID: {program.deck_id}")
        program.deck_id = 3
        db.session.commit()
        print(f"New Deck ID: {program.deck_id} (Conjugaison Italien)")
    else:
        print("No program found.")

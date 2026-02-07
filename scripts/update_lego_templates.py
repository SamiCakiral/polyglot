
import os
import sys

sys.path.append(os.getcwd())

from app import create_app, db
from app.models import TrainingProgram

NEW_TEMPLATES = [
    {
        "pattern": "[SUJET] [DOVERE] [VERBE] [OBJET]",
        "slots": {
            "SUJET": {"type": "subject"},
            "DOVERE": {"type": "modal"},
            "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
            "OBJET": {"type": "object", "match_context": "VERBE"}
        }
    },
    {
        "pattern": "[SUJET] [NON] [POTERE] [VERBE] [OBJET]",
        "slots": {
            "SUJET": {"type": "subject"},
            "NON": {"type": "fixed", "value": "non"},
            "POTERE": {"type": "modal"},
            "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
            "OBJET": {"type": "object", "match_context": "VERBE"}
        }
    },
    {
        "pattern": "[SUJET] [VOLERE] [VERBE] [OBJET]",
        "slots": {
            "SUJET": {"type": "subject"},
            "VOLERE": {"type": "modal"},
            "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
            "OBJET": {"type": "object", "match_context": "VERBE"}
        }
    }
]

app = create_app()
with app.app_context():
    program = TrainingProgram.query.first()
    if program:
        print(f"Updating Templates for Program ID {program.id}...")
        program.lego_templates = NEW_TEMPLATES
        db.session.commit()
        print("Templates updated successfully.")
    else:
        print("No program found.")

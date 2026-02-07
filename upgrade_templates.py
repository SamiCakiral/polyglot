from app import create_app, db
from app.models import TrainingProgram

def upgrade_templates():
    app = create_app()
    with app.app_context():
        # Update all programs
        programs = TrainingProgram.query.all()
        
        for p in programs:
            print(f"Updating program: {p.name}")
            new_templates = [
                {
                    "pattern": "[SUJET] + [VERBE_INF] + [OBJET]",
                    "example": "Io voglio mangiare la pizza",
                    "translation": "Je veux manger la pizza",
                    "slots": {
                        "SUJET": {"category": "Sujet"},
                        "VERBE_INF": {"category": "Infinitif"},
                        "OBJET": {"category": "Objet"}
                    }
                },
                {
                    "pattern": "[SUJET] + [VERBE_IO] + [OBJET]",
                    "example": "Io mangio la mela",
                    "translation": "Je mange la pomme",
                    "slots": {
                        "SUJET": {"category": "Sujet", "tags": ["io"]},
                        "VERBE_IO": {"category": "Verbe"}, # ideally filtering for IO conjugation but kept simple
                        "OBJET": {"category": "Objet"}
                    }
                },
                 {
                    "pattern": "[SUJET] + [VERBE_TU] + [OBJET]",
                    "example": "Tu mangi la mela",
                    "translation": "Tu manges la pomme",
                    "slots": {
                        "SUJET": {"category": "Sujet"},
                        "VERBE_TU": {"category": "Verbe"}, 
                        "OBJET": {"category": "Objet"}
                    }
                }
            ]
            
            p.lego_templates = new_templates
            # Update prompt for lego generation to match new format expectation if needed
            # (Though our python code handles the generation now, LLM just checks)
        
        db.session.commit()
        print("✅ Templates updated!")

if __name__ == '__main__':
    upgrade_templates()

"""
Migration script to add learner profile columns.
Adds:
- user.learner_profile (JSON)
- training_program.program_profile (JSON)
"""
from app import create_app, db
import sqlite3
import os

def migrate():
    app = create_app()
    with app.app_context():
        # Get database path - use the engine URL directly
        engine = db.engine
        # For SQLite, the URL is like sqlite:///path/to/db
        db_path = str(engine.url).replace('sqlite:///', '')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check and add user.learner_profile
        cursor.execute("PRAGMA table_info(user)")
        user_columns = [col[1] for col in cursor.fetchall()]
        
        if 'learner_profile' not in user_columns:
            print("Adding learner_profile to user table...")
            cursor.execute("ALTER TABLE user ADD COLUMN learner_profile TEXT")
            # Set default value for existing users
            default_profile = '{"native_language": "french", "known_languages": [], "learning_style": "balanced", "correction_preference": "moderate"}'
            cursor.execute("UPDATE user SET learner_profile = ?", (default_profile,))
            print("✅ user.learner_profile added")
        else:
            print("⏭️ user.learner_profile already exists")
        
        # Check and add training_program.program_profile
        cursor.execute("PRAGMA table_info(training_program)")
        program_columns = [col[1] for col in cursor.fetchall()]
        
        if 'program_profile' not in program_columns:
            print("Adding program_profile to training_program table...")
            cursor.execute("ALTER TABLE training_program ADD COLUMN program_profile TEXT")
            # Set default value for existing programs
            default_profile = '{"current_level": "A2", "years_learning": 0, "goals": ["conversation", "travel"], "correction_strictness": "moderate", "focus_areas": []}'
            cursor.execute("UPDATE training_program SET program_profile = ?", (default_profile,))
            print("✅ training_program.program_profile added")
        else:
            print("⏭️ training_program.program_profile already exists")
        
        conn.commit()
        conn.close()
        print("\n🎉 Migration complete!")

if __name__ == '__main__':
    migrate()

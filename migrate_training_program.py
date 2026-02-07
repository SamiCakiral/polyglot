"""
Migration script to add TrainingProgram table.
Run this script once to update the database schema.
"""
import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'anki.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='training_program'")
    if cursor.fetchone():
        print("Table 'training_program' already exists. Skipping.")
        conn.close()
        return
    
    # Create TrainingProgram table
    cursor.execute('''
        CREATE TABLE training_program (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            deck_id INTEGER NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            target_language VARCHAR(50) DEFAULT 'italian',
            native_language VARCHAR(50) DEFAULT 'french',
            exercise_config JSON,
            lego_templates JSON,
            fsi_mutations JSON,
            shadowing_resources JSON,
            daily_themes JSON,
            current_theme_index INTEGER DEFAULT 0,
            llm_prompts JSON,
            daily_cheat_tokens INTEGER DEFAULT 3,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (deck_id) REFERENCES deck(id)
        )
    ''')
    
    conn.commit()
    print("Created table 'training_program' successfully!")
    
    conn.close()

if __name__ == '__main__':
    migrate()

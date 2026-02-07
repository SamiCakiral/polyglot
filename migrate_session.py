#!/usr/bin/env python3
"""Migration script to add ProgramSession and DailyText tables."""

import sqlite3
import os

# Get the database path
db_path = os.path.join(os.path.dirname(__file__), 'anki.db')

print(f"Migrating database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create ProgramSession table
cursor.execute('''
CREATE TABLE IF NOT EXISTS program_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_date DATE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    current_module VARCHAR(50) DEFAULT 'flashcards',
    module_index INTEGER DEFAULT 0,
    cheat_tokens_remaining INTEGER DEFAULT 3,
    daily_words JSON,
    daily_words_theme VARCHAR(200),
    gym_exercises_done JSON,
    writing_quest TEXT,
    writing_text TEXT,
    writing_feedback TEXT,
    debt_words JSON,
    results JSON,
    FOREIGN KEY (program_id) REFERENCES training_program(id),
    FOREIGN KEY (user_id) REFERENCES user(id)
)
''')
print("✓ Created program_session table")

# Create DailyText table
cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_date DATE,
    theme VARCHAR(200),
    original_text TEXT NOT NULL,
    user_translation TEXT,
    llm_correction TEXT,
    used_for_output BOOLEAN DEFAULT 0,
    user_recode TEXT,
    diff_results JSON,
    FOREIGN KEY (program_id) REFERENCES training_program(id),
    FOREIGN KEY (user_id) REFERENCES user(id)
)
''')
print("✓ Created daily_text table")

conn.commit()
conn.close()

print("\n✅ Migration complete!")

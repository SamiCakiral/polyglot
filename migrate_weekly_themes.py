#!/usr/bin/env python3
"""
Migration script for WeeklyTheme and GeneratedVocabulary tables.
Run with: python3.11 migrate_weekly_themes.py
"""

import sqlite3
import os

def migrate():
    db_path = 'instance/anki.db'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Creating WeeklyTheme table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_theme (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            week_number INTEGER NOT NULL,
            main_theme VARCHAR(200) NOT NULL,
            theme_description TEXT,
            daily_breakdown JSON,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            based_on_goals JSON,
            based_on_level VARCHAR(10),
            previous_themes_considered JSON,
            completed BOOLEAN DEFAULT FALSE,
            days_completed INTEGER DEFAULT 0,
            FOREIGN KEY (program_id) REFERENCES training_program(id),
            FOREIGN KEY (user_id) REFERENCES user(id),
            UNIQUE (program_id, year, week_number)
        )
    ''')
    print("  -> weekly_theme created")
    
    print("Creating GeneratedVocabulary table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generated_vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            front VARCHAR(200) NOT NULL,
            back VARCHAR(200) NOT NULL,
            word_type VARCHAR(50),
            domain VARCHAR(100),
            example_sentence TEXT,
            weekly_theme_id INTEGER,
            day_focus VARCHAR(200),
            fb_stability REAL DEFAULT 0.0,
            fb_difficulty REAL DEFAULT 0.0,
            fb_next_review DATETIME,
            fb_last_reviewed DATETIME,
            bf_stability REAL DEFAULT 0.0,
            bf_difficulty REAL DEFAULT 0.0,
            bf_next_review DATETIME,
            bf_last_reviewed DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            times_reviewed INTEGER DEFAULT 0,
            mastered BOOLEAN DEFAULT FALSE,
            mastered_at DATETIME,
            FOREIGN KEY (program_id) REFERENCES training_program(id),
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (weekly_theme_id) REFERENCES weekly_theme(id)
        )
    ''')
    print("  -> generated_vocabulary created")
    
    print("Creating indexes...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_program ON generated_vocabulary(program_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_user ON generated_vocabulary(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_mastered ON generated_vocabulary(mastered)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_fb_review ON generated_vocabulary(fb_next_review)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_bf_review ON generated_vocabulary(bf_next_review)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_theme_program_week ON weekly_theme(program_id, year, week_number)')
    print("  -> indexes created")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration completed successfully!")
    return True


if __name__ == '__main__':
    migrate()

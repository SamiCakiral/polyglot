"""
Migration script to add new models: LegoStructure, ShadowingVideo, DebtWord
Run this script to update the database schema.
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
    
    # Check existing tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]
    print(f"Existing tables: {existing_tables}")
    
    # Create LegoStructure table
    if 'lego_structure' not in existing_tables:
        print("Creating lego_structure table...")
        cursor.execute("""
            CREATE TABLE lego_structure (
                id INTEGER PRIMARY KEY,
                program_id INTEGER NOT NULL,
                pattern VARCHAR(500) NOT NULL,
                example_target VARCHAR(500),
                example_native VARCHAR(500),
                description TEXT,
                stability FLOAT DEFAULT 1.0,
                difficulty FLOAT DEFAULT 0.5,
                due_date DATE,
                last_review DATE,
                review_count INTEGER DEFAULT 0,
                complexity_level VARCHAR(10) DEFAULT 'A2',
                tags JSON,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (program_id) REFERENCES training_program(id)
            )
        """)
        print("✓ lego_structure table created")
    else:
        print("- lego_structure table already exists")
    
    # Create ShadowingVideo table
    if 'shadowing_video' not in existing_tables:
        print("Creating shadowing_video table...")
        cursor.execute("""
            CREATE TABLE shadowing_video (
                id INTEGER PRIMARY KEY,
                program_id INTEGER NOT NULL,
                url VARCHAR(500) NOT NULL,
                title VARCHAR(200),
                description TEXT,
                duration_seconds INTEGER,
                segments JSON,
                times_used INTEGER DEFAULT 0,
                last_used DATETIME,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (program_id) REFERENCES training_program(id)
            )
        """)
        print("✓ shadowing_video table created")
    else:
        print("- shadowing_video table already exists")
    
    # Create DebtWord table
    if 'debt_word' not in existing_tables:
        print("Creating debt_word table...")
        cursor.execute("""
            CREATE TABLE debt_word (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                program_id INTEGER NOT NULL,
                word_front VARCHAR(200) NOT NULL,
                word_back VARCHAR(200) NOT NULL,
                source VARCHAR(50) NOT NULL,
                context VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_date DATE,
                processed BOOLEAN DEFAULT 0,
                processed_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES user(id),
                FOREIGN KEY (program_id) REFERENCES training_program(id)
            )
        """)
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX idx_debt_word_user_program 
            ON debt_word(user_id, program_id, processed)
        """)
        print("✓ debt_word table created")
    else:
        print("- debt_word table already exists")
    
    conn.commit()
    conn.close()
    print("\n✓ Migration complete!")
    return True

if __name__ == '__main__':
    migrate()

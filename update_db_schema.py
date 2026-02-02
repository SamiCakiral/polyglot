import sqlite3
import os

def update_schema():
    db_path = 'instance/anki.db'
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if columns exist
    cursor.execute("PRAGMA table_info(user)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'password_hash' not in columns:
        print("Adding password_hash column...")
        cursor.execute("ALTER TABLE user ADD COLUMN password_hash TEXT")
        
    if 'avatar_color' not in columns:
        print("Adding avatar_color column...")
        cursor.execute("ALTER TABLE user ADD COLUMN avatar_color TEXT DEFAULT '#3498db'")
        
    conn.commit()
    conn.close()
    print("Schema update complete.")

if __name__ == '__main__':
    update_schema()

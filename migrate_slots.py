from app import create_app, db
from sqlalchemy import text

def run_migration():
    app = create_app()
    
    with app.app_context():
        print(f"Migrating database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        try:
            # Check if column exists
            with db.engine.connect() as conn:
                # SQLite specific check
                result = conn.execute(text("PRAGMA table_info(card)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'slot_type' not in columns:
                    print("Adding slot_type column to card table...")
                    conn.execute(text("ALTER TABLE card ADD COLUMN slot_type TEXT"))
                    conn.commit()
                    print("✓ Added slot_type column")
                else:
                    print("ℹ️ slot_type column already exists")
            
            print("\n✅ Migration complete!")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")

if __name__ == '__main__':
    run_migration()

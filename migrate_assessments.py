"""Migration script to create Assessment and AssessmentSection tables."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

def migrate():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Assessment and AssessmentSection tables created (or already exist).")

if __name__ == '__main__':
    migrate()

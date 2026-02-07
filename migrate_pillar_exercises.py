"""
Migration script to add PillarExercise and PillarExerciseResult tables.
Run: python3.11 migrate_pillar_exercises.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

def migrate():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("PillarExercise and PillarExerciseResult tables created (or already exist).")

if __name__ == '__main__':
    migrate()

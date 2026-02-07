"""
Migration script for Pillars feature.

This script:
1. Creates the UserLanguage table
2. Migrates existing learner_profile data to the new enriched format
3. Optionally creates UserLanguage entries from existing TrainingProgram languages

Run with: python3.11 migrate_pillars.py
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, UserLanguage, TrainingProgram
from sqlalchemy import inspect


def table_exists(table_name):
    """Check if a table exists in the database."""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def migrate_learner_profiles():
    """Migrate existing learner_profile to the new enriched format."""
    print("\n[2/4] Migrating learner profiles...")
    
    users = User.query.all()
    migrated = 0
    
    for user in users:
        if not user.learner_profile:
            # Initialize empty profile
            user.learner_profile = {
                'native_language': 'fr',
                'known_languages': [],
                'learning_style': 'balanced',
                'correction_preference': 'moderate',
                'goals': [],
                'daily_time_available': 30
            }
            migrated += 1
        else:
            profile = user.learner_profile
            needs_update = False
            
            # Convert old native_language format (full name to code)
            old_lang_map = {
                'french': 'fr', 'english': 'en', 'spanish': 'es', 
                'german': 'de', 'italian': 'it', 'portuguese': 'pt',
                'russian': 'ru', 'chinese': 'zh', 'japanese': 'ja',
                'korean': 'ko', 'arabic': 'ar', 'turkish': 'tr'
            }
            
            native = profile.get('native_language', '')
            if native in old_lang_map:
                profile['native_language'] = old_lang_map[native]
                needs_update = True
            elif not native:
                profile['native_language'] = 'fr'
                needs_update = True
            
            # Convert old known_languages format (list of strings to list of dicts)
            known = profile.get('known_languages', [])
            if known and isinstance(known, list) and len(known) > 0:
                if isinstance(known[0], str):
                    # Old format: ['english', 'spanish']
                    new_known = []
                    for lang in known:
                        lang_code = old_lang_map.get(lang.lower(), lang[:2])
                        new_known.append({
                            'code': lang_code,
                            'level': 'A2',  # Default level
                            'years': 0
                        })
                    profile['known_languages'] = new_known
                    needs_update = True
            
            # Ensure new fields exist
            if 'goals' not in profile:
                profile['goals'] = []
                needs_update = True
            
            if 'daily_time_available' not in profile:
                profile['daily_time_available'] = 30
                needs_update = True
            
            if needs_update:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user, 'learner_profile')
                migrated += 1
    
    db.session.commit()
    print(f"   -> Migrated {migrated} user profiles")


def create_user_languages_from_programs():
    """Create UserLanguage entries from existing TrainingProgram target languages."""
    print("\n[3/4] Creating UserLanguage entries from programs...")
    
    # Map program target_language to pillar language codes
    lang_map = {
        'italian': 'it', 'japanese': 'ja', 'spanish': 'es',
        'german': 'de', 'russian': 'ru', 'turkish': 'tr',
        'chinese': 'zh', 'korean': 'ko', 'french': 'fr',
        'english': 'en', 'portuguese': 'pt'
    }
    
    programs = TrainingProgram.query.all()
    created = 0
    
    for program in programs:
        target_lang = program.target_language
        lang_code = lang_map.get(target_lang, target_lang[:2] if target_lang else None)
        
        if not lang_code or lang_code not in ['ja', 'zh', 'ko', 'ru', 'tr', 'es', 'it']:
            # Only create for supported pillar languages
            continue
        
        # Check if UserLanguage already exists for this user/language
        existing = UserLanguage.query.filter_by(
            user_id=program.user_id,
            language_code=lang_code
        ).first()
        
        if not existing:
            # Get level from program profile
            level = 'A0'
            if program.program_profile:
                level = program.program_profile.get('current_level', 'A0')
            
            user_lang = UserLanguage(
                user_id=program.user_id,
                language_code=lang_code,
                estimated_level=level,
                pillar_progress={},
                show_romanization=True
            )
            db.session.add(user_lang)
            created += 1
    
    db.session.commit()
    print(f"   -> Created {created} UserLanguage entries")


def main():
    """Run the migration."""
    print("=" * 60)
    print("PILLARS MIGRATION SCRIPT")
    print("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        # Step 1: Create UserLanguage table if needed
        print("\n[1/4] Checking UserLanguage table...")
        
        if not table_exists('user_language'):
            print("   -> Creating UserLanguage table...")
            db.create_all()
            print("   -> Table created successfully")
        else:
            print("   -> UserLanguage table already exists")
        
        # Step 2: Migrate learner profiles
        migrate_learner_profiles()
        
        # Step 3: Create UserLanguage from programs
        create_user_languages_from_programs()
        
        # Step 4: Create pillar_content directory
        print("\n[4/4] Creating pillar_content directory...")
        content_dir = os.path.join(os.path.dirname(__file__), 'pillar_content')
        if not os.path.exists(content_dir):
            os.makedirs(content_dir)
            # Create subdirectories for each language
            for lang in ['ja', 'zh', 'ko', 'ru', 'tr', 'es', 'it']:
                lang_dir = os.path.join(content_dir, lang)
                os.makedirs(lang_dir, exist_ok=True)
            print("   -> Created pillar_content directory structure")
        else:
            print("   -> pillar_content directory already exists")
        
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Run the pillar content generation script:")
        print("   python3.11 scripts/generate_pillar_content.py")
        print("2. Restart your Flask application")
        print("3. Visit /pillars to see your languages")


if __name__ == '__main__':
    main()

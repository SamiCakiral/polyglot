
import os
import sys
import random

sys.path.append(os.getcwd())

from app import create_app, db
from app.models import TrainingProgram, Card, Category
from app.lego_generator import generate_lego_sentence

def test_generation():
    app = create_app()
    with app.app_context():
        program = TrainingProgram.query.first()
        if not program:
            print("No program found!")
            return

        print(f"Testing Lego Generator with Program ID: {program.id}")
        print(f"Deck ID: {program.deck_id}")
        
        # Check if templates are loaded
        templates = program.lego_templates
        if not templates:
            print("No templates found in program!")
            return
            
        print(f"Found {len(templates)} templates.")
        
        # Test 5 generations
        for i in range(5):
            print(f"\n--- Generation {i+1} ---")
            template = random.choice(templates)
            result = generate_lego_sentence(program, template)
            
            if not result:
                print("FAILED to generate sentence.")
                continue
                
            print(f"Pattern: {result['template']['pattern']}")
            print(f"Raw Sentence: {result['raw_sentence']}")
            print(f"Blocks: {result.get('blocks')}")
            
            # Verify basic logic
            blocks = result.get('blocks', [])
            if len(blocks) < 3:
                print("WARNING: Too few blocks.")
            
            # Check if any block is missing
            if any("???" in str(b) or "manquante" in str(b) for b in blocks):
                print("WARNING: Missing semantic match.")

if __name__ == '__main__':
    test_generation()

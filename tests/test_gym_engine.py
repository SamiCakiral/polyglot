
import os
import sys

sys.path.append(os.getcwd())

from app import create_app
from app.models import TrainingProgram
from app.gym_engine import GymSessionEngine

def test_session_engine():
    app = create_app()
    with app.app_context():
        program = TrainingProgram.query.first()
        if not program:
            print("No program found.")
            return

        print(f"Testing Engine with Program ID: {program.id}")
        engine = GymSessionEngine(program)
        
        # Test 1: Loading
        print(f"Loaded {len(engine.structures)} structures.")
        if not engine.structures:
            print("FAILED: No structures loaded.")
            return

        # Test 2: Volume for 5 mins
        print("\n--- Generating 5 Minute Session ---")
        steps_5 = engine.generate_daily_session(duration_minutes=5)
        print(f"Generated {len(steps_5)} steps.")
        
        # Verify structure
        for i, step in enumerate(steps_5):
            print(f"[{i+1}] {step['type'].upper()} - {step['structure_name']}")
            if step['type'] == 'lego':
                print(f"   RAW: {step['data'].get('raw_sentence')}")
            elif step['type'] == 'fsi':
                print(f"   Instruction: {step.get('instruction')}")
                print(f"   Context: {step.get('context_sentence')}")

        # Test 3: Volume for 15 mins
        print("\n--- Generating 15 Minute Session ---")
        steps_15 = engine.generate_daily_session(duration_minutes=15)
        print(f"Generated {len(steps_15)} steps (Expected ~20).")

if __name__ == '__main__':
    test_session_engine()

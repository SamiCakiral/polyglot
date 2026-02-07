from app import create_app
from app.lego_generator import generate_lego_sentence
from app.models import TrainingProgram, Deck, Card

app = create_app()

with app.app_context():
    # Find a program or deck
    program = TrainingProgram.query.first()
    if not program:
        print("No program found")
        exit()
        
    print(f"Testing with program: {program.name} (Deck: {program.deck.name})")
    
    # Create a test template
    template = {
        "pattern": "[SUJET] + [VERBE_INF] + [OBJET]",
        "slots": {
            "SUJET": {"category": "Sujet"}, 
            "VERBE_INF": {"category": "Infinitif"},
            "OBJET": {"category": "Objet"} 
        }
    }
    
    print("\nAttempting generation...")
    try:
        result = generate_lego_sentence(program, template)
        
        if result:
            print("\n✅ Generation Successful!")
            print(f"Global Sentence: {result['raw_sentence']}")
            print("Used Cards:")
            for c in result['used_cards']:
                if isinstance(c, dict):
                     print(f" - {c.get('front')} ({c.get('slot_type', 'No Slot Type')})")
                else:
                     print(f" - {c}")
        else:
            print("\n❌ Generation returned None")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

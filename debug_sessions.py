
from app import create_app, db
from app.models import ProgramSession, User

app = create_app()

with app.app_context():
    user = User.query.first() # Assuming single user or first user
    print(f"User: {user.username} (ID: {user.id})")
    
    sessions = ProgramSession.query.filter_by(
        user_id=user.id,
        completed_at=None
    ).all()
    
    print(f"Found {len(sessions)} active sessions:")
    for ps in sessions:
        word_count = len(ps.daily_words) if ps.daily_words else 0
        print(f" - Session {ps.id} (Program {ps.program_id}): {word_count} words.")
        print(f"   Date: {ps.session_date}")
        if ps.results and 'flashcards' in ps.results:
             print(f"   Stored Total in Results: {ps.results['flashcards'].get('total')}")


from app import create_app, db
from app.models import ProgramSession
from sqlalchemy.orm.attributes import flag_modified
import random

app = create_app()

with app.app_context():
    # Target specific session 2 identified in debug
    ps = ProgramSession.query.get(2)
    
    if ps:
        words = ps.daily_words
        print(f"Session {ps.id} current words: {len(words)}")
        
        if len(words) <= 15:
            new_words = []
            seen_fronts = set()
            
            for w in words:
                # Original
                new_words.append(w)
                seen_fronts.add(w['front'])
                
                # Reverse
                if w['back'] in seen_fronts: continue
                
                rev = w.copy()
                rev['front'] = w['back']
                rev['back'] = w['front']
                rev['direction'] = 'reverse'
                new_words.append(rev)
            
            random.shuffle(new_words)
            ps.daily_words = new_words
            flag_modified(ps, 'daily_words')
            
            # Reset results
            if ps.results and 'flashcards' in ps.results:
                ps.results['flashcards']['total'] = len(new_words)
                ps.results['flashcards']['correct'] = 0
                flag_modified(ps, 'results')
                
            db.session.commit()
            print(f"Updated Session {ps.id} to {len(new_words)} words.")
        else:
            print("Session already has > 15 words.")
    else:
        print("Session 2 not found.")

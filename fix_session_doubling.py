
from app import create_app,db
from app.models import ProgramSession
from sqlalchemy.orm.attributes import flag_modified
import random

app = create_app()

with app.app_context():
    # Find the most recent active session
    ps = ProgramSession.query.order_by(ProgramSession.started_at.desc()).first()
    
    if ps and ps.daily_words:
        words = ps.daily_words
        print(f"Current word count: {len(words)}")
        
        # Check if already doubled (naive check: count > 20)
        # Or just forcefully redo if it looks like the original batch (15)
        if len(words) <= 15:
            new_words = []
            seen_fronts = set()
            
            for w in words:
                # Original
                new_words.append(w)
                seen_fronts.add(w['front'])
                
                # Reverse
                # Avoid duplicates if by chance it's already there (unlikely if len=15)
                if w['back'] in seen_fronts: continue
                
                rev = w.copy()
                rev['front'] = w['back']
                rev['back'] = w['front']
                rev['direction'] = 'reverse'
                new_words.append(rev)
            
            random.shuffle(new_words)
            ps.daily_words = new_words
            
            # Reset counters/results to be safe or keep them?
            # User wants to restart anyway.
            # Let's reset the results for flashcards so they can start fresh
            if ps.results and 'flashcards' in ps.results:
                ps.results['flashcards']['total'] = len(new_words)
                ps.results['flashcards']['correct'] = 0
                flag_modified(ps, 'results')
            
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ps, 'daily_words')
            db.session.commit()
            print(f"Updated word count to: {len(new_words)}")
        else:
            print("Session already has > 15 words, likely already processed.")

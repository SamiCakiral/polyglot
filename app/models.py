from datetime import datetime
from app import db

# Association table for Card-Category many-to-many relationship
card_categories = db.Table('card_categories',
    db.Column('card_id', db.Integer, db.ForeignKey('card.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))  # Optional password
    is_pro = db.Column(db.Boolean, default=False)
    avatar_color = db.Column(db.String(7), default='#3498db')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    decks = db.relationship('Deck', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        from werkzeug.security import check_password_hash
        if not self.password_hash:
            return True
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_pro': self.is_pro,
            'avatar_color': self.avatar_color,
            'has_password': bool(self.password_hash),
            'created_at': self.created_at.isoformat()
        }


class Deck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    cards = db.relationship('Card', backref='deck', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='deck', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'card_count': len(self.cards),
            'category_count': len(self.categories),
            'created_at': self.created_at.isoformat()
        }
    
    def get_stats(self):
        total = len(self.cards)
        if total == 0:
            return {'total': 0, 'due': 0, 'new': 0, 'learning': 0, 'mastered': 0}
        
        now = datetime.utcnow()
        # Count considering both directions
        due = 0
        new = 0
        learning = 0
        mastered = 0
        
        for c in self.cards:
            # Check front→back direction
            if c.fb_repetitions == 0:
                new += 1
            elif c.fb_repetitions >= 5:
                mastered += 1
            else:
                learning += 1
            if c.fb_next_review and c.fb_next_review <= now:
                due += 1
                
            # Check back→front direction  
            if c.bf_repetitions == 0:
                new += 1
            elif c.bf_repetitions >= 5:
                mastered += 1
            else:
                learning += 1
            if c.bf_next_review and c.bf_next_review <= now:
                due += 1
        
        return {
            'total': total * 2,  # Both directions count
            'due': due,
            'new': new,
            'learning': learning,
            'mastered': mastered
        }


class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('deck.id'), nullable=False)
    front = db.Column(db.Text, nullable=False)
    back = db.Column(db.Text, nullable=False)
    
    # SM-2 fields for FRONT→BACK direction (type_back mode: see front, answer back)
    fb_easiness = db.Column(db.Float, default=2.5)
    fb_interval = db.Column(db.Integer, default=0)
    fb_repetitions = db.Column(db.Integer, default=0)
    fb_next_review = db.Column(db.DateTime, default=datetime.utcnow)
    fb_last_reviewed = db.Column(db.DateTime)
    
    # SM-2 fields for BACK→FRONT direction (type_front mode: see back, answer front)
    bf_easiness = db.Column(db.Float, default=2.5)
    bf_interval = db.Column(db.Integer, default=0)
    bf_repetitions = db.Column(db.Integer, default=0)
    bf_next_review = db.Column(db.DateTime, default=datetime.utcnow)
    bf_last_reviewed = db.Column(db.DateTime)
    
    # FSRS fields for FRONT→BACK direction
    fb_difficulty = db.Column(db.Float, default=0.0)  # 0 = new, 1-10 = difficulty
    fb_stability = db.Column(db.Float, default=0.0)   # 0 = new, days until R=90%
    
    # FSRS fields for BACK→FRONT direction
    bf_difficulty = db.Column(db.Float, default=0.0)
    bf_stability = db.Column(db.Float, default=0.0)
    
    # Legacy fields for compatibility (used by flip mode)
    easiness = db.Column(db.Float, default=2.5)
    interval = db.Column(db.Integer, default=0)
    repetitions = db.Column(db.Integer, default=0)
    next_review = db.Column(db.DateTime, default=datetime.utcnow)
    last_reviewed = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Many-to-many with categories
    categories = db.relationship('Category', secondary=card_categories, lazy='subquery',
                                 backref=db.backref('cards', lazy=True))
    reviews = db.relationship('Review', backref='card', lazy=True, cascade='all, delete-orphan')
    
    def get_sm2_for_direction(self, direction):
        """Get SM-2 values for a specific direction.
        direction: 'fb' (front→back), 'bf' (back→front), or 'flip' (uses fb)
        """
        if direction == 'fb' or direction == 'type_back' or direction == 'flip':
            return {
                'easiness': self.fb_easiness,
                'interval': self.fb_interval,
                'repetitions': self.fb_repetitions,
                'next_review': self.fb_next_review,
                'last_reviewed': self.fb_last_reviewed
            }
        elif direction == 'bf' or direction == 'type_front':
            return {
                'easiness': self.bf_easiness,
                'interval': self.bf_interval,
                'repetitions': self.bf_repetitions,
                'next_review': self.bf_next_review,
                'last_reviewed': self.bf_last_reviewed
            }
        else:  # default to fb
            return {
                'easiness': self.fb_easiness,
                'interval': self.fb_interval,
                'repetitions': self.fb_repetitions,
                'next_review': self.fb_next_review,
                'last_reviewed': self.fb_last_reviewed
            }
    
    def set_sm2_for_direction(self, direction, easiness, interval, repetitions, next_review):
        """Set SM-2 values for a specific direction.
        For 'flip' mode, updates BOTH directions.
        """
        now = datetime.utcnow()
        
        if direction == 'fb' or direction == 'type_back':
            self.fb_easiness = easiness
            self.fb_interval = interval
            self.fb_repetitions = repetitions
            self.fb_next_review = next_review
            self.fb_last_reviewed = now
        elif direction == 'bf' or direction == 'type_front':
            self.bf_easiness = easiness
            self.bf_interval = interval
            self.bf_repetitions = repetitions
            self.bf_next_review = next_review
            self.bf_last_reviewed = now
        else:  # flip mode - update BOTH directions
            self.fb_easiness = easiness
            self.fb_interval = interval
            self.fb_repetitions = repetitions
            self.fb_next_review = next_review
            self.fb_last_reviewed = now
            self.bf_easiness = easiness
            self.bf_interval = interval
            self.bf_repetitions = repetitions
            self.bf_next_review = next_review
            self.bf_last_reviewed = now
    
    def is_due_for_direction(self, direction):
        """Check if card is due for review in a specific direction."""
        sm2 = self.get_sm2_for_direction(direction)
        now = datetime.utcnow()
        return sm2['repetitions'] == 0 or (sm2['next_review'] and sm2['next_review'] <= now)
    
    def get_fsrs_for_direction(self, direction):
        """Get FSRS values (D, S, last_reviewed) for a specific direction."""
        if direction == 'fb' or direction == 'type_back' or direction == 'flip':
            return {
                'difficulty': self.fb_difficulty or 0.0,
                'stability': self.fb_stability or 0.0,
                'last_reviewed': self.fb_last_reviewed
            }
        else:  # bf or type_front
            return {
                'difficulty': self.bf_difficulty or 0.0,
                'stability': self.bf_stability or 0.0,
                'last_reviewed': self.bf_last_reviewed
            }
    
    def set_fsrs_for_direction(self, direction, difficulty, stability, next_review):
        """Set FSRS values for a specific direction."""
        now = datetime.utcnow()
        
        if direction == 'fb' or direction == 'type_back':
            self.fb_difficulty = difficulty
            self.fb_stability = stability
            self.fb_next_review = next_review
            self.fb_last_reviewed = now
            # Keep SM-2 fields in sync for compatibility
            self.fb_repetitions = (self.fb_repetitions or 0) + 1
            self.fb_interval = max(1, int(stability))
        elif direction == 'bf' or direction == 'type_front':
            self.bf_difficulty = difficulty
            self.bf_stability = stability
            self.bf_next_review = next_review
            self.bf_last_reviewed = now
            self.bf_repetitions = (self.bf_repetitions or 0) + 1
            self.bf_interval = max(1, int(stability))
        else:  # flip mode - update BOTH directions
            self.fb_difficulty = difficulty
            self.fb_stability = stability
            self.fb_next_review = next_review
            self.fb_last_reviewed = now
            self.fb_repetitions = (self.fb_repetitions or 0) + 1
            self.fb_interval = max(1, int(stability))
            self.bf_difficulty = difficulty
            self.bf_stability = stability
            self.bf_next_review = next_review
            self.bf_last_reviewed = now
            self.bf_repetitions = (self.bf_repetitions or 0) + 1
            self.bf_interval = max(1, int(stability))
    
    def get_retrievability_for_direction(self, direction):
        """Get current retrievability (0-1) for a specific direction."""
        from app.fsrs import calculate_retrievability
        
        fsrs = self.get_fsrs_for_direction(direction)
        if fsrs['stability'] <= 0:
            return 0.0  # New card
        
        # Calculate days since last review
        if fsrs['last_reviewed']:
            t = (datetime.utcnow() - fsrs['last_reviewed']).total_seconds() / 86400
        else:
            t = 0
        
        return calculate_retrievability(t, fsrs['stability'])
    
    def get_grade_for_direction(self, direction):
        """Get letter grade for a specific direction (uses FSRS Stability)."""
        from app.fsrs import stability_to_grade_letter
        
        fsrs = self.get_fsrs_for_direction(direction)
        return stability_to_grade_letter(fsrs['stability'])
    
    def get_grade_info_for_direction(self, direction):
        """Get full grade info for a specific direction (uses FSRS Stability)."""
        from app.fsrs import stability_to_grade_letter, get_grade_color_from_S, get_grade_description_from_S
        
        fsrs = self.get_fsrs_for_direction(direction)
        S = fsrs['stability']
        return {
            'grade': stability_to_grade_letter(S),
            'color': get_grade_color_from_S(S),
            'description': get_grade_description_from_S(S)
        }
    
    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'front': self.front,
            'back': self.back,
            'fb_stats': self.get_sm2_for_direction('fb'),
            'bf_stats': self.get_sm2_for_direction('bf'),
            'fb_grade': self.get_grade_for_direction('fb'),
            'bf_grade': self.get_grade_for_direction('bf'),
            'categories': [c.to_dict() for c in self.categories],
            'created_at': self.created_at.isoformat()
        }


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('deck.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3498db')  # Hex color
    
    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'name': self.name,
            'color': self.color,
            'card_count': len(self.cards)
        }
    
    def get_stats(self):
        total = len(self.cards)
        if total == 0:
            return {'total': 0, 'due': 0, 'new': 0, 'learning': 0, 'mastered': 0}
        
        now = datetime.utcnow()
        due = sum(1 for c in self.cards if c.next_review and c.next_review <= now)
        new = sum(1 for c in self.cards if c.repetitions == 0)
        learning = sum(1 for c in self.cards if 0 < c.repetitions < 5)
        mastered = sum(1 for c in self.cards if c.repetitions >= 5)
        
        return {
            'total': total,
            'due': due,
            'new': new,
            'learning': learning,
            'mastered': mastered
        }


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('card.id'), nullable=False)
    quality = db.Column(db.Integer, nullable=False)  # 0-5
    direction = db.Column(db.String(10), default='flip')  # 'fb', 'bf', or 'flip'
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'card_id': self.card_id,
            'quality': self.quality,
            'direction': self.direction,
            'reviewed_at': self.reviewed_at.isoformat()
        }


class TrainingSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('deck.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Store the entire session state as JSON
    # Structure:
    # {
    #    'card_ids': [...],
    #    'card_modes': [...],
    #    'card_directions': [...],
    #    'current_index': 0,
    #    'category_ids': [...],
    #    'mode': '...',
    #    'type_directions': [...],
    #    'results': {...},
    #    'reviewed_indices': [...]
    # }
    data = db.Column(db.JSON, nullable=False)
    
    deck_rel = db.relationship('Deck', backref=db.backref('sessions', lazy=True))


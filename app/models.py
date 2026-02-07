from datetime import datetime
from flask_login import UserMixin
from app import db

# Association table for Card-Category many-to-many relationship
card_categories = db.Table('card_categories',
    db.Column('card_id', db.Integer, db.ForeignKey('card.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))  # Password obligatoire pour nouveaux users
    is_pro = db.Column(db.Boolean, default=False)
    avatar_color = db.Column(db.String(7), default='#3498db')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Learner Profile (global settings for LLM context)
    # Enriched structure:
    # {
    #     'native_language': 'fr',
    #     'known_languages': [
    #         {'code': 'en', 'level': 'B2', 'years': 10},
    #         {'code': 'es', 'level': 'A2', 'years': 2}
    #     ],
    #     'learning_style': 'balanced',
    #     'correction_preference': 'moderate',
    #     'goals': ['conversation', 'travel'],
    #     'daily_time_available': 30
    # }
    learner_profile = db.Column(db.JSON, default=lambda: {
        'native_language': 'fr',
        'known_languages': [],  # [{code, level, years}]
        'learning_style': 'balanced',  # visual, auditory, reading, kinesthetic, balanced
        'correction_preference': 'moderate',  # strict, moderate, encouraging
        'goals': [],  # conversation, travel, work, exams, culture
        'daily_time_available': 30  # minutes
    })
    
    decks = db.relationship('Deck', backref='user', lazy=True, cascade='all, delete-orphan')
    languages = db.relationship('UserLanguage', backref='user', lazy=True, cascade='all, delete-orphan')
    
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
            'learner_profile': self.learner_profile,
            'created_at': self.created_at.isoformat()
        }


class UserLanguage(db.Model):
    """A language the user is learning with pillar progress tracking."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    language_code = db.Column(db.String(10), nullable=False)  # 'ja', 'tr', 'es', 'ru', 'it', 'zh', 'ko'
    
    # Evaluation
    estimated_level = db.Column(db.String(5), default='A0')  # CECRL: A0, A1, A2, B1, B2, C1, C2
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Progression piliers (JSON)
    # Format: {
    #     "hiragana": {"status": "completed", "mastery": 100, "deck_id": 123, "completed_at": "..."},
    #     "katakana": {"status": "in_progress", "mastery": 45, "deck_id": 124},
    #     "particles": {"status": "locked", "mastery": 0}
    # }
    pillar_progress = db.Column(db.JSON, default=dict)
    
    # Config
    show_romanization = db.Column(db.Boolean, default=True)  # Show romaji/pinyin etc.
    bridge_language = db.Column(db.String(10))  # Language to use for explanations (e.g., 'en' if user knows English well)
    
    # Statistics
    total_study_time = db.Column(db.Integer, default=0)  # in minutes
    sessions_completed = db.Column(db.Integer, default=0)
    
    def get_pillar_status(self, pillar_id):
        """Get status for a specific pillar."""
        if not self.pillar_progress:
            return {'status': 'locked', 'mastery': 0}
        return self.pillar_progress.get(pillar_id, {'status': 'locked', 'mastery': 0})
    
    def update_pillar(self, pillar_id, status=None, mastery=None, deck_id=None):
        """Update a pillar's progress."""
        if self.pillar_progress is None:
            self.pillar_progress = {}
        
        if pillar_id not in self.pillar_progress:
            self.pillar_progress[pillar_id] = {'status': 'locked', 'mastery': 0}
        
        if status:
            self.pillar_progress[pillar_id]['status'] = status
            if status == 'completed':
                self.pillar_progress[pillar_id]['completed_at'] = datetime.utcnow().isoformat()
        if mastery is not None:
            self.pillar_progress[pillar_id]['mastery'] = mastery
        if deck_id:
            self.pillar_progress[pillar_id]['deck_id'] = deck_id
    
    def get_completed_pillars_count(self):
        """Count completed pillars (ignore special keys like _exercise_difficulty)."""
        if not self.pillar_progress:
            return 0
        return sum(1 for k, p in self.pillar_progress.items() 
                   if not k.startswith('_') and isinstance(p, dict) and p.get('status') == 'completed')
    
    def get_total_mastery(self):
        """Calculate average mastery across all started pillars (ignore special keys)."""
        if not self.pillar_progress:
            return 0
        started = [p for k, p in self.pillar_progress.items() 
                   if not k.startswith('_') and isinstance(p, dict) and p.get('status') != 'locked']
        if not started:
            return 0
        return sum(p.get('mastery', 0) for p in started) / len(started)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'language_code': self.language_code,
            'estimated_level': self.estimated_level,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'pillar_progress': self.pillar_progress,
            'show_romanization': self.show_romanization,
            'bridge_language': self.bridge_language,
            'total_study_time': self.total_study_time,
            'sessions_completed': self.sessions_completed,
            'completed_pillars': self.get_completed_pillars_count(),
            'total_mastery': self.get_total_mastery()
        }


class PillarExercise(db.Model):
    """Generated exercise for pillar practice (conjugation, fill_blank, transform, etc.)."""
    __tablename__ = 'pillar_exercise'
    id = db.Column(db.Integer, primary_key=True)
    language_code = db.Column(db.String(10), nullable=False)
    exercise_type = db.Column(db.String(30), nullable=False)  # conjugation, fill_blank, transform, word_order, particles, gender
    pillar_id = db.Column(db.String(50))  # optional, some exercises are transversal
    difficulty = db.Column(db.Integer, default=1)  # 1-5
    content = db.Column(db.JSON, nullable=False)  # structure varies by type
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(50))

    results = db.relationship('PillarExerciseResult', backref='exercise', lazy=True, cascade='all, delete-orphan')


class PillarExerciseResult(db.Model):
    """User result for a pillar exercise attempt."""
    __tablename__ = 'pillar_exercise_result'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('pillar_exercise.id'), nullable=False)
    language_code = db.Column(db.String(10), nullable=False)
    exercise_type = db.Column(db.String(30), nullable=False)
    correct = db.Column(db.Boolean, nullable=False)
    user_answer = db.Column(db.String(500))
    time_taken_ms = db.Column(db.Integer)
    difficulty = db.Column(db.Integer)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('pillar_exercise_results', lazy=True))


class Assessment(db.Model):
    """CECR level assessment (controle de passage de niveau)."""
    __tablename__ = 'assessment'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    language_code = db.Column(db.String(10), nullable=False)
    target_level = db.Column(db.String(5), nullable=False)  # A1, A2, B1, B2, C1, C2
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, passed, failed
    total_score = db.Column(db.Float)  # 0-100
    passing_score = db.Column(db.Float, default=65)
    time_limit_minutes = db.Column(db.Integer)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    feedback = db.Column(db.JSON)  # LLM-generated overall feedback

    sections = db.relationship('AssessmentSection', backref='assessment', lazy=True,
                               cascade='all, delete-orphan', order_by='AssessmentSection.order_idx')
    user = db.relationship('User', backref=db.backref('assessments', lazy=True))

    def calculate_score(self):
        """Calculate total score from sections."""
        total_max = sum(s.max_points for s in self.sections if s.max_points)
        total_earned = sum(s.earned_points or 0 for s in self.sections)
        if total_max == 0:
            return 0
        return round((total_earned / total_max) * 100, 1)

    def is_passed(self):
        """Check if the assessment is passed."""
        return self.total_score is not None and self.total_score >= (self.passing_score or 65)


class AssessmentSection(db.Model):
    """A section within a CECR assessment."""
    __tablename__ = 'assessment_section'
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    section_type = db.Column(db.String(30), nullable=False)  # grammar, vocabulary, reading, listening, writing
    order_idx = db.Column(db.Integer, default=0)
    content = db.Column(db.JSON)  # LLM-generated questions/content
    max_points = db.Column(db.Integer, default=20)
    earned_points = db.Column(db.Integer)
    user_answers = db.Column(db.JSON)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    feedback = db.Column(db.JSON)  # Per-section LLM feedback


class Deck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    is_program_deck = db.Column(db.Boolean, default=False)  # Auto-created for training programs
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
    
    # Lego Slot Type (e.g. SUJET, VERBE, OBJET)
    slot_type = db.Column(db.String(50), nullable=True)
    
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
    
    def apply_fsrs_penalty(self, direction='fb', penalty_factor=0.7):
        """Apply penalty to stability (used when word is revealed in Word Bank).
        
        Reduces stability by penalty_factor (default 30% reduction).
        Sets next_review to tomorrow.
        """
        from datetime import timedelta
        now = datetime.utcnow()
        tomorrow = now + timedelta(days=1)
        
        if direction in ('fb', 'both'):
            self.fb_stability = max(0.5, (self.fb_stability or 1) * penalty_factor)
            self.fb_next_review = tomorrow
        if direction in ('bf', 'both'):
            self.bf_stability = max(0.5, (self.bf_stability or 1) * penalty_factor)
            self.bf_next_review = tomorrow
    
    @property
    def is_learned(self):
        """Card is considered learned when both directions are B+ or better (stability >= 60 days)."""
        return (self.fb_stability or 0) >= 60 and (self.bf_stability or 0) >= 60
    
    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'front': self.front,
            'back': self.back,
            'slot_type': self.slot_type,
            'fb_stats': self.get_sm2_for_direction('fb'),
            'bf_stats': self.get_sm2_for_direction('bf'),
            'fb_grade': self.get_grade_for_direction('fb'),
            'bf_grade': self.get_grade_for_direction('bf'),
            'is_learned': self.is_learned,
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


class TrainingProgram(db.Model):
    """Configuration for a custom training program."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deck_id = db.Column(db.Integer, db.ForeignKey('deck.id'), nullable=False)
    
    # Metadata
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_language = db.Column(db.String(50), default='italian')
    native_language = db.Column(db.String(50), default='french')
    
    # Exercise configuration (order + enabled status)
    exercise_config = db.Column(db.JSON, default=lambda: {
        'order': ['flashcards', 'git_input', 'gym', 'shadowing', 'git_output', 'writing'],
        'enabled': {
            'flashcards': True,
            'git_input': True,
            'gym': True,
            'shadowing': True,
            'git_output': True,
            'writing': True
        },
        'duration_target': 30
    })
    
    # Program-specific learner profile (overrides User.learner_profile)
    program_profile = db.Column(db.JSON, default=lambda: {
        'current_level': 'A2',  # CECRL level
        'years_learning': 0,
        'goals': ['conversation', 'travel'],  # conversation, travel, work, exams, culture
        'correction_strictness': 'moderate',  # strict, moderate, encouraging
        'focus_areas': []  # grammar, vocabulary, pronunciation, listening, writing
    })
    
    # Lego templates (phrase structures)
    lego_templates = db.Column(db.JSON, default=lambda: [
        {
            "pattern": "[SUJET] deve [VERBE] [OBJET]",
            "slots": {
                "SUJET": {"type": "subject"},
                "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
                "OBJET": {"type": "object", "match_context": "VERBE"}
            }
        },
        {
            "pattern": "[SUJET] non può [VERBE] [OBJET]",
            "slots": {
                "SUJET": {"type": "subject"},
                "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
                "OBJET": {"type": "object", "match_context": "VERBE"}
            }
        },
        {
            "pattern": "[SUJET] vuole [VERBE] [OBJET]",
            "slots": {
                "SUJET": {"type": "subject"},
                "VERBE": {"type": "verb", "tags": ["Tag:Action"]},
                "OBJET": {"type": "object", "match_context": "VERBE"}
            }
        }
    ])
    
    # FSI Mutations (available transformations)
    fsi_mutations = db.Column(db.JSON, default=lambda: ['NEGATION', 'FUTUR', 'PASSE', 'PLURIEL', 'QUESTION'])
    
    # Shadowing resources (YouTube links, podcasts)
    shadowing_resources = db.Column(db.JSON, default=list)
    
    # Daily themes (rotation)
    daily_themes = db.Column(db.JSON, default=list)
    current_theme_index = db.Column(db.Integer, default=0)
    
    # Custom LLM prompts
    llm_prompts = db.Column(db.JSON, default=lambda: {
        'text_generation': "Génère un texte court (50-80 mots) en {target_language} sur le thème: {theme}. Niveau A2, phrases simples.",
        'quest_generation': "Crée une mission courte en {native_language} demandant à l'utilisateur de raconter une anecdote utilisant ces mots: {words}",
        'correction': "Tu es un correcteur strict. Corrige ce texte en {target_language}. Affiche les erreurs et explique-les.",
        'lego_generation': "Génère 5 templates de structures de phrases pour apprendre {target_language} au niveau A2. Format JSON: [{\"pattern\": \"...\", \"example\": \"...\"}]"
    })
    
    # Economy
    daily_cheat_tokens = db.Column(db.Integer, default=3)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('programs', lazy=True))
    deck = db.relationship('Deck', backref=db.backref('programs', lazy=True))
    
    def get_current_theme(self):
        """Get the current theme based on rotation."""
        if not self.daily_themes:
            return None
        return self.daily_themes[self.current_theme_index % len(self.daily_themes)]
    
    def advance_theme(self):
        """Move to the next theme in rotation."""
        if self.daily_themes:
            self.current_theme_index = (self.current_theme_index + 1) % len(self.daily_themes)
    
    def get_enabled_exercises(self):
        """Get list of enabled exercises in order."""
        config = self.exercise_config or {}
        order = config.get('order', [])
        enabled = config.get('enabled', {})
        return [ex for ex in order if enabled.get(ex, False)]
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'target_language': self.target_language,
            'native_language': self.native_language,
            'deck_id': self.deck_id,
            'deck_name': self.deck.name if self.deck else None,
            'exercise_config': self.exercise_config,
            'program_profile': self.program_profile,
            'lego_templates': self.lego_templates,
            'fsi_mutations': self.fsi_mutations,
            'shadowing_resources': self.shadowing_resources,
            'daily_themes': self.daily_themes,
            'current_theme': self.get_current_theme(),
            'llm_prompts': self.llm_prompts,
            'daily_cheat_tokens': self.daily_cheat_tokens,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProgramSession(db.Model):
    """Active training session from a program."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_date = db.Column(db.Date, default=lambda: datetime.utcnow().date())
    
    # Session state
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    current_module = db.Column(db.String(50), default='flashcards')
    module_index = db.Column(db.Integer, default=0)
    
    # Economy - tokens for SOS/cheat
    cheat_tokens_remaining = db.Column(db.Integer, default=3)
    
    # Daily generated words [{front, back, category}]
    daily_words = db.Column(db.JSON, default=list)
    daily_words_theme = db.Column(db.String(200))
    
    # Gym exercises done (for tracking)
    gym_exercises_done = db.Column(db.JSON, default=list)
    
    # Smart writing text
    writing_quest = db.Column(db.Text)
    writing_text = db.Column(db.Text)
    writing_feedback = db.Column(db.Text)
    
    # Debt words - words user asked for translation (SOS or word bank)
    # Format: [{front: "word", back: "translation", source: "sos|wordbank"}]
    debt_words = db.Column(db.JSON, default=list)
    
    # Results per module
    results = db.Column(db.JSON, default=lambda: {
        'flashcards': {'correct': 0, 'total': 0},
        'git_input': {'completed': False, 'score': None},
        'gym': {'lego_done': 0, 'fsi_done': 0},
        'shadowing': {'done': 0, 'total': 0},
        'git_output': {'completed': False, 'diff_errors': 0},
        'writing': {'completed': False, 'tokens_used': 0}
    })
    
    # Relationships
    program = db.relationship('TrainingProgram', backref=db.backref('sessions', lazy=True))
    user = db.relationship('User', backref=db.backref('program_sessions', lazy=True))
    
    def get_current_module_name(self):
        """Get display name for current module."""
        names = {
            'flashcards': '📚 Vocabulaire',
            'git_input': '📝 Git Input',
            'gym': '🏋️ The Gym',
            'shadowing': '🎧 Shadowing',
            'git_output': '🔄 Git Output',
            'writing': '✍️ Smart Writing'
        }
        return names.get(self.current_module, self.current_module)
    
    def add_debt_word(self, front, back, source='wordbank'):
        """Add a word to debt list (will be reviewed tomorrow)."""
        if self.debt_words is None:
            self.debt_words = []
        # Avoid duplicates
        for w in self.debt_words:
            if w.get('front') == front:
                return
        self.debt_words.append({
            'front': front,
            'back': back,
            'source': source,
            'added_at': datetime.utcnow().isoformat()
        })
    
    def use_cheat_token(self):
        """Use a cheat token, returns False if none remaining."""
        if self.cheat_tokens_remaining <= 0:
            return False
        self.cheat_tokens_remaining -= 1
        return True
    
    def to_dict(self):
        return {
            'id': self.id,
            'program_id': self.program_id,
            'session_date': self.session_date.isoformat() if self.session_date else None,
            'current_module': self.current_module,
            'module_index': self.module_index,
            'cheat_tokens_remaining': self.cheat_tokens_remaining,
            'daily_words_count': len(self.daily_words or []),
            'debt_words_count': len(self.debt_words or []),
            'results': self.results,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class DailyText(db.Model):
    """Stores Git Input texts for J+1 recall in Git Output."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_date = db.Column(db.Date, default=lambda: datetime.utcnow().date())
    
    # Theme used for generation
    theme = db.Column(db.String(200))
    
    # Original text in target_language (e.g., Italian)
    original_text = db.Column(db.Text, nullable=False)
    
    # User's translation to native_language (e.g., French)
    user_translation = db.Column(db.Text)
    
    # LLM correction of user translation (optional)
    llm_correction = db.Column(db.Text)
    
    # Has this been used for Git Output?
    used_for_output = db.Column(db.Boolean, default=False)
    
    # User's attempt to recode (Git Output)
    user_recode = db.Column(db.Text)
    
    # Diff results (list of errors)
    diff_results = db.Column(db.JSON)
    
    # Relationships
    program = db.relationship('TrainingProgram', backref=db.backref('daily_texts', lazy=True))
    user = db.relationship('User', backref=db.backref('daily_texts', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'program_id': self.program_id,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'theme': self.theme,
            'original_text': self.original_text,
            'user_translation': self.user_translation,
            'used_for_output': self.used_for_output
        }


class LegoStructure(db.Model):
    """Phrase structure templates with FSRS-like scheduling for rotation."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    
    # The structure itself
    pattern = db.Column(db.String(500), nullable=False)  # "Quand [SUJET] [VERBE] [LIEU], [SUJET] [VERBE2]"
    example_target = db.Column(db.String(500))  # Example in target language
    example_native = db.Column(db.String(500))  # Translation in native language
    
    # Description/explanation of when to use this structure
    description = db.Column(db.Text)
    
    # FSRS-like scheduling for rotation
    stability = db.Column(db.Float, default=1.0)  # Days until R=90%
    difficulty = db.Column(db.Float, default=0.5)  # 0-1 scale
    due_date = db.Column(db.Date)  # When this structure is due for practice
    last_review = db.Column(db.Date)  # Last time user practiced this
    review_count = db.Column(db.Integer, default=0)  # How many times practiced
    
    # Metadata
    complexity_level = db.Column(db.String(10), default='A2')  # CECRL level: A1, A2, B1, B2, C1, C2
    tags = db.Column(db.JSON)  # ["modal", "temporal", "conditionnel", "negation"]
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    program = db.relationship('TrainingProgram', backref=db.backref('lego_structures', lazy=True))
    
    def update_after_review(self, grade):
        """Update FSRS-like scheduling after a review.
        
        grade: 1 (fail), 2 (hard), 3 (good), 4 (easy)
        """
        from datetime import timedelta
        
        self.last_review = datetime.utcnow().date()
        self.review_count += 1
        
        # Simple FSRS-like algorithm
        if grade == 1:  # Fail - reset
            self.stability = 1.0
            self.difficulty = min(1.0, self.difficulty + 0.1)
        elif grade == 2:  # Hard
            self.stability = self.stability * 1.2
            self.difficulty = min(1.0, self.difficulty + 0.05)
        elif grade == 3:  # Good
            self.stability = self.stability * 2.0
            self.difficulty = max(0.0, self.difficulty - 0.02)
        else:  # Easy
            self.stability = self.stability * 2.5
            self.difficulty = max(0.0, self.difficulty - 0.05)
        
        # Calculate next due date
        interval_days = max(1, int(self.stability))
        self.due_date = datetime.utcnow().date() + timedelta(days=interval_days)
    
    def to_dict(self):
        return {
            'id': self.id,
            'program_id': self.program_id,
            'pattern': self.pattern,
            'example_target': self.example_target,
            'example_native': self.example_native,
            'description': self.description,
            'stability': self.stability,
            'difficulty': self.difficulty,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'last_review': self.last_review.isoformat() if self.last_review else None,
            'review_count': self.review_count,
            'complexity_level': self.complexity_level,
            'tags': self.tags,
            'is_active': self.is_active
        }


class ShadowingVideo(db.Model):
    """YouTube videos for shadowing practice."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    
    # Video info
    url = db.Column(db.String(500), nullable=False)  # YouTube URL
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    duration_seconds = db.Column(db.Integer)  # Total video duration
    
    # Specific segments to use (optional - if empty, use random)
    # Format: [{"start": 30, "end": 60, "description": "Dialogue au restaurant"}]
    segments = db.Column(db.JSON, default=list)
    
    # Usage tracking
    times_used = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    program = db.relationship('TrainingProgram', backref=db.backref('shadowing_videos', lazy=True))
    
    def get_random_segment(self, duration=30):
        """Get a random segment from the video.
        
        If segments are defined, pick one randomly.
        Otherwise, pick a random start time.
        
        Returns: {"start": seconds, "end": seconds}
        """
        import random
        
        if self.segments:
            return random.choice(self.segments)
        
        # Random segment
        if self.duration_seconds and self.duration_seconds > duration:
            max_start = self.duration_seconds - duration
            start = random.randint(0, max_start)
            return {"start": start, "end": start + duration}
        
        # Fallback: start from beginning
        return {"start": 0, "end": duration}
    
    def get_youtube_embed_url(self, start_seconds=0):
        """Convert YouTube URL to embed URL with start time."""
        import re
        
        # Extract video ID from various YouTube URL formats
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        ]
        
        video_id = None
        for pattern in patterns:
            match = re.search(pattern, self.url)
            if match:
                video_id = match.group(1)
                break
        
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}?start={start_seconds}&autoplay=1"
        
        return self.url
    
    def mark_used(self):
        """Mark video as used."""
        self.times_used += 1
        self.last_used = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'program_id': self.program_id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'duration_seconds': self.duration_seconds,
            'segments': self.segments,
            'times_used': self.times_used,
            'is_active': self.is_active
        }


class DebtWord(db.Model):
    """Words that user revealed/asked for - must be reviewed tomorrow."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    
    # The word
    word_front = db.Column(db.String(200), nullable=False)  # Target language
    word_back = db.Column(db.String(200), nullable=False)   # Native language
    
    # Source of the debt
    source = db.Column(db.String(50), nullable=False)  # 'wordbank', 'chatbot', 'sos'
    
    # Context (optional - what exercise were they doing)
    context = db.Column(db.String(200))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_date = db.Column(db.Date, default=lambda: datetime.utcnow().date())
    
    # Processing status
    processed = db.Column(db.Boolean, default=False)  # True when converted to flashcard or added to daily_words
    processed_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('debt_words', lazy=True))
    program = db.relationship('TrainingProgram', backref=db.backref('debt_words', lazy=True))
    
    @classmethod
    def add_debt(cls, user_id, program_id, word_front, word_back, source, context=None):
        """Add a debt word, avoiding duplicates for the same day."""
        from app import db
        
        today = datetime.utcnow().date()
        
        # Check if already exists for today
        existing = cls.query.filter_by(
            user_id=user_id,
            program_id=program_id,
            word_front=word_front,
            created_date=today,
            processed=False
        ).first()
        
        if existing:
            return existing
        
        debt = cls(
            user_id=user_id,
            program_id=program_id,
            word_front=word_front,
            word_back=word_back,
            source=source,
            context=context
        )
        db.session.add(debt)
        return debt
    
    @classmethod
    def get_unprocessed_debts(cls, user_id, program_id):
        """Get all unprocessed debts for a user/program."""
        return cls.query.filter_by(
            user_id=user_id,
            program_id=program_id,
            processed=False
        ).order_by(cls.created_at.asc()).all()
    
    def mark_processed(self):
        """Mark debt as processed."""
        self.processed = True
        self.processed_at = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'word_front': self.word_front,
            'word_back': self.word_back,
            'source': self.source,
            'context': self.context,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed': self.processed
        }


class WeeklyTheme(db.Model):
    """Theme hebdomadaire genere par LLM avec decoupe journaliere."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Semaine (ISO week number + year)
    year = db.Column(db.Integer, nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    
    # Theme principal
    main_theme = db.Column(db.String(200), nullable=False)
    theme_description = db.Column(db.Text)
    
    # Decoupe journaliere (JSON)
    # Format: [
    #   {day: 1, focus: "Arrivee, demander son chemin", vocab_domains: ["directions", "transport"]},
    #   {day: 2, focus: "Commander au restaurant", vocab_domains: ["food", "politeness"]},
    #   ...
    # ]
    daily_breakdown = db.Column(db.JSON, default=list)
    
    # Metadata generation
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    based_on_goals = db.Column(db.JSON)
    based_on_level = db.Column(db.String(10))
    
    # Historique (pour eviter repetitions)
    previous_themes_considered = db.Column(db.JSON, default=list)
    
    # Statut
    completed = db.Column(db.Boolean, default=False)
    days_completed = db.Column(db.Integer, default=0)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('weekly_themes', lazy=True))
    program = db.relationship('TrainingProgram', backref=db.backref('weekly_themes', lazy=True))
    
    def get_day_focus(self, day_index: int) -> dict:
        """Get the focus for a specific day (0-6)."""
        if not self.daily_breakdown or day_index >= len(self.daily_breakdown):
            return {'focus': 'General practice', 'vocab_domains': ['general']}
        return self.daily_breakdown[day_index]
    
    def to_dict(self):
        return {
            'id': self.id,
            'year': self.year,
            'week_number': self.week_number,
            'main_theme': self.main_theme,
            'theme_description': self.theme_description,
            'daily_breakdown': self.daily_breakdown,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'based_on_goals': self.based_on_goals,
            'based_on_level': self.based_on_level,
            'completed': self.completed,
            'days_completed': self.days_completed
        }



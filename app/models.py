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
    is_pro = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    decks = db.relationship('Deck', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_pro': self.is_pro,
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


class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('deck.id'), nullable=False)
    front = db.Column(db.Text, nullable=False)
    back = db.Column(db.Text, nullable=False)
    
    # SM-2 algorithm fields
    easiness = db.Column(db.Float, default=2.5)  # E-Factor
    interval = db.Column(db.Integer, default=0)   # Days until next review
    repetitions = db.Column(db.Integer, default=0)
    next_review = db.Column(db.DateTime, default=datetime.utcnow)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_reviewed = db.Column(db.DateTime)
    
    # Many-to-many with categories
    categories = db.relationship('Category', secondary=card_categories, lazy='subquery',
                                 backref=db.backref('cards', lazy=True))
    reviews = db.relationship('Review', backref='card', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'front': self.front,
            'back': self.back,
            'easiness': self.easiness,
            'interval': self.interval,
            'repetitions': self.repetitions,
            'next_review': self.next_review.isoformat() if self.next_review else None,
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
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'card_id': self.card_id,
            'quality': self.quality,
            'reviewed_at': self.reviewed_at.isoformat()
        }

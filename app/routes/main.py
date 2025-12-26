from flask import Blueprint, render_template, redirect, url_for
from app.models import Deck, User
from app import db
from datetime import datetime

bp = Blueprint('main', __name__)


def get_or_create_default_user():
    """Get or create a default user for demo purposes."""
    user = User.query.first()
    if not user:
        user = User(username='demo', is_pro=True)
        db.session.add(user)
        db.session.commit()
    return user


@bp.route('/')
def index():
    """Dashboard - main page showing all decks and global stats."""
    user = get_or_create_default_user()
    decks = Deck.query.filter_by(user_id=user.id).all()
    
    # Calculate global stats
    total_cards = sum(len(d.cards) for d in decks)
    now = datetime.utcnow()
    due_cards = sum(
        sum(1 for c in d.cards if c.next_review and c.next_review <= now)
        for d in decks
    )
    new_cards = sum(
        sum(1 for c in d.cards if c.repetitions == 0)
        for d in decks
    )
    
    return render_template('dashboard.html', 
                           user=user,
                           decks=decks,
                           total_cards=total_cards,
                           due_cards=due_cards,
                           new_cards=new_cards)

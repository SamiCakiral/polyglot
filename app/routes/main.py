from flask import Blueprint, render_template, redirect, url_for
from app.models import Deck, User, Card, Review
from app import db
from datetime import datetime, timedelta

bp = Blueprint('main', __name__)


def get_or_create_default_user():
    """Get or create a default user for demo purposes."""
    user = User.query.first()
    if not user:
        user = User(username='Sami', is_pro=True)
        db.session.add(user)
        db.session.commit()
    return user


def get_recommendations(decks):
    """Generate smart recommendations based on user's learning data."""
    recommendations = []
    now = datetime.utcnow()
    
    for deck in decks:
        # Count due cards in each direction
        fb_due = 0
        bf_due = 0
        fb_new = 0
        bf_new = 0
        difficult_cards = 0
        
        for card in deck.cards:
            # Front->Back direction
            if card.fb_repetitions == 0:
                fb_new += 1
            elif card.fb_next_review and card.fb_next_review <= now:
                fb_due += 1
            
            # Back->Front direction
            if card.bf_repetitions == 0:
                bf_new += 1
            elif card.bf_next_review and card.bf_next_review <= now:
                bf_due += 1
            
            # Difficult cards (low easiness)
            if card.fb_easiness and card.fb_easiness < 2.0:
                difficult_cards += 1
            if card.bf_easiness and card.bf_easiness < 2.0:
                difficult_cards += 1
        
        total_due = fb_due + bf_due
        total_new = fb_new + bf_new
        
        if total_due > 0:
            recommendations.append({
                'type': 'due',
                'priority': 1,
                'deck': deck,
                'count': total_due,
                'message': f'{total_due} carte{"s" if total_due > 1 else ""} à réviser',
                'icon': '⏰',
                'action': 'Réviser maintenant',
                'action_url': f'/train/deck/{deck.id}'
            })
        
        if total_new > 10:
            recommendations.append({
                'type': 'new',
                'priority': 2,
                'deck': deck,
                'count': total_new,
                'message': f'{total_new} nouvelles cartes à apprendre',
                'icon': '🆕',
                'action': 'Commencer',
                'action_url': f'/train/deck/{deck.id}'
            })
        
        if difficult_cards > 5:
            recommendations.append({
                'type': 'difficult',
                'priority': 3,
                'deck': deck,
                'count': difficult_cards,
                'message': f'{difficult_cards} cartes difficiles',
                'icon': '💪',
                'action': 'Pratiquer',
                'action_url': f'/train/deck/{deck.id}'
            })
    
    # Sort by priority
    recommendations.sort(key=lambda x: x['priority'])
    return recommendations[:5]  # Top 5


def get_streak_info(user):
    """Calculate user's study streak."""
    now = datetime.utcnow()
    today = now.date()
    
    # Get reviews from last 30 days
    reviews = Review.query.filter(
        Review.reviewed_at >= now - timedelta(days=30)
    ).order_by(Review.reviewed_at.desc()).all()
    
    if not reviews:
        return {'current': 0, 'best': 0, 'today': 0}
    
    # Count reviews today
    today_count = sum(1 for r in reviews if r.reviewed_at.date() == today)
    
    # Calculate streak
    streak = 0
    check_date = today
    
    while True:
        day_reviews = [r for r in reviews if r.reviewed_at.date() == check_date]
        if day_reviews:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
    
    return {'current': streak, 'best': streak, 'today': today_count}


@bp.route('/')
def index():
    """Dashboard - main page showing all decks and global stats."""
    user = get_or_create_default_user()
    decks = Deck.query.filter_by(user_id=user.id).all()
    
    now = datetime.utcnow()
    
    # Calculate global stats considering both directions
    total_cards = 0
    due_cards = 0
    new_cards = 0
    learning_cards = 0
    mastered_cards = 0
    
    for deck in decks:
        for card in deck.cards:
            total_cards += 2  # Both directions
            
            # FB direction
            if card.fb_repetitions == 0:
                new_cards += 1
            elif card.fb_repetitions >= 5:
                mastered_cards += 1
            else:
                learning_cards += 1
            if card.fb_next_review and card.fb_next_review <= now:
                due_cards += 1
            
            # BF direction
            if card.bf_repetitions == 0:
                new_cards += 1
            elif card.bf_repetitions >= 5:
                mastered_cards += 1
            else:
                learning_cards += 1
            if card.bf_next_review and card.bf_next_review <= now:
                due_cards += 1
    
    recommendations = get_recommendations(decks)
    streak = get_streak_info(user)
    
    return render_template('dashboard.html', 
                           user=user,
                           decks=decks,
                           total_cards=total_cards,
                           due_cards=due_cards,
                           new_cards=new_cards,
                           learning_cards=learning_cards,
                           mastered_cards=mastered_cards,
                           recommendations=recommendations,
                           streak=streak)

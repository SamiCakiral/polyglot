from flask import Blueprint, render_template
from app.models import Deck, Card, Category, Review, User
from app.routes.main import get_or_create_default_user
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint('stats', __name__, url_prefix='/stats')


@bp.route('/')
def global_stats():
    """Show global statistics across all decks."""
    user = get_or_create_default_user()
    decks = Deck.query.filter_by(user_id=user.id).all()
    
    # Basic stats
    total_decks = len(decks)
    total_cards = sum(len(d.cards) for d in decks)
    total_reviews = Review.query.join(Card).join(Deck).filter(Deck.user_id == user.id).count()
    
    # Due and new cards
    now = datetime.utcnow()
    due_cards = sum(
        sum(1 for c in d.cards if c.next_review and c.next_review <= now)
        for d in decks
    )
    new_cards = sum(
        sum(1 for c in d.cards if c.repetitions == 0)
        for d in decks
    )
    
    # Card status breakdown
    learning = sum(sum(1 for c in d.cards if 0 < c.repetitions < 5) for d in decks)
    mastered = sum(sum(1 for c in d.cards if c.repetitions >= 5) for d in decks)
    
    # Reviews in last 7 days
    week_ago = now - timedelta(days=7)
    recent_reviews = Review.query.join(Card).join(Deck).filter(
        Deck.user_id == user.id,
        Review.reviewed_at >= week_ago
    ).count()
    
    # Daily review counts for chart
    daily_reviews = []
    for i in range(7):
        day = now - timedelta(days=6-i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        count = Review.query.join(Card).join(Deck).filter(
            Deck.user_id == user.id,
            Review.reviewed_at >= day_start,
            Review.reviewed_at < day_end
        ).count()
        
        daily_reviews.append({
            'date': day.strftime('%d/%m'),
            'count': count
        })
    
    # Per-deck stats
    deck_stats = []
    for deck in decks:
        stats = deck.get_stats()
        deck_stats.append({
            'deck': deck,
            'stats': stats
        })
    
    return render_template('stats/global.html',
                           total_decks=total_decks,
                           total_cards=total_cards,
                           total_reviews=total_reviews,
                           due_cards=due_cards,
                           new_cards=new_cards,
                           learning=learning,
                           mastered=mastered,
                           recent_reviews=recent_reviews,
                           daily_reviews=daily_reviews,
                           deck_stats=deck_stats)


@bp.route('/deck/<int:deck_id>')
def deck_stats(deck_id):
    """Show statistics for a specific deck."""
    from app.grades import calculate_deck_progress, get_grade_distribution, GRADES
    
    deck = Deck.query.get_or_404(deck_id)
    stats = deck.get_stats()
    
    now = datetime.utcnow()
    
    # Category breakdown
    category_stats = []
    for category in deck.categories:
        cat_stats = category.get_stats()
        category_stats.append({
            'category': category,
            'stats': cat_stats
        })
    
    # Average easiness
    if deck.cards:
        avg_easiness = sum(c.easiness for c in deck.cards) / len(deck.cards)
    else:
        avg_easiness = 2.5
    
    # Grade distribution for front→back direction
    fb_grade_dist = get_grade_distribution(deck.cards, 'fb')
    fb_progress = calculate_deck_progress(deck.cards, 'fb')
    
    # Grade distribution for back→front direction
    bf_grade_dist = get_grade_distribution(deck.cards, 'bf')
    bf_progress = calculate_deck_progress(deck.cards, 'bf')
    
    # Combined grade info (for histograms)
    grade_colors = {g[0]: g[3] for g in GRADES}
    grade_order = [g[0] for g in reversed(GRADES)]  # E to A+
    
    # Review history
    week_ago = now - timedelta(days=7)
    reviews = Review.query.join(Card).filter(
        Card.deck_id == deck_id,
        Review.reviewed_at >= week_ago
    ).all()
    
    # Success rate
    if reviews:
        success_count = sum(1 for r in reviews if r.quality >= 3)
        success_rate = (success_count / len(reviews)) * 100
    else:
        success_rate = 0
    
    # Daily breakdown
    daily_reviews = []
    for i in range(7):
        day = now - timedelta(days=6-i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        count = Review.query.join(Card).filter(
            Card.deck_id == deck_id,
            Review.reviewed_at >= day_start,
            Review.reviewed_at < day_end
        ).count()
        
        daily_reviews.append({
            'date': day.strftime('%d/%m'),
            'count': count
        })
    
    return render_template('stats/deck.html',
                           deck=deck,
                           stats=stats,
                           category_stats=category_stats,
                           avg_easiness=avg_easiness,
                           success_rate=success_rate,
                           total_reviews=len(reviews),
                           daily_reviews=daily_reviews,
                           fb_grade_dist=fb_grade_dist,
                           bf_grade_dist=bf_grade_dist,
                           fb_progress=fb_progress,
                           bf_progress=bf_progress,
                           grade_colors=grade_colors,
                           grade_order=grade_order)

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import Card, Deck, Category, Review
from app.sm2 import calculate_sm2, get_review_buttons
from app import db
from datetime import datetime
import random

bp = Blueprint('training', __name__, url_prefix='/train')


@bp.route('/deck/<int:deck_id>')
def start_training(deck_id):
    """Start a training session for a deck, optionally filtered by categories."""
    deck = Deck.query.get_or_404(deck_id)
    
    # Get category filter from query params
    category_ids = request.args.getlist('categories', type=int)
    
    return render_template('training/setup.html', 
                           deck=deck, 
                           selected_categories=category_ids)


@bp.route('/deck/<int:deck_id>/session', methods=['POST'])
def create_session(deck_id):
    """Create a training session and redirect to first card."""
    deck = Deck.query.get_or_404(deck_id)
    category_ids = request.form.getlist('categories', type=int)
    
    # Get training mode
    mode = request.form.get('mode', 'flip')  # flip, type_front, type_back
    
    # Get cards to review
    now = datetime.utcnow()
    
    if category_ids:
        # Filter by categories
        cards = Card.query.filter(
            Card.deck_id == deck_id,
            Card.categories.any(Category.id.in_(category_ids))
        ).filter(
            (Card.next_review <= now) | (Card.repetitions == 0)
        ).all()
    else:
        # All cards in deck
        cards = Card.query.filter_by(deck_id=deck_id).filter(
            (Card.next_review <= now) | (Card.repetitions == 0)
        ).all()
    
    if not cards:
        flash('Aucune carte à réviser pour le moment !', 'info')
        return redirect(url_for('decks.view_deck', deck_id=deck_id))
    
    # Shuffle cards
    random.shuffle(cards)
    
    # Store session data
    session['training'] = {
        'deck_id': deck_id,
        'card_ids': [c.id for c in cards],
        'current_index': 0,
        'category_ids': category_ids,
        'mode': mode,
        'results': {'correct': 0, 'incorrect': 0}
    }
    
    return redirect(url_for('training.show_card'))


@bp.route('/card')
def show_card():
    """Show the current card in the training session."""
    training = session.get('training')
    
    if not training or training['current_index'] >= len(training['card_ids']):
        return redirect(url_for('training.session_complete'))
    
    card_id = training['card_ids'][training['current_index']]
    card = Card.query.get_or_404(card_id)
    deck = card.deck
    
    # Calculate progress
    total = len(training['card_ids'])
    current = training['current_index'] + 1
    progress = (training['current_index'] / total) * 100
    
    # Get review buttons
    buttons = get_review_buttons(card)
    
    # Get training mode
    mode = training.get('mode', 'flip')
    
    return render_template('training/card.html',
                           card=card,
                           deck=deck,
                           buttons=buttons,
                           current=current,
                           total=total,
                           progress=progress,
                           mode=mode,
                           results=training['results'])


@bp.route('/check-answer', methods=['POST'])
def check_answer():
    """Check the typed answer for typing mode."""
    training = session.get('training')
    
    if not training:
        return {'error': 'Session expirée'}, 400
    
    card_id = training['card_ids'][training['current_index']]
    card = Card.query.get_or_404(card_id)
    
    mode = training.get('mode', 'flip')
    typed_answer = request.form.get('answer', '').strip().lower()
    
    # Determine expected answer based on mode
    if mode == 'type_back':
        # Question is front, answer is back
        expected = card.back.strip().lower()
    else:  # type_front
        # Question is back, answer is front
        expected = card.front.strip().lower()
    
    # Check if correct (allow some flexibility)
    # Remove common punctuation and extra spaces
    typed_clean = ''.join(typed_answer.split())
    expected_clean = ''.join(expected.split())
    
    is_correct = typed_clean == expected_clean
    
    return {
        'correct': is_correct,
        'expected': card.back if mode == 'type_back' else card.front,
        'typed': typed_answer
    }


@bp.route('/review', methods=['POST'])
def submit_review():
    """Submit a review for the current card."""
    training = session.get('training')
    
    if not training:
        flash('Session expirée.', 'error')
        return redirect(url_for('main.index'))
    
    card_id = training['card_ids'][training['current_index']]
    quality = int(request.form.get('quality', 4))
    
    card = Card.query.get_or_404(card_id)
    
    # Apply SM-2 algorithm
    new_easiness, new_interval, new_repetitions, next_review = calculate_sm2(
        quality, card.easiness, card.interval, card.repetitions
    )
    
    card.easiness = new_easiness
    card.interval = new_interval
    card.repetitions = new_repetitions
    card.next_review = next_review
    card.last_reviewed = datetime.utcnow()
    
    # Record the review
    review = Review(card_id=card.id, quality=quality)
    db.session.add(review)
    db.session.commit()
    
    # Update session results
    if quality >= 3:
        training['results']['correct'] += 1
    else:
        training['results']['incorrect'] += 1
    
    # Move to next card
    training['current_index'] += 1
    session['training'] = training
    
    return redirect(url_for('training.show_card'))


@bp.route('/complete')
def session_complete():
    """Show session completion summary."""
    training = session.pop('training', None)
    
    if not training:
        return redirect(url_for('main.index'))
    
    deck = Deck.query.get(training['deck_id'])
    results = training['results']
    total_reviewed = results['correct'] + results['incorrect']
    
    if total_reviewed > 0:
        accuracy = (results['correct'] / total_reviewed) * 100
    else:
        accuracy = 0
    
    return render_template('training/complete.html',
                           deck=deck,
                           results=results,
                           total_reviewed=total_reviewed,
                           accuracy=accuracy)


@bp.route('/stop', methods=['POST'])
def stop_training():
    """Stop the current training session."""
    training = session.pop('training', None)
    
    if training:
        deck_id = training['deck_id']
        flash('Session d\'entraînement arrêtée.', 'info')
        return redirect(url_for('decks.view_deck', deck_id=deck_id))
    
    return redirect(url_for('main.index'))

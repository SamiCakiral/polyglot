from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g
from app.models import Card, Deck, Category, Review, TrainingSession
from app.sm2 import calculate_sm2, get_review_buttons
from app import db
from datetime import datetime, timedelta
import random
from collections import defaultdict
from sqlalchemy import and_
from sqlalchemy.orm.attributes import flag_modified
from app.grades import calculate_grade, grade_to_numeric

bp = Blueprint('training', __name__, url_prefix='/train')


@bp.before_request
def check_login():
    if not g.user:
        return redirect(url_for('auth.login'))


@bp.route('/deck/<int:deck_id>')
def start_training(deck_id):
    """Start a training session for a deck, optionally filtered by categories."""
    deck = Deck.query.get_or_404(deck_id)
    if deck.user_id != g.user.id:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('main.index'))
    
    # Get category filter from query params
    category_ids = request.args.getlist('categories', type=int)
    
    # Get sample cards for dynamic examples
    sample_front = None
    sample_back = None
    if deck.cards:
        sample_card = deck.cards[0]
        sample_front = sample_card.front[:15] + ('...' if len(sample_card.front) > 15 else '')
        sample_back = sample_card.back[:15] + ('...' if len(sample_card.back) > 15 else '')
    
    return render_template('training/setup.html', 
                           deck=deck, 
                           selected_categories=category_ids,
                           sample_front=sample_front,
                           sample_back=sample_back)


def get_due_cards_with_direction(deck_id, category_ids=None, required_category_ids=None, filter_mode='or', directions=None, 
                                   max_grade=None, only_new=False, include_all=False):
    """Get cards for review, with their direction.
    Returns list of tuples: (card, direction)
    
    Args:
        deck_id: ID of the deck
        category_ids: Optional list of category IDs to filter (OR logic -> "Include any of these")
        required_category_ids: List of category IDs that MUST be present (AND logic)
        filter_mode: 'or' or 'and' for optional category filtering (defaults to 'or')
        directions: List of directions to include
        max_grade: If set, only include cards with grade <= max_grade
        only_new: If True, only include cards with 0 repetitions
        include_all: If True, ignore due date filter
    """
    
    if directions is None:
        directions = ['type_back', 'type_front']
    
    now = datetime.utcnow()
    
    # Base query
    query = Card.query.filter(Card.deck_id == deck_id)
    
    # 1. Apply REQUIRED categories (AND logic: must have ALL)
    if required_category_ids:
        for req_id in required_category_ids:
            query = query.filter(Card.categories.any(Category.id == req_id))
    
    # 2. Apply OPTIONAL categories (Standard selection)
    if category_ids:
        if filter_mode == 'and':
            # Must have ALL of the optional ones too (strict AND)
            for cat_id in category_ids:
                query = query.filter(Card.categories.any(Category.id == cat_id))
            cards = query.all()
        else:
            # Must have AT LEAST ONE of the optional ones (OR)
            query = query.filter(Card.categories.any(Category.id.in_(category_ids)))
            cards = query.all()
    else:
        # If no optional categories selected, just return what passed required filter
        # (Or all cards if no filters at all)
        cards = query.all()
    
    # Build list of (card, direction) pairs
    items = []
    
    # Calculate max grade numeric if specified
    max_grade_numeric = grade_to_numeric(max_grade) if max_grade else None
    
    for card in cards:
        for direction in directions:
            # Skip if not due and we're not including all
            if not include_all and not card.is_due_for_direction(direction):
                continue
            
            # Apply grade filter if specified
            if only_new:
                sm2 = card.get_sm2_for_direction(direction)
                if sm2['repetitions'] != 0:
                    continue
            elif max_grade_numeric is not None:
                grade = card.get_grade_for_direction(direction)
                if grade_to_numeric(grade) > max_grade_numeric:
                    continue
            
            items.append((card, direction))
    
    return items


@bp.route('/deck/<int:deck_id>/count')
def count_cards(deck_id):
    """API endpoint to count cards based on selected categories and grade filter."""
    deck = Deck.query.get_or_404(deck_id)
    category_ids = request.args.getlist('categories', type=int)
    required_category_ids = request.args.getlist('required_categories', type=int)
    filter_mode = request.args.get('filter_mode', 'or')
    max_grade = request.args.get('max_grade')  # e.g., 'B' to exclude A, A+
    only_new = request.args.get('only_new', 'false').lower() == 'true'
    include_all = request.args.get('include_all', 'false').lower() == 'true'
    
    # Count both directions
    items = get_due_cards_with_direction(
        deck_id, 
        category_ids=category_ids, 
        required_category_ids=required_category_ids,
        filter_mode=filter_mode, 
        directions=['type_back', 'type_front'],
        max_grade=max_grade,
        only_new=only_new,
        include_all=include_all
    )
    
    return jsonify({'count': len(items)})


@bp.route('/deck/<int:deck_id>/session', methods=['POST'])
def create_session(deck_id):
    """Create a training session and redirect to first card."""
    deck = Deck.query.get_or_404(deck_id)
    if deck.user_id != g.user.id:
        return redirect(url_for('main.index'))
    
    # Store params in session for restart
    params = {
        'categories': request.form.getlist('categories', type=int),
        'required_categories': request.form.getlist('required_categories', type=int),
        'filter_mode': request.form.get('filter_mode', 'or'),
        'mode': request.form.get('mode', 'flip'),
        'directions': request.form.getlist('directions'),
        'max_grade': request.form.get('max_grade'),
        'only_new': request.form.get('only_new', 'false').lower() == 'true',
        'include_all': request.form.get('include_all', 'false').lower() == 'true',
        'type_directions': request.form.getlist('type_directions'),
        'max_cards': request.form.get('max_cards_value', '0')
    }
    
    session['last_training_params'] = params
    session['last_deck_id'] = deck_id
    
    return _create_session_logic(deck_id, params)


@bp.route('/restart')
def restart_session():
    """Restart the last training session with same parameters."""
    params = session.get('last_training_params')
    deck_id = session.get('last_deck_id')
    
    if not params or not deck_id:
        flash('Aucune session récente à relancer.', 'error')
        return redirect(url_for('main.index'))
    
    return _create_session_logic(deck_id, params)


def _create_session_logic(deck_id, params):
    """Internal logic to create a session from params."""
    category_ids = params['categories']
    required_category_ids = params.get('required_categories')
    filter_mode = params['filter_mode']
    mode_input = params['mode']
    directions_input = params['directions']
    if not directions_input:
        directions_input = ['fb']
        
    direction_map = {
        'fb': 'type_back',
        'bf': 'type_front'
    }
    
    selected_directions = [direction_map[d] for d in directions_input if d in direction_map]
    
    # If mode is 'flip' and no directions selected (or force both for better UX), default to BOTH
    if mode_input == 'flip' and (not selected_directions or len(selected_directions) == 1):
        if not selected_directions:
             selected_directions = ['type_back', 'type_front']
    
    if not selected_directions:
        selected_directions = ['type_back']

    max_grade = params['max_grade']
    only_new = params['only_new']
    include_all = params['include_all']
    type_directions = params['type_directions'] or ['type_back']
    
    # Get cards
    items = get_due_cards_with_direction(
        deck_id, 
        category_ids=category_ids, 
        required_category_ids=required_category_ids,
        filter_mode=filter_mode, 
        directions=selected_directions,
        max_grade=max_grade, 
        only_new=only_new, 
        include_all=include_all
    )
    
    if not items:
        flash('Aucune carte à réviser !', 'info')
        return redirect(url_for('decks.view_deck', deck_id=deck_id))

    # ============================================================
    # NEW ALGORITHM: Group by word, limit occurrences, distribute evenly
    # ============================================================
    
    # Step 1: Group items by card_id (same word)
    by_card = defaultdict(list)
    for item in items:
        by_card[item[0].id].append(item)
    
    # Step 2: For each word, limit to max 2 directions and assign mode
    processed_items = []
    
    for card_id, item_list in by_card.items():
        random.shuffle(item_list)
        for item in item_list[:2]:
            card, direction = item
            if mode_input == 'flip':
                 processed_items.append((card, direction, 'flip'))
            elif mode_input == 'type_mode':
                 processed_items.append((card, direction, direction))
            elif mode_input == 'mixed':
                 processed_items.append((card, direction, 'mixed_placeholder'))
            else:
                 processed_items.append((card, direction, 'flip'))
    
    # Step 3: Sort by stability for initial prioritization
    # Step 3: Sort by stability for initial prioritization (with random tie-breaker)
    def get_stability_sort_key(item):
        card, direction, _ = item
        fsrs = card.get_fsrs_for_direction(direction)
        stat = fsrs['stability'] or 0
        # Add random jitter to simple stability sort to mix same-level cards
        return (stat, random.random())
    
    processed_items.sort(key=get_stability_sort_key)
    
    # Step 4: Distribute same-word occurrences evenly
    by_card_final = defaultdict(list)
    for item in processed_items:
        by_card_final[item[0].id].append(item)
    
    for group in by_card_final.values():
        random.shuffle(group)
    
    groups = list(by_card_final.values())
    random.shuffle(groups)
    
    distributed_items = []
    while groups:
        for group in groups[:]:
            if group:
                distributed_items.append(group.pop(0))
            if not group:
                groups.remove(group)
    
    # Final validation: consecutive check
    final_items = []
    for item in distributed_items:
        if final_items and item[0].id == final_items[-1][0].id:
            inserted = False
            for j in range(len(final_items) - 2, -1, -1):
                if final_items[j][0].id != item[0].id and (j == 0 or final_items[j-1][0].id != item[0].id):
                    final_items.insert(j, item)
                    inserted = True
                    break
            if not inserted:
                final_items.append(item)
        else:
            final_items.append(item)
            
    items = [(item[0], item[1]) for item in final_items]
    
    # Resolve 'mixed_placeholder' to actual modes (50/50 alternating)
    card_modes_precomputed = []
    mixed_counter = 0
    for item in final_items:
        mode = item[2]
        if mode == 'mixed_placeholder' or (mode_input == 'mixed' and mode == 'mixed'): # Handle potential legacy
            # Alternating
            if mixed_counter % 2 == 0:
                card_modes_precomputed.append(item[1]) # typing
            else:
                card_modes_precomputed.append('flip')
            mixed_counter += 1
        else:
            card_modes_precomputed.append(mode)

    # Limit max cards
    max_cards = params['max_cards']
    try:
        max_cards = int(max_cards)
    except ValueError:
        max_cards = 0
    
    if max_cards > 0 and len(items) > max_cards:
        items = items[:max_cards]
        card_modes_precomputed = card_modes_precomputed[:max_cards]
    
    card_ids = [item[0].id for item in items]
    card_directions = [item[1] for item in items]
    
    # Create DB Session
    ts = TrainingSession(deck_id=deck_id)
    # total_cards is stored in data, not as a column
    ts.data = {
        'card_ids': card_ids,
        'card_modes': card_modes_precomputed, # Use precomputed modes
        'card_directions': card_directions,
        'current_index': 0,
        'reviewed_indices': [],
        'deck_id': deck_id,
        'results': {'correct': 0, 'incorrect': 0, 'direction_stats': {'type_back': {'correct': 0, 'total': 0}, 'type_front': {'correct': 0, 'total': 0}, 'flip': {'correct': 0, 'total': 0}}}
    }
    db.session.add(ts)
    db.session.commit()
    
    # Store ID in cookie
    # Do NOT clear session here, as we need to preserve 'last_training_params' for restart
    session['training_session_id'] = ts.id
    
    return redirect(url_for('training.show_card'))


def get_current_training_session():
    """Helper to retrieve the current training session from DB."""
    session_id = session.get('training_session_id')
    if not session_id:
        return None, None
    
    ts = TrainingSession.query.get(session_id)
    if not ts:
        return None, None
        
    return ts, ts.data


@bp.route('/card')
def show_card():
    """Show the current card in the training session."""
    ts, training = get_current_training_session()
    
    if not training or training['current_index'] >= len(training['card_ids']):
        return redirect(url_for('training.session_complete'))
    
    card_id = training['card_ids'][training['current_index']]
    card = Card.query.get(card_id)
    
    # If card doesn't exist (DB was reset), clear session and redirect
    if not card:
        session.pop('training_session_id', None)
        flash('Session expirée. Veuillez démarrer un nouvel entraînement.', 'info')
        return redirect(url_for('main.index'))
    
    deck = card.deck
    
    # Calculate progress
    total = len(training['card_ids'])
    current = training['current_index'] + 1
    progress = (training['current_index'] / total) * 100
    
    # Get current card's mode and direction
    current_mode = training['card_modes'][training['current_index']]
    current_direction = training.get('card_directions', training['card_modes'])[training['current_index']]
    
    # Get SM-2 values for the current direction
    sm2 = card.get_sm2_for_direction(current_direction)
    
    # Get review buttons based on direction-specific values
    buttons = get_review_buttons_for_sm2(sm2['easiness'], sm2['interval'], sm2['repetitions'])
    
    # Check if already reviewed
    is_reviewed = training['current_index'] in training.get('reviewed_indices', [])
    
    # Detect TTS language from associated program
    tts_language = 'auto'
    from app.models import TrainingProgram
    program = TrainingProgram.query.filter_by(deck_id=deck.id, user_id=g.user.id).first()
    if program:
        tts_language = program.target_language or 'auto'
    
    return render_template('training/card.html',
                           card=card,
                           deck=deck,
                           buttons=buttons,
                           current=current,
                           total=total,
                           progress=progress,
                           mode=current_mode,
                           direction=current_direction,
                           results=training['results'],
                           is_reviewed=is_reviewed,
                           tts_language=tts_language)


def get_review_buttons_for_sm2(easiness, interval, repetitions):
    """Generate review buttons based on SM-2 values."""
    from app.sm2 import calculate_sm2
    
    buttons = []
    qualities = [
        (1, 'À revoir', 'quality-1'),
        (3, 'Difficile', 'quality-3'),
        (4, 'Bien', 'quality-4'),
        (5, 'Facile', 'quality-5')
    ]
    
    for quality, label, css_class in qualities:
        _, new_interval, _, _ = calculate_sm2(quality, easiness, interval, repetitions)
        
        if new_interval == 0:
            interval_text = "< 1j"
        elif new_interval == 1:
            interval_text = "1 jour"
        else:
            interval_text = f"{new_interval} jours"
        
        buttons.append({
            'quality': quality,
            'label': label,
            'interval': interval_text,
            'css_class': css_class
        })
    
    return buttons


def normalize_answer(text):
    """Normalize an answer for comparison."""
    import re
    import unicodedata
    
    if not text:
        return ""
    
    # Lowercase
    text = text.lower().strip()
    
    # Remove content in parentheses like "(4)" or "(masc.)"
    text = re.sub(r'\s*\([^)]*\)', '', text)
    
    # Remove accents for comparison (but keep original for display)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Remove punctuation and extra whitespace
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    
    return text


@bp.route('/check-answer', methods=['POST'])
def check_answer():
    """Check the typed answer for typing mode."""
    ts, training = get_current_training_session()
    
    if not training:
        return {'error': 'Session expirée'}, 400
    
    card_id = training['card_ids'][training['current_index']]
    card = Card.query.get_or_404(card_id)
    
    # Get current mode for this card
    current_mode = training['card_modes'][training['current_index']]
    
    typed_answer = request.form.get('answer', '').strip()
    
    # Determine expected answer based on mode
    if current_mode == 'type_back':
        expected_raw = card.back
    else:  # type_front
        expected_raw = card.front
    
    # Normalize both for comparison
    typed_normalized = normalize_answer(typed_answer)
    expected_normalized = normalize_answer(expected_raw)
    
    is_correct = typed_normalized == expected_normalized
    
    # Also check if it matches without spaces (for compound words)
    if not is_correct:
        typed_no_space = typed_normalized.replace(' ', '')
        expected_no_space = expected_normalized.replace(' ', '')
        is_correct = typed_no_space == expected_no_space
    
    return {
        'correct': is_correct,
        'expected': expected_raw.strip(),
        'typed': typed_answer
    }


@bp.route('/review', methods=['POST'])
def submit_review():
    """Submit a review for the current card (uses FSRS)."""
    from app.fsrs import calculate_next_state, calculate_optimal_interval
    
    ts, training = get_current_training_session()
    
    if not training:
        flash('Session expirée.', 'error')
        return redirect(url_for('main.index'))
    
    card_id = training['card_ids'][training['current_index']]
    quality = int(request.form.get('quality', 4))
    
    # Map SM-2 quality (1-5) to FSRS grade (1-4)
    # SM-2: 1=Again, 3=Hard, 4=Good, 5=Easy
    # FSRS: 1=Again, 2=Hard, 3=Good, 4=Easy
    fsrs_grade_map = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}
    fsrs_grade = fsrs_grade_map.get(quality, 3)
    
    card = Card.query.get_or_404(card_id)
    
    # Get the direction for this card
    current_direction = training.get('card_directions', training['card_modes'])[training['current_index']]
    
    # Get current FSRS values for this direction
    fsrs = card.get_fsrs_for_direction(current_direction)
    
    # Calculate days since last review
    if fsrs['last_reviewed']:
        t = (datetime.utcnow() - fsrs['last_reviewed']).total_seconds() / 86400
    else:
        t = 0
    
    # Apply FSRS algorithm
    new_D, new_S, _ = calculate_next_state(
        fsrs['difficulty'], fsrs['stability'], t, fsrs_grade
    )
    
    # Calculate next review date
    optimal_interval = calculate_optimal_interval(new_S)
    next_review = datetime.utcnow() + timedelta(days=optimal_interval)
    
    # Update the card with FSRS values
    card.set_fsrs_for_direction(current_direction, new_D, new_S, next_review)
    
    # Cross-direction boost
    if fsrs_grade >= 3:
        other_direction = 'type_front' if current_direction in ['fb', 'type_back', 'flip'] else 'type_back'
        other_fsrs = card.get_fsrs_for_direction(other_direction)
        
        if other_fsrs['stability'] > 0:
            # Boost other direction's stability by 30% of the gain
            old_S = fsrs['stability'] if fsrs['stability'] > 0 else 1.0
            S_gain = new_S - old_S
            if S_gain > 0:
                boosted_S = other_fsrs['stability'] + (S_gain * 0.3)
                other_next_review = datetime.utcnow() + timedelta(days=calculate_optimal_interval(boosted_S))
                card.set_fsrs_for_direction(other_direction, other_fsrs['difficulty'], boosted_S, other_next_review)
    
    # Record the review with direction
    review = Review(card_id=card.id, quality=quality, direction=current_direction)
    db.session.add(review)
    
    # Update session results (MODIFYING SESSION DATA)
    if quality >= 3:
        training['results']['correct'] += 1
    else:
        training['results']['incorrect'] += 1
    
    if 'direction_stats' not in training['results']:
        training['results']['direction_stats'] = {'type_back': {'correct': 0, 'total': 0}, 'type_front': {'correct': 0, 'total': 0}, 'flip': {'correct': 0, 'total': 0}}
    
    dir_key = current_direction if current_direction in training['results']['direction_stats'] else 'flip'
    training['results']['direction_stats'][dir_key]['total'] += 1
    if quality >= 3:
        training['results']['direction_stats'][dir_key]['correct'] += 1
    
    # Move to next card and track review
    if 'reviewed_indices' not in training:
         training['reviewed_indices'] = []
    
    if training['current_index'] not in training['reviewed_indices']:
        training['reviewed_indices'].append(training['current_index'])
        
    training['current_index'] += 1
    
    # IMPORTANT: Commit changes to TrainingSession
    flag_modified(ts, "data")
    db.session.commit()
    
    return redirect(url_for('training.show_card'))


@bp.route('/complete')
def session_complete():
    """Show session completion summary."""
    ts, training = get_current_training_session()
    
    if not training:
        return redirect(url_for('main.index'))
    
    deck = Deck.query.get(training['deck_id'])
    results = training['results']
    total_reviewed = results['correct'] + results['incorrect']
    
    if total_reviewed > 0:
        accuracy = (results['correct'] / total_reviewed) * 100
    else:
        accuracy = 0
    
    # Clean up session cookie (optional, data remains in DB for history if needed)
    session.pop('training_session_id', None)
    
    return render_template('training/complete.html',
                           deck=deck,
                           results=results,
                           total_reviewed=total_reviewed,
                           accuracy=accuracy)


@bp.route('/stop', methods=['POST'])
def stop_training():
    """Stop the current training session."""
    ts, training = get_current_training_session()
    
    if training:
        deck_id = training['deck_id']
        session.pop('training_session_id', None)
        flash('Session d\'entraînement arrêtée.', 'info')
        return redirect(url_for('decks.view_deck', deck_id=deck_id))
    
    return redirect(url_for('main.index'))


@bp.route('/back')
def go_back():
    """Go back to the previous card in training session."""
    ts, training = get_current_training_session()
    
    if not training:
        flash('Session expirée.', 'error')
        return redirect(url_for('main.index'))
    
    # Decrement the index if possible
    if training['current_index'] > 0:
        training['current_index'] -= 1
        # Commit change
        flag_modified(ts, "data")
        db.session.commit()
    
    return redirect(url_for('training.show_card'))


@bp.route('/forward')
def go_forward():
    """Go forward to the next card (only if already reviewed or skipping)."""
    ts, training = get_current_training_session()
    
    if not training:
        flash('Session expirée.', 'error')
        return redirect(url_for('main.index'))
    
    # Increment the index if possible
    if training['current_index'] < len(training['card_ids']):
        training['current_index'] += 1
        # Commit change
        flag_modified(ts, "data")
        db.session.commit()
    
    return redirect(url_for('training.show_card'))


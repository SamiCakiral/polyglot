from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from app.models import Deck, Card, User
from app import db
from app.authz import owned_deck_or_404

bp = Blueprint('decks', __name__, url_prefix='/decks')


@bp.before_request
def check_login():
    """Ensure user is logged in."""
    if not g.user:
        return redirect(url_for('auth.login'))


@bp.route('/')
def list_decks():
    """List all decks."""
    decks = Deck.query.filter_by(user_id=g.user.id).all()
    return render_template('decks/list.html', decks=decks)


@bp.route('/import-public', methods=['GET', 'POST'])
def import_public_deck():
    """Import a deck from another user."""
    if request.method == 'POST':
        deck_id = request.form.get('deck_id')
        source_deck = Deck.query.get_or_404(deck_id)
        
        # Clone deck
        new_deck = Deck(
            user_id=g.user.id, 
            name=f"{source_deck.name} (Import)", 
            description=source_deck.description
        )
        db.session.add(new_deck)
        db.session.flush() # get ID
        
        # Clone categories mapping
        cat_map = {}
        for cat in source_deck.categories:
            new_cat = cat.__class__(
                deck_id=new_deck.id,
                name=cat.name,
                color=cat.color
            )
            db.session.add(new_cat)
            db.session.flush()
            cat_map[cat.id] = new_cat
            
        # Clone cards
        for card in source_deck.cards:
            new_card = Card(
                deck_id=new_deck.id,
                front=card.front,
                back=card.back,
                # Reset stats
                fb_easiness=2.5, bf_easiness=2.5
            )
            db.session.add(new_card)
            # Add categories
            for cat in card.categories:
                if cat.id in cat_map:
                    new_card.categories.append(cat_map[cat.id])
        
        db.session.commit()
        flash(f'Paquet "{source_deck.name}" importé avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=new_deck.id))
    
    # Show all decks NOT owned by current user
    public_decks = Deck.query.filter(Deck.user_id != g.user.id).all()
    return render_template('decks/import.html', decks=public_decks)


@bp.route('/new', methods=['GET', 'POST'])
def new_deck():
    """Create a new deck."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('Le nom du paquet est requis.', 'error')
            return render_template('decks/form.html', deck=None)
        
        deck = Deck(user_id=g.user.id, name=name, description=description)
        db.session.add(deck)
        db.session.commit()
        
        flash(f'Paquet "{name}" créé avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('decks/form.html', deck=None)


@bp.route('/<int:deck_id>')
def view_deck(deck_id):
    """View a specific deck with its cards and categories."""
    from app.grades import get_grade_distribution, calculate_deck_progress, GRADES
    
    deck = Deck.query.get_or_404(deck_id)
    
    # Ownership check
    if deck.user_id != g.user.id:
        flash('Vous ne pouvez pas accéder à ce paquet directement. Vous pouvez l\'importer.', 'info')
        return redirect(url_for('decks.import_public_deck'))
        
    stats = deck.get_stats()
    
    # Get sample cards for training mode examples
    sample_front = None
    sample_back = None
    if deck.cards:
        sample_card = deck.cards[0]
        sample_front = sample_card.front[:20] + ('...' if len(sample_card.front) > 20 else '')
        sample_back = sample_card.back[:20] + ('...' if len(sample_card.back) > 20 else '')
    
    # Get grade distribution for both directions
    fb_grade_dist = get_grade_distribution(deck.cards, 'fb')
    bf_grade_dist = get_grade_distribution(deck.cards, 'bf')
    fb_progress = calculate_deck_progress(deck.cards, 'fb')
    bf_progress = calculate_deck_progress(deck.cards, 'bf')
    
    # Grade colors and order for display
    grade_colors = {g[0]: g[3] for g in GRADES}
    grade_order = [g[0] for g in reversed(GRADES)]  # E to A+
    
    # Detect TTS language from associated program
    tts_language = 'auto'
    from app.models import TrainingProgram
    program = TrainingProgram.query.filter_by(deck_id=deck.id, user_id=g.user.id).first()
    if program:
        tts_language = program.target_language or 'auto'
    
    return render_template('decks/view.html', 
                           deck=deck, 
                           stats=stats,
                           sample_front=sample_front,
                           sample_back=sample_back,
                           fb_grade_dist=fb_grade_dist,
                           bf_grade_dist=bf_grade_dist,
                           fb_progress=fb_progress,
                           bf_progress=bf_progress,
                           grade_colors=grade_colors,
                           grade_order=grade_order,
                           tts_language=tts_language)


@bp.route('/<int:deck_id>/edit', methods=['GET', 'POST'])
def edit_deck(deck_id):
    """Edit a deck."""
    deck = owned_deck_or_404(deck_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('Le nom du paquet est requis.', 'error')
            return render_template('decks/form.html', deck=deck)
        
        deck.name = name
        deck.description = description
        db.session.commit()
        
        flash('Paquet modifié avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('decks/form.html', deck=deck)


@bp.route('/<int:deck_id>/delete', methods=['POST'])
def delete_deck(deck_id):
    """Delete a deck."""
    deck = owned_deck_or_404(deck_id)
    name = deck.name
    db.session.delete(deck)
    db.session.commit()
    
    flash(f'Paquet "{name}" supprimé.', 'success')
    return redirect(url_for('main.index'))


@bp.route('/<int:deck_id>/reset', methods=['GET', 'POST'])
def reset_deck(deck_id):
    """Reset deck progress - set all cards back to new state."""
    deck = owned_deck_or_404(deck_id)
    
    if request.method == 'POST':
        # Reset all cards in the deck
        from datetime import datetime
        for card in deck.cards:
            # Reset legacy fields (flip mode)
            card.easiness = 2.5
            card.interval = 0
            card.repetitions = 0
            card.next_review = datetime.utcnow()
            card.last_reviewed = None
            
            # Reset front→back direction
            card.fb_easiness = 2.5
            card.fb_interval = 0
            card.fb_repetitions = 0
            card.fb_next_review = datetime.utcnow()
            card.fb_last_reviewed = None
            
            # Reset back→front direction
            card.bf_easiness = 2.5
            card.bf_interval = 0
            card.bf_repetitions = 0
            card.bf_next_review = datetime.utcnow()
            card.bf_last_reviewed = None
        
        # Optionally delete review history
        if request.form.get('delete_history'):
            from app.models import Review
            for card in deck.cards:
                Review.query.filter_by(card_id=card.id).delete()
        
        db.session.commit()
        
        flash(f'Progression du paquet "{deck.name}" réinitialisée !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('decks/reset.html', deck=deck)

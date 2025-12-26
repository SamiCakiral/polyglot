from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import Deck, User
from app import db
from app.routes.main import get_or_create_default_user

bp = Blueprint('decks', __name__, url_prefix='/decks')


@bp.route('/')
def list_decks():
    """List all decks."""
    user = get_or_create_default_user()
    decks = Deck.query.filter_by(user_id=user.id).all()
    return render_template('decks/list.html', decks=decks)


@bp.route('/new', methods=['GET', 'POST'])
def new_deck():
    """Create a new deck."""
    if request.method == 'POST':
        user = get_or_create_default_user()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('Le nom du paquet est requis.', 'error')
            return render_template('decks/form.html', deck=None)
        
        deck = Deck(user_id=user.id, name=name, description=description)
        db.session.add(deck)
        db.session.commit()
        
        flash(f'Paquet "{name}" créé avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('decks/form.html', deck=None)


@bp.route('/<int:deck_id>')
def view_deck(deck_id):
    """View a specific deck with its cards and categories."""
    deck = Deck.query.get_or_404(deck_id)
    stats = deck.get_stats()
    return render_template('decks/view.html', deck=deck, stats=stats)


@bp.route('/<int:deck_id>/edit', methods=['GET', 'POST'])
def edit_deck(deck_id):
    """Edit a deck."""
    deck = Deck.query.get_or_404(deck_id)
    
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
    deck = Deck.query.get_or_404(deck_id)
    name = deck.name
    db.session.delete(deck)
    db.session.commit()
    
    flash(f'Paquet "{name}" supprimé.', 'success')
    return redirect(url_for('main.index'))

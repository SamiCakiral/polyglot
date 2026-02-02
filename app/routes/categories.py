from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from app.models import Category, Deck
from app import db

bp = Blueprint('categories', __name__, url_prefix='/categories')


@bp.before_request
def login_required():
    if not g.user:
        return redirect(url_for('auth.profiles'))


@bp.route('/deck/<int:deck_id>')
def list_categories(deck_id):
    """List all categories for a deck."""
    deck = Deck.query.get_or_404(deck_id)
    if deck.user_id != g.user.id:
        return redirect(url_for('main.index'))
    return render_template('categories/list.html', deck=deck)


@bp.route('/deck/<int:deck_id>/new', methods=['GET', 'POST'])
def new_category(deck_id):
    """Create a new category."""
    deck = Deck.query.get_or_404(deck_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '#3498db')
        
        if not name:
            flash('Le nom de la catégorie est requis.', 'error')
            return render_template('categories/form.html', deck=deck, category=None)
        
        # Check for duplicate name
        existing = Category.query.filter_by(deck_id=deck.id, name=name).first()
        if existing:
            flash('Une catégorie avec ce nom existe déjà.', 'error')
            return render_template('categories/form.html', deck=deck, category=None)
        
        category = Category(deck_id=deck.id, name=name, color=color)
        db.session.add(category)
        db.session.commit()
        
        flash(f'Catégorie "{name}" créée avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('categories/form.html', deck=deck, category=None)


@bp.route('/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    """Edit a category."""
    category = Category.query.get_or_404(category_id)
    deck = Deck.query.get(category.deck_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '#3498db')
        
        if not name:
            flash('Le nom de la catégorie est requis.', 'error')
            return render_template('categories/form.html', deck=deck, category=category)
        
        # Check for duplicate name (excluding current)
        existing = Category.query.filter_by(deck_id=deck.id, name=name).filter(Category.id != category_id).first()
        if existing:
            flash('Une catégorie avec ce nom existe déjà.', 'error')
            return render_template('categories/form.html', deck=deck, category=category)
        
        category.name = name
        category.color = color
        db.session.commit()
        
        flash('Catégorie modifiée avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('categories/form.html', deck=deck, category=category)


@bp.route('/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    """Delete a category (cards keep their other categories)."""
    category = Category.query.get_or_404(category_id)
    deck_id = category.deck_id
    name = category.name
    
    db.session.delete(category)
    db.session.commit()
    
    flash(f'Catégorie "{name}" supprimée.', 'success')
    return redirect(url_for('decks.view_deck', deck_id=deck_id))


@bp.route('/<int:category_id>/stats')
def category_stats(category_id):
    """Get stats for a specific category."""
    category = Category.query.get_or_404(category_id)
    deck = Deck.query.get(category.deck_id)
    stats = category.get_stats()
    
    return render_template('categories/stats.html', deck=deck, category=category, stats=stats)

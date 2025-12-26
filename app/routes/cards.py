from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import Card, Deck, Category
from app import db
import json

bp = Blueprint('cards', __name__, url_prefix='/cards')


@bp.route('/deck/<int:deck_id>/new', methods=['GET', 'POST'])
def new_card(deck_id):
    """Create a new card in a deck."""
    deck = Deck.query.get_or_404(deck_id)
    
    if request.method == 'POST':
        front = request.form.get('front', '').strip()
        back = request.form.get('back', '').strip()
        category_ids = request.form.getlist('categories')
        
        if not front or not back:
            flash('Le recto et le verso sont requis.', 'error')
            return render_template('cards/form.html', deck=deck, card=None)
        
        card = Card(deck_id=deck.id, front=front, back=back)
        
        # Add categories
        if category_ids:
            categories = Category.query.filter(Category.id.in_(category_ids)).all()
            card.categories = categories
        
        db.session.add(card)
        db.session.commit()
        
        flash('Carte créée avec succès !', 'success')
        
        # Check if user wants to add another card
        if request.form.get('add_another'):
            return redirect(url_for('cards.new_card', deck_id=deck.id))
        
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('cards/form.html', deck=deck, card=None)


@bp.route('/<int:card_id>/edit', methods=['GET', 'POST'])
def edit_card(card_id):
    """Edit a card."""
    card = Card.query.get_or_404(card_id)
    deck = card.deck
    
    if request.method == 'POST':
        front = request.form.get('front', '').strip()
        back = request.form.get('back', '').strip()
        category_ids = request.form.getlist('categories')
        
        if not front or not back:
            flash('Le recto et le verso sont requis.', 'error')
            return render_template('cards/form.html', deck=deck, card=card)
        
        card.front = front
        card.back = back
        
        # Update categories
        if category_ids:
            categories = Category.query.filter(Category.id.in_(category_ids)).all()
            card.categories = categories
        else:
            card.categories = []
        
        db.session.commit()
        
        flash('Carte modifiée avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('cards/form.html', deck=deck, card=card)


@bp.route('/<int:card_id>/delete', methods=['POST'])
def delete_card(card_id):
    """Delete a card."""
    card = Card.query.get_or_404(card_id)
    deck_id = card.deck_id
    db.session.delete(card)
    db.session.commit()
    
    flash('Carte supprimée.', 'success')
    return redirect(url_for('decks.view_deck', deck_id=deck_id))


@bp.route('/bulk-create/<int:deck_id>', methods=['GET', 'POST'])
def bulk_create(deck_id):
    """Bulk create cards from a text list (automated creation)."""
    deck = Deck.query.get_or_404(deck_id)
    
    if request.method == 'POST':
        raw_data = request.form.get('data', '').strip()
        separator = request.form.get('separator', ';')
        category_ids = request.form.getlist('categories')
        
        if not raw_data:
            flash('Veuillez entrer des données.', 'error')
            return render_template('cards/bulk.html', deck=deck)
        
        # Get categories
        categories = []
        if category_ids:
            categories = Category.query.filter(Category.id.in_(category_ids)).all()
        
        # Parse lines
        lines = raw_data.strip().split('\n')
        created = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(separator, 1)
            if len(parts) != 2:
                continue
            
            front, back = parts[0].strip(), parts[1].strip()
            if front and back:
                card = Card(deck_id=deck.id, front=front, back=back)
                card.categories = categories
                db.session.add(card)
                created += 1
        
        db.session.commit()
        
        flash(f'{created} cartes créées avec succès !', 'success')
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('cards/bulk.html', deck=deck)


@bp.route('/json-import/<int:deck_id>', methods=['GET', 'POST'])
def json_import(deck_id):
    """Import cards from JSON file."""
    deck = Deck.query.get_or_404(deck_id)
    
    if request.method == 'POST':
        json_data = None
        
        # Check for file upload
        if 'json_file' in request.files:
            file = request.files['json_file']
            if file and file.filename:
                try:
                    json_data = json.load(file)
                except json.JSONDecodeError:
                    flash('Fichier JSON invalide.', 'error')
                    return render_template('cards/json_import.html', deck=deck)
        
        # Check for pasted JSON
        if not json_data:
            json_text = request.form.get('json_text', '').strip()
            if json_text:
                try:
                    json_data = json.loads(json_text)
                except json.JSONDecodeError:
                    flash('JSON invalide.', 'error')
                    return render_template('cards/json_import.html', deck=deck)
        
        if not json_data:
            flash('Veuillez fournir un fichier JSON ou coller le JSON.', 'error')
            return render_template('cards/json_import.html', deck=deck)
        
        # Process JSON
        created_cards = 0
        created_categories = 0
        
        # Handle categories if present
        category_map = {}
        if 'categories' in json_data:
            for cat_data in json_data['categories']:
                name = cat_data.get('name', '').strip()
                if name:
                    # Check if category exists
                    category = Category.query.filter_by(deck_id=deck.id, name=name).first()
                    if not category:
                        category = Category(
                            deck_id=deck.id,
                            name=name,
                            color=cat_data.get('color', '#3498db')
                        )
                        db.session.add(category)
                        db.session.flush()  # Get the ID
                        created_categories += 1
                    category_map[name] = category
        
        # Handle cards
        cards_data = json_data.get('cards', json_data if isinstance(json_data, list) else [])
        
        for card_data in cards_data:
            front = card_data.get('front', card_data.get('question', '')).strip()
            back = card_data.get('back', card_data.get('answer', '')).strip()
            
            if front and back:
                card = Card(deck_id=deck.id, front=front, back=back)
                
                # Add categories
                card_categories = card_data.get('categories', [])
                if isinstance(card_categories, str):
                    card_categories = [card_categories]
                
                for cat_name in card_categories:
                    if cat_name in category_map:
                        card.categories.append(category_map[cat_name])
                    else:
                        # Create category if not exists
                        category = Category.query.filter_by(deck_id=deck.id, name=cat_name).first()
                        if not category:
                            category = Category(deck_id=deck.id, name=cat_name)
                            db.session.add(category)
                            db.session.flush()
                            created_categories += 1
                        category_map[cat_name] = category
                        card.categories.append(category)
                
                db.session.add(card)
                created_cards += 1
        
        db.session.commit()
        
        message = f'{created_cards} cartes importées'
        if created_categories > 0:
            message += f', {created_categories} catégories créées'
        flash(message + ' !', 'success')
        
        return redirect(url_for('decks.view_deck', deck_id=deck.id))
    
    return render_template('cards/json_import.html', deck=deck)

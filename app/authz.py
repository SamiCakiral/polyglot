from flask import abort
from flask_login import current_user

from app.models import Card, Category, Deck, TrainingSession


def _current_user_id():
    if not current_user.is_authenticated:
        abort(401)
    return current_user.id


def owned_deck_or_404(deck_id):
    deck = Deck.query.get_or_404(deck_id)
    if deck.user_id != _current_user_id():
        abort(404)
    return deck


def owned_card_or_404(card_id):
    card = Card.query.get_or_404(card_id)
    if not card.deck or card.deck.user_id != _current_user_id():
        abort(404)
    return card


def owned_category_or_404(category_id):
    category = Category.query.get_or_404(category_id)
    if not category.deck or category.deck.user_id != _current_user_id():
        abort(404)
    return category


def owned_training_session_or_none(session_id):
    if not session_id or not current_user.is_authenticated:
        return None

    training_session = TrainingSession.query.get(session_id)
    if not training_session:
        return None

    if not training_session.deck_rel or training_session.deck_rel.user_id != current_user.id:
        return None

    return training_session


def categories_for_deck(deck_id, category_ids):
    if not category_ids:
        return []
    return Category.query.filter(
        Category.deck_id == deck_id,
        Category.id.in_(category_ids),
    ).all()

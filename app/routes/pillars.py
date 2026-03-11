"""
Routes for Language Pillars - Foundation learning system.
"""
from flask import Blueprint, render_template, redirect, url_for, session, g, request, jsonify, flash
from app.models import User, UserLanguage, Deck, Card, Category, TrainingProgram, PillarExercise
from app import db
from app.pillar_config import (
    LANGUAGES, SUPPORTED_LANGUAGES, get_language, get_language_name,
    get_pillars_for_language, get_pillar, get_pillars_by_level,
    get_required_pillars, check_pillar_available, get_onboarding_questions,
    get_all_languages_summary, get_cefr_for_pillar, get_pillars_by_cefr,
    ONBOARDING_LEVELS, CEFR_LEVEL_NAMES, CECRL_LEVELS
)
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified
import json
import os

bp = Blueprint('pillars', __name__, url_prefix='/pillars')


@bp.before_request
def check_login():
    """Ensure user is logged in."""
    if not g.user:
        return redirect(url_for('auth.login'))


# =============================================================================
# MAIN VIEWS
# =============================================================================

@bp.route('/')
def index():
    """List all languages the user is learning + option to add new."""
    if not g.user:
        return redirect(url_for('auth.login'))
    
    # Get user's languages
    user_languages = UserLanguage.query.filter_by(user_id=g.user.id).all()
    
    # Enrich with language config
    languages_data = []
    for ul in user_languages:
        lang_config = get_language(ul.language_code)
        if lang_config:
            # Count pillars
            total_pillars = len(lang_config['pillars'])
            completed = ul.get_completed_pillars_count()
            
            languages_data.append({
                'user_language': ul,
                'config': lang_config,
                'total_pillars': total_pillars,
                'completed_pillars': completed,
                'progress_percent': (completed / total_pillars * 100) if total_pillars > 0 else 0
            })
    
    # Get available languages (not yet started)
    started_codes = [ul.language_code for ul in user_languages]
    available_languages = [
        lang for lang in get_all_languages_summary()
        if lang['code'] not in started_codes
    ]
    
    return render_template('pillars/index.html',
                         languages=languages_data,
                         available_languages=available_languages)


@bp.route('/<lang>')
def language_view(lang):
    """View pillars tree for a specific language."""
    if not g.user:
        return redirect(url_for('auth.login'))
    
    # Check if language is valid
    lang_config = get_language(lang)
    if not lang_config:
        flash(f"Langue '{lang}' non supportee", 'error')
        return redirect(url_for('pillars.index'))
    
    # Get or create UserLanguage
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        # Language not started - redirect to onboarding
        return redirect(url_for('pillars.onboarding', lang=lang))
    
    # Build pillars tree with status
    pillars_by_level = {}
    completed_pillars = []
    
    # First pass: collect completed pillars
    for pillar in lang_config['pillars']:
        progress = user_language.get_pillar_status(pillar['id'])
        if progress.get('status') == 'completed':
            completed_pillars.append(pillar['id'])
    
    # Collect all deck IDs to find linked training programs
    all_deck_ids = []
    for pillar in lang_config['pillars']:
        progress = user_language.get_pillar_status(pillar['id'])
        did = progress.get('deck_id')
        if did:
            all_deck_ids.append(did)
    
    # Batch query training programs for these decks
    program_by_deck = {}
    if all_deck_ids:
        programs = TrainingProgram.query.filter(
            TrainingProgram.user_id == g.user.id,
            TrainingProgram.deck_id.in_(all_deck_ids)
        ).all()
        for p in programs:
            program_by_deck[p.deck_id] = p.id
    
    # Second pass: build tree with availability
    for pillar in lang_config['pillars']:
        level = pillar['level']
        if level not in pillars_by_level:
            pillars_by_level[level] = []
        
        progress = user_language.get_pillar_status(pillar['id'])
        status = progress.get('status', 'locked')
        
        # Check if available (prereqs met)
        if status == 'locked':
            if check_pillar_available(lang, pillar['id'], completed_pillars):
                status = 'available'
        
        deck_id = progress.get('deck_id')
        pillars_by_level[level].append({
            'config': pillar,
            'status': status,
            'mastery': progress.get('mastery', 0),
            'deck_id': deck_id,
            'program_id': program_by_deck.get(deck_id),
        })
    
    # Sort levels
    sorted_levels = sorted(pillars_by_level.keys())
    
    return render_template('pillars/language.html',
                         lang_config=lang_config,
                         lang_code=lang,
                         user_language=user_language,
                         pillars_by_level=pillars_by_level,
                         sorted_levels=sorted_levels,
                         completed_count=len(completed_pillars),
                         total_count=len(lang_config['pillars']))


@bp.route('/<lang>/<pillar_id>')
def pillar_detail(lang, pillar_id):
    """Dedicated page for a single pillar — lesson + exercises + LLM chat."""
    if not g.user:
        return redirect(url_for('auth.login'))
    
    lang_config = get_language(lang)
    if not lang_config:
        flash(f"Langue '{lang}' non supportee", 'error')
        return redirect(url_for('pillars.index'))
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id, language_code=lang
    ).first()
    if not user_language:
        return redirect(url_for('pillars.onboarding', lang=lang))
    
    pillar_config = get_pillar(lang, pillar_id)
    if not pillar_config:
        flash(f"Pilier '{pillar_id}' non trouve", 'error')
        return redirect(url_for('pillars.language_view', lang=lang))
    
    progress = user_language.get_pillar_status(pillar_id)
    
    # Load lesson from pre-generated JSON
    lesson = None
    content_path = os.path.join('pillar_content', lang, f'{pillar_id}.json')
    if os.path.exists(content_path):
        try:
            with open(content_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            lesson = content.get('lesson', {})
        except Exception:
            pass
    
    # Exercise type labels
    ex_labels = {
        'conjugation': {'name': 'Conjugaison', 'icon': '📝', 'desc': 'Grille pronoms + temps'},
        'fill_blank': {'name': 'Phrases à trous', 'icon': '✏️', 'desc': 'Compléter la bonne forme'},
        'transform': {'name': 'Transformation', 'icon': '🔄', 'desc': 'Négation, question, temps'},
        'word_order': {'name': 'Ordre des mots', 'icon': '🔀', 'desc': "Remettre dans l'ordre"},
        'particles': {'name': 'Particules', 'icon': '⚙️', 'desc': 'Choisir la bonne particule'},
        'gender': {'name': 'Genre / articles', 'icon': '♀️', 'desc': 'Accord et déterminants'},
    }
    
    # Filter to only this pillar's exercise types
    pillar_exercises = []
    for et in pillar_config.get('exercise_types', []):
        if et in ex_labels:
            pillar_exercises.append({**ex_labels[et], 'type': et})
    
    # Check if cards exist for this pillar
    deck_id = progress.get('deck_id')
    has_cards = False
    if deck_id:
        from app.models import Card
        has_cards = Card.query.filter_by(deck_id=deck_id).count() > 0
    
    return render_template('pillars/pillar_detail.html',
                         lang_config=lang_config,
                         lang_code=lang,
                         user_language=user_language,
                         pillar=pillar_config,
                         progress=progress,
                         lesson=lesson,
                         pillar_exercises=pillar_exercises,
                         has_exercises=len(pillar_exercises) > 0,
                         has_cards=has_cards,
                         deck_id=deck_id)


@bp.route('/<lang>/onboarding')
def onboarding(lang):
    """Onboarding flow for starting a new language."""
    if not g.user:
        return redirect(url_for('auth.login'))
    
    lang_config = get_language(lang)
    if not lang_config:
        flash(f"Langue '{lang}' non supportee", 'error')
        return redirect(url_for('pillars.index'))
    
    # Check if already started
    existing = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if existing:
        return redirect(url_for('pillars.language_view', lang=lang))
    
    # Get onboarding levels for CEFR picker
    onboarding_levels = get_onboarding_questions(lang)

    return render_template('pillars/onboarding.html',
                         lang_config=lang_config,
                         lang_code=lang,
                         onboarding_levels=onboarding_levels,
                         cefr_level_names=CEFR_LEVEL_NAMES)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@bp.route('/<lang>/start', methods=['POST'])
def start_language(lang):
    """Start learning a new language."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    lang_config = get_language(lang)
    if not lang_config:
        return jsonify({'error': f"Langue '{lang}' non supportee"}), 400
    
    # Check if already exists
    existing = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if existing:
        return jsonify({'error': 'Langue deja commencee', 'redirect': url_for('pillars.language_view', lang=lang)})
    
    # Get onboarding data from form
    data = request.json if request.is_json else {}

    # New system: read estimated CEFR level chosen by user
    chosen_cefr = data.get('estimated_level', 'A0')
    if chosen_cefr not in CECRL_LEVELS:
        chosen_cefr = 'A0'

    cefr_index = CECRL_LEVELS.index(chosen_cefr)

    # Backwards compat: if old-style 'answers' dict is passed, convert
    answers = data.get('answers', {})
    if answers and not data.get('estimated_level'):
        # Old format - just start at A0
        chosen_cefr = 'A0'
        cefr_index = 0

    # Create UserLanguage
    user_language = UserLanguage(
        user_id=g.user.id,
        language_code=lang,
        estimated_level=chosen_cefr,
        pillar_progress={}
    )

    # Set bridge language from user profile
    profile = g.user.learner_profile or {}
    known_langs = profile.get('known_languages', [])
    if known_langs:
        best_bridge = None
        best_level = -1
        level_order = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 6}
        for kl in known_langs:
            if isinstance(kl, dict):
                lvl = level_order.get(kl.get('level', 'A1'), 0)
                if lvl > best_level:
                    best_level = lvl
                    best_bridge = kl.get('code')
        user_language.bridge_language = best_bridge

    # Initialize pillar progress
    # - Pillars at CEFR levels STRICTLY BELOW chosen level => auto-completed
    # - Pillars at chosen CEFR level => available (if prereqs met)
    # - Pillars above => locked
    pillars = get_pillars_for_language(lang)
    initial_progress = {}
    skipped_pillars = set()

    # First pass: mark auto-completed pillars
    for pillar in pillars:
        pid = pillar['id']
        pillar_cefr = pillar.get('cefr', 'A0')
        pillar_cefr_idx = CECRL_LEVELS.index(pillar_cefr) if pillar_cefr in CECRL_LEVELS else 0

        if pillar_cefr_idx < cefr_index:
            # Auto-complete all pillars below chosen level
            initial_progress[pid] = {
                'status': 'completed',
                'mastery': 100,
                'completed_at': datetime.utcnow().isoformat(),
                'skipped': True
            }
            skipped_pillars.add(pid)

    # Second pass: set status for remaining pillars
    for pillar in pillars:
        pid = pillar['id']
        if pid in skipped_pillars:
            continue

        prereqs = pillar.get('prereq', [])
        prereqs_met = all(p in skipped_pillars for p in prereqs)

        pillar_cefr = pillar.get('cefr', 'A0')
        pillar_cefr_idx = CECRL_LEVELS.index(pillar_cefr) if pillar_cefr in CECRL_LEVELS else 0

        if pillar_cefr_idx == cefr_index:
            # At chosen level: available if prereqs met, else locked
            initial_progress[pid] = {
                'status': 'available' if prereqs_met else 'locked',
                'mastery': 0
            }
        elif not prereqs:
            # No prereqs (entry point) => available
            initial_progress[pid] = {
                'status': 'available',
                'mastery': 0
            }
        else:
            initial_progress[pid] = {
                'status': 'available' if prereqs_met else 'locked',
                'mastery': 0
            }

    user_language.pillar_progress = initial_progress

    db.session.add(user_language)
    db.session.commit()

    return jsonify({
        'success': True,
        'redirect': url_for('pillars.language_view', lang=lang),
        'auto_completed': len(skipped_pillars),
        'estimated_level': chosen_cefr
    })


@bp.route('/<lang>/<pillar_id>/start', methods=['POST'])
def start_pillar(lang, pillar_id):
    """Start working on a specific pillar."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    # Get user language
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        return jsonify({'error': 'Langue non commencee'}), 400
    
    # Get pillar config
    pillar_config = get_pillar(lang, pillar_id)
    if not pillar_config:
        return jsonify({'error': f"Pilier '{pillar_id}' non trouve"}), 400
    
    # Check status
    progress = user_language.get_pillar_status(pillar_id)
    # No lock check - user can start any pillar freely
    
    if progress.get('status') == 'completed':
        return jsonify({'error': 'Pilier deja complete', 'deck_id': progress.get('deck_id')})
    
    # Check if deck already exists
    if progress.get('deck_id'):
        return jsonify({
            'success': True,
            'deck_id': progress.get('deck_id'),
            'message': 'Deck existant'
        })
    
    # Create a deck for this pillar
    lang_config = get_language(lang)
    deck_name = f"[Pilier] {lang_config['name']} - {pillar_config['name']}"
    
    deck = Deck(
        user_id=g.user.id,
        name=deck_name,
        description=pillar_config.get('description', ''),
        is_program_deck=True
    )
    db.session.add(deck)
    db.session.flush()  # Get deck.id
    
    # Try to load pre-generated content
    content_path = os.path.join('pillar_content', lang, f"{pillar_id}.json")
    cards_loaded = 0
    exercises_loaded = 0
    
    # CEFR to difficulty mapping
    cefr_difficulty = {'A0': 1, 'A1': 2, 'A2': 3, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 5}
    pillar_cefr = pillar_config.get('cefr', 'A0')
    pillar_difficulty = cefr_difficulty.get(pillar_cefr, 1)
    
    if os.path.exists(content_path):
        try:
            with open(content_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            # Create cards from content
            for card_data in content.get('cards', []):
                card = Card(
                    deck_id=deck.id,
                    front=card_data.get('front', ''),
                    back=card_data.get('back', ''),
                    slot_type=pillar_config.get('category', 'pillar')
                )
                db.session.add(card)
                cards_loaded += 1
            
            # Load pre-generated exercises
            for ex_type, ex_list in content.get('exercises', {}).items():
                if not isinstance(ex_list, list):
                    continue
                for ex_data in ex_list:
                    exercise = PillarExercise(
                        language_code=lang,
                        exercise_type=ex_type,
                        difficulty=pillar_difficulty,
                        content=ex_data,
                        pillar_id=pillar_id,
                        batch_id=f"pregenerated_{pillar_id}",
                    )
                    db.session.add(exercise)
                    exercises_loaded += 1
        except Exception as e:
            print(f"Error loading pillar content: {e}")
    
    # Update pillar progress
    user_language.update_pillar(pillar_id, status='in_progress', deck_id=deck.id)
    flag_modified(user_language, 'pillar_progress')
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'deck_id': deck.id,
        'cards_loaded': cards_loaded,
        'exercises_loaded': exercises_loaded,
        'message': f'Deck cree avec {cards_loaded} cartes et {exercises_loaded} exercices'
    })


@bp.route('/<lang>/<pillar_id>/complete', methods=['POST'])
def complete_pillar(lang, pillar_id):
    """Mark a pillar as completed."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        return jsonify({'error': 'Langue non commencee'}), 400
    
    pillar_config = get_pillar(lang, pillar_id)
    if not pillar_config:
        return jsonify({'error': f"Pilier '{pillar_id}' non trouve"}), 400
    
    # Update status
    user_language.update_pillar(pillar_id, status='completed', mastery=100)
    
    # Unlock dependent pillars
    all_pillars = get_pillars_for_language(lang)
    completed_pillars = [
        pid for pid, p in user_language.pillar_progress.items()
        if p.get('status') == 'completed'
    ]
    completed_pillars.append(pillar_id)
    
    for pillar in all_pillars:
        pid = pillar['id']
        current_status = user_language.get_pillar_status(pid).get('status')
        if current_status == 'locked':
            if check_pillar_available(lang, pid, completed_pillars):
                user_language.update_pillar(pid, status='available')
    
    # Update estimated level based on completed pillars (CEFR field)
    cefr_order = {c: i for i, c in enumerate(CECRL_LEVELS)}
    max_cefr = 'A0'
    for pid in completed_pillars:
        p = get_pillar(lang, pid)
        if p:
            c = p.get('cefr', 'A0')
            if cefr_order.get(c, 0) > cefr_order.get(max_cefr, 0):
                max_cefr = c
    user_language.estimated_level = max_cefr
    
    flag_modified(user_language, 'pillar_progress')
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f"Pilier '{pillar_config['name']}' complete!",
        'new_level': user_language.estimated_level
    })


@bp.route('/<lang>/<pillar_id>/progress', methods=['POST'])
def update_pillar_progress(lang, pillar_id):
    """Update mastery progress for a pillar."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        return jsonify({'error': 'Langue non commencee'}), 400
    
    mastery = request.json.get('mastery', 0)
    user_language.update_pillar(pillar_id, mastery=min(100, max(0, mastery)))
    
    # Auto-complete if mastery >= 80%
    if mastery >= 80:
        user_language.update_pillar(pillar_id, status='completed')
    
    flag_modified(user_language, 'pillar_progress')
    db.session.commit()
    
    return jsonify({'success': True, 'mastery': mastery})


@bp.route('/<lang>/delete', methods=['POST'])
def delete_language(lang):
    """Delete a language and all its progress (with confirmation)."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        return jsonify({'error': 'Langue non trouvee'}), 404
    
    # Delete associated pillar decks
    for pillar_id, progress in (user_language.pillar_progress or {}).items():
        deck_id = progress.get('deck_id')
        if deck_id:
            deck = Deck.query.get(deck_id)
            if deck and deck.user_id == g.user.id:
                db.session.delete(deck)
    
    db.session.delete(user_language)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f"Langue supprimee",
        'redirect': url_for('pillars.index')
    })


# =============================================================================
# LESSON API
# =============================================================================

@bp.route('/<lang>/<pillar_id>/lesson')
def api_lesson(lang, pillar_id):
    """Return lesson content for a pillar from pre-generated JSON."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    content_path = os.path.join('pillar_content', lang, f'{pillar_id}.json')
    if not os.path.exists(content_path):
        return jsonify({'lesson': None, 'message': 'Pas de contenu pre-genere'})
    
    try:
        with open(content_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        lesson = content.get('lesson', {})
        return jsonify({
            'lesson': lesson,
            'pillar_id': pillar_id,
            'name': content.get('name', ''),
            'cefr': content.get('cefr', ''),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<lang>/<pillar_id>/cards')
def api_cards(lang, pillar_id):
    """Return flashcards for a pillar's deck."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id, language_code=lang
    ).first()
    if not user_language:
        return jsonify({'cards': []})
    
    progress = user_language.get_pillar_status(pillar_id)
    deck_id = progress.get('deck_id')
    if not deck_id:
        return jsonify({'cards': []})
    
    from app.models import Card
    cards = Card.query.filter_by(deck_id=deck_id).all()
    return jsonify({
        'cards': [
            {'id': c.id, 'front': c.front, 'back': c.back}
            for c in cards
        ]
    })


# =============================================================================
# API - GET DATA
# =============================================================================

@bp.route('/api/languages')
def api_languages():
    """Get all supported languages."""
    return jsonify(get_all_languages_summary())


@bp.route('/api/<lang>/pillars')
def api_pillars(lang):
    """Get all pillars for a language."""
    lang_config = get_language(lang)
    if not lang_config:
        return jsonify({'error': 'Langue non supportee'}), 404
    
    return jsonify({
        'language': {
            'code': lang,
            'name': lang_config['name'],
            'native_name': lang_config['native_name']
        },
        'pillars': lang_config['pillars']
    })


@bp.route('/api/<lang>/progress')
def api_progress(lang):
    """Get user's progress for a language."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    
    user_language = UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()
    
    if not user_language:
        return jsonify({'error': 'Langue non commencee'}), 404
    
    return jsonify(user_language.to_dict())

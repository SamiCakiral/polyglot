"""
Routes pour les exercices piliers: page liste, session de jeu, API generate/check/stats/difficulty.
"""
import json
from flask import Blueprint, render_template, redirect, url_for, g, request, jsonify
from app import db
from app.models import (
    UserLanguage,
    PillarExercise,
    PillarExerciseResult,
)
from app.pillar_config import get_language
from app.exercise_config import get_available_exercise_types, get_pronouns, get_tenses
from app.exercise_generator import generate_exercise_batch
from app.cecr_config import (
    MASTERY_POINTS, MASTERY_PENALTY, MASTERY_THRESHOLDS,
    get_pillars_for_exercise_type, get_exercise_types_for_pillar,
    check_level_readiness,
    get_next_level, CECR_PILLAR_MAPPING, CECR_ORDER,
)
from sqlalchemy.orm.attributes import flag_modified

bp = Blueprint('pillar_exercises', __name__)


def _check_login():
    if not g.user:
        return redirect(url_for('auth.login'))
    return None


def _get_user_language(lang):
    if not g.user:
        return None
    return UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()


def _get_exercise_difficulty(user_language):
    """Difficulty 1-5 stored in UserLanguage.pillar_progress['_exercise_difficulty']."""
    if not user_language or not user_language.pillar_progress:
        return 1
    return user_language.pillar_progress.get('_exercise_difficulty', 1)


def _set_exercise_difficulty(user_language, value):
    """Set difficulty 1-5."""
    if not user_language:
        return
    if user_language.pillar_progress is None:
        user_language.pillar_progress = {}
    user_language.pillar_progress['_exercise_difficulty'] = max(1, min(5, int(value)))
    flag_modified(user_language, 'pillar_progress')
    db.session.commit()


# =============================================================================
# PAGE ROUTES
# =============================================================================

@bp.route('/pillars/<lang>/exercises')
def exercises_list(lang):
    """Page liste des mini-jeux (onglet S'exercer).
    
    Query params:
      - pillar: filter exercises to those relevant to a specific pillar ID
      - type: show specific exercise type directly ('all' for all)
    """
    redir = _check_login()
    if redir:
        return redir
    lang_config = get_language(lang)
    if not lang_config:
        return redirect(url_for('pillars.index'))
    user_language = _get_user_language(lang)
    if not user_language:
        return redirect(url_for('pillars.onboarding', lang=lang))

    available = get_available_exercise_types(lang_config)
    
    # Filtre par pilier : on ne garde que les types d'exercices lies a ce pilier
    pillar_filter = request.args.get('pillar')
    pillar_name = None
    if pillar_filter:
        pillars = lang_config.get('pillars', [])
        pillar_cfg = next((p for p in pillars if p['id'] == pillar_filter), None)
        if pillar_cfg:
            pillar_name = pillar_cfg.get('name', pillar_filter)
            relevant_types = get_exercise_types_for_pillar(pillar_cfg)
            if relevant_types:
                available = [(t, n, d) for (t, n, d) in available if t in relevant_types]

    # Stats par type
    stats_by_type = {}
    for typ, _name, _desc in available:
        correct = db.session.query(PillarExerciseResult).filter(
            PillarExerciseResult.user_id == g.user.id,
            PillarExerciseResult.language_code == lang,
            PillarExerciseResult.exercise_type == typ,
            PillarExerciseResult.correct == True
        ).count()
        total = db.session.query(PillarExerciseResult).filter(
            PillarExerciseResult.user_id == g.user.id,
            PillarExerciseResult.language_code == lang,
            PillarExerciseResult.exercise_type == typ,
        ).count()
        stats_by_type[typ] = {'correct': correct, 'total': total}

    completed_count = user_language.get_completed_pillars_count()
    total_count = len(lang_config.get('pillars', []))
    skip_advice = (user_language.pillar_progress or {}).get('_skip_advice', False)

    return render_template(
        'pillars/exercises.html',
        lang_code=lang,
        lang_config=lang_config,
        user_language=user_language,
        available_types=available,
        stats_by_type=stats_by_type,
        difficulty=_get_exercise_difficulty(user_language),
        completed_count=completed_count,
        total_count=total_count,
        skip_advice=skip_advice,
        pillar_filter=pillar_filter,
        pillar_name=pillar_name,
    )


@bp.route('/pillars/<lang>/exercises/<exercise_type>')
def exercise_session(lang, exercise_type):
    """Page de jeu pour un type d'exercice."""
    redir = _check_login()
    if redir:
        return redir
    lang_config = get_language(lang)
    if not lang_config:
        return redirect(url_for('pillars.index'))
    user_language = _get_user_language(lang)
    if not user_language:
        return redirect(url_for('pillars.onboarding', lang=lang))

    available = get_available_exercise_types(lang_config)
    type_ids = [t[0] for t in available]
    if exercise_type not in type_ids:
        return redirect(url_for('pillar_exercises.exercises_list', lang=lang))

    difficulty = _get_exercise_difficulty(user_language)
    type_name = next((t[1] for t in available if t[0] == exercise_type), exercise_type)
    skip_advice = (user_language.pillar_progress or {}).get('_skip_advice', False)

    return render_template(
        'pillars/exercise_session.html',
        lang_code=lang,
        lang_config=lang_config,
        user_language=user_language,
        exercise_type=exercise_type,
        exercise_type_name=type_name,
        difficulty=difficulty,
        pronouns=get_pronouns(lang),
        tenses=get_tenses(lang),
        skip_advice=skip_advice,
    )


# =============================================================================
# API ROUTES
# =============================================================================

def _build_user_context(user, user_language):
    """
    Construit un dict user_context à partir du profil utilisateur
    pour personnaliser la génération d'exercices et d'examens.
    """
    ctx = {}
    if user and hasattr(user, 'learner_profile') and user.learner_profile:
        profile = user.learner_profile
        ctx['native_language'] = profile.get('native_language', 'fr')
        ctx['known_languages'] = profile.get('known_languages', [])
        ctx['goals'] = profile.get('goals', [])
        ctx['correction_preference'] = profile.get('correction_preference', 'moderate')
        ctx['learning_style'] = profile.get('learning_style', 'balanced')

    if user_language:
        progress = user_language.pillar_progress or {}
        weakness = progress.get('_weakness_profile')
        if weakness and isinstance(weakness, dict):
            ctx['weakness_profile'] = weakness

    return ctx if ctx else None


@bp.route('/api/pillars/<lang>/exercises/generate', methods=['POST'])
def api_generate(lang):
    """Génère un batch d'exercices (arrière-plan ou synchrone)."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    lang_config = get_language(lang)
    if not lang_config:
        return jsonify({'error': 'Langue non supportee'}), 400
    data = request.get_json() or {}
    exercise_type = data.get('exercise_type')
    difficulty = int(data.get('difficulty', 1))
    count = int(data.get('count', 10))
    pillar_id = data.get('pillar_id')
    verb_mode = data.get('verb_mode', 'both')  # 'regular', 'irregular', 'both'
    available = get_available_exercise_types(lang_config)
    type_ids = [t[0] for t in available]
    if not exercise_type or exercise_type not in type_ids:
        return jsonify({'error': 'Type d\'exercice invalide'}), 400
    count = max(1, min(20, count))
    difficulty = max(1, min(5, difficulty))

    # Construire le contexte utilisateur pour personnaliser la génération
    user_language = _get_user_language(lang)
    user_context = _build_user_context(g.user, user_language)

    try:
        created = generate_exercise_batch(
            lang, exercise_type, difficulty,
            count=count, pillar_id=pillar_id, verb_mode=verb_mode,
            user_context=user_context,
        )
        if not created:
            return jsonify({'created': 0, 'batch_id': None, 'warning': 'Le LLM n\'a pas pu generer d\'exercices. Verifiez que le serveur LLM est accessible.'}), 200
        return jsonify({'created': len(created), 'batch_id': created[0].batch_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/pillars/<lang>/exercises/check', methods=['POST'])
def api_check(lang):
    """Valide une réponse utilisateur (exact ou LLM selon type)."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    data = request.get_json() or {}
    exercise_id = data.get('exercise_id')
    user_answer = data.get('user_answer')
    time_taken_ms = data.get('time_taken_ms')
    if not exercise_id:
        return jsonify({'error': 'exercise_id manquant'}), 400
    ex = PillarExercise.query.get(exercise_id)
    if not ex or ex.language_code != lang:
        return jsonify({'error': 'Exercice introuvable'}), 404
    # Parse conjugation grid from JSON string
    if ex.exercise_type == 'conjugation' and isinstance(user_answer, str):
        try:
            user_answer = json.loads(user_answer) if user_answer.strip() else {}
        except (ValueError, TypeError):
            user_answer = {}
    if user_answer is None:
        user_answer = ''
    answer_for_db = json.dumps(user_answer)[:500] if isinstance(user_answer, dict) else str(user_answer)[:500]
    correct, feedback = _validate_answer(ex, user_answer)
    diff = ex.difficulty or 1
    r = PillarExerciseResult(
        user_id=g.user.id,
        exercise_id=ex.id,
        language_code=lang,
        exercise_type=ex.exercise_type,
        correct=correct,
        user_answer=answer_for_db,
        time_taken_ms=time_taken_ms,
        difficulty=diff,
    )
    db.session.add(r)

    # Auto-mastery: update pillar progress based on exercise result
    mastery_info = _update_pillar_mastery(lang, ex.exercise_type, correct, diff)

    # Weakness tracking: update error patterns
    _update_weakness_profile(lang, ex.exercise_type, correct, ex.content, diff)

    db.session.commit()
    return jsonify({
        'correct': correct,
        'feedback': feedback,
        'expected': _get_expected_answer(ex),
        'mastery_update': mastery_info,
    })


def _update_weakness_profile(lang, exercise_type, correct, content, difficulty):
    """
    Track error patterns for adaptive learning.
    Stores weakness profile in UserLanguage.pillar_progress['_weakness_profile'].
    """
    user_language = _get_user_language(lang)
    if not user_language:
        return

    if user_language.pillar_progress is None:
        user_language.pillar_progress = {}

    profile = user_language.pillar_progress.get('_weakness_profile', {
        'total_exercises': 0,
        'total_correct': 0,
        'by_type': {},
        'by_difficulty': {},
        'recent_errors': [],
    })

    # Update totals
    profile['total_exercises'] = profile.get('total_exercises', 0) + 1
    if correct:
        profile['total_correct'] = profile.get('total_correct', 0) + 1

    # Update by type
    by_type = profile.get('by_type', {})
    if exercise_type not in by_type:
        by_type[exercise_type] = {'total': 0, 'correct': 0}
    by_type[exercise_type]['total'] += 1
    if correct:
        by_type[exercise_type]['correct'] += 1
    profile['by_type'] = by_type

    # Update by difficulty
    by_diff = profile.get('by_difficulty', {})
    diff_str = str(difficulty)
    if diff_str not in by_diff:
        by_diff[diff_str] = {'total': 0, 'correct': 0}
    by_diff[diff_str]['total'] += 1
    if correct:
        by_diff[diff_str]['correct'] += 1
    profile['by_difficulty'] = by_diff

    # Track recent errors (keep last 20)
    if not correct and content:
        error_info = {
            'type': exercise_type,
            'difficulty': difficulty,
        }
        # Extract relevant info from content
        if exercise_type == 'conjugation':
            error_info['verb'] = content.get('verb', '')
            error_info['tense'] = content.get('tense', '')
        elif exercise_type == 'fill_blank':
            error_info['hint'] = content.get('hint_verb', '') or content.get('hint_tense', '')
        elif exercise_type == 'gender':
            error_info['word'] = content.get('word', '')

        recent = profile.get('recent_errors', [])
        recent.append(error_info)
        profile['recent_errors'] = recent[-20:]  # Keep last 20

    user_language.pillar_progress['_weakness_profile'] = profile
    flag_modified(user_language, 'pillar_progress')


def _update_pillar_mastery(lang, exercise_type, correct, difficulty):
    """
    Update pillar mastery based on exercise result.
    Returns info about what was updated for the frontend.
    """
    user_language = _get_user_language(lang)
    if not user_language:
        return None

    lang_config = get_language(lang)
    if not lang_config:
        return None

    # Find which pillars this exercise type reinforces
    pillar_ids = get_pillars_for_exercise_type(lang_config, exercise_type)
    if not pillar_ids:
        return None

    # Also include specific pillar_id if the exercise has one
    if user_language.pillar_progress is None:
        user_language.pillar_progress = {}

    points = MASTERY_POINTS.get(difficulty, 2) if correct else MASTERY_PENALTY.get(difficulty, -1)
    updated = []

    for pid in pillar_ids:
        p = user_language.pillar_progress.get(pid)
        if not isinstance(p, dict):
            continue
        # Only update in_progress or available pillars
        status = p.get('status', 'locked')
        if status in ('locked', 'completed'):
            continue

        old_mastery = p.get('mastery', 0)
        new_mastery = max(0, min(100, old_mastery + points))
        p['mastery'] = new_mastery

        # Auto-complete if threshold reached
        if new_mastery >= MASTERY_THRESHOLDS['auto_complete'] and status != 'completed':
            p['status'] = 'completed'
            from datetime import datetime
            p['completed_at'] = datetime.utcnow().isoformat()

        updated.append({
            'pillar_id': pid,
            'mastery': new_mastery,
            'delta': points,
            'status': p.get('status'),
        })

    if updated:
        flag_modified(user_language, 'pillar_progress')

    return updated if updated else None


def _normalize(s):
    if s is None:
        return ''
    return ' '.join(str(s).lower().strip().split())


def _validate_answer(ex, user_answer):
    """Return (correct: bool, feedback: str)."""
    c = ex.content or {}
    if ex.exercise_type == 'conjugation':
        # user_answer can be JSON dict { "io": "vado", ... } or single string for one cell
        if isinstance(user_answer, dict):
            answers = c.get('answers') or {}
            for pron, expected in answers.items():
                if _normalize(user_answer.get(pron, '')) != _normalize(expected):
                    return False, f"'{pron}': attendu « {expected} »."
            return True, "Tout est correct."
        # single line validation: not used for full grid; assume we get dict from front
        return False, "Réponse invalide (format grille)."
    if ex.exercise_type == 'fill_blank':
        expected = c.get('answer', '')
        ok = _normalize(user_answer) == _normalize(expected)
        return ok, expected if not ok else "Correct."
    if ex.exercise_type == 'transform':
        expected = c.get('answer', '')
        ok = _normalize(user_answer) == _normalize(expected)
        return ok, expected if not ok else "Correct."
    if ex.exercise_type == 'word_order':
        expected = c.get('answer', '')
        ok = _normalize(user_answer) == _normalize(expected)
        return ok, expected if not ok else "Correct."
    if ex.exercise_type == 'particles':
        expected = c.get('answer', '')
        ok = _normalize(user_answer) == _normalize(expected)
        return ok, (c.get('explanation') or expected) if not ok else "Correct."
    if ex.exercise_type == 'gender':
        expected = c.get('answer', '')
        ok = _normalize(user_answer) == _normalize(expected)
        return ok, (c.get('full') or expected) if not ok else "Correct."
    return False, "Type inconnu."


def _get_expected_answer(ex):
    """Return the expected answer for display after wrong attempt."""
    c = ex.content or {}
    if ex.exercise_type == 'conjugation':
        return c.get('answers')
    return c.get('answer') or c.get('full') or ''


@bp.route('/api/pillars/<lang>/exercises/stats')
def api_stats(lang):
    """Statistiques de l'utilisateur pour cette langue."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    q = PillarExerciseResult.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
    )
    total = q.count()
    correct = q.filter_by(correct=True).count()
    by_type = {}
    rows = PillarExerciseResult.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
    ).all()
    for r in rows:
        if r.exercise_type not in by_type:
            by_type[r.exercise_type] = {'total': 0, 'correct': 0}
        by_type[r.exercise_type]['total'] += 1
        if r.correct:
            by_type[r.exercise_type]['correct'] += 1
    return jsonify({
        'total_attempts': total,
        'total_correct': correct,
        'by_type': by_type,
    })


@bp.route('/api/pillars/<lang>/exercises/difficulty', methods=['POST'])
def api_difficulty(lang):
    """Ajuster la difficulté (1-5) pour les exercices de cette langue."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    user_language = _get_user_language(lang)
    if not user_language:
        return jsonify({'error': 'Langue non démarrée'}), 400
    data = request.get_json() or {}
    value = data.get('difficulty', 1)
    try:
        value = max(1, min(5, int(value)))
    except (TypeError, ValueError):
        value = 1
    _set_exercise_difficulty(user_language, value)
    return jsonify({'difficulty': value})


@bp.route('/api/pillars/<lang>/exercises/next')
def api_next(lang):
    """Retourne les N prochains exercices non tentés (ou à réviser)."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    exercise_type = request.args.get('exercise_type')
    difficulty = request.args.get('difficulty', type=int) or 1
    limit = request.args.get('limit', type=int) or 5
    verb_mode = request.args.get('verb_mode', 'both')  # 'regular', 'irregular', 'both'
    limit = max(1, min(20, limit))
    if not exercise_type:
        return jsonify({'error': 'exercise_type manquant'}), 400
    # Exercices de ce type/lang/difficulty que l'utilisateur n'a pas encore réussis
    sub = db.session.query(PillarExerciseResult.exercise_id).filter(
        PillarExerciseResult.user_id == g.user.id,
        PillarExerciseResult.correct == True,
    )
    q = PillarExercise.query.filter(
        PillarExercise.language_code == lang,
        PillarExercise.exercise_type == exercise_type,
        PillarExercise.difficulty == difficulty,
        ~PillarExercise.id.in_(sub),
    )
    # Filter by verb mode (conjugation only)
    if exercise_type == 'conjugation' and verb_mode in ('regular', 'irregular'):
        all_ex = q.all()
        if verb_mode == 'irregular':
            exercises = [ex for ex in all_ex if (ex.content or {}).get('irregular', False)][:limit]
        else:  # regular
            exercises = [ex for ex in all_ex if not (ex.content or {}).get('irregular', False)][:limit]
    else:
        exercises = q.order_by(PillarExercise.id).limit(limit).all()
    # Si moins de 5, le front peut déclencher generate
    out = []
    for ex in exercises:
        out.append({
            'id': ex.id,
            'exercise_type': ex.exercise_type,
            'difficulty': ex.difficulty,
            'content': ex.content,
        })
    return jsonify({'exercises': out})


@bp.route('/api/pillars/<lang>/exercises/skip-advice', methods=['POST'])
def api_skip_advice(lang):
    """Marquer 'ne plus afficher le conseil' pour cette langue."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    user_language = _get_user_language(lang)
    if not user_language:
        return jsonify({'error': 'Langue non demarree'}), 400
    if user_language.pillar_progress is None:
        user_language.pillar_progress = {}
    user_language.pillar_progress['_skip_advice'] = True
    flag_modified(user_language, 'pillar_progress')
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/api/pillars/<lang>/exercises/weakness-profile')
def api_weakness_profile(lang):
    """Get the user's weakness profile and adaptive suggestions."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    user_language = _get_user_language(lang)
    if not user_language:
        return jsonify({'error': 'Langue non demarree'}), 400

    progress = user_language.pillar_progress or {}
    profile = progress.get('_weakness_profile', {})

    if not profile or profile.get('total_exercises', 0) < 5:
        return jsonify({
            'profile': profile,
            'suggestions': None,
            'message': 'Pas assez de donnees. Faites au moins 5 exercices.',
        })

    # Calculate weakest areas
    by_type = profile.get('by_type', {})
    weakest_types = []
    for ex_type, stats in by_type.items():
        total = stats.get('total', 0)
        correct = stats.get('correct', 0)
        if total >= 3:
            rate = correct / total
            weakest_types.append({'type': ex_type, 'success_rate': round(rate * 100), 'total': total})

    weakest_types.sort(key=lambda x: x['success_rate'])

    # Find weakest difficulty
    by_diff = profile.get('by_difficulty', {})
    weakest_diff = None
    min_rate = 1.0
    for diff_str, stats in by_diff.items():
        total = stats.get('total', 0)
        if total >= 3:
            rate = stats.get('correct', 0) / total
            if rate < min_rate:
                min_rate = rate
                weakest_diff = int(diff_str)

    # Build suggestions
    suggestions = {
        'weakest_types': weakest_types[:3],
        'recommended_type': weakest_types[0]['type'] if weakest_types else None,
        'recommended_difficulty': weakest_diff or 1,
        'overall_rate': round(profile.get('total_correct', 0) / max(profile.get('total_exercises', 1), 1) * 100),
        'recent_error_patterns': _analyze_error_patterns(profile.get('recent_errors', [])),
    }

    return jsonify({
        'profile': profile,
        'suggestions': suggestions,
    })


def _analyze_error_patterns(recent_errors):
    """Analyze recent errors to find patterns."""
    if not recent_errors:
        return []

    patterns = {}
    for err in recent_errors:
        key = err.get('type', 'unknown')
        if err.get('verb'):
            key += f":{err['verb']}"
        elif err.get('tense'):
            key += f":{err['tense']}"
        patterns[key] = patterns.get(key, 0) + 1

    # Return top patterns
    sorted_patterns = sorted(patterns.items(), key=lambda x: -x[1])
    return [{'pattern': p, 'count': c} for p, c in sorted_patterns[:5]]


@bp.route('/api/pillars/<lang>/level-readiness')
def api_level_readiness(lang):
    """Check if user is ready to take the CECR level exam."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401
    user_language = _get_user_language(lang)
    if not user_language:
        return jsonify({'error': 'Langue non demarree'}), 400
    lang_config = get_language(lang)
    if not lang_config:
        return jsonify({'error': 'Langue non supportee'}), 400

    current_level = user_language.estimated_level or 'A0'
    next_level = get_next_level(current_level)
    if not next_level:
        return jsonify({
            'current_level': current_level,
            'next_level': None,
            'ready': False,
            'reason': 'Niveau maximum atteint',
        })

    readiness = check_level_readiness(user_language, lang_config, next_level)
    readiness['current_level'] = current_level
    readiness['next_level'] = next_level
    readiness['level_label'] = CECR_PILLAR_MAPPING.get(next_level, {}).get('label', '')
    return jsonify(readiness)

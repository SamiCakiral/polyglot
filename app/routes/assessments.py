"""
Routes pour le systeme d'evaluation CECR: hub, creation d'examen, soumission de sections, resultats.
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, g, request, jsonify
from app import db
from app.models import UserLanguage, Assessment, AssessmentSection
from app.pillar_config import get_language
from app.cecr_config import (
    check_level_readiness, get_next_level, CECR_PILLAR_MAPPING,
    CECR_ORDER, EXAM_SECTIONS, EXAM_SECTIONS_BY_LEVEL,
    get_required_pillars_for_level,
)
from app.assessment_generator import create_assessment, grade_section
from app.llm_service import call_llm
from sqlalchemy.orm.attributes import flag_modified

bp = Blueprint('assessments', __name__)


def _check_login():
    if not g.user:
        return redirect(url_for('auth.login'))
    return None


def _build_assessment_user_context(user, user_language):
    """
    Construit un dict user_context à partir du profil utilisateur
    pour personnaliser la génération d'examens CECR.
    """
    ctx = {}
    if user and hasattr(user, 'learner_profile') and user.learner_profile:
        profile = user.learner_profile
        ctx['native_language'] = profile.get('native_language', 'fr')
        ctx['known_languages'] = profile.get('known_languages', [])
        ctx['goals'] = profile.get('goals', [])
        ctx['correction_preference'] = profile.get('correction_preference', 'moderate')

    if user_language:
        progress = user_language.pillar_progress or {}
        weakness = progress.get('_weakness_profile')
        if weakness and isinstance(weakness, dict):
            ctx['weakness_profile'] = weakness

    return ctx if ctx else None


def _get_user_language(lang):
    if not g.user:
        return None
    return UserLanguage.query.filter_by(
        user_id=g.user.id,
        language_code=lang
    ).first()


# =============================================================================
# PAGE ROUTES
# =============================================================================

@bp.route('/pillars/<lang>/assessments')
def assessment_hub(lang):
    """Hub page showing available and past assessments."""
    redir = _check_login()
    if redir:
        return redir
    lang_config = get_language(lang)
    if not lang_config:
        return redirect(url_for('pillars.index'))
    user_language = _get_user_language(lang)
    if not user_language:
        return redirect(url_for('pillars.onboarding', lang=lang))

    current_level = user_language.estimated_level or 'A0'
    next_level = get_next_level(current_level)

    # Check readiness for next level
    readiness = None
    if next_level:
        readiness = check_level_readiness(user_language, lang_config, next_level)
        readiness['next_level'] = next_level
        readiness['level_label'] = CECR_PILLAR_MAPPING.get(next_level, {}).get('label', '')

    # Past assessments
    past_assessments = Assessment.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
    ).order_by(Assessment.started_at.desc()).all()

    # Check if there's an in-progress assessment
    in_progress = Assessment.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
        status='in_progress',
    ).first()

    return render_template(
        'assessments/hub.html',
        lang_code=lang,
        lang_config=lang_config,
        user_language=user_language,
        current_level=current_level,
        next_level=next_level,
        readiness=readiness,
        past_assessments=past_assessments,
        in_progress=in_progress,
        cecr_mapping=CECR_PILLAR_MAPPING,
    )


@bp.route('/pillars/<lang>/dashboard')
def cecr_dashboard(lang):
    """CECR progress dashboard with radar chart and history."""
    redir = _check_login()
    if redir:
        return redir
    lang_config = get_language(lang)
    if not lang_config:
        return redirect(url_for('pillars.index'))
    user_language = _get_user_language(lang)
    if not user_language:
        return redirect(url_for('pillars.onboarding', lang=lang))

    current_level = user_language.estimated_level or 'A0'
    next_level = get_next_level(current_level)

    # Gather stats
    from app.models import PillarExerciseResult
    from sqlalchemy import func

    # Exercise stats by type
    type_stats = db.session.query(
        PillarExerciseResult.exercise_type,
        func.count(PillarExerciseResult.id),
        func.sum(db.case((PillarExerciseResult.correct == True, 1), else_=0))
    ).filter(
        PillarExerciseResult.user_id == g.user.id,
        PillarExerciseResult.language_code == lang,
    ).group_by(PillarExerciseResult.exercise_type).all()

    skill_scores = {}
    for ex_type, total, correct in type_stats:
        rate = int((correct / total) * 100) if total > 0 else 0
        skill_scores[ex_type] = {'total': total, 'correct': int(correct), 'rate': rate}

    # Assessment history
    assessments = Assessment.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
    ).order_by(Assessment.started_at.asc()).all()

    # Weakness profile
    progress = user_language.pillar_progress or {}
    weakness = progress.get('_weakness_profile', {})

    # Pillar completion stats
    pillar_count = 0
    completed_count = 0
    for k, v in progress.items():
        if not k.startswith('_') and isinstance(v, dict):
            pillar_count += 1
            if v.get('status') == 'completed':
                completed_count += 1

    return render_template(
        'assessments/dashboard.html',
        lang_code=lang,
        lang_config=lang_config,
        user_language=user_language,
        current_level=current_level,
        next_level=next_level,
        skill_scores=skill_scores,
        assessments=assessments,
        weakness=weakness,
        pillar_count=pillar_count,
        completed_count=completed_count,
        cecr_order=CECR_ORDER,
    )


@bp.route('/pillars/<lang>/assessments/<int:assessment_id>')
def assessment_exam(lang, assessment_id):
    """Exam mode page - locked interface with timer."""
    redir = _check_login()
    if redir:
        return redir
    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id or assessment.language_code != lang:
        return redirect(url_for('assessments.assessment_hub', lang=lang))
    if assessment.status not in ('in_progress',):
        return redirect(url_for('assessments.assessment_results', lang=lang, assessment_id=assessment_id))

    lang_config = get_language(lang)
    sections_config = {k: v for k, v in EXAM_SECTIONS.items()}

    return render_template(
        'assessments/exam.html',
        lang_code=lang,
        lang_config=lang_config,
        assessment=assessment,
        sections_config=sections_config,
    )


@bp.route('/pillars/<lang>/assessments/<int:assessment_id>/results')
def assessment_results(lang, assessment_id):
    """Results page after completing an assessment."""
    redir = _check_login()
    if redir:
        return redir
    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id or assessment.language_code != lang:
        return redirect(url_for('assessments.assessment_hub', lang=lang))
    if assessment.status == 'in_progress':
        return redirect(url_for('assessments.assessment_exam', lang=lang, assessment_id=assessment_id))

    lang_config = get_language(lang)
    sections_config = {k: v for k, v in EXAM_SECTIONS.items()}

    # Count pillars validated by this exam
    user_language = _get_user_language(lang)
    validated_pillars = []
    if user_language and assessment.status == 'passed':
        progress = user_language.pillar_progress or {}
        for pid, pdata in progress.items():
            if isinstance(pdata, dict) and pdata.get('validated_by_exam') == assessment.id:
                # Find pillar name
                pname = pid
                for p in lang_config.get('pillars', []):
                    if p['id'] == pid:
                        pname = p['name']
                        break
                validated_pillars.append(pname)

    return render_template(
        'assessments/results.html',
        lang_code=lang,
        lang_config=lang_config,
        assessment=assessment,
        sections_config=sections_config,
        validated_pillars=validated_pillars,
    )


# =============================================================================
# API ROUTES
# =============================================================================

@bp.route('/api/pillars/<lang>/assessments/start', methods=['POST'])
def api_start_assessment(lang):
    """Start a new assessment for the next CECR level."""
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
        return jsonify({'error': 'Niveau maximum atteint'}), 400

    # Check if there's already an in-progress assessment
    existing = Assessment.query.filter_by(
        user_id=g.user.id,
        language_code=lang,
        status='in_progress',
    ).first()
    if existing:
        return jsonify({'assessment_id': existing.id, 'resumed': True})

    # Build user context for personalized assessment generation
    user_context = _build_assessment_user_context(g.user, user_language)

    # Generate the assessment
    try:
        assessment = create_assessment(g.user.id, lang, next_level, user_context=user_context)
        if not assessment:
            return jsonify({'error': 'Impossible de generer l\'examen. Verifiez le serveur LLM.'}), 500
        return jsonify({'assessment_id': assessment.id, 'resumed': False})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/pillars/<lang>/assessments/<int:assessment_id>/section/<int:section_id>/submit', methods=['POST'])
def api_submit_section(lang, assessment_id, section_id):
    """Submit answers for a specific section."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401

    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id:
        return jsonify({'error': 'Examen introuvable'}), 404
    if assessment.status != 'in_progress':
        return jsonify({'error': 'Examen deja termine'}), 400

    section = AssessmentSection.query.get(section_id)
    if not section or section.assessment_id != assessment_id:
        return jsonify({'error': 'Section introuvable'}), 404

    data = request.get_json() or {}
    user_answers = data.get('answers')

    # Grade the section
    earned_points, feedback = grade_section(section, user_answers)

    section.user_answers = user_answers
    section.earned_points = earned_points
    section.feedback = feedback
    section.completed_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'earned_points': earned_points,
        'max_points': section.max_points,
        'feedback': feedback,
    })


@bp.route('/api/pillars/<lang>/assessments/<int:assessment_id>/complete', methods=['POST'])
def api_complete_assessment(lang, assessment_id):
    """Complete an assessment and calculate final results."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401

    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id:
        return jsonify({'error': 'Examen introuvable'}), 404

    # Calculate total score
    total_score = assessment.calculate_score()
    assessment.total_score = total_score
    assessment.completed_at = datetime.utcnow()

    passed = assessment.is_passed()
    assessment.status = 'passed' if passed else 'failed'

    # If passed, update user level AND auto-validate pillars
    validated_pillars = []
    if passed:
        user_language = _get_user_language(lang)
        if user_language:
            user_language.estimated_level = assessment.target_level
            user_language.last_activity = datetime.utcnow()

            # Auto-validate all pillars for this level and below
            lang_config = get_language(lang)
            if lang_config:
                required_pillars = get_required_pillars_for_level(lang_config, assessment.target_level)
                progress = user_language.pillar_progress or {}

                for pid in required_pillars:
                    p = progress.get(pid, {})
                    if not isinstance(p, dict):
                        p = {}
                    if p.get('status') != 'completed':
                        p['status'] = 'completed'
                        p['mastery'] = max(p.get('mastery', 0), 80)
                        p['validated_by_exam'] = assessment.id
                        progress[pid] = p
                        validated_pillars.append(pid)

                if validated_pillars:
                    user_language.pillar_progress = progress
                    flag_modified(user_language, 'pillar_progress')

    db.session.commit()

    return jsonify({
        'total_score': total_score,
        'passing_score': assessment.passing_score,
        'passed': passed,
        'new_level': assessment.target_level if passed else None,
        'validated_pillars': validated_pillars,
        'validated_count': len(validated_pillars),
    })


@bp.route('/api/pillars/<lang>/assessments/<int:assessment_id>')
def api_get_assessment(lang, assessment_id):
    """Get assessment details with sections."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401

    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id:
        return jsonify({'error': 'Examen introuvable'}), 404

    sections = []
    for s in assessment.sections:
        sec = {
            'id': s.id,
            'section_type': s.section_type,
            'order_idx': s.order_idx,
            'max_points': s.max_points,
            'earned_points': s.earned_points,
            'completed': s.completed_at is not None,
            'content': s.content,
        }
        # Only include user answers and feedback if section is completed
        if s.completed_at:
            sec['user_answers'] = s.user_answers
            sec['feedback'] = s.feedback
        sections.append(sec)

    return jsonify({
        'id': assessment.id,
        'target_level': assessment.target_level,
        'status': assessment.status,
        'total_score': assessment.total_score,
        'passing_score': assessment.passing_score,
        'time_limit_minutes': assessment.time_limit_minutes,
        'started_at': assessment.started_at.isoformat() if assessment.started_at else None,
        'completed_at': assessment.completed_at.isoformat() if assessment.completed_at else None,
        'sections': sections,
    })


@bp.route('/api/pillars/<lang>/assessments/<int:assessment_id>/dialogue/<int:section_id>/chat', methods=['POST'])
def api_dialogue_chat(lang, assessment_id, section_id):
    """Send a message in the interactive dialogue section and get the character's response."""
    if not g.user:
        return jsonify({'error': 'Non connecte'}), 401

    assessment = Assessment.query.get(assessment_id)
    if not assessment or assessment.user_id != g.user.id:
        return jsonify({'error': 'Examen introuvable'}), 404

    section = AssessmentSection.query.get(section_id)
    if not section or section.assessment_id != assessment_id or section.section_type != 'dialogue':
        return jsonify({'error': 'Section introuvable'}), 404

    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Message vide'}), 400

    content = section.content or {}
    character = content.get('character', {})
    context = content.get('context', '')
    messages = content.get('messages', [])

    # Build conversation history
    lang_config = get_language(lang)
    lang_name = lang_config.get('name', lang) if lang_config else lang

    system_prompt = f"""Tu es {character.get('name', 'un personnage')} ({character.get('role', '')}).
Personnalite: {character.get('personality', 'normal')}.
Contexte: {context}

Tu joues ce personnage dans un dialogue en {lang_name} avec un apprenant de niveau {assessment.target_level}.
Reponds UNIQUEMENT en {lang_name}. Sois naturel, coherent avec ton role.
Tes repliques doivent etre de 1 a 3 phrases maximum.
Si l'apprenant fait une erreur grave, tu peux reagir naturellement (ex: ne pas comprendre)
mais reste bienveillant et aide-le a continuer la conversation."""

    # Build messages for the LLM
    llm_messages = [{'role': 'system', 'content': system_prompt}]
    for m in messages:
        role = 'assistant' if m.get('role') != 'user' else 'user'
        llm_messages.append({'role': role, 'content': m.get('text', '')})
    llm_messages.append({'role': 'user', 'content': user_message})

    # Call LLM
    try:
        response = call_llm(system_prompt, user_message, temperature=0.7, timeout=30)
        if not response:
            response = "..."  # Fallback
    except Exception:
        response = "..."

    # Save messages
    messages.append({'role': 'user', 'text': user_message, 'name': 'Vous'})
    messages.append({'role': 'assistant', 'text': response, 'name': character.get('name', 'Personnage')})
    content['messages'] = messages
    section.content = content
    flag_modified(section, 'content')
    db.session.commit()

    return jsonify({
        'response': response,
        'character_name': character.get('name', 'Personnage'),
        'exchange_count': len([m for m in messages if m.get('role') == 'user']),
        'expected_exchanges': content.get('expected_exchanges', 8),
    })

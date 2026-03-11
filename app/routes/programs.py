"""
Routes for Training Program Builder.
Allows users to create and configure custom training programs.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g
from app.models import TrainingProgram, Deck, User
from app import db
from app.llm_service import generate_lego_templates, generate_daily_themes
from sqlalchemy.orm.attributes import flag_modified
import json

bp = Blueprint('programs', __name__, url_prefix='/programs')

# Available languages (native first, then target languages)
LANGUAGES = [
    ('french', '🇫🇷 Français'),
    ('italian', '🇮🇹 Italien'),
    ('spanish', '🇪🇸 Espagnol'),
    ('german', '🇩🇪 Allemand'),
    ('english', '🇬🇧 Anglais'),
    ('portuguese', '🇵🇹 Portugais'),
    ('japanese', '🇯🇵 Japonais'),
    ('chinese', '🇨🇳 Chinois'),
    ('korean', '🇰🇷 Coréen'),
    ('arabic', '🇸🇦 Arabe'),
    ('russian', '🇷🇺 Russe'),
]

# Exercise definitions
EXERCISES = [
    ('flashcards', '📚 Flashcards', 'Révision des cartes avec système de dette prioritaire'),
    ('git_input', '📝 Git Input', 'Traduire un texte de la langue cible vers ta langue'),
    ('gym', '🏋️ The Gym', 'Exercices Lego (construction) et FSI (mutations)'),
    ('shadowing', '🎧 Shadowing', 'Écoute et répétition avec TTS ou YouTube'),
    ('git_output', '🔄 Git Output', 'Reconstruire le texte d\'hier dans la langue cible'),
    ('writing', '✍️ Smart Writing', 'Écriture créative avec économie de tokens'),
]

# Default FSI mutations (extended)
DEFAULT_FSI_MUTATIONS = ['NEGATION', 'FUTUR', 'PASSE', 'PLURIEL', 'QUESTION', 'CONDITIONNEL', 'FORMEL', 'POINT_DE_VUE']

# Interest suggestions for theme preferences
INTEREST_OPTIONS = [
    'sport', 'cuisine', 'voyage', 'tech', 'cinema', 'musique',
    'nature', 'art', 'histoire', 'actualite', 'business', 'sante', 'mode', 'gaming'
]


@bp.before_request
def check_login():
    if not g.user:
        return redirect(url_for('auth.login'))


@bp.route('/')
def list_programs():
    """List all training programs for current user."""
    programs = TrainingProgram.query.filter_by(user_id=g.user.id).all()
    return render_template('programs/list.html', programs=programs)


@bp.route('/new')
def new_program():
    """Start the program creation wizard."""
    # Clear any existing wizard data
    session.pop('program_wizard', None)
    return redirect(url_for('programs.wizard_step', step=1))


@bp.route('/new/step/<int:step>', methods=['GET', 'POST'])
def wizard_step(step):
    """Handle each step of the 5-step creation wizard."""
    # Initialize wizard data if needed
    if 'program_wizard' not in session:
        session['program_wizard'] = {}
    
    wizard_data = session['program_wizard']
    
    if request.method == 'POST':
        if step == 1:
            # =============================================
            # STEP 1: Basic info + Learner profile
            # =============================================
            wizard_data['name'] = request.form.get('name', '').strip()
            wizard_data['description'] = request.form.get('description', '').strip()
            wizard_data['target_language'] = request.form.get('target_language', 'italian')
            wizard_data['native_language'] = request.form.get('native_language', 'french')
            
            if not wizard_data['name']:
                flash('Le nom du programme est requis.', 'error')
                return render_template('programs/wizard/step1.html', 
                                     step=1, data=wizard_data, languages=LANGUAGES)
            
            # Learner profile
            wizard_data['program_profile'] = {
                'current_level': request.form.get('current_level', 'A2'),
                'years_learning': int(request.form.get('years_learning', 0)),
                'goals': request.form.getlist('goals') or ['conversation'],
                'focus_areas': request.form.getlist('focus_areas') or [],
                'correction_strictness': request.form.get('correction_strictness', 'moderate')
            }
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=2))
            
        elif step == 2:
            # =============================================
            # STEP 2: Theme preferences
            # =============================================
            wizard_data['theme_preferences'] = {
                'interests': request.form.getlist('interests') or [],
                'custom_interests': request.form.get('custom_interests', '').strip(),
                'avoid_topics': request.form.get('avoid_topics', '').strip(),
                'theme_style': request.form.get('theme_style', 'quotidien_realiste'),
                'geographic_context': request.form.get('geographic_context', '').strip()
            }
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=3))
            
        elif step == 3:
            # =============================================
            # STEP 3: Exercises + FSI + Duration
            # =============================================
            order = request.form.getlist('exercise_order')
            enabled = {}
            for ex_id, _, _ in EXERCISES:
                enabled[ex_id] = request.form.get(f'enabled_{ex_id}') == 'on'
            
            duration = request.form.get('duration_target', type=int) or 30
            
            wizard_data['exercise_config'] = {
                'order': order if order else [ex[0] for ex in EXERCISES],
                'enabled': enabled,
                'duration_target': duration
            }
            
            wizard_data['fsi_mutations'] = request.form.getlist('fsi_mutations') or DEFAULT_FSI_MUTATIONS[:5]
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=4))
            
        elif step == 4:
            # =============================================
            # STEP 4: Shadowing resources
            # =============================================
            shadowing_json = request.form.get('shadowing_resources', '[]')
            try:
                wizard_data['shadowing_resources'] = json.loads(shadowing_json)
            except:
                wizard_data['shadowing_resources'] = []
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=5))
            
        elif step == 5:
            # =============================================
            # STEP 5: Finalize & Create/Update
            # =============================================
            session['program_wizard'] = wizard_data
            
            editing_id = wizard_data.get('editing_program_id')
            
            # Merge theme_preferences into program_profile
            program_profile = wizard_data.get('program_profile', {})
            program_profile['theme_preferences'] = wizard_data.get('theme_preferences', {})
            
            llm_prompts = {
                'user_profile': {
                    'interests': wizard_data.get('theme_preferences', {}).get('custom_interests', ''),
                    'known_topics': wizard_data.get('theme_preferences', {}).get('avoid_topics', '')
                }
            }
            
            if editing_id:
                # ====== UPDATE existing program ======
                program = TrainingProgram.query.get_or_404(editing_id)
                if program.user_id != g.user.id:
                    flash('Acces non autorise.', 'error')
                    return redirect(url_for('programs.list_programs'))
                
                program.name = wizard_data['name']
                program.description = wizard_data.get('description')
                program.target_language = wizard_data['target_language']
                program.native_language = wizard_data['native_language']
                program.exercise_config = wizard_data.get('exercise_config', program.exercise_config)
                program.program_profile = program_profile
                program.fsi_mutations = wizard_data.get('fsi_mutations', DEFAULT_FSI_MUTATIONS[:5])
                program.shadowing_resources = wizard_data.get('shadowing_resources', [])
                program.llm_prompts = llm_prompts
                
                # Sync shadowing videos
                from app.models import ShadowingVideo
                for resource in wizard_data.get('shadowing_resources', []):
                    url = resource.get('url', '').strip()
                    if not url:
                        continue
                    existing = ShadowingVideo.query.filter_by(program_id=program.id, url=url).first()
                    if not existing:
                        db.session.add(ShadowingVideo(
                            program_id=program.id, url=url,
                            title=resource.get('title', ''),
                            duration_seconds=resource.get('duration', 0) or None
                        ))
                
                flag_modified(program, 'exercise_config')
                flag_modified(program, 'program_profile')
                db.session.commit()
                
                session.pop('program_wizard', None)
                flash(f'Programme "{program.name}" mis a jour !', 'success')
                return redirect(url_for('programs.view_program', program_id=program.id))
            
            else:
                # ====== CREATE new program ======
                target_lang = wizard_data['target_language'].title()
                program_name = wizard_data['name']
                dedicated_deck = Deck(
                    user_id=g.user.id,
                    name=f"{target_lang} - {program_name}",
                    description=f"Deck du programme \"{program_name}\"",
                    is_program_deck=True
                )
                db.session.add(dedicated_deck)
                db.session.flush()
                
                program = TrainingProgram(
                    user_id=g.user.id,
                    deck_id=dedicated_deck.id,
                    name=wizard_data['name'],
                    description=wizard_data.get('description'),
                    target_language=wizard_data['target_language'],
                    native_language=wizard_data['native_language'],
                    exercise_config=wizard_data.get('exercise_config'),
                    program_profile=program_profile,
                    lego_templates=[],
                    fsi_mutations=wizard_data.get('fsi_mutations', DEFAULT_FSI_MUTATIONS[:5]),
                    shadowing_resources=wizard_data.get('shadowing_resources', []),
                    daily_themes=[],
                    llm_prompts=llm_prompts,
                    daily_cheat_tokens=3
                )
                
                db.session.add(program)
                db.session.commit()
                
                # Auto-generate initial content
                generation_report = []
                
                try:
                    from app.theme_generator import generate_new_weekly_theme
                    weekly_theme = generate_new_weekly_theme(program, g.user)
                    generation_report.append(f"Theme \"{weekly_theme.main_theme}\" genere")
                except Exception as e:
                    print(f"[Wizard] Theme generation failed: {e}")
                    generation_report.append("Theme: echec")
                
                try:
                    generate_initial_batch(program)
                    generation_report.append("15 mots generes")
                except Exception as e:
                    print(f"[Wizard] Vocab generation failed: {e}")
                    generation_report.append("Vocabulaire: echec")
                
                try:
                    from app.gym_engine import create_default_structures
                    structures = create_default_structures(
                        program.id, program.target_language, program.native_language
                    )
                    generation_report.append(f"{len(structures)} structures Lego")
                except Exception as e:
                    print(f"[Wizard] Lego generation failed: {e}")
                    generation_report.append("Structures: echec")
                
                session.pop('program_wizard', None)
                
                report = ' | '.join(generation_report)
                flash(f'Programme "{program.name}" cree ! {report}', 'success')
                
                return redirect(url_for('programs.view_program', program_id=program.id))
    
    # =============================================
    # GET request - render the appropriate step
    # =============================================
    if step == 1:
        return render_template('programs/wizard/step1.html', 
                             step=1, data=wizard_data, languages=LANGUAGES)
    elif step == 2:
        return render_template('programs/wizard/step2_themes.html',
                             step=2, data=wizard_data)
    elif step == 3:
        return render_template('programs/wizard/step3_exercises.html',
                             step=3, data=wizard_data, exercises=EXERCISES, 
                             fsi_mutations=DEFAULT_FSI_MUTATIONS)
    elif step == 4:
        return render_template('programs/wizard/step4_resources.html',
                             step=4, data=wizard_data)
    elif step == 5:
        return render_template('programs/wizard/step5_finalize.html',
                             step=5, data=wizard_data)

def generate_initial_batch(program):
    """Generate initial vocabulary batch (45 words) for the new program.
    
    If a WeeklyTheme exists for this program, use its first 3 days'
    vocab_domains to generate themed vocabulary.
    """
    from app.llm_service import call_llm
    from app.models import Card, WeeklyTheme
    import json
    
    # Initial batch: just enough for first 2 days (~15 new/day)
    # This will grow organically with daily generation
    count = 15
    
    # Try to get the weekly theme for context
    weekly_theme = WeeklyTheme.query.filter_by(
        program_id=program.id
    ).order_by(WeeklyTheme.generated_at.desc()).first()
    
    # Build theme context
    theme = "Les bases / Salutations / Presentation"
    vocab_hint = ""
    if weekly_theme and weekly_theme.daily_breakdown:
        theme = weekly_theme.main_theme
        # Collect vocab domains from first 3 days
        domains = []
        for day in weekly_theme.daily_breakdown[:3]:
            domains.extend(day.get('vocab_domains', []))
        if domains:
            vocab_hint = f"\nVocabulary domains to cover: {', '.join(domains)}"
    
    # Context from program profile
    pp = program.program_profile or {}
    user_level = pp.get('current_level', 'A2')
    theme_prefs = pp.get('theme_preferences', {})
    avoid = theme_prefs.get('avoid_topics', '')
    
    avoid_hint = f"\nTopics to AVOID: {avoid}" if avoid else ""
    
    prompt = f"""Generate {count} vocabulary words for learning {program.target_language} (Native: {program.native_language}).
Theme: {theme}{vocab_hint}{avoid_hint}
Level: {user_level}

The words should be practical, everyday vocabulary that fits the theme.
Mix nouns, verbs, adjectives, and useful expressions.

Return ONLY a JSON array:
[
  {{"front": "word in {program.target_language}", "back": "translation in {program.native_language}"}},
  ...
]

Return ONLY the JSON array, no other text."""

    response = call_llm(
        "You are a language teacher. Generate vocabulary lists in JSON format only.",
        prompt,
        temperature=0.7
    )
    
    if not response:
        return
        
    try:
        text = response.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
            text = text.rsplit('```', 1)[0]
        
        words = json.loads(text)
        
        # Add to deck
        for w in words:
            card = Card(
                deck_id=program.deck_id,
                front=w['front'],
                back=w['back'],
                slot_type='vocabulary'
            )
            db.session.add(card)
        
        db.session.commit()
        print(f"[Wizard] Generated {len(words)} vocabulary cards for program {program.id}")
    except Exception as e:
        print(f"Initial generation failed: {e}")


@bp.route('/<int:program_id>')
def view_program(program_id):
    """View a training program."""
    from app.models import WeeklyTheme, ProgramSession, DebtWord, LegoStructure
    
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        flash('Acces non autorise.', 'error')
        return redirect(url_for('programs.list_programs'))
    
    # Get current weekly theme
    weekly_theme = WeeklyTheme.query.filter_by(
        program_id=program.id
    ).order_by(WeeklyTheme.generated_at.desc()).first()
    
    # Get Lego structures
    lego_structures = LegoStructure.query.filter_by(
        program_id=program.id, is_active=True
    ).order_by(LegoStructure.stability.asc()).all()
    
    # Stats
    session_count = ProgramSession.query.filter_by(
        program_id=program.id, user_id=g.user.id
    ).count()
    
    debt_count = DebtWord.query.filter_by(
        user_id=g.user.id, program_id=program.id, processed=False
    ).count()
    
    return render_template('programs/view.html', 
                         program=program, 
                         exercises=EXERCISES,
                         weekly_theme=weekly_theme,
                         lego_structures=lego_structures,
                         lego_count=len(lego_structures),
                         session_count=session_count,
                         debt_count=debt_count)


@bp.route('/<int:program_id>/edit', methods=['GET'])
def edit_program(program_id):
    """Edit a training program - redirects to wizard with pre-filled data."""
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        flash('Acces non autorise.', 'error')
        return redirect(url_for('programs.list_programs'))
    
    pp = program.program_profile or {}
    ec = program.exercise_config or {}
    tp = pp.get('theme_preferences', {})
    
    # Pre-fill wizard data from existing program
    session['program_wizard'] = {
        'editing_program_id': program.id,
        'name': program.name or '',
        'description': program.description or '',
        'target_language': program.target_language or 'italian',
        'native_language': program.native_language or 'french',
        'program_profile': {
            'current_level': pp.get('current_level', 'A2'),
            'years_learning': pp.get('years_learning', 0),
            'goals': pp.get('goals', ['conversation']),
            'focus_areas': pp.get('focus_areas', []),
            'correction_strictness': pp.get('correction_strictness', 'moderate')
        },
        'theme_preferences': {
            'interests': tp.get('interests', []),
            'custom_interests': tp.get('custom_interests', ''),
            'avoid_topics': tp.get('avoid_topics', ''),
            'theme_style': tp.get('theme_style', 'quotidien_realiste'),
            'geographic_context': tp.get('geographic_context', '')
        },
        'exercise_config': ec,
        'fsi_mutations': program.fsi_mutations or DEFAULT_FSI_MUTATIONS[:5],
        'shadowing_resources': program.shadowing_resources or []
    }
    
    return redirect(url_for('programs.wizard_step', step=1))


@bp.route('/<int:program_id>/delete', methods=['POST'])
def delete_program(program_id):
    """Delete a training program."""
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('programs.list_programs'))
    
    name = program.name
    db.session.delete(program)
    db.session.commit()
    
    flash(f'Programme "{name}" supprimé.', 'success')
    return redirect(url_for('programs.list_programs'))


@bp.route('/<int:program_id>/toggle', methods=['POST'])
def toggle_program(program_id):
    """Toggle program active status."""
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    program.is_active = not program.is_active
    db.session.commit()
    
    return jsonify({'is_active': program.is_active})


# API endpoints for LLM generation
@bp.route('/api/generate-templates', methods=['POST'])
def api_generate_templates():
    """Generate Lego templates using LLM."""
    target_language = request.json.get('target_language', 'italian')
    count = request.json.get('count', 5)
    
    templates = generate_lego_templates(target_language, count=count)
    
    if templates:
        return jsonify({'success': True, 'templates': templates})
    else:
        return jsonify({'success': False, 'error': 'LLM generation failed'}), 500


@bp.route('/api/generate-themes', methods=['POST'])
def api_generate_themes():
    """Generate daily themes using LLM."""
    target_language = request.json.get('target_language', 'italian')
    count = request.json.get('count', 7)
    
    themes = generate_daily_themes(target_language, count=count)
    
    if themes:
        return jsonify({'success': True, 'themes': themes})
    else:
        return jsonify({'success': False, 'error': 'LLM generation failed'}), 500

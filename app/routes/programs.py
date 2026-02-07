"""
Routes for Training Program Builder.
Allows users to create and configure custom training programs.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g
from app.models import TrainingProgram, Deck, User
from app import db
from app.llm_service import generate_lego_templates, generate_daily_themes
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

# Default FSI mutations
DEFAULT_FSI_MUTATIONS = ['NEGATION', 'FUTUR', 'PASSE', 'PLURIEL', 'QUESTION', 'CONDITIONNEL']


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
    """Handle each step of the creation wizard."""
    # Initialize wizard data if needed
    if 'program_wizard' not in session:
        session['program_wizard'] = {}
    
    wizard_data = session['program_wizard']
    
    # Get user's decks for step 1
    decks = Deck.query.filter_by(user_id=g.user.id).all()
    
    if request.method == 'POST':
        if step == 1:
            # Basic info
            wizard_data['name'] = request.form.get('name', '').strip()
            wizard_data['description'] = request.form.get('description', '').strip()
            wizard_data['target_language'] = request.form.get('target_language', 'italian')
            wizard_data['native_language'] = request.form.get('native_language', 'french')
            wizard_data['deck_id'] = request.form.get('deck_id', type=int)
            
            if not wizard_data['name']:
                flash('Le nom du programme est requis.', 'error')
                return render_template('programs/wizard/step1.html', 
                                     step=1, data=wizard_data, decks=decks, languages=LANGUAGES)
            
            # Deck selection is no longer required (auto-created)
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=2))
            
        elif step == 2:
            # Exercise configuration
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
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=3))
            
        elif step == 3:
            # Templates & Resources
            # Lego templates
            lego_json = request.form.get('lego_templates', '[]')
            try:
                wizard_data['lego_templates'] = json.loads(lego_json)
            except:
                wizard_data['lego_templates'] = []
            
            # FSI mutations
            wizard_data['fsi_mutations'] = request.form.getlist('fsi_mutations')
            
            # Shadowing resources
            shadowing_json = request.form.get('shadowing_resources', '[]')
            try:
                wizard_data['shadowing_resources'] = json.loads(shadowing_json)
            except:
                wizard_data['shadowing_resources'] = []
            
            # Daily themes
            themes_raw = request.form.get('daily_themes', '')
            wizard_data['daily_themes'] = [t.strip() for t in themes_raw.split('\n') if t.strip()]
            
            # User profile data
            wizard_data['user_interests'] = request.form.get('user_interests', '').strip()
            wizard_data['known_topics'] = request.form.get('known_topics', '').strip()
            
            session['program_wizard'] = wizard_data
            return redirect(url_for('programs.wizard_step', step=4))
            
        elif step == 4:
            # LLM prompts & finalize
            wizard_data['llm_prompts'] = {
                'text_generation': request.form.get('prompt_text_generation', ''),
                'quest_generation': request.form.get('prompt_quest_generation', ''),
                'correction': request.form.get('prompt_correction', ''),
                'lego_generation': request.form.get('prompt_lego_generation', ''),
                'user_profile': {
                    'interests': wizard_data.get('user_interests', ''),
                    'known_topics': wizard_data.get('known_topics', '')
                }
            }
            
            wizard_data['daily_cheat_tokens'] = request.form.get('daily_cheat_tokens', type=int) or 3
            
            session['program_wizard'] = wizard_data
            
            # Auto-create a dedicated deck for this program
            target_lang = wizard_data['target_language'].title()
            program_name = wizard_data['name']
            dedicated_deck = Deck(
                user_id=g.user.id,
                name=f"📚 {target_lang} - {program_name}",
                description=f"Deck auto-créé pour le programme \"{program_name}\"",
                is_program_deck=True
            )
            db.session.add(dedicated_deck)
            db.session.flush()  # Get the ID
            
            # Create the program with the dedicated deck
            program = TrainingProgram(
                user_id=g.user.id,
                deck_id=dedicated_deck.id,
                name=wizard_data['name'],
                description=wizard_data.get('description'),
                target_language=wizard_data['target_language'],
                native_language=wizard_data['native_language'],
                exercise_config=wizard_data.get('exercise_config'),
                lego_templates=wizard_data.get('lego_templates', []),
                fsi_mutations=wizard_data.get('fsi_mutations', DEFAULT_FSI_MUTATIONS),
                shadowing_resources=wizard_data.get('shadowing_resources', []),
                daily_themes=wizard_data.get('daily_themes', []),
                llm_prompts=wizard_data.get('llm_prompts'),
                daily_cheat_tokens=wizard_data.get('daily_cheat_tokens', 3)
            )
            
            db.session.add(program)
            db.session.commit()
            
            # Pre-generate content (3 days worth) to avoid waiting in session
            try:
                generate_initial_batch(program)
                flash(f'Programme "{program.name}" créé avec succès ! 45 mots générés.', 'success')
            except Exception as e:
                print(f"Error generating initial batch: {e}")
                flash(f'Programme "{program.name}" créé, mais la génération a échoué.', 'warning')
            
            # Clear wizard data
            session.pop('program_wizard', None)
            
            return redirect(url_for('programs.view_program', program_id=program.id))
    
    # GET request - render the appropriate step
    if step == 1:
        return render_template('programs/wizard/step1.html', 
                             step=1, data=wizard_data, decks=decks, languages=LANGUAGES)
    elif step == 2:
        return render_template('programs/wizard/step2.html',
                             step=2, data=wizard_data, exercises=EXERCISES)
    elif step == 3:
        return render_template('programs/wizard/step3.html',
                             step=3, data=wizard_data, fsi_mutations=DEFAULT_FSI_MUTATIONS)
    elif step == 4:
        # Default prompts
        default_prompts = {
            'text_generation': "Génère un texte court (50-80 mots) en {target_language} sur le thème: {theme}. Niveau A2, phrases simples.",
            'quest_generation': "Crée une mission courte en {native_language} demandant à l'utilisateur de raconter une anecdote utilisant ces mots: {words}",
            'correction': "Tu es un correcteur strict. Corrige ce texte en {target_language}. Affiche les erreurs et explique-les.",
            'lego_generation': "Génère 5 templates de structures de phrases pour apprendre {target_language} au niveau A2."
        }
        return render_template('programs/wizard/step4.html',
                             step=4, data=wizard_data, default_prompts=default_prompts)

def generate_initial_batch(program):
    """Generate initial vocabulary batch (45 words) for the new program."""
    from app.llm_service import call_llm
    from app.models import Card
    import json
    
    theme = "Les bases / Salutations / Présentation"
    count = 45
    
    # Context from user profile
    llm_prompts = program.llm_prompts or {}
    user_profile = llm_prompts.get('user_profile', {})
    interests = user_profile.get('interests', '')
    known = user_profile.get('known_topics', '')
    
    context = ""
    if interests:
        context += f"\nUser Interests (incorporate if possible): {interests}"
    if known:
        context += f"\nAvoid these topics (already known): {known}"
    
    prompt = f"""Generate {count} vocabulary words for learning {program.target_language} (Native: {program.native_language}).
Theme: {theme}{context}
Level: A1-A2 (Beginner)

Return ONLY a JSON array with this format:
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
    except Exception as e:
        print(f"Initial generation failed: {e}")
    
    return redirect(url_for('programs.wizard_step', step=1))


@bp.route('/<int:program_id>')
def view_program(program_id):
    """View a training program."""
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('programs.list_programs'))
    
    return render_template('programs/view.html', program=program, exercises=EXERCISES)


@bp.route('/<int:program_id>/edit', methods=['GET', 'POST'])
def edit_program(program_id):
    """Edit a training program."""
    program = TrainingProgram.query.get_or_404(program_id)
    if program.user_id != g.user.id:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('programs.list_programs'))
    
    decks = Deck.query.filter_by(user_id=g.user.id).all()
    
    if request.method == 'POST':
        program.name = request.form.get('name', '').strip()
        program.description = request.form.get('description', '').strip()
        program.target_language = request.form.get('target_language', 'italian')
        program.native_language = request.form.get('native_language', 'french')
        program.deck_id = request.form.get('deck_id', type=int)
        
        # Exercise config
        order = request.form.getlist('exercise_order')
        enabled = {}
        for ex_id, _, _ in EXERCISES:
            enabled[ex_id] = request.form.get(f'enabled_{ex_id}') == 'on'
        
        program.exercise_config = {
            'order': order if order else program.exercise_config.get('order', []),
            'enabled': enabled,
            'duration_target': request.form.get('duration_target', type=int) or 30
        }
        
        # Lego templates
        lego_json = request.form.get('lego_templates', '[]')
        try:
            program.lego_templates = json.loads(lego_json)
        except:
            pass
        
        # FSI mutations
        program.fsi_mutations = request.form.getlist('fsi_mutations')
        
        # Shadowing - Save to both legacy JSON and new ShadowingVideo model
        from app.models import ShadowingVideo
        shadowing_json = request.form.get('shadowing_resources', '[]')
        try:
            shadowing_data = json.loads(shadowing_json)
            program.shadowing_resources = shadowing_data
            
            # Sync to ShadowingVideo model
            # Deactivate old videos not in the new list
            existing_urls = {v.url for v in ShadowingVideo.query.filter_by(program_id=program.id).all()}
            new_urls = {r.get('url', '') for r in shadowing_data if r.get('url')}
            
            # Deactivate removed videos
            for video in ShadowingVideo.query.filter_by(program_id=program.id).all():
                if video.url not in new_urls:
                    video.is_active = False
            
            # Add/update videos
            for resource in shadowing_data:
                url = resource.get('url', '').strip()
                if not url:
                    continue
                    
                # Check if already exists
                existing = ShadowingVideo.query.filter_by(
                    program_id=program.id,
                    url=url
                ).first()
                
                if existing:
                    existing.title = resource.get('title', '')
                    existing.is_active = True
                else:
                    video = ShadowingVideo(
                        program_id=program.id,
                        url=url,
                        title=resource.get('title', ''),
                        duration_seconds=resource.get('duration', 0) or None
                    )
                    db.session.add(video)
        except Exception as e:
            print(f"Error syncing shadowing videos: {e}")
        
        # Daily themes
        themes_raw = request.form.get('daily_themes', '')
        program.daily_themes = [t.strip() for t in themes_raw.split('\n') if t.strip()]
        
        # LLM prompts
        program.llm_prompts = {
            'text_generation': request.form.get('prompt_text_generation', ''),
            'quest_generation': request.form.get('prompt_quest_generation', ''),
            'correction': request.form.get('prompt_correction', ''),
            'lego_generation': request.form.get('prompt_lego_generation', '')
        }
        
        program.daily_cheat_tokens = request.form.get('daily_cheat_tokens', type=int) or 3
        
        db.session.commit()
        flash('Programme mis à jour !', 'success')
        return redirect(url_for('programs.view_program', program_id=program.id))
    
    return render_template('programs/edit.html', 
                         program=program, 
                         decks=decks, 
                         languages=LANGUAGES,
                         exercises=EXERCISES,
                         fsi_mutations=DEFAULT_FSI_MUTATIONS)


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

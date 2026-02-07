"""
Session blueprint - Handles training session execution from programs.

This is the core engine that orchestrates all 6 learning modules:
1. Flashcards (vocab)
2. Git Input (Target → Native)
3. Gym (Lego + FSI)
4. Shadowing (TTS)
5. Git Output (Native → Target, J+1)
6. Smart Writing (Boss Fight)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g
from app.models import (
    TrainingProgram, ProgramSession, DailyText, 
    Card, Deck, Category, db,
    WeeklyTheme
)
from app import db
from datetime import datetime, date, timedelta
from sqlalchemy.orm.attributes import flag_modified
import json

bp = Blueprint('session', __name__, url_prefix='/session')


# Module order (fixed for now, could be configurable later)
MODULE_ORDER = ['flashcards', 'git_input', 'gym', 'shadowing', 'git_output', 'writing']

MODULE_NAMES = {
    'flashcards': '📚 Vocabulaire',
    'git_input': '📝 Git Input',
    'gym': '🏋️ The Gym',
    'shadowing': '🎧 Shadowing',
    'git_output': '🔄 Git Output',
    'writing': '✍️ Smart Writing'
}


@bp.before_request
def check_login():
    if not g.user:
        return redirect(url_for('auth.login'))


def get_current_session():
    """Get current active session from flask session."""
    session_id = session.get('program_session_id')
    if not session_id:
        return None
    ps = ProgramSession.query.get(session_id)
    if ps and ps.user_id == g.user.id:
        return ps
    return None


def select_cards_for_session(program, time_minutes):
    """
    Select cards for today's session based on available time.
    
    Priority order:
    1. Due cards with grade < C (critical - stability < 14 days)
    2. Due cards with grade < B (important - stability < 30 days)
    3. Due cards with grade < B+ (stability < 60 days)
    4. All due cards
    5. New cards (stability = 0)
    
    Returns: list of card dicts with {card_id, front, back, grade, priority}
    """
    from app.fsrs import stability_to_grade_letter
    
    deck = program.deck
    if not deck:
        return []
    
    now = datetime.utcnow()
    avg_time_per_card = 0.5  # 30 seconds average per card
    max_cards = int(time_minutes / avg_time_per_card)
    
    # Get all cards from the deck
    cards = Card.query.filter_by(deck_id=deck.id).all()
    
    # Categorize cards by priority
    critical = []    # < C (stability < 14)
    important = []   # < B (stability < 30)
    learning = []    # < B+ (stability < 60)
    review = []      # Due but B+ or better
    new_cards = []   # Never seen
    
    for card in cards:
        fb_stability = card.fb_stability or 0
        bf_stability = card.bf_stability or 0
        min_stability = min(fb_stability, bf_stability)
        
        # Check if due (any direction)
        fb_due = card.fb_next_review and card.fb_next_review <= now
        bf_due = card.bf_next_review and card.bf_next_review <= now
        is_due = fb_due or bf_due
        
        card_info = {
            'card_id': card.id,
            'front': card.front,
            'back': card.back,
            'grade': stability_to_grade_letter(min_stability),
            'stability': min_stability,
            'is_due': is_due,
            'revealed': False
        }
        
        if min_stability == 0:
            new_cards.append(card_info)
        elif min_stability < 14:  # < C
            critical.append(card_info)
        elif min_stability < 30:  # < B
            important.append(card_info)
        elif min_stability < 60:  # < B+
            learning.append(card_info)
        elif is_due:
            review.append(card_info)
    
    # Sort each category by stability (lowest first)
    for cat in [critical, important, learning, review, new_cards]:
        cat.sort(key=lambda x: x['stability'])
    
    # Build selection following priority
    selected = []
    for category in [critical, important, learning, review, new_cards]:
        for card_info in category:
            if len(selected) >= max_cards:
                break
            selected.append(card_info)
        if len(selected) >= max_cards:
            break
            
    # BI-DIRECTIONAL LOGIC for Session Review
    # We want to review cards in BOTH directions
    import random
    
    bidirectional_selection = []
    for c in selected:
        # Direction 1: Original (Target -> Native usually, or whatever is stored)
        bidirectional_selection.append(c)
        
        # Direction 2: Reverse
        rev = c.copy()
        rev['front'] = c['back']
        rev['back'] = c['front']
        rev['direction'] = 'reverse'
        # We might want to track separate grading for reverse in the future, 
        # but for now we test both.
        bidirectional_selection.append(rev)
        
    random.shuffle(bidirectional_selection)
    
    return bidirectional_selection


def get_word_bank(ps):
    """
    Get the word bank for current session.
    
    Includes:
    - Cards selected for today's session (from daily_words)
    - Debt words (revealed/SOS words)
    - Non-learned cards (< B+ grade)
    
    Returns: list of {front, back, card_id, revealed, grade, source}
    """
    word_bank = []
    seen_fronts = set()
    
    # Add daily_words first (selected for today)
    for word in (ps.daily_words or []):
        front = word.get('front', '')
        if front and front not in seen_fronts:
            word_bank.append({
                'front': front,
                'back': word.get('back', ''),
                'card_id': word.get('card_id'),
                'revealed': word.get('revealed', False),
                'grade': word.get('grade', 'E'),
                'source': 'daily'
            })
            seen_fronts.add(front)
    
    # Add debt words (SOS + revealed)
    for debt in (ps.debt_words or []):
        front = debt.get('front', '')
        if front and front not in seen_fronts:
            word_bank.append({
                'front': front,
                'back': debt.get('back', ''),
                'card_id': debt.get('card_id'),
                'revealed': True,  # Debt words are always revealed
                'grade': 'debt',
                'source': debt.get('source', 'sos')
            })
            seen_fronts.add(front)
    
    return word_bank


# ============================================================
# SESSION LIFECYCLE
# ============================================================

@bp.route('/start/<int:program_id>')
def start_session(program_id):
    """Start a new training session from a program."""
    from app.models import DebtWord
    
    program = TrainingProgram.query.get_or_404(program_id)
    
    if program.user_id != g.user.id:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('main.index'))
    
    # Check if there's already an active session for today
    today = date.today()
    existing = ProgramSession.query.filter_by(
        program_id=program_id,
        user_id=g.user.id,
        session_date=today
    ).filter(ProgramSession.completed_at.is_(None)).first()
    
    if existing:
        # Resume existing session
        session['program_session_id'] = existing.id
        return redirect(url_for('session.current_module'))
    
    # =========================================================
    # 1. BUILD SESSION CONTEXT (theme + vocab_domains + key_situations)
    # =========================================================
    theme_display = None
    weekly_theme = None
    session_context = {}
    
    try:
        from app.theme_generator import get_or_generate_weekly_theme, get_current_day_focus, build_session_context
        weekly_theme = get_or_generate_weekly_theme(program, g.user)
        day_focus_data = get_current_day_focus(program, g.user)
        theme_display = f"{weekly_theme.main_theme}: {day_focus_data.get('focus', '')}"
        
        # Build complete context for LLM prompts
        # (will be updated with daily_words after card selection)
        session_context = {
            'theme_name': weekly_theme.main_theme,
            'theme_description': weekly_theme.theme_description,
            'day_focus': day_focus_data.get('focus', 'Pratique générale'),
            'vocab_domains': day_focus_data.get('vocab_domains', ['general']),
            'key_situations': day_focus_data.get('key_situations', []),
            'past_themes': [{'theme': t.main_theme, 'description': t.theme_description} 
                           for t in weekly_theme.program.weekly_themes[:4] if t.id != weekly_theme.id] if weekly_theme else []
        }
    except Exception as e:
        print(f"[Session] Theme generation skipped: {e}")
        # Fallback to program's daily_themes if available
        theme_display = program.get_current_theme()
        session_context = {
            'theme_name': theme_display or 'Session d\'entraînement',
            'theme_description': '',
            'day_focus': 'Pratique générale',
            'vocab_domains': ['general'],
            'key_situations': [],
            'past_themes': []
        }
    
    # =========================================================
    # 2. PROCESS DEBT WORDS FROM PREVIOUS DAYS
    # =========================================================
    unprocessed_debts = DebtWord.get_unprocessed_debts(g.user.id, program_id)
    debt_words_to_add = []
    
    for debt in unprocessed_debts:
        debt_words_to_add.append({
            'front': debt.word_front,
            'back': debt.word_back,
            'source': f'debt_{debt.source}',
            'card_id': None,
            'is_debt': True
        })
        debt.mark_processed()
    
    # =========================================================
    # 3. SELECT CARDS (using existing system)
    # =========================================================
    exercise_config = program.exercise_config or {}
    time_budget = exercise_config.get('duration_target', 15)
    selected_cards = select_cards_for_session(program, time_budget)
    
    # Add debt words to the beginning (priority review)
    all_daily_words = debt_words_to_add + selected_cards
    
    # =========================================================
    # 4. UPDATE CONTEXT WITH DAILY WORDS
    # =========================================================
    # Add vocabulary to context for LLM prompts
    session_context['daily_vocabulary'] = [
        f"{w.get('front', '')} = {w.get('back', '')}" 
        for w in all_daily_words[:20] if isinstance(w, dict)
    ]
    session_context['vocab_count'] = len(all_daily_words)
    
    # Add timing info
    exercise_config = program.exercise_config or {}
    session_context['session_duration'] = exercise_config.get('duration_target', 30)
    
    # Add language info
    program_profile = program.program_profile or {}
    user_profile = g.user.learner_profile or {}
    session_context['target_language'] = program.target_language or 'langue cible'
    session_context['native_language'] = program.native_language or user_profile.get('native_language', 'français')
    session_context['user_level'] = program_profile.get('current_level', 'A2')
    session_context['user_goals'] = program_profile.get('goals', [])
    
    # =========================================================
    # 5. CREATE SESSION
    # =========================================================
    ps = ProgramSession(
        program_id=program_id,
        user_id=g.user.id,
        cheat_tokens_remaining=program.daily_cheat_tokens or 3,
        daily_words=all_daily_words,
        debt_words=[],
        results={
            'flashcards': {'correct': 0, 'total': 0, 'cards_selected': len(all_daily_words), 'debt_reviewed': len(debt_words_to_add)},
            'git_input': {'completed': False, 'score': None},
            'gym': {'discovery': 0, 'construction': 0, 'fsi': 0, 'translation': 0},
            'shadowing': {'done': 0, 'total': 0},
            'git_output': {'completed': False, 'diff_errors': 0},
            'writing': {'completed': False, 'tokens_used': 0},
            'session_context': session_context  # Store context for all modules
        }
    )
    
    # Determine starting module based on program config
    enabled = program.get_enabled_exercises()
    if enabled:
        ps.current_module = enabled[0]
        ps.module_index = 0
    
    # Set theme for today (from WeeklyTheme or fallback)
    if theme_display:
        ps.daily_words_theme = theme_display
    else:
        program.advance_theme()
        ps.daily_words_theme = program.get_current_theme()
    
    # Update weekly theme progress if exists
    if weekly_theme:
        day_index = datetime.now().weekday()
        weekly_theme.days_completed = day_index + 1
        if day_index == 6:
            weekly_theme.completed = True
    
    db.session.add(ps)
    db.session.commit()
    
    session['program_session_id'] = ps.id
    
    if debt_words_to_add:
        print(f"[Session] Processed {len(debt_words_to_add)} debt words for user {g.user.id}")
    
    return redirect(url_for('session.current_module'))


@bp.route('/module')
def current_module():
    """Show the current module in the session."""
    ps = get_current_session()
    if not ps:
        flash('Aucune session active.', 'info')
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    # Route to correct module template
    module = ps.current_module
    
    if module == 'flashcards':
        return redirect(url_for('session.module_flashcards'))
    elif module == 'git_input':
        return redirect(url_for('session.module_git_input'))
    elif module == 'gym':
        return redirect(url_for('session.module_gym'))
    elif module == 'shadowing':
        return redirect(url_for('session.module_shadowing'))
    elif module == 'git_output':
        return redirect(url_for('session.module_git_output'))
    elif module == 'writing':
        return redirect(url_for('session.module_writing'))
    else:
        return redirect(url_for('session.complete'))


@bp.route('/next')
def next_module():
    """Move to the next module in the session."""
    ps = get_current_session()
    if not ps:
        flash('Aucune session active.', 'info')
        return redirect(url_for('main.index'))
    
    program = ps.program
    enabled = program.get_enabled_exercises()
    
    # Find next enabled module
    current_idx = ps.module_index
    next_idx = current_idx + 1
    
    if next_idx >= len(enabled):
        # Session complete
        ps.completed_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('session.complete'))
    
    ps.module_index = next_idx
    ps.current_module = enabled[next_idx]
    db.session.commit()
    
    return redirect(url_for('session.current_module'))


@bp.route('/complete')
def complete():
    """Show session completion summary."""
    ps = get_current_session()
    if not ps:
        flash('Aucune session active.', 'info')
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    # Mark as complete if not already
    if not ps.completed_at:
        ps.completed_at = datetime.utcnow()
        db.session.commit()
    
    # Process debt words - add as cards with special category
    debt_count = len(ps.debt_words or [])
    
    # Clear session
    session.pop('program_session_id', None)
    
    return render_template('session/complete.html',
                          session=ps,
                          program=program,
                          debt_count=debt_count)


@bp.route('/stop', methods=['POST'])
def stop_session():
    """Stop the current session early."""
    ps = get_current_session()
    if ps:
        # Don't delete, just mark incomplete
        session.pop('program_session_id', None)
        flash('Session interrompue. Vous pourrez la reprendre plus tard.', 'info')
    return redirect(url_for('programs.view_program', program_id=ps.program_id if ps else 1))


# ============================================================
# MODULE 1: FLASHCARDS
# ============================================================

@bp.route('/flashcards')
def module_flashcards():
    """Flashcards module - vocabulary learning."""
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    deck = program.deck
    
    # Generate daily words if not done
    if not ps.daily_words or len(ps.daily_words) == 0:
        # Will be populated via AJAX call
        pass
    
    return render_template('session/flashcards.html',
                          session=ps,
                          program=program,
                          deck=deck,
                          theme=ps.daily_words_theme)


@bp.route('/sidebar-data')
@bp.route('/flashcards/sidebar-data')
def get_sidebar_data():
    """Get data for the word bank sidebar."""
    ps = get_current_session()
    if not ps:
        return jsonify({'success': False})
    
    word_bank = get_word_bank(ps)
    return jsonify({
        'success': True,
        'word_bank': word_bank,
        'debt_count': len(ps.debt_words or [])
    })

# ... (rest of file)




@bp.route('/flashcards/generate-words', methods=['POST'])
def generate_daily_words():
    """Generate daily vocabulary words via LLM."""
    from app.llm_service import call_llm
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No active session'}), 400
    
    program = ps.program
    theme = ps.daily_words_theme or program.get_current_theme() or 'daily life'
    count = request.json.get('count', 15)
    
    # Build prompt (language-agnostic)
    prompt = f"""Generate {count} vocabulary words for learning {program.target_language}.
Theme: {theme}
Level: A2-B1

Return ONLY a JSON array with this format:
[
  {{"front": "word in {program.target_language}", "back": "translation in {program.native_language}"}},
  ...
]

Examples for reference:
- front should be the word in {program.target_language}
- back should be the translation in {program.native_language}

Return ONLY the JSON array, no other text."""

    response = call_llm(
        "You are a language teacher. Generate vocabulary lists in JSON format only.",
        prompt,
        temperature=0.7
    )
    
    if not response:
        return jsonify({'error': 'LLM unavailable'}), 500
    
    # Parse response
    try:
        # Clean up response
        text = response.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
            text = text.rsplit('```', 1)[0]
        
        words = json.loads(text)
        
        # Validate format
        if not isinstance(words, list):
            raise ValueError("Not a list")
            
        # BI-DIRECTIONAL LOGIC:
        # User wants to check "in the other sense too".
        # We duplicate the list with swapped front/back.
        import random
        
        bidirectional_words = []
        for w in words:
            # Original (Target -> Native)
            bidirectional_words.append(w)
            
            # Reverse (Native -> Target)
            # We create a copy to avoid mutation issues
            reverse_w = w.copy()
            reverse_w['front'] = w['back']
            reverse_w['back'] = w['front']
            # Optional: Add a metadata flag if we want to style them differently later
            reverse_w['direction'] = 'reverse' 
            bidirectional_words.append(reverse_w)
            
        # Shuffle to mix them up
        random.shuffle(bidirectional_words)
        
        ps.daily_words = bidirectional_words
        flag_modified(ps, 'daily_words')
        db.session.commit()
        
        return jsonify({'success': True, 'words': bidirectional_words})
        
    except (json.JSONDecodeError, ValueError) as e:
        return jsonify({'error': f'Parse error: {str(e)}', 'raw': response}), 500


@bp.route('/flashcards/complete', methods=['POST'])
def flashcards_complete():
    """Mark flashcards module as complete."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    data = request.json or {}
    
    # Update results
    results = ps.results or {}
    results['flashcards'] = {
        'correct': data.get('correct', 0),
        'total': data.get('total', 0)
    }
    ps.results = results
    flag_modified(ps, 'results')
    db.session.commit()
    
    return jsonify({'success': True, 'next': url_for('session.next_module')})




# ============================================================
# MODULE 2: GIT INPUT (Target → Native)
# ============================================================

@bp.route('/git-input')
def module_git_input():
    """Git Input module - translate from target to native language."""
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    # Check for existing text for today
    today = date.today()
    daily_text = DailyText.query.filter_by(
        program_id=program.id,
        user_id=g.user.id,
        created_date=today
    ).first()
    
    return render_template('session/git_input.html',
                          session=ps,
                          program=program,
                          daily_text=daily_text,
                          theme=ps.daily_words_theme,
                          daily_vocab=ps.daily_words or [])


@bp.route('/git-input/generate', methods=['POST'])
def generate_git_input_text():
    """Generate text in target language for translation."""
    from app.llm_service import call_llm
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    
    # Get session context for coherent generation
    results = ps.results or {}
    session_context = results.get('session_context', {})
    
    # Extract context data with fallbacks
    theme_name = session_context.get('theme_name', ps.daily_words_theme or 'daily life')
    theme_description = session_context.get('theme_description', '')
    day_focus = session_context.get('day_focus', 'Pratique générale')
    vocab_domains = session_context.get('vocab_domains', ['general'])
    key_situations = session_context.get('key_situations', [])
    daily_vocabulary = session_context.get('daily_vocabulary', [])
    user_level = session_context.get('user_level', 'A2')
    
    # Check if text already exists
    today = date.today()
    existing = DailyText.query.filter_by(
        program_id=program.id,
        user_id=g.user.id,
        created_date=today
    ).first()
    
    if existing:
        return jsonify({'success': True, 'text': existing.original_text})
    
    # Use custom prompt if available
    custom_prompt = program.llm_prompts.get('text_generation') if program.llm_prompts else None
    
    if custom_prompt:
        prompt = custom_prompt.format(
            target_language=program.target_language,
            native_language=program.native_language,
            theme=theme_name,
            theme_description=theme_description,
            day_focus=day_focus,
            vocab_domains=', '.join(vocab_domains),
            key_situations=', '.join(key_situations),
            daily_vocabulary='\n'.join(daily_vocabulary[:10])
        )
    else:
        # Build enriched prompt with session context
        vocab_context = ""
        if daily_vocabulary:
            vocab_list = daily_vocabulary[:10]
            vocab_context = f"\n\nVOCABULAIRE A UTILISER (intègre ces mots naturellement):\n" + "\n".join(vocab_list)
        
        situations_context = ""
        if key_situations:
            situations_context = f"\n\nSITUATIONS CLÉS: {', '.join(key_situations)}"
        
        domains_context = ""
        if vocab_domains and vocab_domains != ['general']:
            domains_context = f"\n\nDOMAINES: {', '.join(vocab_domains)}"
        
        theme_full = theme_name
        if theme_description:
            theme_full += f" - {theme_description}"
        
        prompt = f"""Écris un court texte (50-80 mots) en {program.target_language}.

THÈME: {theme_full}
FOCUS DU JOUR: {day_focus}
NIVEAU: {user_level}{situations_context}{domains_context}{vocab_context}

INSTRUCTIONS:
- Utilise des phrases simples adaptées au niveau {user_level}
- Rends le texte naturel et conversationnel
- Intègre le vocabulaire du jour de manière naturelle si possible
- Reflète les situations clés mentionnées
- Écris UNIQUEMENT le texte en {program.target_language}, rien d'autre."""

    response = call_llm(
        f"Tu es un locuteur natif de {program.target_language} qui écrit des textes simples pour des apprenants.",
        prompt,
        temperature=0.8
    )
    
    if not response:
        return jsonify({'error': 'LLM unavailable'}), 500
    
    # Save to DailyText
    daily_text = DailyText(
        program_id=program.id,
        user_id=g.user.id,
        theme=theme_name,
        original_text=response.strip()
    )
    db.session.add(daily_text)
    db.session.commit()
    
    return jsonify({'success': True, 'text': response.strip(), 'id': daily_text.id})



@bp.route('/chat_helper', methods=['POST'])
def chat_helper():
    """Contextual Chatbot Helper with target language enforcement and random behaviors."""
    from app.llm_service import call_llm
    from app.prompt_templates import get_random_chatbot_behavior, get_system_prompt_for_exercise
    from app.models import DebtWord
    import random
    
    ps = get_current_session()
    program = None
    if ps:
        program = ps.program
    else:
        # Fallback to first program
        from app.models import TrainingProgram
        program = TrainingProgram.query.filter_by(user_id=g.user.id).first()
        
    if not program:
        return jsonify({'message': "Aucun programme actif trouvé.", 'refusal': True})
        
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'message': "...", 'refusal': True})

    target_lang = program.target_language
    native_lang = program.native_language
    
    # Get random chatbot behavior (the "fourbe" element)
    behavior = get_random_chatbot_behavior()
    behavior_addon = behavior.get('prompt_addon', '').format(
        target_language=target_lang,
        native_language=native_lang
    ) if behavior.get('prompt_addon') else ''
    
    # Build the prompt
    prompt = f"""Tu es un assistant d'apprentissage de {target_lang}. L'utilisateur parle {native_lang}.

RÈGLE STRICTE #1 - DÉTECTION DE LANGUE:
- La question doit être MAJORITAIREMENT en {target_lang} pour être acceptée.
- Si l'utilisateur demande "Come si dice 'maison'?" c'est en {target_lang} même si le mot entre guillemets est en {native_lang} - c'est NORMAL car il demande la traduction !
- ACCEPTE les questions où la structure grammaticale est en {target_lang}, même si quelques mots étrangers sont cités.
- Ne refuse QUE si la phrase entière est clairement en {native_lang} ou autre langue.

IMPORTANT: Une fois que tu as décidé qu'une question est valide, tu DOIS répondre. Ne change pas d'avis.

RÈGLE #2: Si tu donnes un mot de vocabulaire en {target_lang}, encadre-le avec [VOCAB]mot[/VOCAB].
Exemple: "La parola 'maison' si dice [VOCAB]casa[/VOCAB] in italiano."

{behavior_addon}

MESSAGE DE L'UTILISATEUR: "{message}"

Réponds en JSON:
{{
    "reply": "Ta réponse utile et encourageante en {target_lang}...",
    "is_target_language": true/false,
    "vocab_word": "le mot en {target_lang} que tu as donné (sans les tags), ou null si aucun"
}}
"""

    response = call_llm(
        f"Tu es un tuteur de {target_lang} strict mais bienveillant. JSON output only.",
        prompt,
        temperature=0.7
    )
    
    try:
        # Parse JSON response
        clean_response = response.strip()
        if '```json' in clean_response:
            clean_response = clean_response.split('```json')[1].split('```')[0]
        elif '```' in clean_response:
            clean_response = clean_response.split('```')[1].split('```')[0]
        
        data = json.loads(clean_response.strip())
        
        reply = data.get('reply', '')
        is_target = data.get('is_target_language', True)
        vocab_word = data.get('vocab_word')
        
        # Add to debt if vocab provided (word user asked for = debt for tomorrow)
        added_to_debt = False
        debt_count = 0
        
        if vocab_word and ps:
            # Create DebtWord for tomorrow
            DebtWord.add_debt(
                user_id=g.user.id,
                program_id=ps.program_id,
                word_front=vocab_word,
                word_back="Aide Chatbot",
                source='chatbot',
                context=ps.current_module
            )
            
            # Also track in session
            ps.add_debt_word(vocab_word, "Aide Chatbot", source="chatbot")
            flag_modified(ps, 'debt_words')
            db.session.commit()
            
            added_to_debt = True
            debt_count = DebtWord.query.filter_by(
                user_id=g.user.id,
                program_id=ps.program_id,
                processed=False
            ).count()
            
            # Add note about debt
            reply += f"\n\n📝 Le mot '{vocab_word}' sera à revoir demain !"

        return jsonify({
            'message': reply,
            'refusal': not is_target,
            'added_to_debt': added_to_debt,
            'debt_count': debt_count,
            'behavior': data.get('behavior_applied', 'normal')
        })

    except Exception as e:
        print(f"Chat helper error: {e}\nRaw response: {response[:500] if response else 'None'}")
        # Fallback: simple refusal in native language
        return jsonify({
            'message': f"Hmm, je n'ai pas bien compris. Peux-tu reformuler en {target_lang} ? 🤔",
            'refusal': True
        })


@bp.route('/git-input/submit', methods=['POST'])
def submit_git_input():
    """Submit translation for Git Input (Iterative Correction)."""
    from app.llm_service import call_llm
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    translation = request.json.get('translation', '').strip()
    text_id = request.json.get('text_id')
    attempt = request.json.get('attempt', 1)
    force_correction = request.json.get('force_correction', False)
    
    if not translation and not force_correction:
        return jsonify({'error': 'Empty translation'}), 400
    
    # Get daily text
    daily_text = DailyText.query.get(text_id)
    if not daily_text or daily_text.user_id != g.user.id:
        return jsonify({'error': 'Text not found'}), 404
    
    # --- LLM Analysis ---
    
    # Determine mode based on attempt
    # Attempt 1-2: HINTS mode (unless perfect)
    # Attempt 3+ or Force: CORRECTION mode
    
    mode_instruction = ""
    if force_correction or attempt >= 3:
        mode_instruction = "Provide a FULL CORRECTION and score."
    else:
        mode_instruction = "If there are errors, provide HINTS only. Do NOT provide the full correction yet. If it is perfect, mark as PERFECT."

    # Get learner profile context
    from app.llm_service import get_learner_context
    learner_context = get_learner_context(program, g.user)

    prompt = f"""Target Text ({program.target_language}):
"{daily_text.original_text}"

User Translation ({program.native_language}):
"{translation}"

Analyze this translation. 
{mode_instruction}

{learner_context}

Return a valid JSON object strictly matching this schema:
{{
  "status": "PERFECT" | "HINTS" | "CORRECTION",
  "score": {{
    "grammar": 0-10,
    "spelling": 0-10,
    "quality": 0-10,
    "explanation": "Brief explanation of the score"
  }},
  "feedback": "General Encouraging Feedback (in {program.native_language})",
  "hints": ["Hint 1", "Hint 2"],
  "correction": "Full corrected text (only if status is CORRECTION or PERFECT)"
}}

Rules:
- If status is HINTS, 'correction' should be null or empty string.
- If status is HINTS, provide specific actionable hints in 'hints' array (e.g. 'Attention à l'accord du verbe...').
- Feedback must be in {program.native_language}.
"""

    response = call_llm(
        f"You are a strict but helpful {program.target_language} teacher. {learner_context}. Output strictly JSON.",
        prompt,
        temperature=0.3
    )
    
    if not response:
        return jsonify({'error': 'LLM unavailable'}), 500
        
    try:
        # Parse JSON
        import re
        text = response.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
            text = text.rsplit('```', 1)[0]
        
        # Cleanup potential json formatting issues
        analysis = json.loads(text)
        
        
        # --- Logic based on Status ---
        
        status = analysis.get('status', 'CORRECTION')
        
        # ALWAYS SAVE TRANSLATION (fix persistence issue)
        daily_text.user_translation = translation
        db.session.commit()
        
        # If force correction, override status to CORRECTION
        if force_correction:
            status = 'CORRECTION'
            analysis['status'] = 'CORRECTION'
            
        validated = (status == 'PERFECT' or status == 'CORRECTION')
        
        if validated:
            # Save final result
            daily_text.user_translation = translation
            # Store full JSON analysis as correction for now (or just the text)
            # We can store the JSON string to render the grid later if we want, 
            # or just extracts. Let's store the whole JSON string.
            daily_text.llm_correction = json.dumps(analysis)
            
            db.session.commit()
            
            # Update session results
            results = ps.results or {}
            results['git_input'] = {
                'completed': True, 
                'score': analysis.get('score', {}).get('quality', 5)
            }
            ps.results = results
            flag_modified(ps, 'results')
            db.session.commit()
            
            return jsonify({
                'success': True,
                'status': status,
                'analysis': analysis,
                'next': url_for('session.next_module')
            })
            
        else:
            # HINTS mode - do not save as final yet
            return jsonify({
                'success': True,
                'status': status,
                'analysis': analysis
            })

    except (json.JSONDecodeError, Exception) as e:
        print(f"JSON Parse Error: {e} \nRaw: {response}")
        return jsonify({'error': 'Error parsing correction', 'raw': response}), 500


# ============================================================
# MODULE 3: THE GYM (Lego + FSI)
# ============================================================

@bp.route('/gym')
def module_gym():
    """Gym module - New 4-step pedagogical flow."""
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    duration = program.exercise_config.get('duration_target', 10) if program.exercise_config else 10
    
    # Get daily vocabulary for display
    daily_vocab = ps.daily_words or []
    
    return render_template('session/gym.html',
                          session=ps,
                          program=program,
                          gym_duration=duration,
                          daily_vocab=daily_vocab)


@bp.route('/gym/get-exercise', methods=['POST'])
def get_gym_exercise():
    """Generate complete Gym session with 4-step flow."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    from app.gym_engine import GymSessionEngine
    
    # Get session context for coherent generation
    results = ps.results or {}
    session_context = results.get('session_context', {})
    
    engine = GymSessionEngine(ps.program, ps, session_context=session_context)
    
    input_dur = request.json.get('duration')
    duration = int(input_dur) if input_dur is not None else 10
    
    session_data = engine.generate_gym_session(duration_minutes=duration)
    
    if session_data.get('error'):
        return jsonify(session_data), 500
    
    return jsonify({
        'session_id': ps.id,
        'structure': session_data.get('structure'),
        'steps': session_data.get('steps', []),
        'total_steps': session_data.get('total_steps', 0),
        'duration_target': duration,
        'theme_context': {
            'theme_name': session_context.get('theme_name', ''),
            'day_focus': session_context.get('day_focus', ''),
            'vocab_domains': session_context.get('vocab_domains', [])
        }
    })


@bp.route('/gym/check', methods=['POST'])
def check_gym_answer():
    """Check gym exercise answer (discovery, construction, fsi, translation)."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    data = request.json
    exercise_type = data.get('type')
    user_answer = data.get('answer', '').strip()
    step_key = data.get('step_key', '')  # Unique key for this step (e.g., "construction_1")
    
    if not user_answer:
        return jsonify({'error': 'Empty answer'}), 400
    
    from app.gym_engine import GymSessionEngine
    
    # Get session context and conversation history
    results = ps.results or {}
    session_context = results.get('session_context', {})
    engine = GymSessionEngine(program, ps, session_context=session_context)
    
    # Get conversation history for this step
    gym_history = results.get('gym_conversation_history', {})
    step_history = gym_history.get(step_key, [])
    
    result = None
    
    # DISCOVERY: Just check if user copied the example correctly
    if exercise_type == 'discovery':
        expected = data.get('expected', '').strip()
        # Normalize both strings for comparison
        def normalize(s):
            return s.lower().replace(' ', '').replace(',', '').replace('.', '').replace("'", "")
        
        is_match = normalize(user_answer) == normalize(expected)
        
        if is_match:
            result = {
                'is_valid': True,
                'feedback': 'Parfait ! Tu as bien recopié la structure. Passons à la suite.',
                'errors': []
            }
        else:
            result = {
                'is_valid': False,
                'feedback': 'Pas tout à fait... Recopie exactement l\'exemple.',
                'errors': [{'segment': user_answer, 'explanation': f'Attendu: {expected}'}],
                'corrected': expected
            }
    
    # CONSTRUCTION: Validate original sentence follows the structure
    elif exercise_type == 'construction':
        pattern = data.get('pattern', '')
        example = data.get('example', '')
        
        result = engine.validate_construction(user_answer, pattern, example, conversation_history=step_history)
    
    # FSI: Validate mutation transformation
    elif exercise_type == 'fsi':
        original_sentence = data.get('sentence', '')
        mutation_type = data.get('mutation', '')
        
        result = engine.validate_fsi(original_sentence, mutation_type, user_answer, conversation_history=step_history)
    
    # TRANSLATION: Validate translation from native to target
    elif exercise_type == 'translation':
        expected = data.get('expected', '')
        
        # Use LLM to validate (more flexible than exact match)
        from app.llm_service import analyze_text
        context = f"Translation exercise. Expected: {expected}"
        llm_result = analyze_text(program.target_language, user_answer, context, program=program, user=g.user)
        
        if llm_result:
            result = {
                'is_valid': llm_result.get('is_correct', False),
                'feedback': llm_result.get('feedback', ''),
                'errors': llm_result.get('errors', []),
                'corrected': llm_result.get('correction', expected)
            }
        else:
            # Fallback to simple comparison
            def normalize(s):
                return s.lower().replace(' ', '').replace(',', '').replace('.', '')
            is_close = normalize(user_answer) == normalize(expected) or expected.lower() in user_answer.lower()
            result = {
                'is_valid': is_close,
                'feedback': 'Bonne traduction !' if is_close else 'Pas tout à fait...',
                'errors': [] if is_close else [{'segment': user_answer, 'explanation': f'Attendu: {expected}'}],
                'corrected': expected
            }
    
    else:
        return jsonify({'error': f'Unknown exercise type: {exercise_type}'}), 400
    
    # Normalize for frontend
    final_result = {
        'valid': result.get('is_valid', result.get('is_correct', False)),
        'feedback': result.get('feedback', ''),
        'suggestion': result.get('corrected', result.get('correction', '')),
        'errors': result.get('errors', []),
        'vocab_errors': result.get('vocab_errors', []),  # Vocabulary mistakes with hints
        'follows_structure': result.get('follows_structure', True)
    }
    
    # Update conversation history for this step (keep context)
    if step_key and exercise_type in ['construction', 'fsi']:
        step_history.append({
            'role': 'user',
            'text': user_answer
        })
        step_history.append({
            'role': 'assistant',
            'text': final_result['suggestion'],
            'feedback': final_result['feedback'],
            'valid': final_result['valid']
        })
        gym_history[step_key] = step_history[-10:]  # Keep last 10 exchanges per step
        results['gym_conversation_history'] = gym_history
    
    # Track progress
    gym_done = ps.gym_exercises_done or []
    gym_done.append({
        'type': exercise_type,
        'valid': final_result['valid'],
        'timestamp': datetime.utcnow().isoformat()
    })
    ps.gym_exercises_done = gym_done
    flag_modified(ps, 'gym_exercises_done')
    
    # Update results
    gym_results = results.get('gym', {'discovery': 0, 'construction': 0, 'fsi': 0, 'translation': 0})
    gym_results[exercise_type] = gym_results.get(exercise_type, 0) + (1 if final_result['valid'] else 0)
    results['gym'] = gym_results
    ps.results = results
    flag_modified(ps, 'results')
    
    db.session.commit()
    
    return jsonify(final_result)


@bp.route('/gym/generate-translations', methods=['POST'])
def generate_gym_translations():
    """Generate translation phrases for the translation step."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    from app.gym_engine import GymSessionEngine
    from app.models import LegoStructure
    
    structure_id = request.json.get('structure_id')
    n_phrases = request.json.get('count', 3)
    
    structure = LegoStructure.query.get(structure_id)
    if not structure:
        return jsonify({'error': 'Structure not found'}), 404
    
    # Get session context for coherent generation
    results = ps.results or {}
    session_context = results.get('session_context', {})
    
    engine = GymSessionEngine(ps.program, ps, session_context=session_context)
    vocab = ps.daily_words or []
    
    phrases = engine.generate_translation_phrases(structure, n_phrases, vocab)
    
    return jsonify({
        'success': True,
        'phrases': phrases
    })


@bp.route('/gym/complete', methods=['POST'])
def gym_complete():
    """Mark gym module as complete and update structure FSRS."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    from app.gym_engine import GymSessionEngine
    
    structure_id = request.json.get('structure_id')
    grade = request.json.get('grade', 3)  # Default to 'good'
    
    # Update FSRS for the structure
    if structure_id:
        engine = GymSessionEngine(ps.program, ps)
        engine.complete_structure_review(structure_id, grade)
    
    return jsonify({'success': True, 'next': url_for('session.next_module')})


@bp.route('/gym/reveal-vocab', methods=['POST'])
def reveal_vocab_word():
    """Reveal a vocabulary word correction and add it to debt for tomorrow."""
    from app.models import DebtWord
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    wrong_word = request.json.get('wrong_word', '').strip()
    correct_word = request.json.get('correct_word', '').strip()
    native_meaning = request.json.get('native_meaning', '').strip()
    
    if not correct_word:
        return jsonify({'error': 'No word to reveal'}), 400
    
    # Add to DebtWord for tomorrow's review
    DebtWord.add_debt(
        user_id=g.user.id,
        program_id=ps.program_id,
        word_front=correct_word,  # Target language
        word_back=native_meaning or wrong_word,  # Native language or the wrong version
        source='gym_vocab_reveal',
        context=f"Erreur: '{wrong_word}' → Correct: '{correct_word}'"
    )
    
    # Also track in session
    ps.add_debt_word(correct_word, native_meaning or wrong_word, source="gym_vocab")
    flag_modified(ps, 'debt_words')
    db.session.commit()
    
    # Count total debts
    debt_count = DebtWord.query.filter_by(
        user_id=g.user.id,
        program_id=ps.program_id,
        processed=False
    ).count()
    
    return jsonify({
        'success': True,
        'correct_word': correct_word,
        'native_meaning': native_meaning,
        'debt_count': debt_count,
        'message': f"'{correct_word}' sera à revoir demain !"
    })


# ============================================================
# MODULE 4: SHADOWING
# ============================================================

@bp.route('/shadowing')
def module_shadowing():
    """Shadowing module - Real videos or TTS fallback."""
    from app.models import ShadowingVideo
    import random
    
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    # Try to get a video from ShadowingVideo model
    videos = ShadowingVideo.query.filter_by(
        program_id=program.id,
        is_active=True
    ).all()
    
    selected_video = None
    video_segment = None
    
    if videos:
        # Select a random video (prefer less used)
        videos.sort(key=lambda v: v.times_used)
        selected_video = videos[0] if videos else None
        
        if selected_video:
            # Get a random segment
            video_segment = selected_video.get_random_segment(duration=30)
            selected_video.mark_used()
            db.session.commit()
    
    # Fallback: TTS phrases if no videos available
    phrases = []
    if not selected_video:
        # Add phrases from daily words
        for word in (ps.daily_words or [])[:5]:
            phrases.append(word.get('front', ''))
        
        # Add sentences from git input
        today = date.today()
        daily_text = DailyText.query.filter_by(
            program_id=program.id,
            user_id=g.user.id,
            created_date=today
        ).first()
        
        if daily_text and daily_text.original_text:
            import re
            sentences = re.split(r'[.!?]+', daily_text.original_text)
            phrases.extend([s.strip() for s in sentences if s.strip()])
    
    return render_template('session/shadowing.html',
                          session=ps,
                          program=program,
                          video=selected_video.to_dict() if selected_video else None,
                          video_segment=video_segment,
                          embed_url=selected_video.get_youtube_embed_url(video_segment.get('start', 0)) if selected_video and video_segment else None,
                          phrases=phrases[:10],
                          has_video=bool(selected_video))


@bp.route('/shadowing/get-next-video', methods=['POST'])
def get_next_shadowing_video():
    """Get next video for shadowing (called when user wants another)."""
    from app.models import ShadowingVideo
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    current_video_id = request.json.get('current_video_id')
    
    videos = ShadowingVideo.query.filter_by(
        program_id=ps.program_id,
        is_active=True
    ).all()
    
    # Filter out current if provided
    if current_video_id:
        videos = [v for v in videos if v.id != current_video_id]
    
    if not videos:
        return jsonify({'error': 'No more videos available'}), 404
    
    # Pick least used
    videos.sort(key=lambda v: v.times_used)
    video = videos[0]
    segment = video.get_random_segment(duration=30)
    video.mark_used()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'video': video.to_dict(),
        'segment': segment,
        'embed_url': video.get_youtube_embed_url(segment.get('start', 0))
    })


@bp.route('/shadowing/complete', methods=['POST'])
def shadowing_complete():
    """Mark shadowing as complete."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    data = request.json or {}
    
    results = ps.results or {}
    results['shadowing'] = {
        'done': data.get('done', 0),
        'total': data.get('total', 0),
        'videos_watched': data.get('videos_watched', 0)
    }
    ps.results = results
    flag_modified(ps, 'results')
    db.session.commit()
    
    return jsonify({'success': True, 'next': url_for('session.next_module')})


# ============================================================
# MODULE 5: GIT OUTPUT (Native → Target, J+1)
# ============================================================

@bp.route('/git-output')
def module_git_output():
    """Git Output module - recode from native to target (J+1)."""
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    # Get yesterday's text
    yesterday = date.today() - timedelta(days=1)
    daily_text = DailyText.query.filter_by(
        program_id=program.id,
        user_id=g.user.id,
        created_date=yesterday,
        used_for_output=False
    ).first()
    
    # If no text from yesterday, try any unused text
    if not daily_text:
        daily_text = DailyText.query.filter_by(
            program_id=program.id,
            user_id=g.user.id,
            used_for_output=False
        ).filter(DailyText.user_translation.isnot(None)).first()
    
    has_text = daily_text is not None
    
    return render_template('session/git_output.html',
                          session=ps,
                          program=program,
                          daily_text=daily_text,
                          has_text=has_text,
                          daily_vocab=ps.daily_words or [])


@bp.route('/git-output/submit', methods=['POST'])
def submit_git_output():
    """Submit recoded text for Git Output with triple comparison."""
    from app.llm_service import call_llm
    from app.prompt_templates import build_prompt
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    recode = request.json.get('recode', '').strip()
    text_id = request.json.get('text_id')
    
    if not recode:
        return jsonify({'error': 'Empty response'}), 400
    
    daily_text = DailyText.query.get(text_id)
    if not daily_text or daily_text.user_id != g.user.id:
        return jsonify({'error': 'Text not found'}), 404
    
    # Save recode
    daily_text.user_recode = recode
    daily_text.used_for_output = True
    
    # Build comparison prompt using template
    prompt = build_prompt(
        'git_output_diff',
        program,
        g.user,
        original_text=daily_text.original_text,
        yesterday_translation=daily_text.user_translation or daily_text.llm_correction or "Non disponible",
        user_recode=recode
    )
    
    diff_result = call_llm(
        f"Tu es un expert en analyse comparative de textes en {program.target_language}. JSON output only.",
        prompt,
        temperature=0.2
    )
    
    diff_data = {
        'errors': [], 
        'accuracy_percent': 100, 
        'feedback': 'Bravo !',
        'preserved_well': [],
        'tips': []
    }
    
    try:
        if diff_result:
            text = diff_result.strip()
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            diff_data = json.loads(text.strip())
    except Exception as e:
        print(f"Git Output diff parse error: {e}")
    
    daily_text.diff_results = diff_data
    
    # Update results
    results = ps.results or {}
    results['git_output'] = {
        'completed': True,
        'diff_errors': len(diff_data.get('errors', [])),
        'accuracy': diff_data.get('accuracy_percent', 0)
    }
    ps.results = results
    flag_modified(ps, 'results')
    
    db.session.commit()
    
    # Return triple comparison data
    return jsonify({
        'success': True,
        'comparison': {
            'original': daily_text.original_text,
            'yesterday_translation': daily_text.user_translation or daily_text.llm_correction,
            'today_recode': recode
        },
        'diff': diff_data,
        'next': url_for('session.next_module')
    })


@bp.route('/git-output/skip', methods=['POST'])
def skip_git_output():
    """Skip git output if no text available."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    results = ps.results or {}
    results['git_output'] = {'completed': True, 'skipped': True}
    ps.results = results
    flag_modified(ps, 'results')
    db.session.commit()
    
    return jsonify({'success': True, 'next': url_for('session.next_module')})


# ============================================================
# MODULE 6: SMART WRITING (Boss Fight)
# ============================================================

@bp.route('/writing')
def module_writing():
    """Smart Writing module - boss fight with quest."""
    ps = get_current_session()
    if not ps:
        return redirect(url_for('main.index'))
    
    program = ps.program
    
    return render_template('session/writing.html',
                          session=ps,
                          program=program,
                          daily_words=ps.daily_words or [],
                          daily_vocab=ps.daily_words or [],
                          theme=ps.daily_words_theme)


@bp.route('/writing/generate-quest', methods=['POST'])
def generate_writing_quest():
    """Generate a writing quest using today's vocabulary and session context."""
    from app.llm_service import call_llm
    from app.prompt_templates import build_prompt
    import random
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    daily_words = ps.daily_words or []
    
    # Get session context for coherent generation
    results = ps.results or {}
    session_context = results.get('session_context', {})
    
    # Extract context data
    theme_name = session_context.get('theme_name', ps.daily_words_theme or 'daily life')
    theme_description = session_context.get('theme_description', '')
    day_focus = session_context.get('day_focus', 'Pratique générale')
    vocab_domains = session_context.get('vocab_domains', ['general'])
    key_situations = session_context.get('key_situations', [])
    user_level = session_context.get('user_level', 'A2')
    
    # Pick 4-6 words to include
    words_to_use = random.sample(daily_words, min(5, len(daily_words))) if daily_words else []
    word_list = ', '.join([w.get('front', '') for w in words_to_use])
    
    # Include Lego patterns if available
    patterns = program.lego_templates or []
    pattern_hint = ''
    if patterns:
        pattern = random.choice(patterns)
        pattern_hint = f"\nStructure suggérée: {pattern.get('pattern', '')}"
    
    # Build context block
    theme_full = theme_name
    if theme_description:
        theme_full += f" - {theme_description}"
    
    situations_str = ', '.join(key_situations) if key_situations else 'conversation quotidienne'
    domains_str = ', '.join(vocab_domains) if vocab_domains else 'général'
    
    # Use build_prompt for consistency
    try:
        prompt = build_prompt(
            'writing_quest',
            program,
            g.user,
            theme=theme_full,
            vocabulary=word_list
        )
    except Exception:
        # Fallback to manual prompt with full context
        prompt = f"""Crée une mission d'écriture en {program.native_language} pour un apprenant de {program.target_language}.

CONTEXTE THÉMATIQUE:
- Thème de la semaine: {theme_full}
- Focus du jour: {day_focus}
- Domaines de vocabulaire: {domains_str}
- Situations clés: {situations_str}

VOCABULAIRE À UTILISER: {word_list}
{pattern_hint}

NIVEAU DE L'APPRENANT: {user_level}

La mission doit:
- Être créative et motivante
- Demander 50-80 mots en {program.target_language}
- Être adaptée au niveau {user_level}
- Correspondre au thème et aux situations du jour
- Encourager l'utilisation du vocabulaire listé

Écris la consigne en {program.native_language}.
Retourne UNIQUEMENT le texte de la mission, rien d'autre."""

    quest = call_llm(
        f"Tu es un professeur de langues créatif et bienveillant.",
        prompt,
        temperature=0.9
    )
    
    if not quest:
        quest = f"Écrivez un court texte sur '{theme_name}' ({day_focus}) en utilisant les mots: {word_list}"
    
    ps.writing_quest = quest.strip()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'quest': quest.strip(),
        'words_to_use': [w.get('front', '') for w in words_to_use],
        'theme_context': {
            'theme': theme_name,
            'focus': day_focus,
            'situations': key_situations
        }
    })


@bp.route('/writing/submit', methods=['POST'])
def submit_writing():
    """Submit writing and get correction with session context."""
    from app.llm_service import call_llm
    from app.prompt_templates import build_prompt
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    text = request.json.get('text', '').strip()
    
    if not text:
        return jsonify({'error': 'Empty text'}), 400
    
    ps.writing_text = text
    
    # Get session context
    results = ps.results or {}
    session_context = results.get('session_context', {})
    
    # Extract vocabulary list
    daily_words = ps.daily_words or []
    vocab_list = ', '.join([w.get('front', '') for w in daily_words[:15]])
    
    # Extract context data
    theme_name = session_context.get('theme_name', ps.daily_words_theme or 'daily life')
    day_focus = session_context.get('day_focus', 'Pratique générale')
    user_level = session_context.get('user_level', 'A2')
    
    # Use build_prompt for consistency
    try:
        correction_prompt = build_prompt(
            'writing_feedback',
            program,
            g.user,
            quest=ps.writing_quest or 'Écriture libre',
            vocabulary=vocab_list,
            user_text=text
        )
    except Exception:
        # Fallback to manual prompt with full context
        correction_prompt = f"""Corrige ce texte en {program.target_language} écrit par un apprenant.

MISSION: {ps.writing_quest or 'Écriture libre'}

CONTEXTE:
- Thème: {theme_name}
- Focus du jour: {day_focus}
- Niveau: {user_level}

VOCABULAIRE DU JOUR (à vérifier): {vocab_list}

TEXTE DE L'APPRENANT:
{text}

Analyse et donne un feedback détaillé en {program.native_language}:
1. Liste toutes les erreurs avec corrections
2. Note de 1 à 10
3. Feedback encourageant
4. Mots du jour bien utilisés
5. Mots du jour manqués (opportunités)

Sois détaillé mais bienveillant. Adapte tes commentaires au niveau {user_level}."""

    feedback = call_llm(
        f"Tu es un professeur de {program.target_language} bienveillant qui donne des feedbacks détaillés.",
        correction_prompt,
        temperature=0.5
    )
    
    ps.writing_feedback = feedback
    
    # Update results
    results['writing'] = {
        'completed': True,
        'words_helped': len(ps.debt_words or []),
        'theme': theme_name,
        'focus': day_focus
    }
    ps.results = results
    flag_modified(ps, 'results')
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'feedback': feedback,
        'next': url_for('session.next_module')
    })


# ============================================================
# WORD BANK & SOS (Available in all modules)
# ============================================================

@bp.route('/wordbank')
def get_wordbank():
    """Get word bank for sidebar."""
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    # Words learned today
    words = []
    for w in (ps.daily_words or []):
        # Check if already revealed (in debt)
        revealed = any(d.get('front') == w.get('front') for d in (ps.debt_words or []))
        words.append({
            'front': w.get('front', ''),
            'back': w.get('back', '') if revealed else None,
            'revealed': revealed
        })
    
    return jsonify({
        'success': True,
        'words': words,
        'debt_count': len(ps.debt_words or [])
    })


@bp.route('/wordbank/reveal', methods=['POST'])
def reveal_word():
    """Reveal a word from word bank - creates a DebtWord for tomorrow's review."""
    from app.models import DebtWord
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    front = request.json.get('front', '')
    context = request.json.get('context', '')  # Optional: which exercise they're doing
    
    # Find the word in daily_words
    word_found = None
    for w in (ps.daily_words or []):
        if w.get('front') == front:
            word_found = w
            break
    
    if not word_found:
        return jsonify({'error': 'Word not found'}), 404
    
    back = word_found.get('back', '')
    
    # Create DebtWord for tomorrow's review
    DebtWord.add_debt(
        user_id=g.user.id,
        program_id=ps.program_id,
        word_front=front,
        word_back=back,
        source='wordbank',
        context=context or ps.current_module
    )
    
    # Also track in session for immediate UI feedback
    ps.add_debt_word(front, back, source='wordbank')
    
    # Apply FSRS penalty to the actual card (if it exists)
    card_id = word_found.get('card_id')
    if card_id:
        card = Card.query.get(card_id)
        if card:
            card.apply_fsrs_penalty(direction='both', penalty_factor=0.7)
    
    flag_modified(ps, 'debt_words')
    db.session.commit()
    
    # Count total debts for this session
    debt_count = DebtWord.query.filter_by(
        user_id=g.user.id,
        program_id=ps.program_id,
        processed=False
    ).count()
    
    return jsonify({
        'success': True,
        'back': back,
        'debt_count': debt_count,
        'penalty_applied': bool(card_id),
        'message': 'Ce mot sera à revoir demain !'
    })


@bp.route('/vocab/add', methods=['POST'])
def add_vocab_word():
    """Add a custom word to vocabulary with LLM verification."""
    from app.llm_service import call_llm
    from app.models import DebtWord
    
    ps = get_current_session()
    program = None
    
    if ps:
        program = ps.program
    else:
        from app.models import TrainingProgram
        program = TrainingProgram.query.filter_by(user_id=g.user.id, is_active=True).first()
    
    if not program:
        return jsonify({'error': 'No active program'}), 400
    
    word = request.json.get('word', '').strip()
    target_lang = request.json.get('target_language', program.target_language)
    native_lang = request.json.get('native_language', program.native_language)
    
    if not word:
        return jsonify({'error': 'No word provided'}), 400
    
    # Use LLM to verify and translate the word
    prompt = f"""L'utilisateur veut ajouter ce mot à son vocabulaire: "{word}"

Langues du programme:
- Langue cible (à apprendre): {target_lang}
- Langue maternelle: {native_lang}

Tâches:
1. Identifie dans quelle langue est le mot
2. Vérifie qu'il existe vraiment
3. Traduis-le dans l'autre langue

Réponds UNIQUEMENT en JSON valide:
{{
    "is_valid": true/false,
    "detected_language": "{target_lang}" ou "{native_lang}" ou "autre",
    "front": "mot en {target_lang}",
    "back": "traduction en {native_lang}",
    "error": "message d'erreur si is_valid=false"
}}
"""

    response = call_llm(
        f"Tu es un lexicographe expert en {target_lang} et {native_lang}. JSON output only.",
        prompt,
        temperature=0.2
    )
    
    try:
        # Parse JSON
        clean = response.strip()
        if '```json' in clean:
            clean = clean.split('```json')[1].split('```')[0]
        elif '```' in clean:
            clean = clean.split('```')[1].split('```')[0]
        
        data = json.loads(clean.strip())
        
        if not data.get('is_valid'):
            return jsonify({
                'success': False,
                'error': data.get('error', 'Mot non reconnu')
            })
        
        front = data.get('front', '').strip()
        back = data.get('back', '').strip()
        
        if not front or not back:
            return jsonify({'success': False, 'error': 'Traduction incomplète'})
        
        # Add to DebtWord for tomorrow (user asked for it = debt)
        if ps:
            DebtWord.add_debt(
                user_id=g.user.id,
                program_id=program.id,
                word_front=front,
                word_back=back,
                source='user_added',
                context='Manual vocabulary addition'
            )
            
            # Add to session daily_words
            daily_words = ps.daily_words or []
            daily_words.append({'front': front, 'back': back})
            ps.daily_words = daily_words
            flag_modified(ps, 'daily_words')
            db.session.commit()
        
        # Also add to deck if doesn't exist
        if program.deck_id:
            existing = Card.query.filter_by(deck_id=program.deck_id, front=front).first()
            if not existing:
                new_card = Card(
                    deck_id=program.deck_id,
                    front=front,
                    back=back,
                    slot_type='vocabulary'
                )
                db.session.add(new_card)
                db.session.commit()
        
        return jsonify({
            'success': True,
            'front': front,
            'back': back,
            'detected_language': data.get('detected_language', 'unknown')
        })
        
    except Exception as e:
        print(f"Add vocab error: {e}\nRaw: {response[:500] if response else 'None'}")
        return jsonify({'success': False, 'error': 'Erreur de traitement'})


@bp.route('/sos', methods=['POST'])
def use_sos():
    """Get a translation for a word - adds to debt for tomorrow (no tokens needed)."""
    from app.llm_service import call_llm
    from app.models import DebtWord
    
    ps = get_current_session()
    if not ps:
        return jsonify({'error': 'No session'}), 400
    
    program = ps.program
    word = request.json.get('word', '').strip()
    direction = request.json.get('direction', 'to_target')  # 'to_target' or 'to_native'
    context = request.json.get('context', '')
    
    if not word:
        return jsonify({'error': 'No word provided'}), 400
    
    # Get translation from LLM
    if direction == 'to_target':
        prompt = f"Translate to {program.target_language}: {word}\nReturn ONLY the translation."
    else:
        prompt = f"Translate to {program.native_language}: {word}\nReturn ONLY the translation."
    
    translation = call_llm(
        f"You are a translator. Give only the translation, nothing else.",
        prompt,
        temperature=0.3
    )
    
    if not translation:
        return jsonify({'error': 'Translation failed'}), 500
    
    translation = translation.strip()
    
    # Determine front/back based on direction
    if direction == 'to_target':
        front = translation  # Target language (what they'll need to produce)
        back = word          # Native language (the hint)
    else:
        front = word          # Target language (what they asked about)
        back = translation    # Native translation
    
    # Create DebtWord for tomorrow
    DebtWord.add_debt(
        user_id=g.user.id,
        program_id=ps.program_id,
        word_front=front,
        word_back=back,
        source='sos',
        context=context or ps.current_module
    )
    
    # Also track in session
    ps.add_debt_word(front, back, source='sos')
    
    # Create a new card in the program's deck (if doesn't exist)
    existing_card = Card.query.filter_by(
        deck_id=program.deck_id,
        front=front
    ).first()
    
    if not existing_card:
        new_card = Card(
            deck_id=program.deck_id,
            front=front,
            back=back,
            slot_type='vocabulary'
        )
        db.session.add(new_card)
    
    flag_modified(ps, 'debt_words')
    db.session.commit()
    
    # Count debts
    debt_count = DebtWord.query.filter_by(
        user_id=g.user.id,
        program_id=ps.program_id,
        processed=False
    ).count()
    
    return jsonify({
        'success': True,
        'translation': translation,
        'debt_count': debt_count,
        'card_created': not existing_card,
        'message': f'"{front}" sera à revoir demain !'
    })

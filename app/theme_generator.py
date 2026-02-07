"""
Theme Generator - Generates weekly themes for training sessions.
"""
import json
from datetime import datetime
from app import db
from app.models import WeeklyTheme, TrainingProgram, User
from app.llm_service import call_llm


# System prompt for theme generation
THEME_SYSTEM_PROMPT = """Tu es un expert en pedagogie des langues et en conception de programmes d'apprentissage.
Tu crées des themes hebdomadaires immersifs et narratifs pour aider les apprenants.
Réponds UNIQUEMENT en JSON valide, sans texte avant ou après."""


def get_or_generate_weekly_theme(program: TrainingProgram, user: User) -> WeeklyTheme:
    """
    Get the current week's theme or generate a new one.
    
    Args:
        program: The training program
        user: The user
    
    Returns:
        WeeklyTheme: The active theme for this week
    """
    year, week_num, _ = datetime.now().isocalendar()
    
    # Check for existing theme this week
    existing = WeeklyTheme.query.filter_by(
        program_id=program.id,
        year=year,
        week_number=week_num
    ).first()
    
    if existing:
        return existing
    
    # Generate a new theme
    return generate_new_weekly_theme(program, user)


def generate_new_weekly_theme(program: TrainingProgram, user: User) -> WeeklyTheme:
    """
    Generate a new weekly theme using LLM.
    
    Args:
        program: The training program
        user: The user
    
    Returns:
        WeeklyTheme: The newly generated theme
    """
    year, week_num, _ = datetime.now().isocalendar()
    
    # Get past themes to avoid repetition (last 12 weeks)
    past_themes = WeeklyTheme.query.filter_by(
        program_id=program.id
    ).order_by(WeeklyTheme.generated_at.desc()).limit(12).all()
    
    past_themes_list = [t.main_theme for t in past_themes]
    
    # Get profile data
    program_profile = program.program_profile or {}
    user_profile = user.learner_profile or {}
    
    user_level = program_profile.get('current_level', 'A2')
    user_goals = program_profile.get('goals', [])
    target_language = program.target_language or 'la langue cible'
    native_language = program.native_language or user_profile.get('native_language', 'français')
    
    # Build prompt
    prompt = build_theme_generation_prompt(
        target_language=target_language,
        native_language=native_language,
        user_level=user_level,
        user_goals=user_goals,
        past_themes=past_themes_list,
        days_count=7
    )
    
    # Call LLM
    response = call_llm(THEME_SYSTEM_PROMPT, prompt, temperature=0.8)
    theme_data = parse_theme_response(response)
    
    if not theme_data:
        # Fallback theme
        theme_data = generate_fallback_theme(target_language)
    
    # Create and save WeeklyTheme
    weekly_theme = WeeklyTheme(
        program_id=program.id,
        user_id=user.id,
        year=year,
        week_number=week_num,
        main_theme=theme_data['main_theme'],
        theme_description=theme_data.get('description', ''),
        daily_breakdown=theme_data.get('daily_breakdown', []),
        based_on_goals=user_goals,
        based_on_level=user_level,
        previous_themes_considered=past_themes_list[:5]  # Keep last 5 for reference
    )
    
    db.session.add(weekly_theme)
    db.session.commit()
    
    return weekly_theme


def build_theme_generation_prompt(
    target_language: str,
    native_language: str,
    user_level: str,
    user_goals: list,
    past_themes: list,
    days_count: int = 7
) -> str:
    """Build the prompt for theme generation."""
    
    goals_str = ', '.join(user_goals) if user_goals else 'communication générale'
    past_themes_str = ', '.join(past_themes) if past_themes else 'aucun'
    
    return f"""Tu es un expert en pedagogie des langues. Genere un theme hebdomadaire pour apprendre {target_language}.

PROFIL APPRENANT:
- Niveau: {user_level}
- Objectifs: {goals_str}
- Langue maternelle: {native_language}

THEMES DEJA COUVERTS (a eviter):
{past_themes_str}

INSTRUCTIONS:
1. Choisis un theme immersif et narratif (voyage, situation de vie, projet...)
2. Decoupe en {days_count} jours avec progression logique
3. Chaque jour doit avoir un focus clair et des domaines de vocabulaire
4. Le theme doit etre adapte au niveau {user_level}
5. Les domaines de vocabulaire doivent etre concrets et utiles

REPONDS EN JSON STRICT (sans markdown, juste le JSON):
{{
    "main_theme": "Titre du theme",
    "description": "Contexte narratif (2-3 phrases)",
    "daily_breakdown": [
        {{
            "day": 1,
            "focus": "Description du focus",
            "vocab_domains": ["domaine1", "domaine2"],
            "key_situations": ["situation1", "situation2"]
        }},
        {{
            "day": 2,
            "focus": "Description du focus jour 2",
            "vocab_domains": ["domaine3", "domaine4"],
            "key_situations": ["situation3"]
        }},
        // ... jusqu'au jour {days_count}
    ]
}}"""


def parse_theme_response(response: str) -> dict:
    """Parse the LLM response into theme data."""
    if not response:
        return None
    
    try:
        # Clean response from markdown code blocks
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        
        data = json.loads(response.strip())
        
        # Validate required fields
        if 'main_theme' not in data:
            return None
        
        # Ensure daily_breakdown exists and has proper structure
        if 'daily_breakdown' not in data or not isinstance(data['daily_breakdown'], list):
            data['daily_breakdown'] = []
        
        # Fill missing days with defaults
        while len(data['daily_breakdown']) < 7:
            day_num = len(data['daily_breakdown']) + 1
            data['daily_breakdown'].append({
                'day': day_num,
                'focus': f'Jour {day_num} - Pratique générale',
                'vocab_domains': ['general'],
                'key_situations': ['conversation quotidienne']
            })
        
        return data
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse theme JSON: {e}")
        print(f"Response was: {response[:500]}")
        return None


def generate_fallback_theme(target_language: str) -> dict:
    """Generate a fallback theme when LLM fails."""
    return {
        'main_theme': f'Semaine de pratique en {target_language}',
        'description': f'Une semaine de pratique variee pour renforcer vos competences en {target_language}.',
        'daily_breakdown': [
            {'day': 1, 'focus': 'Salutations et presentations', 'vocab_domains': ['greetings', 'basics'], 'key_situations': ['se presenter']},
            {'day': 2, 'focus': 'La vie quotidienne', 'vocab_domains': ['daily_routine', 'time'], 'key_situations': ['raconter sa journee']},
            {'day': 3, 'focus': 'Faire des achats', 'vocab_domains': ['shopping', 'numbers'], 'key_situations': ['au magasin']},
            {'day': 4, 'focus': 'Au restaurant', 'vocab_domains': ['food', 'ordering'], 'key_situations': ['commander un repas']},
            {'day': 5, 'focus': 'Se deplacer', 'vocab_domains': ['transport', 'directions'], 'key_situations': ['demander son chemin']},
            {'day': 6, 'focus': 'Loisirs et hobbies', 'vocab_domains': ['hobbies', 'entertainment'], 'key_situations': ['parler de ses passions']},
            {'day': 7, 'focus': 'Revision et consolidation', 'vocab_domains': ['general', 'mixed'], 'key_situations': ['conversation libre']}
        ]
    }


def get_current_day_focus(program: TrainingProgram, user: User) -> dict:
    """
    Get the focus for today's session.
    
    Returns:
        dict with 'focus', 'vocab_domains', 'key_situations', 'weekly_theme'
    """
    weekly_theme = get_or_generate_weekly_theme(program, user)
    day_index = datetime.now().weekday()  # 0 = Monday, 6 = Sunday
    
    day_focus = weekly_theme.get_day_focus(day_index)
    
    return {
        'weekly_theme': weekly_theme,
        'focus': day_focus.get('focus', 'Pratique generale'),
        'vocab_domains': day_focus.get('vocab_domains', ['general']),
        'key_situations': day_focus.get('key_situations', []),
        'day_index': day_index,
        'theme_name': weekly_theme.main_theme,
        'theme_description': weekly_theme.theme_description
    }


def build_session_context(program: TrainingProgram, user: User, daily_words: list = None) -> dict:
    """
    Build complete session context for LLM prompts.
    This context should be used by ALL LLM generators (flashcards, git input, gym, writing).
    
    Returns:
        dict with all context needed for coherent generation
    """
    # Get weekly theme and day focus
    try:
        weekly_theme = get_or_generate_weekly_theme(program, user)
        day_index = datetime.now().weekday()
        day_focus = weekly_theme.get_day_focus(day_index)
    except Exception as e:
        print(f"[Context] Theme error: {e}")
        weekly_theme = None
        day_focus = {'focus': 'Pratique générale', 'vocab_domains': ['general'], 'key_situations': []}
    
    # Get past themes for context (avoid repetition)
    past_themes = []
    if weekly_theme:
        past = WeeklyTheme.query.filter_by(
            program_id=program.id
        ).filter(WeeklyTheme.id != weekly_theme.id).order_by(
            WeeklyTheme.generated_at.desc()
        ).limit(4).all()
        past_themes = [{'theme': t.main_theme, 'description': t.theme_description} for t in past]
    
    # Get profile data
    program_profile = program.program_profile or {}
    user_profile = user.learner_profile or {}
    
    # Build vocabulary list from daily_words
    vocab_list = []
    if daily_words:
        for w in daily_words[:20]:  # Limit to 20 words for prompt size
            if isinstance(w, dict):
                vocab_list.append(f"{w.get('front', '')} = {w.get('back', '')}")
    
    # Session timing
    exercise_config = program.exercise_config or {}
    duration_minutes = exercise_config.get('duration_target', 30)
    
    return {
        # Theme info
        'theme_name': weekly_theme.main_theme if weekly_theme else 'Session d\'entraînement',
        'theme_description': weekly_theme.theme_description if weekly_theme else '',
        'day_focus': day_focus.get('focus', 'Pratique générale'),
        'vocab_domains': day_focus.get('vocab_domains', ['general']),
        'key_situations': day_focus.get('key_situations', []),
        'past_themes': past_themes,
        
        # Language info
        'target_language': program.target_language or 'langue cible',
        'native_language': program.native_language or user_profile.get('native_language', 'français'),
        
        # User profile
        'user_level': program_profile.get('current_level', 'A2'),
        'user_goals': program_profile.get('goals', []),
        'correction_style': program_profile.get('correction_strictness', 'moderate'),
        
        # Session vocabulary
        'daily_vocabulary': vocab_list,
        'vocab_count': len(vocab_list),
        
        # Timing
        'session_duration': duration_minutes,
        'exercises_budget': calculate_exercises_budget(duration_minutes),
        
        # Raw objects for advanced use
        'weekly_theme': weekly_theme,
        'program': program,
        'user': user
    }


def calculate_exercises_budget(duration_minutes: int) -> dict:
    """
    Calculate how many exercises/items based on session duration.
    
    Rough estimates:
    - Flashcards: ~30 sec per card (both directions)
    - Git Input: ~5-8 min for text + translation
    - Gym: ~2 min per structure (discovery + construction + FSI)
    - Shadowing: ~3 min per segment
    - Git Output: ~5 min
    - Writing: ~8-10 min
    """
    # Reserve time for each module (proportional)
    # Flashcards: 30%, Git Input: 15%, Gym: 25%, Shadowing: 10%, Git Output: 10%, Writing: 10%
    
    flashcard_time = duration_minutes * 0.30
    gym_time = duration_minutes * 0.25
    
    return {
        'flashcard_pairs': max(5, int(flashcard_time * 2)),  # ~30s per pair
        'new_words': max(3, int(flashcard_time / 2)),        # New words to learn
        'gym_structures': max(1, int(gym_time / 3)),         # ~3 min per structure cycle
        'gym_phrases_per_structure': max(2, int(gym_time / 4)),
        'shadowing_segments': max(1, int(duration_minutes * 0.10 / 3)),
        'writing_words_target': max(30, duration_minutes * 2)  # ~2 words per minute of session
    }


def build_llm_context_block(context: dict) -> str:
    """
    Build a formatted context block to inject into LLM prompts.
    Use this at the start of any LLM prompt for consistency.
    """
    vocab_str = ', '.join(context['daily_vocabulary'][:10]) if context['daily_vocabulary'] else 'aucun'
    domains_str = ', '.join(context['vocab_domains'])
    situations_str = ', '.join(context['key_situations']) if context['key_situations'] else 'conversation générale'
    past_str = ', '.join([p['theme'] for p in context['past_themes']]) if context['past_themes'] else 'aucun'
    goals_str = ', '.join(context['user_goals']) if context['user_goals'] else 'communication générale'
    
    return f"""CONTEXTE DE SESSION:
- Thème de la semaine: {context['theme_name']}
- Description: {context['theme_description']}
- Focus du jour: {context['day_focus']}
- Domaines de vocabulaire: {domains_str}
- Situations clés: {situations_str}
- Thèmes passés (à éviter): {past_str}

PROFIL APPRENANT:
- Niveau: {context['user_level']}
- Objectifs: {goals_str}
- Langue cible: {context['target_language']}
- Langue maternelle: {context['native_language']}

VOCABULAIRE DU JOUR ({context['vocab_count']} mots):
{vocab_str}

CONTRAINTES:
- Utilise le vocabulaire du jour dans les exemples
- Reste cohérent avec le thème et le focus
- Adapte la difficulté au niveau {context['user_level']}
"""

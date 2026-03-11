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
    Uses theme_preferences from program_profile for personalization.
    """
    year, week_num, _ = datetime.now().isocalendar()
    
    # Get past themes to avoid repetition (last 12 weeks)
    past_themes = WeeklyTheme.query.filter_by(
        program_id=program.id
    ).order_by(WeeklyTheme.generated_at.desc()).limit(12).all()
    
    past_themes_list = [
        {'theme': t.main_theme, 'description': t.theme_description or ''}
        for t in past_themes
    ]
    
    # Collect all covered vocab domains from past themes
    covered_domains = set()
    for t in past_themes[:4]:
        if t.daily_breakdown:
            for day in t.daily_breakdown:
                for d in day.get('vocab_domains', []):
                    covered_domains.add(d)
    
    # Get profile data
    program_profile = program.program_profile or {}
    user_profile = user.learner_profile or {}
    theme_prefs = program_profile.get('theme_preferences', {})
    
    user_level = program_profile.get('current_level', 'A2')
    user_goals = program_profile.get('goals', [])
    years_learning = program_profile.get('years_learning', 0)
    target_language = program.target_language or 'la langue cible'
    native_language = program.native_language or user_profile.get('native_language', 'français')
    
    # Theme preferences
    interests = theme_prefs.get('interests', [])
    custom_interests = theme_prefs.get('custom_interests', '')
    avoid_topics = theme_prefs.get('avoid_topics', '')
    theme_style = theme_prefs.get('theme_style', 'quotidien_realiste')
    geographic_context = theme_prefs.get('geographic_context', '')
    
    # Build prompt
    prompt = build_theme_generation_prompt(
        target_language=target_language,
        native_language=native_language,
        user_level=user_level,
        user_goals=user_goals,
        years_learning=years_learning,
        past_themes=past_themes_list,
        covered_domains=list(covered_domains),
        interests=interests,
        custom_interests=custom_interests,
        avoid_topics=avoid_topics,
        theme_style=theme_style,
        geographic_context=geographic_context,
        days_count=7
    )
    
    # Call LLM
    response = call_llm(THEME_SYSTEM_PROMPT, prompt, temperature=0.8)
    theme_data = parse_theme_response(response)
    
    if not theme_data:
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
        previous_themes_considered=[t['theme'] for t in past_themes_list[:5]]
    )
    
    db.session.add(weekly_theme)
    db.session.commit()
    
    return weekly_theme


def build_theme_generation_prompt(
    target_language: str,
    native_language: str,
    user_level: str,
    user_goals: list,
    years_learning: int = 0,
    past_themes: list = None,
    covered_domains: list = None,
    interests: list = None,
    custom_interests: str = '',
    avoid_topics: str = '',
    theme_style: str = 'quotidien_realiste',
    geographic_context: str = '',
    days_count: int = 7
) -> str:
    """Build an enriched prompt for theme generation with user preferences."""
    
    goals_str = ', '.join(user_goals) if user_goals else 'communication generale'
    
    # Past themes with descriptions
    past_str = 'aucun'
    if past_themes:
        past_items = []
        for t in past_themes[:8]:
            desc = t.get('description', '') if isinstance(t, dict) else ''
            name = t.get('theme', str(t)) if isinstance(t, dict) else str(t)
            past_items.append(f"- {name}" + (f" ({desc[:60]})" if desc else ''))
        past_str = '\n'.join(past_items)
    
    # Covered vocabulary domains
    covered_str = ', '.join(covered_domains[:15]) if covered_domains else 'aucun encore'
    
    # Interests
    all_interests = list(interests or [])
    if custom_interests:
        all_interests.append(custom_interests)
    interests_str = ', '.join(all_interests) if all_interests else 'pas de preference particuliere'
    
    # Avoid topics
    avoid_str = avoid_topics if avoid_topics else 'aucun'
    
    # Theme style description
    style_descriptions = {
        'quotidien_realiste': 'Situations du QUOTIDIEN realiste: courses, travail, transports, amis, routine. Pas de scenarios fantaisistes.',
        'aventure_narrative': 'Une HISTOIRE qui se deroule sur 7 jours: un voyage, un demenagement, un nouveau travail, un projet. Chaque jour est un chapitre.',
        'professionnel': 'Contextes PROFESSIONNELS: reunion, email, presentation, negociation, entretien, vie de bureau.',
        'culturel': 'Decouverte CULTURELLE du pays: traditions, art, cuisine regionale, histoire locale, medias, fetes.'
    }
    style_desc = style_descriptions.get(theme_style, style_descriptions['quotidien_realiste'])
    
    # Geographic context
    geo_str = ''
    if geographic_context:
        geo_str = f"\n- Contexte geographique: {geographic_context} (utilise ce lieu et sa culture comme ancrage pour le theme)"
    
    return f"""Tu es un expert en pedagogie des langues et un scenariste creatif. Genere un theme hebdomadaire NARRATIF et COHERENT pour apprendre {target_language}.

PROFIL APPRENANT:
- Niveau: {user_level}
- Experience: {years_learning} an(s) d'apprentissage
- Objectifs: {goals_str}
- Langue maternelle: {native_language}

PREFERENCES THEMATIQUES:
- Centres d'interet: {interests_str}
- Sujets a EVITER absolument: {avoid_str}
- Style prefere: {style_desc}{geo_str}

HISTORIQUE (a eviter, ne pas repeter):
{past_str}

DOMAINES DE VOCABULAIRE DEJA COUVERTS:
{covered_str}

CONSIGNES STRICTES:
1. Cree un theme NARRATIF coherent sur {days_count} jours avec un FIL ROUGE qui relie chaque jour
2. PAS de themes cliches ("visiter Rome et manger une pizza"). Sois original et ancre dans la realite
3. Integre NATURELLEMENT les centres d'interet de l'apprenant dans le scenario
4. Progression: Jour 1-2 = decouverte/installation, Jour 3-5 = approfondissement/complications, Jour 6-7 = synthese/resolution
5. CHAQUE JOUR doit avoir:
   - Un focus narratif precis (une scene, un evenement)
   - 3 domaines de vocabulaire CONCRETS
   - 2-3 situations cles DETAILLEES (dialogues possibles)
   - 2-3 key_concepts grammaticaux/communicatifs adaptes au niveau {user_level}
   - Un suggested_lego_intent (intention communicative du jour: se_presenter, exprimer_un_souhait, raconter_passe, etc.)
   - Des suggested_fsi_mutations pertinentes pour le contexte du jour
   - Un narrative_link (1 phrase qui relie au fil rouge et contextualise la journee)
6. Adapte la COMPLEXITE au niveau {user_level}

REPONDS EN JSON STRICT (sans markdown, sans commentaires, juste le JSON):
{{
    "main_theme": "Titre evocateur du theme",
    "description": "Contexte narratif en 3-4 phrases: qui est le personnage, ou, pourquoi, quel est l'enjeu de la semaine",
    "daily_breakdown": [
        {{
            "day": 1,
            "focus": "Scene precise du jour",
            "vocab_domains": ["domaine1", "domaine2", "domaine3"],
            "key_situations": ["situation detaillee 1", "situation detaillee 2"],
            "key_concepts": ["concept grammatical 1", "concept communicatif 2"],
            "suggested_lego_intent": "intention_communicative",
            "suggested_fsi_mutations": ["mutation1", "mutation2"],
            "narrative_link": "Phrase de contexte narratif pour ce jour"
        }}
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
        
        # Fill missing days with defaults (including new fields)
        while len(data['daily_breakdown']) < 7:
            day_num = len(data['daily_breakdown']) + 1
            data['daily_breakdown'].append({
                'day': day_num,
                'focus': f'Jour {day_num} - Pratique generale',
                'vocab_domains': ['general'],
                'key_situations': ['conversation quotidienne'],
                'key_concepts': ['vocabulaire courant'],
                'suggested_lego_intent': 'general',
                'suggested_fsi_mutations': ['negation', 'question'],
                'narrative_link': f'Jour {day_num} de la semaine.'
            })
        
        # Ensure each day has the new fields (backward compat)
        for day in data['daily_breakdown']:
            day.setdefault('key_concepts', ['vocabulaire courant'])
            day.setdefault('suggested_lego_intent', 'general')
            day.setdefault('suggested_fsi_mutations', ['negation', 'question'])
            day.setdefault('narrative_link', day.get('focus', ''))
        
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
            {'day': 1, 'focus': 'Salutations et presentations', 'vocab_domains': ['greetings', 'basics'], 'key_situations': ['se presenter'], 'key_concepts': ['pronoms personnels', 'verbe etre'], 'suggested_lego_intent': 'se_presenter', 'suggested_fsi_mutations': ['question', 'negation'], 'narrative_link': 'Premier contact dans un nouveau pays.'},
            {'day': 2, 'focus': 'La vie quotidienne', 'vocab_domains': ['daily_routine', 'time'], 'key_situations': ['raconter sa journee'], 'key_concepts': ['present indicatif', 'adverbes de temps'], 'suggested_lego_intent': 'raconter_habitude', 'suggested_fsi_mutations': ['negation', 'question'], 'narrative_link': 'Ta premiere journee complete.'},
            {'day': 3, 'focus': 'Faire des achats', 'vocab_domains': ['shopping', 'numbers'], 'key_situations': ['au magasin'], 'key_concepts': ['nombres', 'articles partitifs'], 'suggested_lego_intent': 'exprimer_souhait', 'suggested_fsi_mutations': ['plural', 'question'], 'narrative_link': 'Il faut faire les courses.'},
            {'day': 4, 'focus': 'Au restaurant', 'vocab_domains': ['food', 'ordering'], 'key_situations': ['commander un repas'], 'key_concepts': ['conditionnel de politesse', 'articles'], 'suggested_lego_intent': 'exprimer_souhait', 'suggested_fsi_mutations': ['formel', 'conditionnel'], 'narrative_link': 'Decouverte gastronomique.'},
            {'day': 5, 'focus': 'Se deplacer', 'vocab_domains': ['transport', 'directions'], 'key_situations': ['demander son chemin'], 'key_concepts': ['imperatif', 'prepositions de lieu'], 'suggested_lego_intent': 'demander', 'suggested_fsi_mutations': ['question', 'formel'], 'narrative_link': 'Explorer la ville.'},
            {'day': 6, 'focus': 'Loisirs et hobbies', 'vocab_domains': ['hobbies', 'entertainment'], 'key_situations': ['parler de ses passions'], 'key_concepts': ['verbes de gout', 'adverbes de frequence'], 'suggested_lego_intent': 'donner_avis', 'suggested_fsi_mutations': ['negation', 'past'], 'narrative_link': 'Temps libre et decouverte.'},
            {'day': 7, 'focus': 'Revision et consolidation', 'vocab_domains': ['general', 'mixed'], 'key_situations': ['conversation libre'], 'key_concepts': ['revision generale'], 'suggested_lego_intent': 'general', 'suggested_fsi_mutations': ['negation', 'future'], 'narrative_link': 'Bilan de la semaine.'}
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
        'theme_name': weekly_theme.main_theme if weekly_theme else "Session d'entrainement",
        'theme_description': weekly_theme.theme_description if weekly_theme else '',
        'day_focus': day_focus.get('focus', 'Pratique generale'),
        'vocab_domains': day_focus.get('vocab_domains', ['general']),
        'key_situations': day_focus.get('key_situations', []),
        'key_concepts': day_focus.get('key_concepts', []),
        'suggested_lego_intent': day_focus.get('suggested_lego_intent', 'general'),
        'suggested_fsi_mutations': day_focus.get('suggested_fsi_mutations', ['negation', 'question']),
        'narrative_link': day_focus.get('narrative_link', ''),
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
    
    Vocabulary scaling logic:
    - NEW words per day scales with duration: 10min->5, 15min->8, 30min->15, 45min->20, 60min->25
    - MAX total cards (new + review + debt) is capped at 30 to avoid overwhelm
    - Day 1: ~15 new words
    - Day 2: ~15 new + ~5-10 reviews from day 1 = ~20-25
    - Steady state: ~10-15 new + ~15-20 reviews = ~25-30
    
    Other modules:
    - Flashcards: ~30 sec per card (both directions = 2 cards per word)
    - Git Input: ~5-8 min for text + translation
    - Gym: ~3 min per structure (discovery + construction + FSI)
    - Shadowing: ~3 min per segment
    - Git Output: ~5 min
    - Writing: ~8-10 min
    """
    # New words: linear scale with soft cap
    # 10min=5, 15min=8, 20min=10, 30min=15, 45min=20, 60min=25
    new_words = max(5, min(25, int(duration_minutes * 0.5)))
    
    # Max total cards per session (including reviews + debt)
    max_total_cards = 30
    
    # Flashcard time: ~30s per card in each direction (so 1 min per word pair)
    # With max 30 words => ~30 min flashcard time max, but we share with other modules
    flashcard_time = duration_minutes * 0.30
    
    gym_time = duration_minutes * 0.25
    
    return {
        'new_words': new_words,
        'max_total_cards': max_total_cards,
        'flashcard_pairs': min(max_total_cards, max(5, int(flashcard_time * 2))),
        'gym_structures': max(1, int(gym_time / 3)),
        'gym_phrases_per_structure': max(2, int(gym_time / 4)),
        'shadowing_segments': max(1, int(duration_minutes * 0.10 / 3)),
        'writing_words_target': max(30, duration_minutes * 2)
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

"""
Configuration CECR (Cadre Europeen Commun de Reference pour les langues).

Mapping entre niveaux CECR, pillar levels, et seuils de mastery.
Definit les conditions de passage de niveau et la structure des evaluations.

NIVEAUX:
  A1 - Decouverte  : mots isoles, phrases tres simples, se presenter
  A2 - Survie      : phrases courtes, situations quotidiennes, decrire
  B1 - Seuil       : paragraphes, situations imprevues, exprimer son avis
  B2 - Avance      : argumentation, textes complexes, nuances
  C1 - Autonome    : textes longs, subtilites, registres
  C2 - Maitrise    : quasi-natif, textes litteraires, ironie
"""

# =============================================================================
# MAPPING CECR <-> PILLAR LEVELS
# =============================================================================

CECR_PILLAR_MAPPING = {
    'A1': {
        'pillar_levels': [0, 1],
        'label': 'Decouverte',
        'description': 'Mots isoles, phrases tres simples: se presenter, saluer, compter',
        'min_mastery': 60,
        'min_exercises': 10,
        'exam_time_minutes': 15,
        'passing_score': 50,
    },
    'A2': {
        'pillar_levels': [2, 3],
        'label': 'Survie',
        'description': 'Phrases courtes sur le quotidien: achats, transports, repas',
        'min_mastery': 65,
        'min_exercises': 25,
        'exam_time_minutes': 30,
        'passing_score': 55,
    },
    'B1': {
        'pillar_levels': [4, 5],
        'label': 'Seuil',
        'description': 'Paragraphes structures, exprimer son avis, raconter au passe',
        'min_mastery': 70,
        'min_exercises': 50,
        'exam_time_minutes': 50,
        'passing_score': 60,
    },
    'B2': {
        'pillar_levels': [],
        'label': 'Avance',
        'description': 'Argumentation, textes complexes, nuances et expressions idiomatiques',
        'min_mastery': 75,
        'min_exercises': 80,
        'exam_time_minutes': 70,
        'passing_score': 60,
    },
    'C1': {
        'pillar_levels': [],
        'label': 'Autonome',
        'description': 'Textes longs, subtilites, registres formels et informels',
        'min_mastery': 80,
        'min_exercises': 120,
        'exam_time_minutes': 85,
        'passing_score': 65,
    },
    'C2': {
        'pillar_levels': [],
        'label': 'Maitrise',
        'description': 'Comprehension quasi-native, production sophistiquee, ironie et style',
        'min_mastery': 85,
        'min_exercises': 180,
        'exam_time_minutes': 110,
        'passing_score': 70,
    },
}

CECR_ORDER = ['A0', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2']

# =============================================================================
# MAPPING EXERCICE TYPE <-> PILLAR CATEGORY
# =============================================================================

EXERCISE_PILLAR_CATEGORIES = {
    'conjugation': ['grammar'],
    'fill_blank': ['grammar', 'vocabulary'],
    'transform': ['grammar'],
    'word_order': ['grammar'],
    'particles': ['grammar'],
    'gender': ['grammar'],
}

EXERCISE_PILLAR_LEVELS = {
    'conjugation': [3, 4],
    'fill_blank': [2, 3, 4],
    'transform': [2, 4, 5],
    'word_order': [2],
    'particles': [1, 2],
    'gender': [2],
}

# =============================================================================
# STRUCTURE DES SECTIONS D'EXAMEN
# =============================================================================

EXAM_SECTIONS = {
    'grammar': {
        'label': 'Grammaire',
        'icon': 'book',
        'weight': 20,
        'description': 'Conjugaison, transformation, phrases a trous',
    },
    'vocabulary': {
        'label': 'Vocabulaire',
        'icon': 'list',
        'weight': 15,
        'description': 'Definitions, QCM contextuel, associations',
    },
    'reading': {
        'label': 'Comprehension ecrite',
        'icon': 'file-text',
        'weight': 20,
        'description': 'Texte + questions de comprehension',
    },
    'listening': {
        'label': 'Comprehension orale',
        'icon': 'headphones',
        'weight': 20,
        'description': 'Dialogue audio (TTS) + questions',
    },
    'writing': {
        'label': 'Production ecrite',
        'icon': 'edit',
        'weight': 25,
        'description': 'Redaction evaluee par le professeur LLM',
    },
    'dialogue': {
        'label': 'Dialogue interactif',
        'icon': 'message-circle',
        'weight': 20,
        'description': 'Conversation avec un personnage dans la langue cible',
    },
}

# Sections par niveau
EXAM_SECTIONS_BY_LEVEL = {
    'A1': ['grammar', 'vocabulary', 'reading'],
    'A2': ['grammar', 'vocabulary', 'reading', 'listening'],
    'B1': ['grammar', 'vocabulary', 'reading', 'listening', 'writing'],
    'B2': ['grammar', 'vocabulary', 'reading', 'listening', 'writing', 'dialogue'],
    'C1': ['grammar', 'vocabulary', 'reading', 'listening', 'writing', 'dialogue'],
    'C2': ['grammar', 'vocabulary', 'reading', 'listening', 'writing', 'dialogue'],
}

# =============================================================================
# PARAMETRES PAR NIVEAU PAR SECTION
# =============================================================================

# --- Grammaire ---
GRAMMAR_PARAMS = {
    'A1': {
        'questions': 5,
        'types': ['fill_blank'],   # Que du QCM simple
        'guidance': (
            'Niveau DEBUTANT ABSOLU. Seulement present simple, etre/avoir. '
            'Phrases de 3-5 mots maximum. Choix tres evidents avec 1 bonne reponse et 3 clairement fausses. '
            'Ex: "Io ___ Marco" (sono/sei/siamo/siete). '
            'PAS de passe compose, PAS de subjonctif, PAS de transformation.'
        ),
    },
    'A2': {
        'questions': 7,
        'types': ['fill_blank', 'transform'],
        'guidance': (
            'Niveau elementaire. Present + passe compose simples. '
            'Phrases courtes (5-8 mots). Transformations simples (affirmatif -> negatif). '
            'Articles, prepositions basiques, accord adjectif simple.'
        ),
    },
    'B1': {
        'questions': 10,
        'types': ['fill_blank', 'transform', 'conjugation'],
        'guidance': (
            'Niveau intermediaire. Tous les temps courants (present, passe, futur, conditionnel). '
            'Phrases de longueur normale. Transformations variees (temps, voix, negation). '
            'Subordonnees simples, conjonctions.'
        ),
    },
    'B2': {
        'questions': 10,
        'types': ['fill_blank', 'transform', 'conjugation'],
        'guidance': (
            'Niveau avance. Subjonctif, conditionnel passe, concordance des temps. '
            'Phrases complexes avec relatives, concessives. '
            'Nuances grammaticales (subjuntivo vs indicativo, etc).'
        ),
    },
    'C1': {
        'questions': 12,
        'types': ['fill_blank', 'transform', 'conjugation'],
        'guidance': (
            'Niveau superieur. Subtilites grammaticales, registre formel/informel. '
            'Phrases longues et complexes. Nuances idiomatiques. '
            'Constructions rares mais correctes.'
        ),
    },
    'C2': {
        'questions': 12,
        'types': ['fill_blank', 'transform', 'conjugation'],
        'guidance': (
            'Niveau quasi-natif. Toutes les subtilites, registre litteraire, '
            'arcaismes, constructions recherchees. Erreurs subtiles a detecter.'
        ),
    },
}

# --- Vocabulaire ---
VOCABULARY_PARAMS = {
    'A1': {
        'questions': 5,
        'guidance': (
            'Niveau DEBUTANT ABSOLU. Mots tres concrets du quotidien : '
            'salutations (bonjour, merci), famille (mama, papa), couleurs, '
            'chiffres 1-20, nourriture basique (eau, pain, cafe), corps. '
            'QCM avec images/contexte tres simple. 4 choix dont 1 evident.'
        ),
    },
    'A2': {
        'questions': 7,
        'guidance': (
            'Niveau elementaire. Vocabulaire du quotidien : achats, vetements, '
            'transports, meteo, maison, professions. '
            'QCM contextuel avec phrases courtes.'
        ),
    },
    'B1': {
        'questions': 8,
        'guidance': (
            'Niveau intermediaire. Vocabulaire varie : sentiments, opinions, '
            'actualite, sante, voyages, loisirs. Synonymes et antonymes.'
        ),
    },
    'B2': {
        'questions': 10,
        'guidance': (
            'Niveau avance. Expressions idiomatiques, registre, '
            'vocabulaire abstrait (economie, politique, philosophie). '
            'Faux amis, nuances de sens.'
        ),
    },
    'C1': {
        'questions': 10,
        'guidance': (
            'Niveau superieur. Vocabulaire specialise, termes techniques, '
            'registre soutenu, argot, expressions regionales.'
        ),
    },
    'C2': {
        'questions': 12,
        'guidance': (
            'Niveau quasi-natif. Proverbes, jeux de mots, double sens, '
            'vocabulaire litteraire, termes rares.'
        ),
    },
}

# --- Comprehension ecrite ---
READING_PARAMS = {
    'A1': {
        'min_words': 30, 'max_words': 50, 'questions': 3,
        'guidance': (
            'Texte TRES court et simple : une carte postale, un SMS, '
            'un panneau, un petit menu. Phrases de 4-6 mots. '
            'Vocabulaire de base uniquement. '
            'Questions en francais, reponses simples (vrai/faux, QCM facile).'
        ),
    },
    'A2': {
        'min_words': 80, 'max_words': 120, 'questions': 4,
        'guidance': (
            'Texte court : email simple, petite annonce, recette courte, '
            'horaires de train. Phrases courtes et directes. '
            'Questions en francais, QCM et vrai/faux.'
        ),
    },
    'B1': {
        'min_words': 180, 'max_words': 280, 'questions': 6,
        'guidance': (
            'Texte de longueur moyenne : article de blog, lettre, '
            'description d\'un evenement. Quelques phrases complexes. '
            'Questions variees : QCM, vrai/faux, reponse courte.'
        ),
    },
    'B2': {
        'min_words': 280, 'max_words': 420, 'questions': 8,
        'guidance': (
            'Texte substantiel : article d\'opinion, critique, reportage. '
            'Argumentation et nuances. '
            'Questions demandant de la deduction et comprehension implicite.'
        ),
    },
    'C1': {
        'min_words': 380, 'max_words': 550, 'questions': 8,
        'guidance': (
            'Texte long et complexe : editorial, texte academique, '
            'extrait litteraire. Registre soutenu. '
            'Questions d\'inference, de style, d\'intention de l\'auteur.'
        ),
    },
    'C2': {
        'min_words': 480, 'max_words': 750, 'questions': 10,
        'guidance': (
            'Texte tres complexe : essai, critique litteraire, texte technique. '
            'Subtilites, ironie, double lecture possible. '
            'Questions tres fines sur le style et l\'argumentation.'
        ),
    },
}

# --- Comprehension orale ---
LISTENING_PARAMS = {
    'A2': {
        'exchanges': 3, 'max_listens': 3, 'questions': 3,
        'guidance': (
            'Dialogue COURT et LENT entre 2 personnes. '
            'Phrases courtes et repetitives. Theme simple : '
            'commander au restaurant, demander son chemin, acheter un billet. '
            'Questions faciles en francais.'
        ),
    },
    'B1': {
        'exchanges': 5, 'max_listens': 3, 'questions': 5,
        'guidance': (
            'Dialogue de longueur moyenne a debit normal. '
            'Themes: rendez-vous, reservation, discussion entre amis. '
            'Questions variees en francais.'
        ),
    },
    'B2': {
        'exchanges': 7, 'max_listens': 2, 'questions': 6,
        'guidance': (
            'Dialogue naturel a debit normal/rapide. '
            'Quelques expressions idiomatiques. '
            'Theme: debat, recit, negociation. '
            'Questions demandant comprehension implicite.'
        ),
    },
    'C1': {
        'exchanges': 8, 'max_listens': 2, 'questions': 8,
        'guidance': (
            'Dialogue rapide et naturel avec hesitations, interruptions. '
            'Registre varie. Theme : debat d\'actualite, interview. '
            'Questions fines.'
        ),
    },
    'C2': {
        'exchanges': 10, 'max_listens': 1, 'questions': 10,
        'guidance': (
            'Dialogue quasi-natif avec argot, ironie, references culturelles. '
            'Theme : conference, debat anime, humour. '
            'Questions tres detaillees.'
        ),
    },
}

# --- Production ecrite ---
WRITING_PARAMS = {
    'B1': {
        'min_words': 60, 'max_words': 100, 'prompts': 1,
        'guidance': (
            'Sujet simple et concret : raconter ses vacances, decrire sa ville, '
            'ecrire un email a un ami. Evaluation souple sur la grammaire.'
        ),
    },
    'B2': {
        'min_words': 120, 'max_words': 180, 'prompts': 1,
        'guidance': (
            'Sujet avec argumentation : donner son avis sur un sujet, '
            'ecrire une lettre formelle, raconter une experience. '
            'Evaluation sur la structure et les nuances.'
        ),
    },
    'C1': {
        'min_words': 150, 'max_words': 250, 'prompts': 1,
        'guidance': (
            'Sujet complexe : essai argumentatif, analyse d\'une situation, '
            'critique. Evaluation sur le style et la precision.'
        ),
    },
    'C2': {
        'min_words': 200, 'max_words': 350, 'prompts': 1,
        'guidance': (
            'Sujet exigeant : texte d\'opinion nuance, pastiche, '
            'argumentation sophistiquee. Evaluation quasi-native.'
        ),
    },
}

# =============================================================================
# MASTERY - CALCUL AUTOMATIQUE
# =============================================================================

MASTERY_POINTS = {
    1: 2,
    2: 3,
    3: 5,
    4: 7,
    5: 10,
}

MASTERY_PENALTY = {
    1: -1,
    2: -1,
    3: -2,
    4: -2,
    5: -3,
}

MASTERY_THRESHOLDS = {
    'suggest_complete': 80,
    'auto_complete': 95,
    'ready_for_exam': 70,
}


# =============================================================================
# HELPERS
# =============================================================================

def get_next_level(current_level):
    """Return the next CECR level, or None if already at max."""
    try:
        idx = CECR_ORDER.index(current_level)
        if idx < len(CECR_ORDER) - 1:
            return CECR_ORDER[idx + 1]
    except ValueError:
        pass
    return None


def get_level_config(level):
    """Get configuration for a specific CECR level."""
    return CECR_PILLAR_MAPPING.get(level)


def get_required_pillars_for_level(lang_config, target_level):
    """
    Get the list of pillar IDs required to reach a target CECR level.
    Accumulates all levels up to and including target.
    """
    required = []
    pillars = lang_config.get('pillars', [])
    target_idx = CECR_ORDER.index(target_level) if target_level in CECR_ORDER else 0

    needed_levels = set()
    for level_name in CECR_ORDER[1:target_idx + 1]:
        config = CECR_PILLAR_MAPPING.get(level_name, {})
        needed_levels.update(config.get('pillar_levels', []))

    for p in pillars:
        if p.get('level') in needed_levels:
            required.append(p['id'])

    return required


def check_level_readiness(user_language, lang_config, target_level):
    """
    Check if a user is ready to take the exam for a target level.
    Returns dict with 'ready' bool and details.
    """
    config = CECR_PILLAR_MAPPING.get(target_level)
    if not config:
        return {'ready': False, 'reason': 'Niveau invalide'}

    required_pillars = get_required_pillars_for_level(lang_config, target_level)
    progress = user_language.pillar_progress or {}

    completed = 0
    total_mastery = 0
    for pid in required_pillars:
        p = progress.get(pid, {})
        if isinstance(p, dict) and p.get('status') == 'completed':
            completed += 1
            total_mastery += p.get('mastery', 0)

    total_required = len(required_pillars)
    avg_mastery = total_mastery / total_required if total_required > 0 else 0

    pillars_ok = completed >= total_required if total_required > 0 else True
    mastery_ok = avg_mastery >= config['min_mastery'] if total_required > 0 else True

    return {
        'ready': pillars_ok and mastery_ok,
        'pillars_completed': completed,
        'pillars_required': total_required,
        'avg_mastery': round(avg_mastery),
        'min_mastery': config['min_mastery'],
        'pillars_ok': pillars_ok,
        'mastery_ok': mastery_ok,
        'exam_time_minutes': config['exam_time_minutes'],
        'passing_score': config['passing_score'],
    }


def get_exercise_types_for_pillar(pillar_config):
    """
    Reverse mapping: given a pillar config dict (with 'category' and 'level'),
    return list of exercise type IDs that reinforce this pillar.
    """
    cat = pillar_config.get('category', '')
    lvl = pillar_config.get('level', -1)

    matching = []
    for ex_type, categories in EXERCISE_PILLAR_CATEGORIES.items():
        if cat in categories:
            levels = EXERCISE_PILLAR_LEVELS.get(ex_type, [])
            if lvl in levels:
                matching.append(ex_type)
    return matching


def get_pillars_for_exercise_type(lang_config, exercise_type):
    """
    Get the list of pillar IDs that are reinforced by a given exercise type.
    """
    categories = EXERCISE_PILLAR_CATEGORIES.get(exercise_type, [])
    levels = EXERCISE_PILLAR_LEVELS.get(exercise_type, [])

    matching = []
    for p in lang_config.get('pillars', []):
        if p.get('category') in categories and p.get('level') in levels:
            matching.append(p['id'])

    return matching

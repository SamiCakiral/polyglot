"""
Generation d'examens CECR via LLM.

Genere un examen complet avec sections (grammaire, vocabulaire, lecture,
ecoute, ecriture, dialogue) adapte au niveau CECR cible et a la langue.

Les parametres de difficulte et le nombre de questions par section
sont definis dans cecr_config.py (GRAMMAR_PARAMS, VOCABULARY_PARAMS, etc.)

Fonctionnalites:
- Diversite forcee: instructions explicites pour varier vocabulaire/themes
- Profil utilisateur: langue maternelle, faiblesses, objectifs injectes
"""
import json
from datetime import datetime
from app import db
from app.models import Assessment, AssessmentSection
from app.llm_service import call_llm
from app.cecr_config import (
    CECR_PILLAR_MAPPING, EXAM_SECTIONS, EXAM_SECTIONS_BY_LEVEL,
    GRAMMAR_PARAMS, VOCABULARY_PARAMS, READING_PARAMS,
    LISTENING_PARAMS, WRITING_PARAMS,
)

LANG_NAMES = {
    'it': 'italien', 'es': 'espagnol', 'fr': 'francais',
    'de': 'allemand', 'ja': 'japonais', 'ru': 'russe',
    'pt': 'portugais', 'zh': 'chinois', 'ko': 'coreen', 'tr': 'turc',
}


def _build_user_context_prompt(user_context):
    """
    Construit un bloc d'instructions basé sur le profil utilisateur
    pour personnaliser la génération d'examen.
    """
    if not user_context:
        return ''

    parts = []

    native = user_context.get('native_language')
    if native:
        native_names = {
            'fr': 'français', 'en': 'anglais', 'es': 'espagnol',
            'de': 'allemand', 'it': 'italien', 'pt': 'portugais',
            'ar': 'arabe', 'ru': 'russe', 'zh': 'chinois',
            'ja': 'japonais', 'ko': 'coréen',
        }
        parts.append(f"L'apprenant parle {native_names.get(native, native)} comme langue maternelle.")

    known = user_context.get('known_languages', [])
    if known:
        known_str = ', '.join(
            f"{k.get('code', '?')} ({k.get('level', '?')})"
            for k in known if isinstance(k, dict)
        )
        if known_str:
            parts.append(f"Langues connues: {known_str}.")

    goals = user_context.get('goals', [])
    if goals:
        goals_map = {
            'conversation': 'conversation courante', 'travel': 'voyage',
            'work': 'contexte professionnel', 'exams': 'examens officiels',
            'culture': 'culture/littérature', 'family': 'contexte familial',
        }
        goals_fr = [goals_map.get(g, g) for g in goals]
        parts.append(f"Objectifs: {', '.join(goals_fr)}. Adapte les thèmes/sujets en conséquence.")

    weakness = user_context.get('weakness_profile', {})
    if weakness:
        by_type = weakness.get('by_type', {})
        weak_areas = []
        for t, stats in by_type.items():
            total = stats.get('total', 0)
            if total >= 5:
                rate = stats.get('correct', 0) / total
                if rate < 0.6:
                    weak_areas.append(f"{t} ({int(rate*100)}%)")
        if weak_areas:
            parts.append(f"Points faibles détectés: {', '.join(weak_areas)}.")

    if not parts:
        return ''
    return '\nCONTEXTE APPRENANT: ' + ' '.join(parts)


def _extract_json(text):
    """Extract JSON from LLM response."""
    if not text or not text.strip():
        return None
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def create_assessment(user_id, language_code, target_level, user_context=None):
    """
    Create a new assessment with all sections generated via LLM.
    Returns the Assessment object or None on failure.
    
    user_context (dict, optional): Contexte utilisateur pour personnaliser:
        - native_language, known_languages, goals, weakness_profile
    """
    config = CECR_PILLAR_MAPPING.get(target_level)
    if not config:
        return None

    lang_name = LANG_NAMES.get(language_code, language_code)
    section_types = EXAM_SECTIONS_BY_LEVEL.get(target_level, ['grammar', 'vocabulary', 'reading'])

    assessment = Assessment(
        user_id=user_id,
        language_code=language_code,
        target_level=target_level,
        status='in_progress',
        passing_score=config['passing_score'],
        time_limit_minutes=config['exam_time_minutes'],
        started_at=datetime.utcnow(),
    )
    db.session.add(assessment)
    db.session.flush()

    for idx, section_type in enumerate(section_types):
        section_config = EXAM_SECTIONS.get(section_type, {})
        max_points = section_config.get('weight', 20)

        content = _generate_section_content(
            section_type, language_code, lang_name, target_level, user_context
        )

        section = AssessmentSection(
            assessment_id=assessment.id,
            section_type=section_type,
            order_idx=idx,
            content=content,
            max_points=max_points,
        )
        db.session.add(section)

    db.session.commit()
    return assessment


def _generate_section_content(section_type, lang_code, lang_name, target_level, user_context=None):
    """Generate content for a specific section via LLM."""
    generators = {
        'grammar': _generate_grammar,
        'vocabulary': _generate_vocabulary,
        'reading': _generate_reading,
        'listening': _generate_listening,
        'writing': _generate_writing,
        'dialogue': _generate_dialogue_scenario,
    }
    gen = generators.get(section_type)
    if gen:
        return gen(lang_code, lang_name, target_level, user_context)
    return {'questions': []}


# =============================================================================
# GRAMMAR
# =============================================================================

def _generate_grammar(lang_code, lang_name, target_level, user_context=None):
    """Generate grammar section calibrated to level."""
    params = GRAMMAR_PARAMS.get(target_level, GRAMMAR_PARAMS['A1'])
    n = params['questions']
    types = params['types']
    guidance = params['guidance']
    ctx_prompt = _build_user_context_prompt(user_context)

    types_str = ', '.join(f'"{t}"' for t in types)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu generes des questions d'examen de grammaire au format JSON strict. "
        f"IMPORTANT: {guidance} "
        f"DIVERSITÉ: Chaque question DOIT utiliser un verbe/structure grammaticale DIFFÉRENT(e). "
        f"Varie les thèmes: famille, travail, nourriture, voyage, loisirs, etc. "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Genere exactement {n} questions de grammaire en {lang_name} pour un examen de niveau {target_level}.
RÈGLE ABSOLUE: Chaque question utilise un verbe/mot DIFFÉRENT. AUCUNE répétition.

Types autorises: {types_str}
- "fill_blank": phrase avec ___ a completer, TOUJOURS avec 4 options (QCM)
- "transform": transformer une phrase (negation, question, temps) - reponse libre
- "conjugation": conjuguer un verbe pour un pronom/temps donne - reponse libre

RAPPEL DE NIVEAU: {guidance}

Chaque question:
- "type": un des types autorises
- "question": l'enonce en {lang_name} (ou mixte francais/{lang_name})
- "options": liste de 4 choix (pour fill_blank), null sinon
- "answer": la bonne reponse
- "explanation": courte explication en francais

Format JSON:
{{"questions": [...]}}"""

    response = call_llm(system, user, temperature=0.6, timeout=60)
    data = _extract_json(response) if response else None
    if data and 'questions' in data:
        return data
    return {'questions': []}


# =============================================================================
# VOCABULARY
# =============================================================================

def _generate_vocabulary(lang_code, lang_name, target_level, user_context=None):
    """Generate vocabulary section calibrated to level."""
    params = VOCABULARY_PARAMS.get(target_level, VOCABULARY_PARAMS['A1'])
    n = params['questions']
    guidance = params['guidance']
    ctx_prompt = _build_user_context_prompt(user_context)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu generes des questions de vocabulaire au format JSON strict. "
        f"IMPORTANT: {guidance} "
        f"DIVERSITÉ: Chaque question porte sur un THÈME DIFFÉRENT (nourriture, couleurs, famille, "
        f"nombres, animaux, vêtements, corps, maison, transports, salutations, métiers, etc.). "
        f"NE JAMAIS répéter le même mot ou la même famille de mots. "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Genere exactement {n} questions de vocabulaire en {lang_name} pour le niveau {target_level}.
RÈGLE ABSOLUE: Chaque question porte sur un mot/thème DIFFÉRENT. Aucune répétition.

Types de questions:
- "definition": quel mot correspond a cette definition ?
- "context": quel mot complete cette phrase ? (QCM)
- "synonym": quel est le synonyme/antonyme ?

RAPPEL DE NIVEAU: {guidance}

Chaque question a TOUJOURS 4 options (QCM).

Chaque question:
- "type": "definition" | "context" | "synonym"
- "question": l'enonce
- "options": liste de 4 choix
- "answer": la bonne reponse
- "explanation": courte explication en francais

Format JSON:
{{"questions": [...]}}"""

    response = call_llm(system, user, temperature=0.6, timeout=60)
    data = _extract_json(response) if response else None
    if data and 'questions' in data:
        return data
    return {'questions': []}


# =============================================================================
# READING COMPREHENSION
# =============================================================================

def _generate_reading(lang_code, lang_name, target_level, user_context=None):
    """Generate reading comprehension calibrated to level."""
    params = READING_PARAMS.get(target_level, READING_PARAMS['A1'])
    guidance = params.get('guidance', '')
    ctx_prompt = _build_user_context_prompt(user_context)

    # Choisir un thème aléatoire pour forcer la diversité
    import random
    themes = [
        'la vie quotidienne', 'un voyage', 'la nourriture et la cuisine',
        'le travail et les métiers', 'la famille', 'les loisirs et le sport',
        'la nature et les animaux', 'la ville et les transports',
        'les fêtes et traditions', 'les courses et le shopping',
        'la santé', 'l\'école et les études', 'la technologie',
        'une rencontre amicale', 'un événement culturel',
    ]
    chosen_theme = random.choice(themes)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu generes un exercice de comprehension ecrite au format JSON strict. "
        f"IMPORTANT: {guidance} "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Genere un exercice de comprehension ecrite en {lang_name} pour le niveau {target_level}.

THÈME IMPOSÉ: {chosen_theme}. Le texte DOIT parler de ce thème.

1. Ecris un texte en {lang_name} de {params['min_words']} a {params['max_words']} mots.
   {guidance}

2. Ecris {params['questions']} questions sur le texte.
   Privilegier les QCM (plus facile a corriger). Vrai/faux accepte aussi.
   Reponses courtes seulement si niveau >= B1.
   Les questions doivent etre en FRANCAIS.

IMPORTANT pour le grading:
- Pour les vrai/faux: "answer" doit etre true ou false (boolean JSON)
- Pour les QCM: "answer" doit etre le TEXTE EXACT de la bonne option (pas juste "A" ou "B")
- Pour les reponses courtes: "answer" doit etre la reponse attendue

Format JSON:
{{"text": "Le texte en {lang_name}...",
  "text_translation": "Traduction en francais du texte",
  "questions": [
    {{"type": "true_false", "question": "Affirmation...", "answer": true, "explanation": "..."}},
    {{"type": "mcq", "question": "Question ?", "options": ["opt A", "opt B", "opt C", "opt D"], "answer": "opt B", "explanation": "..."}},
    {{"type": "short_answer", "question": "Question ?", "answer": "Reponse", "explanation": "..."}}
  ]
}}"""

    response = call_llm(system, user, temperature=0.6, timeout=90)
    data = _extract_json(response) if response else None
    if data and 'text' in data:
        return data
    return {'text': '', 'questions': []}


# =============================================================================
# LISTENING COMPREHENSION
# =============================================================================

def _generate_listening(lang_code, lang_name, target_level, user_context=None):
    """Generate listening comprehension calibrated to level."""
    params = LISTENING_PARAMS.get(target_level, {'exchanges': 3, 'max_listens': 3, 'questions': 3})
    guidance = params.get('guidance', '')
    ctx_prompt = _build_user_context_prompt(user_context)

    # Situation aléatoire pour forcer la diversité
    import random
    situations = [
        'au restaurant', 'dans un magasin', 'à la gare',
        'au téléphone', 'chez le médecin', 'à l\'hôtel',
        'dans la rue (demander son chemin)', 'au marché',
        'entre amis au café', 'au bureau', 'à l\'aéroport',
        'chez des voisins', 'lors d\'une fête', 'au supermarché',
    ]
    chosen_situation = random.choice(situations)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu generes un exercice de comprehension orale au format JSON strict. "
        f"Le dialogue sera lu par un TTS, ecris des phrases naturelles et claires. "
        f"IMPORTANT: {guidance} "
        f"Utilise un vocabulaire VARIÉ et des expressions idiomatiques adaptées au niveau. "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Genere un exercice de comprehension orale en {lang_name} pour le niveau {target_level}.

SITUATION IMPOSÉE: {chosen_situation}. Le dialogue DOIT se passer dans ce contexte.

1. Ecris un dialogue entre 2 personnes ({params['exchanges']} echanges).
   {guidance}
   Utilise des prénoms typiques de la culture {lang_name}.

2. Ecris {params['questions']} questions QCM sur le dialogue.
   Les questions doivent etre en FRANCAIS.
   Chaque question a 4 options. "answer" = le TEXTE EXACT de la bonne option.

Format JSON:
{{"dialogue": [
    {{"speaker": "A", "name": "Prenom1", "text": "Phrase en {lang_name}"}},
    {{"speaker": "B", "name": "Prenom2", "text": "Reponse en {lang_name}"}}
  ],
  "dialogue_translation": "Traduction complete en francais",
  "context": "Description courte de la situation",
  "max_listens": {params['max_listens']},
  "questions": [
    {{"question": "Question en francais ?", "options": ["opt A", "opt B", "opt C", "opt D"], "answer": "opt B", "explanation": "..."}}
  ]
}}"""

    response = call_llm(system, user, temperature=0.7, timeout=90)
    data = _extract_json(response) if response else None
    if data and 'dialogue' in data:
        return data
    return {'dialogue': [], 'questions': []}


# =============================================================================
# WRITING
# =============================================================================

def _generate_writing(lang_code, lang_name, target_level, user_context=None):
    """Generate writing prompts calibrated to level."""
    params = WRITING_PARAMS.get(target_level, {'min_words': 60, 'max_words': 100, 'prompts': 1})
    guidance = params.get('guidance', '')
    ctx_prompt = _build_user_context_prompt(user_context)

    # Thème aléatoire pour diversité
    import random
    writing_themes = [
        'écrire un email à un ami', 'décrire sa journée typique',
        'raconter un souvenir de vacances', 'se présenter pour un travail',
        'décrire sa famille', 'parler de ses loisirs préférés',
        'donner son avis sur un film/livre', 'décrire sa ville/quartier',
        'écrire une carte postale', 'raconter une anecdote amusante',
        'parler de ses projets futurs', 'décrire un plat favori',
    ]
    chosen_theme = random.choice(writing_themes)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu generes des sujets de production ecrite au format JSON strict. "
        f"IMPORTANT: {guidance} "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Genere {params['prompts']} sujet(s) de production ecrite en {lang_name} pour le niveau {target_level}.

THÈME SUGGÉRÉ: {chosen_theme}

{guidance}

Chaque sujet:
- Consigne claire en francais
- Longueur: {params['min_words']}-{params['max_words']} mots
- Criteres d'evaluation adaptes au niveau

Format JSON:
{{"prompts": [
    {{"prompt": "Consigne en francais",
     "context": "Contexte supplementaire",
     "min_words": {params['min_words']},
     "max_words": {params['max_words']},
     "criteria": ["grammaire", "vocabulaire", "coherence", "longueur"]
    }}
]}}"""

    response = call_llm(system, user, temperature=0.7, timeout=60)
    data = _extract_json(response) if response else None
    if data and 'prompts' in data:
        return data
    return {'prompts': []}


# =============================================================================
# DIALOGUE
# =============================================================================

def _generate_dialogue_scenario(lang_code, lang_name, target_level, user_context=None):
    """Generate an interactive dialogue scenario."""
    ctx_prompt = _build_user_context_prompt(user_context)

    # Rôle et situation aléatoires pour diversité
    import random
    scenarios = [
        ('serveur/serveuse', 'au restaurant, commande d\'un repas'),
        ('vendeur/vendeuse', 'dans un magasin de vêtements'),
        ('réceptionniste', 'à l\'accueil d\'un hôtel'),
        ('collègue', 'premier jour au bureau'),
        ('voisin/voisine', 'nouvelle rencontre dans l\'immeuble'),
        ('guide touristique', 'visite d\'un monument'),
        ('médecin', 'consultation pour un rhume'),
        ('employé(e) de gare', 'achat d\'un billet de train'),
        ('boulanger/boulangère', 'achat de pain et viennoiseries'),
        ('ami(e)', 'organiser une sortie le weekend'),
        ('professeur', 'inscription à un cours'),
        ('pharmacien(ne)', 'demande de médicaments'),
    ]
    chosen = random.choice(scenarios)

    system = (
        f"Tu es un examinateur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu crees un scenario de dialogue interactif au format JSON strict. "
        f"Utilise un vocabulaire riche et varié adapté au niveau. "
        f"Les prénoms doivent être typiques de la culture {lang_name}. "
        f"{ctx_prompt} "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Cree un scenario de dialogue interactif en {lang_name} pour le niveau {target_level}.

SCÉNARIO IMPOSÉ: Le personnage est un(e) {chosen[0]}, situation: {chosen[1]}.

Le scenario doit:
- Definir un personnage avec un prénom typique de la culture {lang_name}
- Donner le contexte de la situation
- Fournir la premiere replique du personnage (en {lang_name})
- Definir 6-8 objectifs pour l'apprenant

Format JSON:
{{"character": {{
    "name": "Nom",
    "role": "Role du personnage",
    "personality": "Personnalite"
  }},
  "context": "Description de la situation",
  "first_message": "Premiere replique en {lang_name}",
  "objectives": ["objectif 1", "objectif 2", "..."],
  "expected_exchanges": 8,
  "evaluation_criteria": ["pertinence", "grammaire", "vocabulaire", "naturel"]
}}"""

    response = call_llm(system, user, temperature=0.7, timeout=60)
    data = _extract_json(response) if response else None
    if data and 'character' in data:
        data['messages'] = []
        return data
    return {
        'character': {'name': 'Interlocuteur', 'role': 'Personnage', 'personality': 'Normal'},
        'context': 'Situation de la vie courante.',
        'first_message': 'Bonjour !',
        'objectives': [],
        'expected_exchanges': 6,
        'messages': [],
    }


# =============================================================================
# GRADING
# =============================================================================

def grade_dialogue(language_code, target_level, scenario, messages):
    """Grade an interactive dialogue section."""
    lang_name = LANG_NAMES.get(language_code, language_code)
    objectives = scenario.get('objectives', [])

    system = (
        f"Tu es un correcteur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu evalues une performance de dialogue interactif. "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    conversation_text = '\n'.join([
        f"{'Apprenant' if m.get('role') == 'user' else m.get('name', 'Personnage')}: {m.get('text', '')}"
        for m in messages
    ])

    user = f"""Evalue ce dialogue d'un apprenant en {lang_name} (niveau {target_level}).

Contexte: {scenario.get('context', '')}
Personnage: {scenario.get('character', {}).get('name', '')} ({scenario.get('character', {}).get('role', '')})

Objectifs:
{chr(10).join(f'- {o}' for o in objectives)}

Dialogue:
{conversation_text}

Evalue sur 4 criteres (chacun sur 25):
1. Pertinence  2. Grammaire  3. Vocabulaire  4. Naturel

Format JSON:
{{"scores": {{"pertinence": 0-25, "grammaire": 0-25, "vocabulaire": 0-25, "naturel": 0-25}},
  "total": 0-100,
  "objectives_met": ["..."],
  "objectives_missed": ["..."],
  "corrections": [{{"original": "...", "corrected": "...", "explanation": "..."}}],
  "comment": "Commentaire bienveillant"
}}"""

    response = call_llm(system, user, temperature=0.3, timeout=90)
    data = _extract_json(response) if response else None
    if data and 'total' in data:
        return data
    return {'total': 0, 'comment': 'Evaluation impossible.'}


def grade_writing(language_code, target_level, prompt_text, user_text):
    """Grade a writing section using LLM analysis."""
    lang_name = LANG_NAMES.get(language_code, language_code)

    system = (
        f"Tu es un correcteur expert en {lang_name} (niveau CECR {target_level}). "
        f"Tu evalues une production ecrite d'un apprenant. "
        f"Sois adapte au niveau : un A1 n'a pas besoin de phrases complexes. "
        f"Reponds UNIQUEMENT avec un objet JSON valide."
    )

    user = f"""Evalue cette production ecrite d'un apprenant en {lang_name} (niveau {target_level}).

Sujet: {prompt_text}

Texte:
\"\"\"{user_text}\"\"\"

Evalue sur 4 criteres (chacun sur 25):
1. Grammaire  2. Vocabulaire  3. Coherence  4. Adequation (respect consigne)

IMPORTANT: Adapte ton evaluation au niveau {target_level}. Un B1 n'a pas besoin d'etre parfait.

Format JSON:
{{"scores": {{"grammar": 0-25, "vocabulary": 0-25, "coherence": 0-25, "adequation": 0-25}},
  "total": 0-100,
  "corrections": [{{"original": "...", "corrected": "...", "explanation": "..."}}],
  "comment": "Commentaire bienveillant",
  "strengths": ["..."],
  "weaknesses": ["..."]
}}"""

    response = call_llm(system, user, temperature=0.3, timeout=90)
    data = _extract_json(response) if response else None
    if data and 'total' in data:
        return data
    return {'total': 0, 'comment': 'Evaluation impossible.'}


def grade_section(section, user_answers):
    """
    Grade a section based on user answers.
    Returns (earned_points, feedback).
    """
    content = section.content or {}
    questions = content.get('questions', [])
    section_type = section.section_type

    # Dialogue - graded by LLM
    if section_type == 'dialogue':
        messages = user_answers.get('messages', []) if isinstance(user_answers, dict) else []
        if messages:
            result = grade_dialogue(
                section.assessment.language_code,
                section.assessment.target_level,
                content, messages
            )
            score_pct = result.get('total', 0) / 100
            earned = round(section.max_points * score_pct)
            return earned, result
        return 0, {'comment': 'Pas de dialogue soumis.'}

    # Writing - graded by LLM
    if section_type == 'writing':
        prompts = content.get('prompts', [])
        if prompts and user_answers:
            prompt_text = prompts[0].get('prompt', '')
            user_text = user_answers.get('text', '') if isinstance(user_answers, dict) else str(user_answers)
            result = grade_writing(
                section.assessment.language_code,
                section.assessment.target_level,
                prompt_text, user_text
            )
            score_pct = result.get('total', 0) / 100
            earned = round(section.max_points * score_pct)
            return earned, result
        return 0, {'comment': 'Pas de texte soumis.'}

    # Other sections (grammar, vocabulary, reading, listening)
    if not questions or not user_answers:
        return 0, {'details': []}

    answers_list = user_answers if isinstance(user_answers, list) else []
    correct_count = 0
    details = []

    import re
    
    def _norm_strict(s):
        """Strip punctuation, lowercase, collapse whitespace."""
        if s is None:
            return ''
        s = str(s).lower().strip()
        s = re.sub(r'[^\w\s]', '', s)
        return ' '.join(s.split())
    
    def _levenshtein_local(s1, s2):
        if len(s1) < len(s2):
            return _levenshtein_local(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[-1]
    
    for i, q in enumerate(questions):
        user_ans = answers_list[i] if i < len(answers_list) else None
        expected = q.get('answer')

        if q.get('type') == 'true_false':
            is_correct = (user_ans is True and expected is True) or (user_ans is False and expected is False)
        else:
            nu = _norm_strict(user_ans)
            ne = _norm_strict(expected)
            if nu == ne:
                is_correct = True
            else:
                # Fuzzy: tolerate 1-2 char difference or <10% for longer answers
                dist = _levenshtein_local(nu, ne)
                max_dist = max(2, len(ne) // 10)
                is_correct = dist <= max_dist

        if is_correct:
            correct_count += 1

        details.append({
            'question_idx': i,
            'correct': is_correct,
            'user_answer': user_ans,
            'expected': expected,
            'explanation': q.get('explanation', ''),
        })

    points_per_q = section.max_points / len(questions) if questions else 0
    earned = round(correct_count * points_per_q)

    return earned, {'details': details, 'correct_count': correct_count, 'total_questions': len(questions)}

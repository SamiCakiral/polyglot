"""
Génération d'exercices piliers via LLM: batch par type, déduplication, stockage en DB.

Fonctionnalités:
- Diversité forcée: les verbes/mots récemment utilisés sont exclus des prompts
- Profil utilisateur: faiblesses, langue maternelle, objectifs, injectés dans les prompts
- Listes de verbes variées: utilise exercise_config pour proposer des verbes diversifiés
"""
import json
import random
import uuid
from app import db
from app.models import PillarExercise, PillarExerciseResult
from app.llm_service import call_llm
from app.exercise_config import (
    get_pronouns,
    get_irregular_verbs,
    get_tenses,
    PRONOUNS_BY_LANG,
    IRREGULAR_VERBS,
)

# Noms de langues pour les prompts
LANG_NAMES = {
    'it': 'italien',
    'es': 'espagnol',
    'fr': 'français',
    'de': 'allemand',
    'ja': 'japonais',
    'ru': 'russe',
    'pt': 'portugais',
    'zh': 'chinois',
    'ko': 'coréen',
    'tr': 'turc',
}


def _get_recently_used_words(language_code, exercise_type, limit=30):
    """
    Récupère les verbes/mots utilisés dans les exercices récents
    pour éviter les répétitions.
    """
    recent = PillarExercise.query.filter_by(
        language_code=language_code,
        exercise_type=exercise_type,
    ).order_by(PillarExercise.id.desc()).limit(limit).all()

    words = set()
    for ex in recent:
        c = ex.content or {}
        if exercise_type == 'conjugation':
            words.add(c.get('verb', '').lower())
        elif exercise_type == 'fill_blank':
            if c.get('hint_verb'):
                words.add(c['hint_verb'].lower())
        elif exercise_type == 'gender':
            words.add(c.get('word', '').lower())
        elif exercise_type == 'word_order':
            words.add(c.get('answer', '').lower())
        elif exercise_type == 'transform':
            words.add(c.get('original', '').lower()[:30])

    words.discard('')
    return list(words)


def _get_suggested_verbs(lang_code, count=8, exclude=None):
    """
    Sélectionne aléatoirement des verbes de la liste exercise_config
    en excluant ceux déjà utilisés récemment.
    """
    all_verbs = IRREGULAR_VERBS.get(lang_code, {})
    if not all_verbs:
        return []

    exclude_set = {v.lower() for v in (exclude or [])}
    available = []
    for verb, info in all_verbs.items():
        if verb.lower() not in exclude_set:
            available.append(f"{verb} ({info.get('meaning', '')})")

    random.shuffle(available)
    return available[:count]


def _build_diversity_instruction(lang_code, exercise_type, user_context=None):
    """
    Construit un bloc d'instruction pour forcer la diversité dans les prompts LLM.
    Inclut: verbes à éviter, verbes suggérés, profil utilisateur.
    """
    parts = []

    # --- Mots/verbes récemment utilisés ---
    recently_used = _get_recently_used_words(lang_code, exercise_type)
    if recently_used:
        sample = recently_used[:15]
        parts.append(
            f"DIVERSITÉ OBLIGATOIRE: NE PAS utiliser ces verbes/mots déjà vus récemment: "
            f"{', '.join(sample)}. Utilise des verbes DIFFÉRENTS et variés."
        )

    # --- Verbes suggérés (conjugation / fill_blank) ---
    if exercise_type in ('conjugation', 'fill_blank'):
        suggested = _get_suggested_verbs(lang_code, count=10, exclude=recently_used)
        if suggested:
            parts.append(
                f"Verbes suggérés (utilise-en plusieurs): {', '.join(suggested)}."
            )

    # --- Profil utilisateur ---
    if user_context:
        # Langue maternelle
        native = user_context.get('native_language')
        if native:
            native_names = {
                'fr': 'français', 'en': 'anglais', 'es': 'espagnol',
                'de': 'allemand', 'it': 'italien', 'pt': 'portugais',
                'ar': 'arabe', 'ru': 'russe', 'zh': 'chinois',
                'ja': 'japonais', 'ko': 'coréen',
            }
            native_name = native_names.get(native, native)
            parts.append(f"L'apprenant est francophone (langue maternelle: {native_name}).")

        # Langues connues
        known = user_context.get('known_languages', [])
        if known:
            known_str = ', '.join(
                f"{k.get('code', '?')} (niveau {k.get('level', '?')})"
                for k in known if isinstance(k, dict)
            )
            if known_str:
                parts.append(f"Langues déjà connues: {known_str}. Tu peux faire des ponts linguistiques.")

        # Objectifs
        goals = user_context.get('goals', [])
        if goals:
            goals_map = {
                'conversation': 'conversation', 'travel': 'voyage',
                'work': 'travail', 'exams': 'examens',
                'culture': 'culture', 'family': 'famille',
            }
            goals_fr = [goals_map.get(g, g) for g in goals]
            parts.append(f"Objectifs: {', '.join(goals_fr)}. Adapte les thèmes en conséquence.")

        # Style de correction
        correction = user_context.get('correction_preference')
        if correction == 'strict':
            parts.append("L'apprenant préfère un style strict. Sois précis dans les consignes.")
        elif correction == 'encouraging':
            parts.append("L'apprenant préfère un style encourageant. Utilise des formulations positives.")

        # Faiblesses
        weakness = user_context.get('weakness_profile', {})
        if weakness:
            recent_errors = weakness.get('recent_errors', [])
            if recent_errors:
                # Identifier les patterns d'erreurs
                error_verbs = [e.get('verb', '') for e in recent_errors if e.get('verb')]
                error_types = [e.get('type', '') for e in recent_errors if e.get('type')]
                if error_verbs:
                    # Inclure les verbes problématiques pour renforcer
                    unique_errors = list(set(error_verbs))[:5]
                    parts.append(
                        f"L'apprenant a des difficultés avec: {', '.join(unique_errors)}. "
                        f"Inclus 1-2 de ces verbes pour renforcer, mais varie aussi avec d'autres."
                    )

            by_type = weakness.get('by_type', {})
            if by_type:
                weakest = None
                min_rate = 1.0
                for t, stats in by_type.items():
                    total = stats.get('total', 0)
                    if total >= 5:
                        rate = stats.get('correct', 0) / total
                        if rate < min_rate:
                            min_rate = rate
                            weakest = t
                if weakest and min_rate < 0.6:
                    parts.append(
                        f"Point faible détecté: {weakest} (taux de réussite: {int(min_rate*100)}%). "
                        f"Adapte les exercices pour renforcer ce point."
                    )

    # Instruction générale de diversité
    parts.append(
        "IMPORTANT: Varie les thèmes (nourriture, voyage, famille, travail, loisirs, etc.), "
        "les temps verbaux, et les structures de phrases. Chaque exercice doit être UNIQUE et différent des autres."
    )

    return '\n'.join(parts)


def _extract_json(text):
    """Extract JSON from LLM response, handling markdown code blocks."""
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


def _content_signature(exercise_type, content):
    """Return a string that uniquely identifies this exercise content for deduplication."""
    if exercise_type == 'conjugation':
        return f"{content.get('verb', '')}:{content.get('tense', '')}"
    if exercise_type == 'fill_blank':
        return content.get('full_sentence', '') or content.get('sentence', '')
    if exercise_type == 'transform':
        return f"{content.get('original', '')}|{content.get('instruction', '')}"
    if exercise_type == 'word_order':
        return content.get('answer', '')
    if exercise_type == 'particles':
        return content.get('sentence', '')
    if exercise_type == 'gender':
        return content.get('word', '') or content.get('full', '')
    return json.dumps(content, sort_keys=True)


def _exists_exercise(language_code, exercise_type, content):
    """Check if an exercise with same signature already exists."""
    sig = _content_signature(exercise_type, content)
    if not sig:
        return False
    # We match by type + lang and check content verb/sentence in DB
    existing = PillarExercise.query.filter_by(
        language_code=language_code,
        exercise_type=exercise_type,
    ).all()
    for ex in existing:
        if _content_signature(exercise_type, ex.content or {}) == sig:
            return True
    return False


def _prompt_conjugation(lang_code, difficulty, count, verb_mode='both', user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    pronouns = get_pronouns(lang_code)
    tenses = get_tenses(lang_code)
    tense_list = ", ".join(f'"{t[0]}"' for t in tenses)
    pronoun_list = ", ".join(f'"{p}"' for p in pronouns)
    diversity = _build_diversity_instruction(lang_code, 'conjugation', user_context)

    system = f"""Tu es un expert en enseignement du {lang_name}.
Tu génères des exercices de conjugaison au format JSON strict.
{diversity}
Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après."""

    # Verb mode instructions
    mode_instruction = ""
    if verb_mode == 'irregular':
        mode_instruction = "Utilise UNIQUEMENT des verbes irreguliers (essere, avere, andare, fare, venire, tenere, dire, sapere, volere, potere, dovere, stare, dare, etc.). Mets 'irregular': true pour tous."
    elif verb_mode == 'regular':
        mode_instruction = "Utilise UNIQUEMENT des verbes reguliers (mangiare, parlare, dormire, scrivere, leggere, etc.). Mets 'irregular': false pour tous."
    else:
        mode_instruction = "Melange des verbes reguliers et irreguliers. Indique correctement le champ 'irregular' pour chaque verbe."

    user = f"""Génère {count} exercices de conjugaison en {lang_name}.
CHAQUE EXERCICE DOIT UTILISER UN VERBE DIFFÉRENT. Aucune répétition de verbe.

Chaque exercice doit être un objet avec:
- "verb": infinitif du verbe dans la langue cible (ex: andare, tener)
- "verb_native": traduction en français (ex: aller, tenir)
- "tense": un des temps suivants: {tense_list}
- "irregular": true si le verbe est irregulier, false sinon
- "answers": objet avec une clé pour chaque pronom: {pronoun_list}
  Les valeurs sont les formes conjuguees correctes.

Difficulté: {difficulty}/5. Pour difficulté 1-2 utilise des verbes courants et le présent.
{mode_instruction}

Format de réponse (JSON array):
[
  {{"verb": "andare", "verb_native": "aller", "tense": "presente", "irregular": true, "answers": {{"io": "vado", "tu": "vai", "lui/lei": "va", "noi": "andiamo", "voi": "andate", "loro": "vanno"}}}}
]"""

    return system, user


def _prompt_fill_blank(lang_code, difficulty, count, user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    diversity = _build_diversity_instruction(lang_code, 'fill_blank', user_context)

    system = f"""Tu es un expert en enseignement du {lang_name}.
Tu génères des exercices "phrase à trou" (un seul trou par phrase) au format JSON.
{diversity}
Réponds UNIQUEMENT avec un tableau JSON valide."""

    user = f"""Génère {count} exercices "phrase à trou" en {lang_name}.
CHAQUE PHRASE DOIT UTILISER UN VERBE/MOT DIFFÉRENT. Varie les thèmes et les contextes.

Chaque exercice: une phrase avec ___ à la place du verbe conjugué (ou du mot manquant).
- "sentence": phrase avec ___
- "hint_verb": infinitif du verbe à conjuguer (ou null si ce n'est pas un verbe)
- "hint_tense": temps (ex: presente, passe_compose) ou null
- "answer": le mot ou forme qui remplace ___
- "full_sentence": la phrase complète
- "translation": traduction de la phrase complète en français

Difficulté {difficulty}/5. Phrases courtes et claires.

Format:
[
  {{"sentence": "Io ___ al cinema", "hint_verb": "andare", "hint_tense": "presente", "answer": "vado", "full_sentence": "Io vado al cinema", "translation": "Je vais au cinéma"}}
]"""

    return system, user


def _prompt_transform(lang_code, difficulty, count, user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    diversity = _build_diversity_instruction(lang_code, 'transform', user_context)

    system = f"""Tu es un expert en enseignement du {lang_name}.
Tu génères des exercices de transformation (négation, question, changement de temps).
{diversity}
Réponds UNIQUEMENT avec un tableau JSON valide."""

    user = f"""Génère {count} exercices de transformation en {lang_name}.
CHAQUE EXERCICE DOIT UTILISER UNE PHRASE DIFFÉRENTE avec des verbes/sujets variés.
Varie aussi les types de transformation (négatif, question, changement de temps).

Chaque exercice:
- "original": phrase de départ
- "instruction": consigne en français (ex: "Mets au négatif", "Pose la question", "Passe au passé")
- "answer": la phrase transformée correcte

Difficulté {difficulty}/5.

Format:
[
  {{"original": "Io mangio una mela", "instruction": "Mets au negatif", "answer": "Io non mangio una mela"}}
]"""

    return system, user


def _prompt_word_order(lang_code, difficulty, count, user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    diversity = _build_diversity_instruction(lang_code, 'word_order', user_context)

    system = f"""Tu es un expert en enseignement du {lang_name}.
Tu génères des exercices "ordre des mots": phrase correcte dont les mots sont mélangés.
{diversity}
Réponds UNIQUEMENT avec un tableau JSON valide."""

    user = f"""Génère {count} exercices d'ordre des mots en {lang_name}.
CHAQUE PHRASE DOIT ÊTRE SUR UN THÈME DIFFÉRENT. Varie: famille, travail, nourriture, voyage, loisirs, etc.

Chaque exercice:
- "words_shuffled": liste des mots dans un ordre mélangé (sans ponctuation finale dans les mots)
- "answer": la phrase correcte (même ordre que words_shuffled mais réordonné)
- "translation": traduction en français

Difficulté {difficulty}/5. Phrases courtes (4-8 mots).

Format:
[
  {{"words_shuffled": ["al", "vado", "cinema", "Io"], "answer": "Io vado al cinema", "translation": "Je vais au cinema"}}
]"""

    return system, user


def _prompt_particles(lang_code, difficulty, count, user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    diversity = _build_diversity_instruction(lang_code, 'particles', user_context)

    system = f"""Tu es un expert en enseignement du {lang_code} (particules).
Tu génères des exercices à trou pour choisir la bonne particule.
{diversity}
Réponds UNIQUEMENT avec un tableau JSON valide."""

    user = f"""Génère {count} exercices de particules en {lang_code}.
CHAQUE EXERCICE DOIT UTILISER UN CONTEXTE ET UNE PARTICULE DIFFÉRENTS. Varie les situations.

Chaque exercice:
- "sentence": phrase avec ___ à la place de la particule manquante
- "options": liste de 4 particules possibles (ex: ["は", "が", "を", "に"])
- "answer": la bonne particule
- "explanation": courte explication en français (pourquoi cette particule)

Format:
[
  {{"sentence": "私 ___ 学生です", "options": ["は", "が", "を", "に"], "answer": "は", "explanation": "は marque le sujet/theme"}}
]"""

    return system, user


def _prompt_gender(lang_code, difficulty, count, user_context=None):
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    diversity = _build_diversity_instruction(lang_code, 'gender', user_context)

    system = f"""Tu es un expert en enseignement du {lang_name} (genre et articles).
Tu génères des exercices pour choisir le bon article/déterminant.
{diversity}
Réponds UNIQUEMENT avec un tableau JSON valide."""

    user = f"""Génère {count} exercices genre/articles en {lang_name}.
CHAQUE EXERCICE DOIT UTILISER UN MOT DIFFÉRENT. Varie les catégories: objets, nourriture, animaux, vêtements, corps, maison, nature, etc.

Chaque exercice:
- "word": le nom (ex: maison, livre)
- "options": liste de 4 choix (ex: ["le", "la", "l'", "les"] pour français)
- "answer": le bon article/déterminant
- "full": phrase ou syntagme complet (ex: "la maison")

Difficulté {difficulty}/5.

Format:
[
  {{"word": "maison", "options": ["le", "la", "l'", "les"], "answer": "la", "full": "la maison"}}
]"""

    return system, user


def _generate_via_llm(exercise_type, language_code, difficulty, count, verb_mode='both', user_context=None):
    """Call LLM and return list of content dicts, or empty list on failure."""
    if exercise_type == 'conjugation':
        system, user = _prompt_conjugation(language_code, difficulty, count, verb_mode=verb_mode, user_context=user_context)
    elif exercise_type == 'fill_blank':
        system, user = _prompt_fill_blank(language_code, difficulty, count, user_context=user_context)
    elif exercise_type == 'transform':
        system, user = _prompt_transform(language_code, difficulty, count, user_context=user_context)
    elif exercise_type == 'word_order':
        system, user = _prompt_word_order(language_code, difficulty, count, user_context=user_context)
    elif exercise_type == 'particles':
        system, user = _prompt_particles(language_code, difficulty, count, user_context=user_context)
    elif exercise_type == 'gender':
        system, user = _prompt_gender(language_code, difficulty, count, user_context=user_context)
    else:
        return []

    # Température plus haute pour plus de diversité
    response = call_llm(system, user, temperature=0.8)
    if not response:
        return []

    data = _extract_json(response)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'exercises' in data:
        return data['exercises']
    if isinstance(data, dict):
        return [data]
    return []


def _normalize_content(exercise_type, raw):
    """Ensure content has required keys for the given type."""
    if not isinstance(raw, dict):
        return None
    if exercise_type == 'conjugation':
        need = ['verb', 'verb_native', 'tense', 'irregular', 'answers']
        if not all(raw.get(k) is not None for k in need):
            return None
        return {k: raw.get(k) for k in need}
    if exercise_type == 'fill_blank':
        need = ['sentence', 'answer', 'full_sentence']
        if not all(raw.get(k) for k in need):
            return None
        return {
            'sentence': raw.get('sentence'),
            'hint_verb': raw.get('hint_verb'),
            'hint_tense': raw.get('hint_tense'),
            'answer': raw.get('answer'),
            'full_sentence': raw.get('full_sentence'),
            'translation': raw.get('translation'),
        }
    if exercise_type == 'transform':
        need = ['original', 'instruction', 'answer']
        if not all(raw.get(k) for k in need):
            return None
        return {k: raw.get(k) for k in need}
    if exercise_type == 'word_order':
        need = ['words_shuffled', 'answer', 'translation']
        if not all(raw.get(k) for k in need):
            return None
        return {k: raw.get(k) for k in need}
    if exercise_type == 'particles':
        need = ['sentence', 'options', 'answer', 'explanation']
        if not all(raw.get(k) for k in need):
            return None
        return {k: raw.get(k) for k in need}
    if exercise_type == 'gender':
        need = ['word', 'options', 'answer', 'full']
        if not all(raw.get(k) for k in need):
            return None
        return {k: raw.get(k) for k in need}
    return None


def generate_exercise_batch(language_code, exercise_type, difficulty, count=10, pillar_id=None, verb_mode='both', user_context=None):
    """
    Génère un batch d'exercices via LLM et les stocke en DB.
    Déduplique avant insertion. Retourne la liste des exercices créés.
    
    user_context (dict, optional): Contexte utilisateur pour personnaliser la génération.
        Clés possibles:
        - native_language: langue maternelle (ex: 'fr')
        - known_languages: langues connues [{code, level, years}]
        - goals: objectifs ['conversation', 'travel', ...]
        - correction_preference: 'strict' | 'moderate' | 'encouraging'
        - weakness_profile: profil de faiblesses {recent_errors, by_type, ...}
    """
    batch_id = uuid.uuid4().hex
    created = []

    items = _generate_via_llm(exercise_type, language_code, difficulty, count, verb_mode=verb_mode, user_context=user_context)
    for raw in items:
        content = _normalize_content(exercise_type, raw)
        if not content:
            continue
        if _exists_exercise(language_code, exercise_type, content):
            continue
        ex = PillarExercise(
            language_code=language_code,
            exercise_type=exercise_type,
            pillar_id=pillar_id,
            difficulty=difficulty,
            content=content,
            batch_id=batch_id,
        )
        db.session.add(ex)
        db.session.flush()
        created.append(ex)

    if created:
        db.session.commit()
    return created

"""
LLM Service for interacting with local LLMs.

Backends (par ordre de priorite) :
1. LM Studio (192.168.0.100:1234) - Backend principal, toujours allume, rapide
2. vLLM (spark-8144:8000)         - Fallback / cours complexes (GPU lourd)
3. Ollama (spark-8144:11434)      - Dernier recours

Tous utilisent l'API OpenAI-compatible sauf Ollama (API native).
"""
import os
import requests
import json

# =============================================================================
# Server Configuration
# =============================================================================

# LM Studio - Default runtime backend (local Mac / NAS)
LMSTUDIO_HOST = os.environ.get("LMSTUDIO_HOST", "192.168.0.100")
LMSTUDIO_PORT = os.environ.get("LMSTUDIO_PORT", "1234")
LMSTUDIO_ENDPOINT = f"http://{LMSTUDIO_HOST}:{LMSTUDIO_PORT}/v1/chat/completions"
LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL", "openai/gpt-oss-20b")

# vLLM on Spark - Heavy GPU, for complex content generation
SPARK_HOST = os.environ.get("SPARK_HOST", "spark-8144.local")
VLLM_PORT = os.environ.get("VLLM_PORT", "8000")
VLLM_ENDPOINT = f"http://{SPARK_HOST}:{VLLM_PORT}/v1/chat/completions"
VLLM_MODEL = "openai/gpt-oss-20b"

# Ollama on Spark - Last resort
OLLAMA_PORT = os.environ.get("OLLAMA_PORT", "11434")
OLLAMA_ENDPOINT = f"http://{SPARK_HOST}:{OLLAMA_PORT}/api/chat"
OLLAMA_MODEL = "gpt-oss:120b"

# Default backend: lmstudio -> vllm -> ollama
LLM_BACKEND = os.environ.get("LLM_BACKEND", "lmstudio")  # "lmstudio", "vllm", "ollama"
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))


def call_llm(system_prompt, user_prompt, temperature=0.7, backend=None, model=None, timeout=None):
    """
    Call the local LLM API.
    
    Chaine de fallback : LM Studio -> vLLM -> Ollama
    
    Args:
        system_prompt: System context/instructions
        user_prompt: User message
        temperature: Creativity level (0-1)
        backend: "lmstudio", "vllm" or "ollama" (default: LLM_BACKEND)
        model: Override model name
        timeout: Override timeout in seconds
    
    Returns:
        str: The LLM response text, or None if error
    """
    backend = backend or LLM_BACKEND
    _timeout = timeout or LLM_TIMEOUT
    
    if backend == "ollama":
        return _call_ollama(system_prompt, user_prompt, temperature, 
                           model or OLLAMA_MODEL, _timeout)
    elif backend == "vllm":
        return _call_vllm(system_prompt, user_prompt, temperature, 
                         model or VLLM_MODEL, _timeout)
    else:
        # Default: LM Studio with fallback chain
        return _call_lmstudio(system_prompt, user_prompt, temperature, 
                             model or LMSTUDIO_MODEL, _timeout)


def _call_openai_compatible(endpoint, system_prompt, user_prompt, temperature, model, timeout):
    """Generic call to any OpenAI-compatible API (LM Studio, vLLM, etc.)."""
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": -1,
            "stream": False
        },
        timeout=timeout
    )
    if response.status_code == 200:
        data = response.json()
        return data['choices'][0]['message']['content']
    else:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")


def _call_lmstudio(system_prompt, user_prompt, temperature, model, timeout):
    """Call LLM via LM Studio (primary). Fallback to vLLM then Ollama."""
    try:
        result = _call_openai_compatible(
            LMSTUDIO_ENDPOINT, system_prompt, user_prompt, temperature, model, timeout)
        if result:
            return result
    except requests.exceptions.Timeout:
        print(f"LM Studio Timeout ({LMSTUDIO_HOST}:{LMSTUDIO_PORT})")
    except requests.exceptions.ConnectionError:
        print(f"LM Studio Connection Error - Is LM Studio running on {LMSTUDIO_HOST}:{LMSTUDIO_PORT}?")
    except Exception as e:
        print(f"LM Studio Error: {e}")

    # Fallback -> vLLM
    print("Falling back to vLLM...")
    return _call_vllm(system_prompt, user_prompt, temperature, VLLM_MODEL, timeout)


def _call_vllm(system_prompt, user_prompt, temperature, model, timeout):
    """Call LLM via vLLM (OpenAI-compatible API). Fallback to Ollama."""
    try:
        result = _call_openai_compatible(
            VLLM_ENDPOINT, system_prompt, user_prompt, temperature, model, timeout)
        if result:
            return result
    except requests.exceptions.Timeout:
        print(f"vLLM Timeout ({SPARK_HOST}:{VLLM_PORT})")
    except requests.exceptions.ConnectionError:
        print(f"vLLM Connection Error - Is vLLM running on {SPARK_HOST}:{VLLM_PORT}?")
    except Exception as e:
        print(f"vLLM Error: {e}")

    # Fallback -> Ollama
    print("Falling back to Ollama...")
    return _call_ollama(system_prompt, user_prompt, temperature, 
                       "gpt-oss:20b", timeout)


def _call_ollama(system_prompt, user_prompt, temperature, model, timeout):
    """Call LLM via Ollama native API (last resort)."""
    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                }
            },
            timeout=timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('message', {}).get('content', '')
        else:
            print(f"Ollama Error: {response.status_code} - {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print("Ollama Timeout")
        return None
    except requests.exceptions.ConnectionError:
        print(f"Ollama Connection Error - Is Ollama running on {SPARK_HOST}:{OLLAMA_PORT}?")
        return None
    except Exception as e:
        print(f"Ollama Error: {e}")
        return None


def generate_lego_templates(target_language, level="A2", count=5):
    """Generate phrase structure templates using LLM."""
    system_prompt = f"""Tu es un expert en linguistique et en enseignement des langues.
Tu génères des templates de structures de phrases pour l'apprentissage du {target_language}.
Réponds UNIQUEMENT avec du JSON valide, sans texte avant ou après."""
    
    user_prompt = f"""Génère {count} templates de structures de phrases pour apprendre le {target_language} au niveau {level}.

Chaque template doit avoir:
- "pattern": la structure avec des slots comme [SUJET], [VERBE], [OBJET], [LAUNCHER], [CONNECTEUR], [ADJECTIF]
- "example": un exemple concret en {target_language}
- "translation": la traduction française

Format JSON strict:
[
  {{"pattern": "[SUJET] + [VERBE] + [OBJET]", "example": "Io mangio la pizza", "translation": "Je mange la pizza"}}
]"""

    response = call_llm(system_prompt, user_prompt, temperature=0.8)
    
    if response:
        try:
            # Try to extract JSON from response
            # Sometimes LLM wraps in markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            return json.loads(response.strip())
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON: {response[:200]}")
            return None
    return None


def generate_daily_themes(target_language, count=7):
    """Generate a list of daily themes for learning."""
    system_prompt = f"""Tu es un expert en enseignement des langues.
Tu génères des thèmes quotidiens pour l'apprentissage du {target_language}.
Réponds UNIQUEMENT avec du JSON valide (un array de strings)."""
    
    user_prompt = f"""Génère {count} thèmes du jour variés et pratiques pour apprendre le {target_language}.

Les thèmes doivent être:
- Concrets et utiles au quotidien
- Progressifs en difficulté
- Variés (vie quotidienne, travail, loisirs, voyages, etc.)

Format: ["thème 1", "thème 2", ...]

Réponds uniquement avec le JSON, sans explication."""

    response = call_llm(system_prompt, user_prompt, temperature=0.8)
    
    if response:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            return json.loads(response.strip())
        except json.JSONDecodeError:
            print(f"Failed to parse themes: {response[:200]}")
            return None
    return None


def generate_text_for_translation(target_language, theme, level="A2"):
    """Generate a short text for translation practice."""
    system_prompt = f"""Tu es un professeur de {target_language} niveau {level}.
Tu génères des textes courts et naturels pour la pratique de la traduction.
Écris UNIQUEMENT le texte en {target_language}, sans traduction ni explication."""
    
    user_prompt = f"""Génère un texte court (50-80 mots) en {target_language} sur le thème: {theme}

Le texte doit:
- Être adapté au niveau {level}
- Utiliser un vocabulaire courant
- Raconter une petite histoire ou situation concrète
- Être naturel et idiomatique

Réponds uniquement avec le texte en {target_language}."""

    return call_llm(system_prompt, user_prompt, temperature=0.8)


def generate_quest(native_language, words):
    """Generate a writing quest using specific words."""
    words_str = ", ".join(words)
    
    system_prompt = f"""Tu es un professeur de langues créatif.
Tu génères des missions d'écriture courtes et engageantes en {native_language}."""
    
    user_prompt = f"""Crée une mission d'écriture courte (1-2 phrases) en {native_language}.

La mission doit demander à l'utilisateur de raconter une anecdote personnelle 
en utilisant ces mots: {words_str}

La mission doit être:
- Motivante et créative
- Claire et concise
- Personnelle (demander une expérience vécue)

Réponds uniquement avec la mission, sans introduction."""

    return call_llm(system_prompt, user_prompt, temperature=0.9)


def correct_text(target_language, text):
    """Correct a text and provide feedback."""
    system_prompt = f"""Tu es un correcteur strict de {target_language}.
Tu corriges les textes et expliques les erreurs de manière pédagogique.
Utilise des emojis pour rendre les corrections plus visuelles."""
    
    user_prompt = f"""Corrige ce texte en {target_language}:

"{text}"

Format ta réponse ainsi:
1. **Texte corrigé:** (le texte complet corrigé)
2. **Erreurs trouvées:** (liste des erreurs avec ❌ et leur correction avec ✅)
3. **Score:** (note sur 10)
4. **Conseil:** (un conseil pour s'améliorer)"""

    return call_llm(system_prompt, user_prompt, temperature=0.3)


def translate_word(word, source_lang, target_lang):
    """Translate a single word (for the SOS/cheat feature)."""
    system_prompt = f"Tu es un traducteur précis. Traduis du {source_lang} vers le {target_lang}."
    user_prompt = f"Traduis ce mot: {word}\n\nRéponds uniquement avec la traduction, sans explication."
    
    return call_llm(system_prompt, user_prompt, temperature=0.1)


def get_learner_context(program=None, user=None):
    """
    Build LLM context from user and program profiles.
    Returns a string to inject into system prompts.
    """
    context_parts = []
    
    style_instruction = ""
    preference = 'moderate'
    
    # User-level profile (global defaults)
    if user and hasattr(user, 'learner_profile') and user.learner_profile:
        profile = user.learner_profile
        native = profile.get('native_language', 'fr')
        context_parts.append(f"Langue maternelle: {native}")
        
        # Enriched known languages format
        known_langs = profile.get('known_languages', [])
        if known_langs:
            if isinstance(known_langs, list) and len(known_langs) > 0:
                if isinstance(known_langs[0], dict):
                    # New format: [{code, level, years}]
                    langs_str = ", ".join([
                        f"{l.get('code', '?')} ({l.get('level', 'A1')})" 
                        for l in known_langs if l.get('code')
                    ])
                else:
                    # Old format: simple list of strings
                    langs_str = ", ".join(known_langs)
                context_parts.append(f"Autres langues connues: {langs_str}")
        
        # Goals
        goals = profile.get('goals', [])
        if goals:
            context_parts.append(f"Objectifs: {', '.join(goals)}")
        
        preference = profile.get('correction_preference', 'moderate')
    
    # Program-level profile (overrides)
    if program and hasattr(program, 'program_profile') and program.program_profile:
        profile = program.program_profile
        context_parts.append(f"Niveau actuel (CECRL): {profile.get('current_level', 'A2')}")
        if profile.get('goals'):
            context_parts.append(f"Objectifs programme: {', '.join(profile.get('goals', []))}")
        preference = profile.get('correction_strictness', preference)

    # Translate preference to instructions
    if preference == 'strict':
        style_instruction = "STYLE: Strict et exigeant. Relève toutes les erreurs (grammaire, syntaxe, nuances). Ne donne pas la réponse tout de suite, aide l'étudiant à comprendre la règle."
    elif preference == 'encouraging':
        style_instruction = "STYLE: Encouraging and positive. Focus on communication over perfection. Ignore minor errors if the meaning is clear."
    else: # moderate
        style_instruction = "STYLE: Équilibré. Corrige les erreurs importantes mais reste bienveillant. Explique le 'pourquoi' de l'erreur."

    context_parts.append(style_instruction)
    
    if context_parts:
        return "PROFIL APPRENANT:\n- " + "\n- ".join(context_parts)
    return ""


def get_known_languages_for_bridges(user):
    """
    Get known languages formatted for language bridges in Prof chatbot.
    Returns a string like "anglais (B2), espagnol (A2)"
    """
    if not user or not user.learner_profile:
        return "aucune"
    
    profile = user.learner_profile
    known_langs = profile.get('known_languages', [])
    
    if not known_langs:
        return "aucune"
    
    # Language code to name mapping
    lang_names = {
        'en': 'anglais', 'fr': 'francais', 'es': 'espagnol', 'de': 'allemand',
        'it': 'italien', 'pt': 'portugais', 'ru': 'russe', 'zh': 'chinois',
        'ja': 'japonais', 'ko': 'coreen', 'ar': 'arabe', 'tr': 'turc',
        'nl': 'neerlandais', 'pl': 'polonais', 'sv': 'suedois'
    }
    
    if isinstance(known_langs, list) and len(known_langs) > 0:
        if isinstance(known_langs[0], dict):
            # New format
            return ", ".join([
                f"{lang_names.get(l.get('code', ''), l.get('code', '?'))} ({l.get('level', 'A1')})"
                for l in known_langs if l.get('code')
            ])
        else:
            # Old format
            return ", ".join(known_langs)
    
    return "aucune"


def chat_with_prof(user, user_message, target_language='fr', current_page=None, 
                   current_pillar=None, estimated_level='A0'):
    """
    Chat with the Prof assistant (enhanced contextual chatbot).
    
    Args:
        user: User object
        user_message: Message from user
        target_language: Language being learned
        current_page: Current page/context (e.g., 'pillar_hiragana')
        current_pillar: Current pillar being studied
        estimated_level: User's estimated level in the language
    
    Returns:
        str: Prof's response
    """
    from app.prompt_templates import PROMPT_TEMPLATES, CORRECTION_STYLES
    
    # Get user profile info
    profile = user.learner_profile if user else {}
    native_language = profile.get('native_language', 'fr')
    known_languages = get_known_languages_for_bridges(user)
    correction_pref = profile.get('correction_preference', 'moderate')
    correction_style = CORRECTION_STYLES.get(correction_pref, CORRECTION_STYLES['moderate'])
    
    # Build learner context
    learner_context = get_learner_context(user=user)
    
    # Build the Prof prompt
    system_prompt = PROMPT_TEMPLATES.get('prof_chatbot', '').format(
        target_language=target_language,
        native_language=native_language,
        learner_context=learner_context,
        current_page=current_page or 'dashboard',
        current_pillar=current_pillar or 'aucun',
        estimated_level=estimated_level,
        known_languages=known_languages,
        correction_style=correction_style,
        user_message=user_message
    )
    
    # Call LLM
    response = call_llm(system_prompt, f"MESSAGE: {user_message}", temperature=0.7)
    
    return response or "Desole, je n'ai pas pu traiter ta question. Reessaie !"


def analyze_text(target_language, user_text, context=None, program=None, user=None):
    """
    Analyze user text for errors with high precision.
    
    Args:
        target_language: The language being learned
        user_text: Text submitted by user
        context: Exercise context (pattern, words, etc.)
        program: TrainingProgram object (for profile context)
        user: User object (for profile context)
    
    Returns JSON with structure:
    {
        "is_correct": boolean,
        "correction": string,
        "errors": [{"segment": "...", "type": "...", "explanation": "..."}],
        "feedback": "..."
    }
    """
    # Build learner context from profiles
    learner_context = get_learner_context(program, user)
    
    system_prompt = f"""Tu es un expert linguistique en {target_language}.
Ton rôle est d'analyser le texte de l'utilisateur comme un compilateur de code.
Tu dois détecter les erreurs, les localiser précisément et expliquer pourquoi.

{learner_context}

Adapte ton feedback au profil de l'apprenant ci-dessus.

Réponds UNIQUEMENT avec ce format JSON strict:
{{
    "is_correct": boolean, // true si 100% correct
    "correction": "Le texte complet corrigé",
    "errors": [
        {{
            "segment": "le partie faux",
            "type": "conjugaison|orthographe|vocabulaire|grammaire",
            "explanation": "explication courte et précise"
        }}
    ],
    "feedback": "Message d'encouragement ou explication globale"
}}"""

    context_str = f"Contexte de l'exercice: {context}" if context else ""
    user_prompt = f"""Analyse ce texte en {target_language}:
"{user_text}"
{context_str}

Réponds uniquement avec le JSON."""

    response = call_llm(system_prompt, user_prompt, temperature=0.2)
    
    if response:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            return json.loads(response.strip())
        except json.JSONDecodeError:
            print(f"Failed to parse analysis JSON: {response[:200]}")
            # Fallback
            return {
                "is_correct": False, 
                "correction": user_text, 
                "errors": [], 
                "feedback": "Erreur d'analyse LLM."
            }
            
    return None

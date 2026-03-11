"""
Pillar Chat API — Context-aware LLM assistant for pillar learning.

The assistant helps the user with the current pillar topic (grammar rules,
vocabulary, tips) in a supportive way. At low CEFR levels (A0-A2), the
assistant speaks French and helps understand. At higher levels (B1+),
it can gradually introduce the target language.
"""
from flask import Blueprint, request, jsonify, g
from app.llm_service import call_llm
from app.pillar_config import get_pillar, get_language

bp = Blueprint('pillar_chat', __name__, url_prefix='/pillars')


def _build_system_prompt(lang_config, pillar_config):
    """Build a context-aware system prompt for the pillar assistant."""
    lang_name = lang_config['name']
    pillar_name = pillar_config['name']
    pillar_desc = pillar_config.get('description', '')
    cefr = pillar_config.get('cefr', 'A0')
    category = pillar_config.get('category', 'grammar')
    
    # Base behavior depends on CEFR level
    if cefr in ('A0', 'A1', 'A2'):
        lang_instruction = (
            f"Parle UNIQUEMENT en français. L'élève est débutant en {lang_name} "
            f"(niveau {cefr}), ne le force PAS à parler en {lang_name}. "
            f"Donne les exemples en {lang_name} avec traduction française."
        )
    elif cefr in ('B1', 'B2'):
        lang_instruction = (
            f"Parle principalement en français mais introduis des mots/phrases "
            f"en {lang_name} quand c'est naturel. L'élève est niveau {cefr}."
        )
    else:
        lang_instruction = (
            f"Tu peux mélanger français et {lang_name}. L'élève est avancé ({cefr})."
        )
    
    return f"""Tu es un tuteur de {lang_name} bienveillant et clair.
L'élève travaille actuellement sur le pilier « {pillar_name} » — {pillar_desc}.
Catégorie : {category}. Niveau CEFR : {cefr}.

{lang_instruction}

RÈGLES :
- Sois concis et utile (max 3-4 phrases par réponse)
- Si l'élève demande une règle de grammaire, explique-la simplement avec un exemple
- Si l'élève fait une erreur, corrige gentiment et explique pourquoi
- Tu peux donner des astuces mnémotechniques
- N'envoie JAMAIS de réponses trop longues
- Utilise des emojis modérément pour rendre les réponses vivantes"""


@bp.route('/<lang>/<pillar_id>/chat', methods=['POST'])
def pillar_chat(lang, pillar_id):
    """Chat with the LLM assistant about the current pillar."""
    if not g.user:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'error': 'Message vide'}), 400
    
    lang_config = get_language(lang)
    pillar_config = get_pillar(lang, pillar_id)
    
    if not lang_config or not pillar_config:
        return jsonify({'error': 'Pilier non trouvé'}), 404
    
    system_prompt = _build_system_prompt(lang_config, pillar_config)
    
    try:
        response = call_llm(system_prompt, user_message, temperature=0.7, timeout=15)
        if response:
            return jsonify({'reply': response.strip()})
        else:
            return jsonify({'reply': "Désolé, je n'ai pas pu répondre. Réessaie ! 🤔"})
    except Exception as e:
        print(f"[PillarChat] Error: {e}")
        return jsonify({'reply': "Le serveur LLM n'est pas disponible pour le moment. 😅"})

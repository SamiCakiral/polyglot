"""
TTS (Text-to-Speech) routes for the language learning app.

Provides endpoints to generate speech audio from text using
Qwen3-TTS (configurable via .env).

Endpoints:
    POST /api/tts       - Generate speech from text
    GET  /api/tts/status - Check TTS service availability
    GET  /api/tts/languages - Get supported TTS languages
"""
from flask import Blueprint, request, jsonify, Response
from flask_login import login_required, current_user

from app.tts_service import (
    generate_speech, is_tts_available, is_language_supported,
    get_supported_languages, get_speakers
)

bp = Blueprint('tts', __name__)


@bp.route('/api/tts', methods=['POST'])
@login_required
def api_generate_tts():
    """
    Generate speech audio from text.
    
    Request JSON:
        {
            "text": "Bonjour le monde",
            "language": "fr",
            "speaker": "serena",    // optional
            "instruct": "Speak slowly"  // optional
        }
    
    Returns:
        WAV audio file (audio/wav content type)
        or JSON error if language not supported / service down
    """
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({"error": "Le champ 'text' est requis"}), 400
    
    text = data['text'].strip()
    language = data.get('language', 'auto')
    speaker = data.get('speaker')
    instruct = data.get('instruct')
    
    # Use user's TTS accent preference if no instruct given
    if not instruct and current_user.is_authenticated:
        user_profile = current_user.learner_profile or {}
        user_accent = user_profile.get('tts_accent', '')
        if user_accent:
            instruct = user_accent
    
    # Check if language is supported
    if language != 'auto' and not is_language_supported(language):
        if language == 'tr':
            return jsonify({
                "error": "Le turc n'est pas supporte pour la prononciation audio.",
                "supported": False,
                "reason": "Qwen3-TTS ne supporte pas le turc. Langues supportees: zh, en, ja, ko, de, fr, ru, pt, es, it."
            }), 400
        return jsonify({
            "error": f"Langue '{language}' non supportee pour le TTS.",
            "supported": False
        }), 400
    
    # Generate speech
    audio_bytes, sample_rate, error = generate_speech(
        text=text,
        language=language,
        speaker=speaker,
        instruct=instruct
    )
    
    if error:
        return jsonify({"error": error}), 503 if "chargement" in error or "disponible" in error else 500
    
    if not audio_bytes:
        return jsonify({"error": "Echec de la generation audio"}), 500
    
    # Return WAV audio
    return Response(
        audio_bytes,
        mimetype='audio/wav',
        headers={
            'Content-Disposition': 'inline; filename=tts_output.wav',
            'X-TTS-Sample-Rate': str(sample_rate),
        }
    )


@bp.route('/api/tts/status', methods=['GET'])
@login_required
def api_tts_status():
    """
    Check TTS service availability.
    
    Returns JSON:
        {
            "available": true/false,
            "info": {...}
        }
    """
    available, info = is_tts_available()
    return jsonify({
        "available": available,
        "info": info
    })


@bp.route('/api/tts/languages', methods=['GET'])
@login_required
def api_tts_languages():
    """
    Get list of languages supported by TTS.
    
    Returns JSON:
        {
            "languages": {"zh": "Chinese", "en": "English", ...},
            "not_supported": ["tr"]
        }
    """
    return jsonify({
        "languages": get_supported_languages(),
        "not_supported": ["tr"],
        "note": "Le turc n'est pas supporte par Qwen3-TTS"
    })


@bp.route('/api/tts/speakers', methods=['GET'])
@login_required
def api_tts_speakers():
    """
    Get available TTS speaker presets.
    
    Returns JSON:
        {"speakers": ["aiden", "dylan", ...]}
    """
    return jsonify({"speakers": get_speakers()})

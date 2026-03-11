"""
TTS Service for Qwen3-TTS on NVIDIA DGX Spark (spark-8144).

Provides text-to-speech functionality for the language learning app.
Communicates with the Qwen3-TTS Docker container running on spark-8144.

Supported languages: zh, en, ja, ko, de, fr, ru, pt, es, it
NOT supported: tr (Turkish)
"""
import os
import requests
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
SPARK_HOST = os.environ.get("SPARK_HOST", "spark-8144.local")
TTS_PORT = os.environ.get("TTS_PORT", "9100")
TTS_BASE_URL = f"http://{SPARK_HOST}:{TTS_PORT}"
TTS_TIMEOUT = 60

# Languages supported by Qwen3-TTS
TTS_SUPPORTED_LANGUAGES = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian"
}

# Default speaker per language (can be overridden per user)
DEFAULT_SPEAKERS = {
    "zh": "uncle_fu",   # Chinese male voice
    "ja": "ono_anna",   # Japanese female voice
    "ko": "sohee",      # Korean female voice
    "ru": "dylan",      # Neutral voice for Russian
    "es": "vivian",     # Female voice for Spanish
    "it": "vivian",     # Female voice for Italian
    "en": "ryan",       # English male voice
    "fr": "serena",     # French female voice
    "de": "eric",       # German male voice
    "pt": "aiden",      # Portuguese male voice
}


def is_tts_available():
    """
    Check if the TTS service is running and healthy.
    
    Returns:
        tuple: (available: bool, info: dict)
    """
    try:
        resp = requests.get(f"{TTS_BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('status') == 'healthy', data
        return False, {"error": f"HTTP {resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return False, {"error": f"Cannot connect to TTS at {TTS_BASE_URL}"}
    except Exception as e:
        return False, {"error": str(e)}


def is_language_supported(lang_code):
    """Check if a language is supported for TTS."""
    return lang_code in TTS_SUPPORTED_LANGUAGES


def get_tts_language_name(lang_code):
    """Get the TTS language name from a language code."""
    return TTS_SUPPORTED_LANGUAGES.get(lang_code, "Auto")


def generate_speech(text, language="auto", speaker=None, instruct=None):
    """
    Generate speech audio from text.
    
    Args:
        text: Text to synthesize (max 2000 chars)
        language: Language code (zh, en, ja, ko, de, fr, ru, pt, es, it)
        speaker: Speaker preset name (default: auto-selected by language)
        instruct: Style instruction (e.g., "Speak slowly and clearly")
    
    Returns:
        tuple: (audio_bytes, sample_rate, error_message)
               audio_bytes is WAV data, or None if error
    """
    # Check language support
    if language == "tr":
        return None, 0, "Le turc n'est pas encore supporte pour la prononciation audio."
    
    # Auto-select speaker based on language
    if not speaker:
        speaker = DEFAULT_SPEAKERS.get(language, "vivian")
    
    try:
        resp = requests.post(
            f"{TTS_BASE_URL}/tts",
            json={
                "text": text[:2000],  # Limit text length
                "language": language,
                "speaker": speaker,
                "instruct": instruct,
            },
            timeout=TTS_TIMEOUT,
        )
        
        if resp.status_code == 200:
            audio_bytes = resp.content
            sample_rate = int(resp.headers.get("X-TTS-Sample-Rate", "24000"))
            duration_ms = resp.headers.get("X-TTS-Duration-Ms", "?")
            logger.info(f"TTS OK: '{text[:30]}...' -> {duration_ms}ms, lang={language}")
            return audio_bytes, sample_rate, None
        
        elif resp.status_code == 400:
            error = resp.json().get("detail", "Bad request")
            return None, 0, error
        
        elif resp.status_code == 503:
            return None, 0, "Le service TTS est en cours de chargement, reessayez dans quelques instants."
        
        else:
            return None, 0, f"Erreur TTS: HTTP {resp.status_code}"
    
    except requests.exceptions.Timeout:
        logger.warning("TTS request timed out")
        return None, 0, "Le service TTS n'a pas repondu a temps."
    
    except requests.exceptions.ConnectionError:
        logger.warning(f"Cannot connect to TTS at {TTS_BASE_URL}")
        return None, 0, "Le service TTS n'est pas disponible actuellement."
    
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None, 0, f"Erreur TTS: {str(e)}"


def get_supported_languages():
    """Get the list of TTS-supported languages."""
    return TTS_SUPPORTED_LANGUAGES


def get_speakers():
    """Get available speaker presets."""
    try:
        resp = requests.get(f"{TTS_BASE_URL}/speakers", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("speakers", [])
    except Exception:
        pass
    
    # Fallback to hardcoded list
    return [
        "aiden", "dylan", "eric", "ono_anna", "ryan",
        "serena", "sohee", "uncle_fu", "vivian"
    ]

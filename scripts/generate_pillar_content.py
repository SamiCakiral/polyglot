"""
Script to generate pillar content using LLM (GPT-OSS 120b) on NVIDIA DGX Spark.

This script generates comprehensive learning content for each pillar:
- Flashcards for vocabulary/grammar
- Exercises for practice
- Explanations for concepts

Uses Ollama on spark-8144 (NVIDIA DGX Spark with GB10 GPU).

Run with: python3.11 scripts/generate_pillar_content.py [language_code]

Examples:
  python3.11 scripts/generate_pillar_content.py ja    # Japanese only
  python3.11 scripts/generate_pillar_content.py       # All languages
  python3.11 scripts/generate_pillar_content.py ja -f # Force regenerate
"""
import sys
import os
import json
import time
import requests

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pillar_config import LANGUAGES, get_language, get_pillars_for_language

# =============================================================================
# LLM Configuration - Ollama on NVIDIA DGX Spark (spark-8144)
# =============================================================================
SPARK_HOST = os.environ.get("SPARK_HOST", "spark-8144.local")
OLLAMA_PORT = os.environ.get("OLLAMA_PORT", "11434")

# Ollama native API for generation (supports gpt-oss:120b)
OLLAMA_CHAT_URL = f"http://{SPARK_HOST}:{OLLAMA_PORT}/api/chat"
OLLAMA_TAGS_URL = f"http://{SPARK_HOST}:{OLLAMA_PORT}/api/tags"

# Model: gpt-oss:120b (116.8B params, MXFP4 quantization, ~65GB)
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-oss:120b")


def check_ollama_available():
    """Verify Ollama is running and model is available."""
    try:
        resp = requests.get(OLLAMA_TAGS_URL, timeout=5)
        if resp.status_code == 200:
            models = [m['name'] for m in resp.json().get('models', [])]
            if LLM_MODEL in models:
                return True, f"Ollama OK, model '{LLM_MODEL}' available"
            else:
                return False, f"Model '{LLM_MODEL}' not found. Available: {', '.join(models)}"
        return False, f"Ollama returned status {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to Ollama at {SPARK_HOST}:{OLLAMA_PORT}"
    except Exception as e:
        return False, f"Error checking Ollama: {e}"


def call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=4096, timeout=600):
    """
    Call gpt-oss:120b via Ollama native API on spark-8144.
    
    Ollama API format:
    POST /api/chat
    {
        "model": "gpt-oss:120b",
        "messages": [...],
        "stream": false,
        "options": {"temperature": 0.7, "num_predict": 4096}
    }
    """
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            },
            timeout=timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data.get('message', {}).get('content', '')
            # Log timing info from Ollama
            eval_duration = data.get('eval_duration', 0)
            if eval_duration:
                eval_seconds = eval_duration / 1e9
                eval_count = data.get('eval_count', 0)
                if eval_seconds > 0:
                    toks_per_sec = eval_count / eval_seconds
                    print(f"   [LLM] {eval_count} tokens in {eval_seconds:.1f}s ({toks_per_sec:.1f} tok/s)")
            return content
        else:
            print(f"   [ERROR] Ollama returned {response.status_code}: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"   [ERROR] LLM request timed out after {timeout}s")
        return None
    except requests.exceptions.ConnectionError:
        print(f"   [ERROR] Cannot connect to Ollama at {SPARK_HOST}:{OLLAMA_PORT}")
        print(f"   TIP: ssh spark-8144 'docker start legalprod-ollama'")
        return None
    except Exception as e:
        print(f"   [ERROR] {e}")
        return None


def extract_json(response):
    """Extract JSON from LLM response, handling markdown code blocks."""
    if not response:
        return None
    
    # Try to extract from code blocks
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0]
    elif "```" in response:
        response = response.split("```")[1].split("```")[0]
    
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError as e:
        print(f"   [ERROR] JSON parsing failed: {e}")
        print(f"   Response preview: {response[:300]}...")
        return None


def generate_writing_system_content(lang_code, pillar_id, lang_config):
    """Generate content for writing system pillars (hiragana, katakana, hangul, etc.)"""
    
    pillar_configs = {
        'hiragana': {
            'name': 'Hiragana',
            'description': 'syllabaire japonais de base',
            'groups': [
                ('voyelles', 'a i u e o', 'あ い う え お'),
                ('ka', 'ka ki ku ke ko', 'か き く け こ'),
                ('sa', 'sa shi su se so', 'さ し す せ そ'),
                ('ta', 'ta chi tsu te to', 'た ち つ て と'),
                ('na', 'na ni nu ne no', 'な に ぬ ね の'),
                ('ha', 'ha hi fu he ho', 'は ひ ふ へ ほ'),
                ('ma', 'ma mi mu me mo', 'ま み む め も'),
                ('ya', 'ya yu yo', 'や ゆ よ'),
                ('ra', 'ra ri ru re ro', 'ら り る れ ろ'),
                ('wa', 'wa wo n', 'わ を ん')
            ]
        },
        'katakana': {
            'name': 'Katakana',
            'description': 'syllabaire japonais pour les mots etrangers',
            'groups': [
                ('voyelles', 'a i u e o', 'ア イ ウ エ オ'),
                ('ka', 'ka ki ku ke ko', 'カ キ ク ケ コ'),
                ('sa', 'sa shi su se so', 'サ シ ス セ ソ'),
                ('ta', 'ta chi tsu te to', 'タ チ ツ テ ト'),
                ('na', 'na ni nu ne no', 'ナ ニ ヌ ネ ノ'),
                ('ha', 'ha hi fu he ho', 'ハ ヒ フ ヘ ホ'),
                ('ma', 'ma mi mu me mo', 'マ ミ ム メ モ'),
                ('ya', 'ya yu yo', 'ヤ ユ ヨ'),
                ('ra', 'ra ri ru re ro', 'ラ リ ル レ ロ'),
                ('wa', 'wa wo n', 'ワ ヲ ン')
            ]
        },
        'hangul': {
            'name': 'Hangul',
            'description': 'alphabet coreen',
            'groups': [
                ('voyelles_simples', 'a eo o u eu i', 'ㅏ ㅓ ㅗ ㅜ ㅡ ㅣ'),
                ('voyelles_composees', 'ae e oe wi', 'ㅐ ㅔ ㅚ ㅟ'),
                ('consonnes_base', 'g n d r m b s', 'ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ'),
                ('consonnes_aspirees', 'k t p ch h', 'ㅋ ㅌ ㅍ ㅊ ㅎ'),
                ('consonnes_doubles', 'kk tt pp ss jj', 'ㄲ ㄸ ㅃ ㅆ ㅉ')
            ]
        },
        'cyrillic': {
            'name': 'Cyrillique',
            'description': 'alphabet russe',
            'groups': [
                ('similaires', 'A K M O T', 'А К М О Т'),
                ('faux_amis', 'B H P C X', 'В Н Р С Х'),
                ('nouvelles', 'Б Г Д Ж З', 'Б Г Д Ж З'),
                ('voyelles', 'Е Ё И Й У Ы Э Ю Я', 'Е Ё И Й У Ы Э Ю Я'),
                ('signes', 'Ь Ъ', 'Ь Ъ')
            ]
        },
        'pinyin': {
            'name': 'Pinyin',
            'description': 'romanisation du chinois et tons',
            'groups': [
                ('ton_1', 'ton haut plat', 'mā, bā, dē'),
                ('ton_2', 'ton montant', 'má, bá, dé'),
                ('ton_3', 'ton descendant-montant', 'mǎ, bǎ, dě'),
                ('ton_4', 'ton descendant', 'mà, bà, dè'),
                ('initiales', 'b p m f d t n l', 'consonnes de base'),
                ('finales', 'a o e i u ü', 'voyelles de base')
            ]
        }
    }
    
    config = pillar_configs.get(pillar_id)
    if not config:
        return None
    
    cards = []
    for group_name, romanized, native in config['groups']:
        items = native.split()
        romanized_items = romanized.split()
        
        for i, item in enumerate(items):
            rom = romanized_items[i] if i < len(romanized_items) else ''
            cards.append({
                'front': item,
                'back': rom,
                'hint': f'Groupe: {group_name}',
                'notes': f'Prononciation: {rom}',
                'tags': [pillar_id, group_name, 'ecriture']
            })
    
    return {
        'pillar_id': pillar_id,
        'language': lang_code,
        'name': config['name'],
        'description': config['description'],
        'type': 'writing_system',
        'cards': cards,
        'total_cards': len(cards),
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }


def generate_grammar_content(lang_code, pillar, lang_config):
    """Generate grammar pillar content using LLM."""
    
    lang_name = lang_config['name']
    pillar_name = pillar['name']
    pillar_id = pillar['id']
    level = pillar['level']
    card_count = pillar.get('cards', 20)
    
    system_prompt = f"""Tu es un expert linguiste et professeur de {lang_name}.
Tu generes du contenu pedagogique de haute qualite pour apprendre le {lang_name}.
Tu reponds UNIQUEMENT avec du JSON valide, sans texte avant ou apres.
Utilise l'UTF-8 pour les caracteres speciaux."""
    
    user_prompt = f"""Genere {card_count} flashcards pour le pilier "{pillar_name}" (niveau {level}) en {lang_name}.

Chaque carte doit enseigner un aspect de ce concept grammatical.
Pour le vocabulaire, utilise des exemples concrets et courants.

Format JSON strict:
{{
  "pillar_id": "{pillar_id}",
  "language": "{lang_code}",
  "name": "{pillar_name}",
  "type": "grammar",
  "explanation": "Explication claire du concept en francais (2-3 phrases)",
  "cards": [
    {{
      "front": "Le mot/concept en {lang_name}",
      "back": "Traduction ou explication en francais",
      "example": "Phrase d'exemple en {lang_name}",
      "example_translation": "Traduction de l'exemple",
      "hint": "Indice pour se souvenir",
      "tags": ["{pillar_id}", "grammar", "niveau_{level}"]
    }}
  ]
}}

Assure-toi que:
- Les exemples sont naturels et courants
- Le vocabulaire est adapte au niveau {level} (0=debutant, 5=avance)
- Chaque carte apporte une information nouvelle"""

    response = call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=8000, timeout=600)
    result = extract_json(response)
    
    if result:
        result['total_cards'] = len(result.get('cards', []))
        result['generated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    return result


def generate_verb_content(lang_code, pillar, lang_config):
    """Generate verb pillar content (conjugation tables, common verbs)."""
    
    lang_name = lang_config['name']
    pillar_name = pillar['name']
    pillar_id = pillar['id']
    level = pillar['level']
    card_count = pillar.get('cards', 30)
    
    # Language-specific conjugation info
    conj_info = {
        'es': 'presente, preterito, futuro simple',
        'it': 'presente, passato prossimo, futuro',
        'ru': 'present, past, imperative (avec aspects)',
        'tr': 'present (-yor), past (-di), future (-acak)',
        'ja': 'forme polie (-ます), forme て, passe (-ました)',
        'ko': 'forme polie (-요), forme honorifique',
        'zh': 'marqueurs aspectuels 了, 过, 会'
    }
    
    system_prompt = f"""Tu es un expert en conjugaison du {lang_name}.
Tu generes des cartes de conjugaison claires et pratiques.
Reponds UNIQUEMENT avec du JSON valide."""
    
    user_prompt = f"""Genere {card_count} flashcards pour le pilier "{pillar_name}" en {lang_name}.

Temps a couvrir: {conj_info.get(lang_code, 'present, passe, futur')}

Pour chaque verbe, cree des cartes qui montrent:
- L'infinitif et sa traduction
- Les conjugaisons principales
- Un exemple d'utilisation

Format JSON strict:
{{
  "pillar_id": "{pillar_id}",
  "language": "{lang_code}",
  "name": "{pillar_name}",
  "type": "verbs",
  "explanation": "Vue d'ensemble de la conjugaison en {lang_name}",
  "cards": [
    {{
      "front": "Conjugaison/forme verbale en {lang_name}",
      "back": "Traduction/explication en francais",
      "example": "Phrase exemple en {lang_name}",
      "example_translation": "Traduction",
      "verb_info": "infinitif: xxx, temps: yyy",
      "tags": ["{pillar_id}", "verbes", "conjugaison"]
    }}
  ]
}}

Focus sur les verbes les plus utilises au quotidien."""

    response = call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=8000, timeout=600)
    result = extract_json(response)
    
    if result:
        result['total_cards'] = len(result.get('cards', []))
        result['generated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    return result


def generate_pillar_content(lang_code, pillar, lang_config):
    """Generate content for a specific pillar."""
    
    pillar_id = pillar['id']
    category = pillar.get('category', 'grammar')
    
    # Route to appropriate generator based on category/pillar type
    if pillar_id in ['hiragana', 'katakana', 'hangul', 'cyrillic', 'pinyin']:
        return generate_writing_system_content(lang_code, pillar_id, lang_config)
    
    elif category == 'verbes' or 'verb' in pillar_id:
        return generate_verb_content(lang_code, pillar, lang_config)
    
    else:
        return generate_grammar_content(lang_code, pillar, lang_config)


def save_pillar_content(content, lang_code, pillar_id):
    """Save generated content to JSON file."""
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    content_dir = os.path.join(base_dir, 'pillar_content', lang_code)
    
    # Create directory if needed
    os.makedirs(content_dir, exist_ok=True)
    
    filepath = os.path.join(content_dir, f'{pillar_id}.json')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    
    return filepath


def generate_language(lang_code, force_regenerate=False):
    """Generate all pillar content for a language."""
    
    lang_config = get_language(lang_code)
    if not lang_config:
        print(f"[ERROR] Unknown language code: {lang_code}")
        return
    
    pillars = get_pillars_for_language(lang_code)
    lang_name = lang_config['name']
    
    print(f"\n{'='*60}")
    print(f"GENERATING CONTENT FOR {lang_name.upper()} ({lang_code})")
    print(f"{'='*60}")
    print(f"Total pillars: {len(pillars)}")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    content_dir = os.path.join(base_dir, 'pillar_content', lang_code)
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for i, pillar in enumerate(pillars):
        pillar_id = pillar['id']
        pillar_name = pillar['name']
        
        # Check if already exists
        filepath = os.path.join(content_dir, f'{pillar_id}.json')
        if os.path.exists(filepath) and not force_regenerate:
            print(f"\n[{i+1}/{len(pillars)}] {pillar_name} - SKIPPED (already exists)")
            skip_count += 1
            continue
        
        print(f"\n[{i+1}/{len(pillars)}] Generating {pillar_name}...")
        
        content = generate_pillar_content(lang_code, pillar, lang_config)
        
        if content:
            saved_path = save_pillar_content(content, lang_code, pillar_id)
            card_count = content.get('total_cards', 0)
            print(f"   -> SUCCESS: {card_count} cards saved to {saved_path}")
            success_count += 1
        else:
            print(f"   -> FAILED: Could not generate content")
            fail_count += 1
        
        # Small delay between API calls
        time.sleep(2)
    
    print(f"\n{'='*60}")
    print(f"SUMMARY FOR {lang_name}")
    print(f"{'='*60}")
    print(f"Success: {success_count}")
    print(f"Skipped: {skip_count}")
    print(f"Failed:  {fail_count}")


def main():
    """Main entry point."""
    
    print("=" * 60)
    print("PILLAR CONTENT GENERATOR")
    print(f"LLM: {LLM_MODEL} via Ollama")
    print(f"Server: {SPARK_HOST}:{OLLAMA_PORT}")
    print("=" * 60)
    
    # Check Ollama connectivity
    print("\nChecking Ollama connection...")
    available, msg = check_ollama_available()
    if available:
        print(f"  [OK] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        print(f"\nTo start Ollama on spark-8144:")
        print(f"  ssh spark-8144 'docker start legalprod-ollama'")
        print(f"\nOr override with env vars:")
        print(f"  SPARK_HOST=192.168.0.101 LLM_MODEL=gpt-oss:20b python3.11 {sys.argv[0]}")
        sys.exit(1)
    
    # Check command line args
    if len(sys.argv) > 1:
        lang_code = sys.argv[1]
        force = '--force' in sys.argv or '-f' in sys.argv
        
        if lang_code in ['--force', '-f']:
            # Generate all with force
            for lc in LANGUAGES.keys():
                generate_language(lc, force_regenerate=True)
        elif lang_code in LANGUAGES:
            generate_language(lang_code, force_regenerate=force)
        else:
            print(f"[ERROR] Unknown language: {lang_code}")
            print(f"Available: {', '.join(LANGUAGES.keys())}")
            sys.exit(1)
    else:
        # Generate for all languages
        total_pillars = sum(len(get_pillars_for_language(lc)) for lc in LANGUAGES.keys())
        print(f"\nGenerating content for all {len(LANGUAGES)} languages ({total_pillars} pillars total)")
        print("This will take a while with gpt-oss:120b.")
        print("\nYou can also run one language at a time:")
        print("  python3.11 scripts/generate_pillar_content.py <lang_code>")
        print(f"\nSupported: {', '.join(LANGUAGES.keys())}\n")
        
        input("Press Enter to continue or Ctrl+C to cancel...")
        
        for lc in LANGUAGES.keys():
            generate_language(lc, force_regenerate=False)
    
    print("\n" + "=" * 60)
    print("GENERATION COMPLETE!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run migration: python3.11 migrate_pillars.py")
    print("2. Restart Flask: python3.11 run.py")
    print("3. Visit /pillars to see your content!")


if __name__ == '__main__':
    main()

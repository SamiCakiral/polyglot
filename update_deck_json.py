import json
import re

# --- CONFIGURATION ---

INPUT_FILE = '/Users/sami/Documents/Code/anki2/card_sets/deck_italien.json'
OUTPUT_FILE = '/Users/sami/Documents/Code/anki2/card_sets/deck_italien_enriched.json'

# Liste des catégories à créer
NEW_CATEGORIES = [
    {"name": "Top 30", "color": "#f1c40f"},       # Jaune/Or
    {"name": "Verbes Irréguliers", "color": "#e74c3c"} # Rouge
]

# Liste des verbes pour chaque catégorie
VERBES_TOP_30 = [
    "Essere", "Avere", "Fare", "Dire", "Potere", "Volere", "Sapere", "Stare", "Dovere", "Vedere", 
    "Andare", "Venire", "Dare", "Parlare", "Trovare", "Sentire", "Lasciare", "Prendere", "Guardare", 
    "Mettere", "Pensare", "Passare", "Credere", "Portare", "Parere", "Tornare", "Sembrare", "Tenere", 
    "Capire", "Morire", "Chiamare", "Chiedere", "Cercare", "Entrare", "Vivere", "Aprire", "Uscire",
    "Scrivere", "Leggere", "Cadere", "Mangiare", "Bere", "Dormire"
]

VERBES_IRREGULIERS = [
    "Essere", "Avere", "Andare", "Dare", "Fare", "Bere", "Dire", "Dovere", "Piacere", "Porre", 
    "Potere", "Rimanere", "Salire", "Sapere", "Scegliere", "Sedere", "Spegnere", "Stare", 
    "Tenere", "Tradurre", "Trarre", "Uscire", "Venire", "Volere", "Morire", "Nascere", "Cadere",
    "Mettere", "Prendere", "Ridere", "Rompere", "Vedere", "Vivere"
]

# --- FONCTIONS ---

def normalize(text):
    return text.lower().strip()

def detect_verb(card):
    # Stratégie 1: Regarder dans les catégories existantes (le nom du verbe y est souvent)
    for cat in card.get('categories', []):
        if cat in VERBES_TOP_30 or cat in VERBES_IRREGULIERS or cat[0].isupper(): 
            # Simple heuristique: si la catégorie correspond à un verbe connu
            # ou commence par majuscule et n'est pas un temps grammatical
            if cat not in ["Infinitif", "Présent", "Passé", "Futur", "Imperfetto", "3 Temps", "Grammaire", "Familles"]:
                 return cat
    
    # Stratégie 2: Analyser le Front. Ex: "Io (Essere)" -> Essere
    # Regex pour capturer ce qu'il y a entre parenthèses ou au début
    match = re.search(r'\((.*?)\)', card.get('front', ''))
    if match:
        return match.group(1).split()[0] # "Essere" from "Essere" or "Essere..."

    # Cas simple: le front EST le verbe
    front = card.get('front', '').split(':')[0].strip()
    if front in VERBES_TOP_30 or front in VERBES_IRREGULIERS:
        return front
        
    return None

# --- MAIN ---

print(f"Lecture de {INPUT_FILE}...")
with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1. Ajouter les nouvelles définitions de catégories
existing_cat_names = {c['name'] for c in data.get('categories', [])}
for new_cat in NEW_CATEGORIES:
    if new_cat['name'] not in existing_cat_names:
        data['categories'].append(new_cat)
        print(f"Ajout de la catégorie globale : {new_cat['name']}")

# 2. Parcourir les cartes et ajouter les tags
count_top30 = 0
count_irreg = 0

for card in data['cards']:
    current_cats = set(card.get('categories', []))
    
    # Détecter de quel verbe il s'agit
    # On regarde si l'une des catégories existantes EST un de nos verbes cibles
    # C'est la méthode la plus fiable car tes cartes sont déjà bien taguées
    
    found_verb = None
    for cat in current_cats:
        # On normalise pour comparer (Essere == essere)
        if cat in VERBES_TOP_30 or cat in VERBES_IRREGULIERS:
             found_verb = cat
             break
    
    # Si pas trouvé dans les catégories, on essaie l'analyse du texte (fallback)
    if not found_verb:
        found_verb = detect_verb(card)

    if found_verb:
        # Check Top 30
        if found_verb in VERBES_TOP_30:
            if "Top 30" not in current_cats:
                card['categories'].append("Top 30")
                count_top30 += 1
        
        # Check Irréguliers
        if found_verb in VERBES_IRREGULIERS:
            if "Verbes Irréguliers" not in current_cats:
                card['categories'].append("Verbes Irréguliers")
                count_irreg += 1

print(f"Traitement terminé.")
print(f"Cartes taguées 'Top 30': {count_top30}")
print(f"Cartes taguées 'Verbes Irréguliers': {count_irreg}")

# 3. Sauvegarder
print(f"Sauvegarde dans {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Fermé.")

# Polyglot – Application d'apprentissage de langues

Application web Flask pour l'apprentissage de langues étrangères, avec répétition espacée (SM-2 / FSRS), exercices générés par IA, et synthèse vocale.

## Pourquoi ce projet ?

En voulant apprendre de nouvelles langues, j'avais besoin d'une application avec des fonctionnalités précises que je ne trouvais nulle part — alors je me suis dit : autant la coder moi-même, et l'améliorer au fur et à mesure.

Le projet a commencé comme un simple outil de révision de vocabulaire avec des flashcards. Mais j'ai vite réalisé que mémoriser des mots isolés ne suffit pas pour vraiment apprendre une langue. J'ai donc ajouté des exercices structurés (traduction, construction de phrases, quêtes d'écriture), puis des cours rapides pour assimiler les spécificités de chaque langue, et enfin une estimation du niveau CECRL avec un LLM qui corrige en temps réel. Ce qui devait être un petit side project est devenu une vraie plateforme d'apprentissage personelle.

## Fonctionnalités

- **Flashcards** avec algorithmes de répétition espacée (SM-2 et FSRS)
- **Exercices adaptatifs** générés par LLM local (structures de phrases, traduction, quêtes d'écriture)
- **Profils d'apprentissage** avec niveaux CECRL (A1→C2)
- **Piliers thématiques** : vocabulaire, grammaire, compréhension, expression
- **Synthèse vocale** (TTS) via Qwen3-TTS
- **Chat pédagogique** avec un "Prof" IA contextuel
- **Programmes d'entraînement** personnalisés avec suivi de progression
- **Évaluations CECRL** pour mesurer le niveau
- **Multi-langues** : italien, japonais, turc, et extensible

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/<user>/polyglot.git
cd polyglot

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

## Configuration

```bash
# Copier le fichier de configuration
cp .env.example .env

# Éditer avec vos valeurs (adresses LLM, etc.)
nano .env
```

Les principaux paramètres :

| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé secrète Flask | `dev-secret-key-change-in-prod` |
| `LLM_BACKEND` | Backend LLM (`lmstudio`, `vllm`, `ollama`) | `lmstudio` |
| `LMSTUDIO_HOST` | Adresse du serveur LM Studio | `localhost` |
| `SPARK_HOST` | Adresse du serveur GPU (vLLM/Ollama/TTS) | `localhost` |

Voir [`.env.example`](.env.example) pour la liste complète.

## Lancement

```bash
source venv/bin/activate
python run.py
```

L'application démarre sur [http://localhost:9001](http://localhost:9001).

## Structure du projet

```
Polyglot/
├── app/                        # Application Flask
│   ├── __init__.py             # Factory + blueprints
│   ├── models.py               # Modèles SQLAlchemy
│   ├── llm_service.py          # Service LLM (LM Studio / vLLM / Ollama)
│   ├── tts_service.py          # Service TTS (Qwen3-TTS)
│   ├── sm2.py                  # Algorithme SM-2
│   ├── fsrs.py                 # Algorithme FSRS
│   ├── grades.py               # Système de notation
│   ├── exercise_generator.py   # Générateur d'exercices
│   ├── assessment_generator.py # Générateur d'évaluations CECRL
│   ├── gym_engine.py           # Moteur d'entraînement
│   ├── pillar_config.py        # Configuration des piliers
│   ├── cecr_config.py          # Configuration CECRL
│   ├── prompt_templates.py     # Prompts pour le LLM
│   ├── routes/                 # Blueprints Flask
│   ├── templates/              # Templates Jinja2
│   └── static/                 # CSS, JS, images
├── config.py                   # Configuration Flask
├── run.py                      # Point d'entrée
├── requirements.txt            # Dépendances Python
├── .env.example                # Variables d'environnement (template)
├── docker/                     # Config Docker (TTS)
├── tests/                      # Tests unitaires
├── scripts/                    # Scripts utilitaires (migrations, debug)
├── card_sets/                  # Jeux de cartes JSON
└── pillar_content/             # Contenu pédagogique généré
```

## Configurer un LLM local

L'application génère les exercices, corrections et conversations via un **LLM local** (aucune API cloud requise). Trois backends sont supportés avec un système de fallback automatique :

### Option 1 : LM Studio (recommandé pour débuter)

1. Télécharger [LM Studio](https://lmstudio.ai/) et installer un modèle (ex: Qwen, Llama, Mistral)
2. Activer le serveur local dans LM Studio (onglet "Local Server")
3. Configurer le `.env` :

```env
LLM_BACKEND=lmstudio
LMSTUDIO_HOST=localhost
LMSTUDIO_PORT=1234
```

### Option 2 : Ollama

1. Installer [Ollama](https://ollama.com/) et télécharger un modèle :

```bash
ollama pull llama3.2
ollama serve
```

2. Configurer le `.env` :

```env
LLM_BACKEND=ollama
SPARK_HOST=localhost
OLLAMA_PORT=11434
```

### Option 3 : vLLM (GPU dédié)

Pour les machines avec un GPU NVIDIA — meilleure performance sur les contenus complexes.

```bash
pip install vllm
vllm serve openai/gpt-oss-20b --port 8000
```

```env
LLM_BACKEND=vllm
SPARK_HOST=localhost
VLLM_PORT=8000
```

### Chaîne de fallback

Si le backend principal ne répond pas, l'application tente automatiquement le suivant :

**LM Studio** → **vLLM** → **Ollama**

Cela garantit que l'application reste fonctionnelle même si un service est temporairement indisponible.

## Licence

Projet personnel – Sami

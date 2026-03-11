# Anki2 – Application d'apprentissage de langues

Application web Flask pour l'apprentissage de langues étrangères, avec répétition espacée (SM-2 / FSRS), exercices générés par IA, et synthèse vocale.

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
git clone https://github.com/<user>/anki2.git
cd anki2

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
| `LMSTUDIO_HOST` | Adresse du serveur LM Studio | `192.168.0.100` |
| `SPARK_HOST` | Adresse du serveur GPU (vLLM/Ollama/TTS) | `spark-8144.local` |

Voir [`.env.example`](.env.example) pour la liste complète.

## Lancement

```bash
source venv/bin/activate
python run.py
```

L'application démarre sur [http://localhost:9001](http://localhost:9001).

## Structure du projet

```
anki2/
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

## Backends LLM

L'application utilise des LLMs locaux via une API OpenAI-compatible, avec chaîne de fallback :

1. **LM Studio** (principal) – serveur local/NAS
2. **vLLM** (fallback) – serveur GPU pour contenu complexe
3. **Ollama** (dernier recours)

## Guides

- [`LOCAL_LLM_GUIDE.md`](LOCAL_LLM_GUIDE.md) – Configuration détaillée des LLMs locaux
- [`DOCKER_GPU_GUIDE.md`](DOCKER_GPU_GUIDE.md) – Déploiement Docker avec GPU

## Licence

Projet personnel – Sami

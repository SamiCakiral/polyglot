# Polyglot V2

Polyglot V2 est une application locale d'apprentissage des langues. Le MVP
couvre le français vers l'italien : diagnostic, fondations, modules, sprint
quotidien adaptatif, cartes FSRS, Word Bank personnelle, entraînement libre,
progression sur quatre axes, évaluations et atelier éditorial.

La V1 reste disponible dans l'historique via le tag `v1.0.0-legacy`. Aucune
donnée V1 n'est migrée.

## Démarrage local

Prérequis : Docker Desktop, au moins 4 Go libres, et macOS pour la voix TTS
italienne `Alice`. LM Studio est facultatif pour apprendre ; il devient requis
uniquement pour la génération auteur.

```bash
./scripts/local-up.sh
```

L'interface est ensuite disponible sur <http://127.0.0.1:9001>. Le premier
démarrage crée un fichier privé `.local/runtime.env`, démarre PostgreSQL,
applique les migrations et construit le frontend et le backend.

```bash
./scripts/local-status.sh
./scripts/local-down.sh
```

Pour la génération locale, démarrer le serveur LM Studio sur le port `1234`
avec le modèle exact `qwen/qwen3.6-35b-a3b`. Une indisponibilité est affichée
comme un échec terminal : aucun retry ni changement de modèle n'est effectué.

## Développement

Versions verrouillées : Python `3.13.11`, Node `22.18.0` et pnpm `11.16.0`.

```bash
cd backend
uv sync --locked
uv run ruff check src tests
uv run mypy src
uv run pytest tests -q

cd ../frontend
pnpm install --frozen-lockfile
pnpm generate:api
pnpm lint
pnpm typecheck
pnpm test --run
pnpm build
pnpm exec playwright test
```

L'OpenAPI versionnée est dans `contracts/openapi/v1.json`. Le client TypeScript
est généré à partir de ce fichier ; les fichiers de `frontend/src/generated` ne
doivent pas être modifiés à la main.

## Architecture

- `backend/` : FastAPI, domaines métier, PostgreSQL et migrations Alembic.
- `frontend/` : React responsive et client API généré.
- `contracts/` : OpenAPI, registres, événements et contrats des 11 outils.
- `fixtures/` : données synthétiques déterministes et oracles.
- `docs/v2/` : architecture produit et plan W00-W19.
- `docs/runbooks/` : exploitation, sauvegarde et restauration locales.
- `docs/evidence/` : preuves techniques versionnées.

PostgreSQL est l'unique source de vérité. Les réponses et preuves pédagogiques
sont immuables ; les projections peuvent être reconstruites. Les outils auteur
créent uniquement des brouillons. La validation, l'approbation et la publication
restent des décisions humaines séparées.

## Sécurité et données

Les secrets locaux ne sont jamais versionnés. Les médias restent privés et sont
servis par URL signée. Les commandes utilisent idempotence, contrôle de version,
cookie sécurisé, protection CSRF et autorisation propriétaire. Les journaux
locaux sont structurés et limités aux métadonnées opérationnelles.

La procédure vérifiée de sauvegarde/restauration est décrite dans
[`docs/runbooks/local-backup-restore.md`](docs/runbooks/local-backup-restore.md).
La suppression et l'export sont accessibles dans les préférences de l'application.

## Limites MVP

Le professeur conversationnel permanent, le STT, le déploiement cloud et le
canary sont post-MVP. Sans STT ni revue humaine, l'expression orale reste
`not_evaluable` et n'attribue jamais de faux crédit.

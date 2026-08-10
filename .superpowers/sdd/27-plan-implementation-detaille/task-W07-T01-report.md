# W07-T01 - Rapport d'incrément

## Périmètre

- Base observée avant W07 : `dd72c01`, puis commits W11/correctifs concurrents sans fichier W07.
- RED : `7e2f9ae` (`test(w07): define FSRS parity contract`).
- GREEN : `d3e708d` (`feat(w07): add pinned FSRS scheduler adapter`).
- Formatage tests : `1aefd7b` (`style(w07): normalize FSRS test imports`).
- RED correction : `0c2dee0` (`test(w07): expose incomplete FSRS provider bounds`).
- GREEN correction : `c545973` (`fix(w07): close FSRS temporal and probability bounds`).
- Aucun push.

## SPK-FSRS

- Python `3.13.11`.
- Paquet officiel `fsrs==6.3.1`.
- Décision : `adopt`.
- Histoires : prompt neuf, deux directions, `again/good/good/easy`, same-day,
  review anticipée/tardive, reset, fusion par rejeu trié et fuseau normalisé UTC.
- Hash SHA-256 du lock :
  `fc227db2f7afe96473da3107744394c2fbbb338a4b7b7774d1c2606edfbb38fe`.
- Preuves : `docs/evidence/W07/SPK-FSRS.md` et `spk-fsrs-raw.json`.

## Cycle TDD

### RED

Commande dans `/tmp/polyglot-w07-src/backend` :

```text
python -m pytest tests/spikes/memory/test_spk_fsrs.py -q
python -m pytest tests/unit/memory/test_fsrs_adapter.py \
  tests/property/memory/test_fsrs_properties.py -q
```

Résultat : spike `2 passed`; contrat Polyglot en échec de collecte sur
`ModuleNotFoundError: polyglot.modules.lexicon.memory`, cause attendue.

### GREEN

```text
python -m pytest tests/spikes/memory tests/unit/memory tests/property/memory -q
python -m ruff check src/polyglot/modules/lexicon/memory \
  tests/unit/memory tests/property/memory tests/spikes/memory
python -m mypy src/polyglot/modules/lexicon/memory
```

Résultat initial : `17 passed`, Ruff sans erreur, mypy strict sans erreur.

Après revue indépendante, un RED ciblé a reproduit deux défauts : absence de
`temporal_cases` dans la preuve (`KeyError`) et récupérabilité `1.5` acceptée
(`DID NOT RAISE`). Le GREEN exécute désormais les reviews anticipée/retardée et
le changement `Europe/Rome -> UTC` contre des goldens constants, et rejette toute
récupérabilité fournisseur hors `[0,1]` par `dependency_unavailable`.

Matrice après correction : `19 passed in 0.19s`, Ruff sans erreur, mypy strict
sans erreur, `uv lock --check --offline` réussi et `uv sync --frozen --offline`
réussi.

Régression autonome élargie dans une archive exacte de HEAD sous `/tmp` :
`pytest tests/unit tests/property -q` -> `285 passed in 2.78s`.

Une tentative incluant tous les contrats n'est pas retenue comme preuve : les
tests d'identité demandaient PostgreSQL et les contrats d'infrastructure
demandaient les fichiers racine volontairement absents de cette archive.

Preuve lock hors réseau : un environnement `/tmp` a été peuplé une fois via le
lock gelé, supprimé, puis recréé avec `uv sync --frozen --offline`; import
`fsrs==6.3.1` vérifié. Aucun environnement sous `Documents` n'a été utilisé.

## Frontières vérifiées

- Le domaine et le port n'importent pas `fsrs`.
- L'adaptateur ne retourne aucun objet fournisseur.
- Aucune formule FSRS n'est recodée.
- Le fuzz du fournisseur est rendu déterministe sous verrou et état RNG restauré.
- Une panne fournisseur produit `dependency_unavailable`, sans transition ni fallback.
- Les dates sont normalisées UTC et les décimaux persistables ne sont pas exposés
  comme `float` métier.
- `after_24h` ne peut avancer une échéance sous 24 heures.
- Les plafonds H0-H4 et `ambiguous|not_evaluable` sont explicites.

## Gates

- Revue indépendante T01 initiale : `FAIL technique ciblé`, rapport
  `task-W07-T01-review.md`.
- Correctifs : appliqués dans `0c2dee0..c545973`; rerevue indépendante
  `task-W07-T01-rereview.md` : `PASS technique`.
- `P-LING` : `pending_human`, non fermé par W07-T01.

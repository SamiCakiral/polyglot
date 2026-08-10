# W07-T02 - Rapport de correction après revue

## Périmètre

Correction de tous les findings métier `P0`, `P1` et `P2` de la revue initiale.
Le finding W11 hors périmètre est exclu. Aucun SQL, HTTP, module W06/W08+,
frontend ou registre W00 n'a été modifié. Aucun push n'a été effectué.

## Cycles TDD

### Certification et invariants

- RED `6621700` : `test(w07): expose unsafe memory review facts`.
- Preuve RED : `25 failed, 3 passed`; l'objet de commande ne portait pas encore
  la certification épinglée et les validations attendues étaient absentes.
- GREEN `b0e4c89` : `fix(w07): bind reviews to pinned prompt facts`.
- Preuve GREEN : `28 passed`; Ruff et mypy strict passés sur les fichiers ciblés.

### Rejeu causal et faits de reprise

- RED `2432bd3` : `test(w07): define causal memory replay`.
- Preuve RED : deux erreurs de collecte sur l'absence de `ResumeMemoryPrompt`,
  interface append-only attendue par les nouveaux oracles unitaires/propriétés.
- GREEN `54532b3` : `fix(w07): replay causal scheduler facts`.
- Preuve GREEN élargie : `62 passed in 1.00s` sur spikes, unitaires et propriétés
  mémoire ; Ruff sans erreur ; mypy strict sans erreur sur 8 fichiers source.

### Continuité des chaînes après rerevue

- RED `378acae` : `test(w07): expose disconnected replay chains`.
- Preuve RED : `4 failed, 43 passed`; une transition auto-cohérente mais
  déconnectée et un reset source antérieur à la création étaient acceptés.
- GREEN `e64934b` : `fix(w07): enforce replay chain continuity`.
- Preuve GREEN élargie : `66 passed in 1.15s`; Ruff sans erreur ; mypy strict
  sans erreur sur 8 fichiers source.

## Corrections livrées

- certification non vide reliée à l'opération `recall`, au protocole et à sa
  révision, ainsi qu'à la révision de cible du prompt ;
- identité scheduler/version/parameter set/policy revision épinglée au prompt et
  à chaque fait de scheduling ;
- résolveur de replay exact et fail-closed avec `dependency_unavailable` si une
  version persistée est absente ou incohérente ;
- faits append-only `MemoryScheduleResumption` distincts pour resume et restore,
  avec état avant/après et checkpoint causal ;
- reviews et resets chaînés par `previous_checkpoint` ; ordre à instant égal
  dérivé de la chaîne causale, jamais de l'UUID seul ;
- review ou fait de calendrier backdaté refusé avant mutation ;
- fusion conservant tous les faits sources, dédupliquant uniquement leurs effets
  et rejouant reviews, resets et reprises avant la frontière de fusion ;
- validation structurelle de l'ownership, des lignées, identités scheduler,
  compteurs, chronologie et transitions persistées ;
- lignée enrichie par la date de création et la clé moteur/politique source ;
  chaque chaîne est initialisée depuis cette origine, puis chaque `state_before`
  doit égaler l'état obtenu au checkpoint causal précédent ;
- propriétés Hypothesis ajoutées pour suspension, reprise/rebuild, fusion avec
  reset et doublon, incompatibilité sans effet, terminalité, ordre causal,
  versions de politique et indépendance des directions après fusion.

## Reproductibilité hors réseau

Exécuté dans `/tmp/polyglot-w07-t02-fix-red2/backend` avec Python `3.13.11` :

```text
uv lock --check --offline
UV_PROJECT_ENVIRONMENT=/tmp/polyglot-w07-lock-env uv sync --frozen --offline --no-install-project
python -m pytest -s -p no:cacheprovider tests/spikes/memory tests/unit/memory tests/property/memory -q
python -m ruff check --no-cache src/polyglot/modules/lexicon/memory tests/spikes/memory tests/unit/memory tests/property/memory
python -m mypy --strict src/polyglot/modules/lexicon/memory
```

Résultats : lock résolu hors réseau, environnement audité, `fsrs` confirmé en
version `6.3.1`, 66 tests passés, Ruff et mypy strict passés.

## Gates

- Revue indépendante initiale de correction : `FAIL` documenté dans
  `task-W07-T02-rereview.md`.
- Revue indépendante finale au checkout exact `e64934b` : `PASS` technique,
  zéro finding `P0|P1|P2`, `48` tests unitaires et `15` propriétés passés,
  Ruff et mypy strict verts. Verdict documenté dans
  `task-W07-T02-final-review.md`.
- W07-T03 : autorisé après commit des preuves T02.
- `P-LING` : `pending_human`; aucune preuve machine ne le clôt.

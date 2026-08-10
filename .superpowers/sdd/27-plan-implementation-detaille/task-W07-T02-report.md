# W07-T02 - Rapport d'incrément

## Périmètre

- RED initial : `8cc2a6a` (`test(w07): define memory prompt lifecycle`).
- GREEN initial : `f43d32d` (`feat(w07): implement append-only memory lifecycle`).
- RED certification : `6621700` (`test(w07): expose unsafe memory review facts`).
- GREEN certification : `b0e4c89` (`fix(w07): bind reviews to pinned prompt facts`).
- RED rejeu causal : `2432bd3` (`test(w07): define causal memory replay`).
- GREEN rejeu causal : `54532b3` (`fix(w07): replay causal scheduler facts`).
- RED continuité : `378acae` (`test(w07): expose disconnected replay chains`).
- GREEN continuité : `e64934b` (`fix(w07): enforce replay chain continuity`).
- Zones : domaine, application, rebuild, exports et tests T02 uniquement.
- Aucun SQL, HTTP, W06, W08+, frontend ou push.

## Cycle TDD

Le RED a échoué pendant la collecte sur l'absence de
`polyglot.modules.lexicon.memory.application`, cause attendue avant tout code
produit T02.

Le premier GREEN fonctionnel a produit `20 passed, 1 failed`. L'échec révélait
un `computed_at` de fusion basé sur l'heure de commande tandis que le rebuild
utilisait le dernier fait causal. Le produit a été corrigé pour rendre la
projection reconstruite identique, puis la matrice a été rejouée.

## Matrice GREEN

Dans `/tmp/polyglot-w07-t02/backend`, Python `3.13.11` :

```text
python -m pytest tests/spikes/memory tests/unit/memory tests/property/memory -q
python -m ruff check src/polyglot/modules/lexicon/memory \
  tests/spikes/memory tests/unit/memory tests/property/memory
python -m mypy src/polyglot/modules/lexicon/memory
```

Résultat : `40 passed in 0.60s`, Ruff sans erreur, mypy strict sans erreur sur
8 fichiers source.

## Invariants couverts

- statut produit distinct de `memory_state` ;
- directions et MWE/composants représentables par prompts séparés ;
- review seulement pour rappel certifié, sans révélation/exposition/incidence ;
- plafonds de note H0-H4 et aucune mutation sur `ambiguous|not_evaluable` ;
- reviews, resets et lignées append-only ;
- suspension neutre et reprise sans `again` implicite ;
- reset conservant les faits et ouvrant une projection `new` ;
- archive réversible, restore fermé si révision absente, delete avec réauth ;
- `superseded|deleted` terminaux ;
- fusion compatible causale et dédupliquée, incompatible sans effet partiel ;
- rebuild déterministe depuis reviews/resets/lignées ;
- aucune facette, preuve, dette ou maîtrise pédagogique produite.

## Revue finale

La revue indépendante finale a inspecté séparément les huit commits W07-T02 au
checkout exact `e64934b`. Elle ne relève aucun finding `P0`, `P1` ou `P2`.

```text
pytest tests/unit/memory -q       -> 48 passed
pytest tests/property/memory -q   -> 15 passed
ruff check                        -> All checks passed
mypy --strict                     -> Success: no issues found in 8 source files
```

## Gates

- Revue indépendante T02 : `PASS` technique, documentée dans
  `task-W07-T02-final-review.md`.
- W07-T03 : autorisé.
- `P-LING` : `pending_human`.

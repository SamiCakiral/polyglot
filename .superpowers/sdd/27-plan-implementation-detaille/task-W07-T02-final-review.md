# W07-T02 - Revue indépendante finale

## Périmètre et méthode

- Commit relu : `e64934bdd66a8e49a773a70df1c6d4f0062c8294`.
- Clone détaché propre : `/tmp/polyglot-v2-w07-t02-e64934b`.
- Inspection limitée aux commits W07-T02 explicitement demandés : `8cc2a6a`,
  `f43d32d`, `6621700`, `b0e4c89`, `2432bd3`, `54532b3`, `378acae` et
  `e64934b`, uniquement avec `git show`. Aucun range ancêtre ni changement W11
  n'a été attribué à ce lot.
- Documents lus : brief W07, revue initiale, rerevue et rapport de correction.

## Findings

Aucun finding bloquant ou résiduel dans le périmètre W07-T02.

| Contrôle | Résultat |
|---|---|
| Certification | Épinglée à `recall`, au protocole et à sa révision, ainsi qu'à la révision de cible du prompt ; une divergence ne crée pas de review. |
| Scheduler et politique | Identité et politique épinglées au prompt et aux faits ; le resolver ne résout que la clé persistée et échoue en `dependency_unavailable` sans fallback. |
| Resume / restore | Deux faits `MemoryScheduleResumption` append-only, avec état avant/après, checkpoint causal et replay vérifié. |
| Reset, merge, replay et reprise | Les reviews, resets et reprises sont chaînés, rejoués dans l'ordre causal et conservés lors d'une fusion ; seuls les effets dupliqués sont dédupliqués. |
| Continuité `state_before` | Chaque review/reprise doit partir de l'état obtenu au checkpoint causal précédent ; les transitions isolément valides mais déconnectées sont rejetées. |
| Backdating et timestamps égaux | Les faits locaux et les sources de fusion antérieurs à leur création, au checkpoint ou à la frontière de fusion sont refusés ; l'ordre d'un même instant suit la chaîne causale. |
| Ownership, lineage et compteurs | Agrégat, prompts sources, lineage, UUID, identités scheduler et compteurs sont validés ; les faits non possédés, branches et checkpoints dupliqués sont rejetés. |
| Hypothesis | Propriétés présentes pour replay causal, indépendance des directions, reset, suspension/reprise, fusion/déduplication, incompatibilité, terminalité, versions et corruptions adversariales. |
| Limites métier | Aucun calcul de maîtrise ni fallback scheduler introduit. |
| Write set | Les huit commits ne touchent que le write set T02 : domaine/application/rebuild/init et tests unitaires/propriétés mémoire. |

## Vérifications exécutées

Depuis `/tmp/polyglot-v2-w07-t02-e64934b/backend`, après `uv sync --frozen --offline` :

```text
uv run pytest tests/unit/memory -q       -> 48 passed in 1.16s
uv run pytest tests/property/memory -q   -> 15 passed in 2.32s
uv run ruff check ...                    -> All checks passed
uv run mypy --strict ...                 -> Success: no issues found in 8 source files
```

## Verdict

`PASS` technique pour W07-T02 au commit `e64934b`.

`P-LING` reste `pending_human` conformément au brief : cette revue ne constitue
pas une validation linguistique ni une acceptation des lots W07 suivants.

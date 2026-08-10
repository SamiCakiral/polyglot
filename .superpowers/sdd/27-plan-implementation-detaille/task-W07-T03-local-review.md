# W07-T03 - Revue technique locale

## Perimetre

- Commit relu : `97bf185`.
- Migration `0007_memory`, repository/service PostgreSQL et tests d'integration.
- Revue realisee localement sans sous-agent, conformement a la demande du
  proprietaire du projet.

## Findings

Aucun finding technique bloquant ne reste ouvert dans le perimetre T03.

| Controle | Resultat |
|---|---|
| Source de verite | Reviews, resets, reprises et lignees sont append-only ; le chargement et la reconstruction relisent ces faits plutot que leur copie dans l'agregat mutable. |
| Divergence | Un identifiant de fait rejoue avec un payload different produit `idempotency_conflict` et ne remplace pas l'original. |
| Projection | `MemoryScheduleState` est mutable, versionnee et reconstruite avec compare-and-swap. |
| Atomicite | Prompt, projection, recu, evenement et outbox partagent la transaction ; crash avant commit annule tout, crash apres commit rejoue le resultat. |
| Idempotence | Creation rejouee 100 fois : un prompt, un recu, un evenement et un message outbox. |
| Faux credit | Une review non certifiee conserve un recu idempotent mais ne cree ni review, ni evenement pedagogique, ni nouvelle projection. |
| Concurrence | Deux reviews sur la meme version produisent un succes et un `version_conflict`. |
| Isolation | RLS forcee sur les sept tables personnelles ; lecture, enumeration et mutation croisees refusees. |
| Migration | Upgrade, downgrade vers `0006`, nouvel upgrade, tete unique et absence de derive Alembic verifies. |

## Preuves executees

Environnement : Python 3.13.11, PostgreSQL local reel, roles migration/runtime
separes.

```text
pytest tests/unit/memory tests/property/memory tests/integration/memory -q
-> 83 passed in 2.97s

ruff check migrations/env.py migrations/versions/0007_memory.py \
  src/polyglot/modules/lexicon/memory tests/unit/memory \
  tests/property/memory tests/integration/memory
-> All checks passed

mypy --strict src/polyglot/modules/lexicon/memory/persistence.py
-> Success: no issues found in 1 source file

alembic downgrade 0006 && alembic upgrade head
-> success

alembic check
-> No new upgrade operations detected
```

## Verdict

`PASS` technique local pour W07-T03 au commit `97bf185`.

Les gates pedagogique et donnees humaines restent `pending_human`. Les routes,
la requete due, `FX-MEMORY` et le replay x100 de T04 ne sont pas couverts par ce
verdict.

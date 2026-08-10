# W03 - Fix round 3

## Verdict

**PASS W03.** Les deux bloquants de `task-W03-final-rereview.md` sont fermes
par des cycles TDD RED/GREEN distincts et verifies sur PostgreSQL 17.10.

## P0 - Stimuli normatifs distincts

Le volume artificiel fonde sur `trial_ordinal` a ete supprime du contrat HTTP,
de l'application et de la migration `0004`. Une mesure correspond desormais a
une unique revision d'item publiee; PostgreSQL impose l'unicite
`(foundation_run_id, session_id, item_revision_id)`.

Le catalogue italien certifie publie maintenant 32 revisions d'item :

- 10 stimuli `ITF-F1-01*` de discrimination grapheme-son, avec 10 IDs et 10
  oracles distincts;
- 10 stimuli `ITF-F1-02*` de lecture ciblee, avec 10 IDs et 10 oracles
  distincts;
- 5 stimuli `ITF-F5-02*` d'echange de survie, avec 5 IDs et 5 oracles
  distincts;
- les 7 autres items F1-F5 executes une fois.

Les checksums de chaque revision et les empreintes des bundles
`FX-CATALOGUE-IT` et `FX-IT-FOUND` ont ete recalcules. Les contrats prouvent
les cardinalites, l'unicite des revisions et l'unicite des oracles. Une session
complete soumet exactement 32 revisions distinctes; repeter une revision ne
peut plus augmenter un denominateur.

## P1 - Finalisation idempotente

`CompleteFoundationGate` reserve ou relit maintenant son recu apres ownership
mais avant les preconditions mutables de version, statut et expiration.

- Un replay exact apres une decision `interrupted` retourne le meme corps et
  le meme ETag sans nouvelle mesure, decision ou version.
- Un replay exact apres une gate `completed` retourne le meme corps et le meme
  ETag sans nouvel evenement ni message outbox.
- La meme cle avec un payload different retourne `idempotency_conflict`, meme
  apres la premiere mutation.
- Le parcours de deux sessions conserve exactement 64 mesures, 2 resultats de
  gate, 2 recus de commande et 1 evenement/outbox de passage.

## Commits TDD

- `b41e85d` RED : exige 10/10/5 revisions et oracles distincts.
- `682d965` GREEN : publie les stimuli certifies et supprime l'ordinal
  artificiel.
- `8b4bf33` RED : exige le replay apres interruption et passage, ainsi que le
  conflit de payload.
- `58bf364` GREEN : lit le recu avant les preconditions mutables et rejoue sans
  effet.

## Verification

Execution depuis le clone `/tmp/polyglot-w03-r2-final` contre le cluster local
dedie `/tmp/polyglot-w03-r2-pgdata`, PostgreSQL 17.10, port 55439.

```text
Tests W03 unit/property/contract/integration    38 passed in 3.49s
Ruff W03                                       All checks passed
mypy W03                                       Success: 8 source files
Alembic head -> base -> head                    passed
Alembic check                                  No new upgrade operations detected
OpenAPI export --check                         passed
```

## Limites et livraison

- La revue linguistique des fixtures reste `pending_human`; aucun credit n'est
  derive d'une evaluation humaine absente.
- Aucun W05, frontend ou travail concurrent n'a ete modifie.
- Aucun push n'a ete effectue.

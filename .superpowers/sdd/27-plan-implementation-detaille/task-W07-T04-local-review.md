# W07-T04 - Revue technique locale finale

## Perimetre

- RED : `16c3871`.
- GREEN relu : `89a84fb`.
- Revue et implementation realisees sans sous-agent.
- Surface : neuf commandes memoire, requete due, replay x100, `FX-MEMORY`,
  OpenAPI et branchement runtime.

## Findings

Aucun finding technique bloquant ne reste ouvert dans W07-T04.

| Controle | Resultat |
|---|---|
| Contrats HTTP | Authentification cookie, Origin, CSRF et `Idempotency-Key` sur les neuf commandes ; `If-Match` sur chaque ressource existante ; payloads fermes. |
| Idempotence | Verrou transactionnel PostgreSQL par acteur/commande/cle ; vingt creations simultanees de meme corps donnent un effet. |
| Transitions | Suspend, resume, reset, archive, restore et delete persistent statut, faits, projection, recu, evenement et outbox. |
| Suppression | Reauthentification recente verifiee sur la session serveur ; date future refusee comme preuve recente. |
| Restauration | Le client ne peut pas declarer une revision disponible ; le backend interroge les revisions publiees du catalogue. |
| Fusion | Sources uniques et versions attendues obligatoires ; sources supersedees ; reviews et lignees rechargeables depuis les faits append-only. |
| File due | Profil isole par RLS, cutoff explicite, ordre `(due_at,prompt_id)`, limite 100, curseur opaque stable et curseur hostile rejete. |
| Replay | Meme historique, ordre, moteur, politique et horloge rejoues 100 fois donnent la meme projection et la meme due. |
| Fixture | `FX-MEMORY` epingle FSRS 6.3.1, politique, horloge, historique, empreinte et oracle final ; aucune dependance reseau. |
| Contrat partage | OpenAPI regenere, valide contre le registre et client TypeScript regenere/compile. |

## Preuves W07

```text
pytest tests/unit/memory tests/property/memory tests/integration/memory \
  tests/contract/memory tests/contract/platform/test_openapi.py -q
-> 102 passed in 13.11s

ruff check [perimetre W07]
-> All checks passed

mypy --strict src/polyglot/modules/lexicon/memory \
  src/polyglot/interfaces/http/routes/memory.py \
  src/polyglot/interfaces/http/app.py
-> Success: no issues found in 12 source files

alembic check
-> No new upgrade operations detected

alembic heads
-> 0007_memory (head)

export_openapi --check contracts/openapi/v1.json
-> success

pnpm generate:api && pnpm typecheck && pnpm lint
-> success (Node 24 local, avertissement car le projet epingle Node 22.18)
```

## Matrice globale segmentee

```text
collection       -> 749 tests
contract         -> 172 passed
unit             -> 293 passed
property         -> 51 passed
integration      -> 222 verifies, dont les 8 controles retention relances avec le role dedie
spikes/performance -> 9 passed, 2 skipped d'infrastructure
mypy src         -> 100 source files sans erreur
```

Le `ruff check .` backend global conserve 63 findings historiques dans
`0001_platform.py`, `0004_language_profiles.py` et `0005_content.py`. Aucun ne
provient de W07 ; ils ne sont pas corriges dans ce lot pour eviter une reecriture
hors perimetre des migrations acceptees.

## Verdict

`PASS` technique local pour W07 au commit `89a84fb`.

Les approbations humaines pedagogie et donnees restent `pending_human` ; la
fixture synthetique ne les remplace pas.

# W05 - Fix round 3

Date : 2026-08-10

## Verdict

**PASS technique.** Tous les constats de `task-W05-final-review.md` sont fermes
par RED/GREEN et rejoues sur PostgreSQL 17 dans un clone exact. `P-LING` reste
`pending_human` et ne fait pas partie de l'acceptation technique.

Commits TDD :

- RED : `cf2e502` (`test(w05): expose final security gaps`) ;
- GREEN : `e3dee18` (`fix(w05): enforce human pack-scoped editing`).

Aucun push n'a ete effectue.

## P0 - Commandes strictement humaines

`content.begin_command` refuse `actor_type=service` pour les six commandes.
Le contexte SQL lie desormais le receipt, l'acteur `account`, la session et le
pack. L'ouverture exige :

- un receipt `started` dont l'acteur correspond au compte de la session ;
- une session W02 active et non revoquee ;
- la preuve brute de session, verifiee par SHA-256 contre
  `identity.auth_sessions.session_fingerprint` et jamais stockee dans W05 ;
- un role present dans le snapshot de session ;
- une affectation editoriale active `author|reviewer|admin` sur le pack ;
- une authentification recente pour `PublishContentRevision`.

Le controle differe impose un receipt `succeeded`, exactement un evenement
canonique porte par le meme acteur humain, exactement un evenement total et une
outbox. Les tests PostgreSQL couvrent les six types avec `service`, une session
d'un autre compte, une preuve forgee, une portee absente et une reauth ancienne.

## P0 - Rapports et manifestes scelles

Un rapport est insere `running`, recoit ses findings ordonnes, puis est scelle
dans la meme commande. PostgreSQL calcule et persiste le nombre de findings et
le checksum canonique. Le scellement refuse :

- `passed` avec un finding `blocking` ou `human_required` ;
- `failed` sans finding bloquant ou avec controle humain ;
- `human_required` sans finding correspondant ;
- des ordinaux non contigus.

Apres scellement, tout INSERT/UPDATE/DELETE est refuse, y compris dans la meme
transaction. Les manifestes portent de meme un `entry_count` ; la transition
vers `published` exige le nombre exact et des ordinaux complets. Une entree
ajoutee apres publication, meme dans la commande active, est refusee.

## T03 - Portee pack et API

`content_items.pack_id` rattache chaque lignee a un pack W04 publiable. Les
affectations editoriales sont explicites et le runtime ne peut pas les modifier.
La portee est verifiee par le service avant reservation/rejeu, puis de nouveau
par le contexte SQL pour chaque mutation.

La matrice HTTP couvre les six commandes et les quatre lectures :

- auteur hors pack : creation, revision et validation refusees ;
- reviewer hors pack : approbation et lectures refusees ;
- admin hors pack : publication, retrait et lectures refusees ;
- auteur, reviewer et admin affectes : commandes et lectures autorisees selon
  leur politique de role ;
- la liste hors portee reste vide et les lectures unitaires retournent 404.

Les controles existants Origin, CSRF, session, `Idempotency-Key`, `If-Match`,
pagination et Problem Details restent verts. OpenAPI exige maintenant `pack_id`
sur `CreateContentDraftRequest` et reste deterministe.

## T04 - Oracles et rejet

`FX-CONTENT` materialise les oracles positifs et negatifs demandes : rejeu
identique a effet unique, concurrence `If-Match`, rollback injecte apres
evenement, refus de service, portee pack, rapport/manifeste scelles, droits,
references, historique et rejet editorial.

La matrice de rejet inclut explicitement :

- `ae0bfc7` : evenement W00 `content_rejected` ;
- `66a8cf5` : RED du parcours de rejet ;
- `8970f09` : decision/API/evenement/outbox/idempotence ;
- `e3dee18` : portee humaine/pack et scellement SQL appliques aussi au rejet.

Les preuves executables imposent une decision append-only `rejected`, exactement
un evenement et une outbox, le rejeu sans second effet, le conflit de cle, la
publication impossible et une nouvelle revision `draft` pointant vers la
revision rejetee avant toute reprise.

## Preuves isolees

Clone : `/tmp/polyglot-w05-fix3-proof-e3dee18`, revision
`e3dee18b7f0265f9578d7b28b6498e6feff6c6a9`.

Base : `polyglot_w05_fix3_proof`, PostgreSQL 17 local. Aucun DSN ni secret n'est
versionne.

- unit/property W05 : `8 passed` ;
- application W05 : `9 passed` ;
- HTTP W05 : `5 passed` ;
- migration/invariants SQL W05 : `23 passed` ;
- contrats/fixtures W05 : `8 passed` ;
- total W05 : `53 passed` ;
- Ruff complet `src tests` : PASS ;
- mypy complet `src` : PASS, 56 fichiers ;
- migration base vide jusqu'a `0005_content` : PASS ;
- `alembic check` : aucune operation nouvelle ;
- cycle `0005 -> 0004_language_profiles -> 0005` : PASS ;
- OpenAPI regeneration puis `--check` : PASS ;
- registre W00 : `contract registry valid` ;
- `git diff --check` : PASS dans le clone de preuve.

Le run monolithique du checkout Documents a ete arrete apres blocage du processus
pytest. Les memes tests ont ensuite ete executes en processus separes dans le
clone exact ci-dessus ; aucun processus de preuve n'est laisse actif.

## Restes

La revue linguistique italienne reste explicitement humaine (`P-LING
pending_human`). Aucun constat technique fix3 ne reste ouvert.

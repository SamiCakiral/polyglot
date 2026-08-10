# Revue independante W04

## Verdict

**FAIL**

Le delta W04 couvre bien les quatre increments `W04-T01..T04` et apporte une
base solide (domaine revisionne, lecture publique, fixture italienne hors
reseau, OpenAPI). Il ne peut toutefois pas etre accepte : trois invariants
normatifs ne sont pas garantis par PostgreSQL et un parcours de lecture n'est
pas borne au niveau de la base.

## Perimetre

Revue read-only des commits :

`da32509`, `c25e943`, `ea5e0f2`, `4783064`, `22c45bf`, `9365ac9`,
`61de6d7`, `63c044e`, `5d5a535`, `9bf6da9`.

Les commits et modifications W17 interleaves ont ete exclus. References
normatives comparees : documents 08, 13, 25, 26, 27 (`W04`) et registre
`W04-T01..T04` du document 31.

## Constats

### Critical

1. **Le contenu enfant d'une revision publiee reste modifiable en place.**

   `backend/migrations/versions/0003_catalogue.py:415-439` protege uniquement
   les cinq tables de revisions principales. Aucune garde equivalente ne couvre
   `language_pack_support_varieties`, `grammar_patterns`, `form_analyses`,
   `form_realizations` ou `expression_components`. Le role de migration peut
   donc modifier ou supprimer un moule, une graphie, une liaison forme-sens ou
   un composant MWE appartenant a une revision deja publiee, sans creer de
   nouvelle revision. Cela viole directement les invariants 25 du document 08
   et 17/18 du document 26. Le test
   `backend/tests/integration/catalogue/test_migration_0003.py:93-106` ne prouve
   que l'immutabilite de la ligne `language_pack_revisions` et laisse ce cas
   central non couvert.

2. **Le DAG `required` peut etre invalide par deux ecritures concurrentes.**

   `backend/migrations/versions/0003_catalogue.py:463-494` verifie le cycle avec
   une lecture recursive ordinaire avant chaque ligne, sans verrou global du
   graphe, isolation serializable ni contrainte differee. Deux transactions
   concurrentes peuvent chacune inserer une arete qui n'est cyclique qu'avec
   l'arete non encore visible de l'autre, puis valider toutes les deux. Le test
   `backend/tests/integration/catalogue/test_migration_0003.py:125-138` ne couvre
   qu'une insertion sequentielle. L'invariant normatif d'acyclicite n'est donc
   pas garanti par la source de verite PostgreSQL.

### Important

3. **Les liaisons forme/analyse/sens n'imposent pas leur coherence.**

   `backend/migrations/versions/0003_catalogue.py:380-397` accepte une
   `form_realization` dont `form_analysis_id`, `unit_revision_id` et
   `sense_revision_id` appartiennent a trois unites ou packs differents : les
   trois FKs sont independantes. De meme,
   `backend/migrations/versions/0003_catalogue.py:399-413` ne verifie ni que la
   racine est une `multiword_expression`, ni que ses composants appartiennent a
   la meme variete/revision de pack. La fixture correcte `puo/può`, `piano` et
   `per favore` masque ce trou ; aucune fixture negative ne prouve le rejet des
   references croisees. Cela compromet la separation normative
   surface/analyse/sens et la resolution fiable des MWE.

4. **La recherche lexicale paginee charge tous les resultats avant de borner.**

   `backend/src/polyglot/modules/catalogue/core/persistence.py:916-948` execute
   la requete sans predicat de curseur et sans `LIMIT`. Le curseur est applique
   ensuite en Python a `backend/src/polyglot/modules/catalogue/core/persistence.py:985-999`.
   `limit <= 100` borne seulement la reponse HTTP, pas la traversee SQL ni la
   memoire du processus. Une surface tres polysemique ou largement analysee
   viole donc l'invariant 46 du document 08 et le resultat attendu de `W04-T03`
   (pagination stable **et bornee**).

5. **Le validateur de fixture ne ferme pas toutes les references publiees.**

   `backend/src/polyglot/modules/catalogue/core/fixtures.py:442-459` verifie la
   fonction d'une structure et l'existence des composants par lemme, mais pas
   les `SkillRevision.target_ref`, l'unicite globale des codes/identifiants, la
   correspondance des composants avec une revision precise, ni le statut
   `published` des sens imbriques. Une fixture peut donc etre acceptee avec une
   cible de competence inexistante ou un sens non publie. `W04-T02` exige que
   toutes les references du pilote soient resolues ; `W04-T04` exige que les
   fixtures negatives soient rejetees, mais le seul negatif livre concerne un
   cycle.

6. **La verification de cycle PostgreSQL est elle-meme non bornee.**

   La CTE recursive de `backend/migrations/versions/0003_catalogue.py:469-481`
   n'a ni profondeur maximale ni budget de noeuds. Elle termine sur un graphe
   fini grace a `UNION`, mais son cout peut croitre avec tout le catalogue. Le
   domaine en memoire, lui, fournit correctement `max_depth` et `max_nodes`
   (`backend/src/polyglot/modules/catalogue/core/graph.py:89-125`). Les deux
   couches n'appliquent donc pas le meme contrat de traversee bornee.

### Minor

7. **La validation des codes differe entre domaine et PostgreSQL.**

   `backend/src/polyglot/modules/catalogue/core/domain.py:80-82` refuse seulement
   le vide, les espaces et les codes de plus de 120 caracteres ; la migration
   applique des expressions ASCII plus strictes, par exemple
   `backend/migrations/versions/0003_catalogue.py:50-56`. Une valeur peut donc
   etre valide dans le domaine puis echouer tardivement en persistance. Le
   contrat machine-readable devrait etre identique aux deux niveaux.

8. **Le round-trip de migration W04 n'a pas de preuve ciblee.**

   `backend/tests/integration/catalogue/test_migration_0003.py:11-154` inspecte
   le schema deja migre, les contraintes et les droits runtime, mais ne fait pas
   `0002 -> 0003 -> 0002 -> 0003`. `downgrade()` se limite a
   `backend/migrations/versions/0003_catalogue.py:550-551`. Le downgrade est
   plausible, mais pas prouve dans la suite W04.

## Points valides

- Les identifiants de domaine sont controles en UUIDv7 et les numeros de
  revision sont positifs (`domain.py:70-77`).
- Les unicites `(stable_id, revision_no)` et la publication active unique par
  `(pack_id, channel, compatibility_range)` sont presentes
  (`0003_catalogue.py:95`, `127-129`, `177`, `251`, `316`, `355`).
- Le graphe en memoire rejette les cycles `required`, ignore les autres types
  pour l'acyclicite et expose une traversee deterministe bornee
  (`graph.py:20-125`).
- Les lectures `/api/v1/language-packs`, `/api/v1/catalogue/targets` et
  `/api/v1/lexicon/search` sont publiques, fermees, documentees et bornent
  `limit` a `1..100` (`routes/catalogue.py:20-21`, `145-194`). L'OpenAPI generee
  expose les parametres obligatoires et les erreurs RFC 9457.
- La recherche conserve les diacritiques : `puo` et `può` ont des cles NFC
  distinctes ; `piano` conserve deux sens et `per favore` une unite MWE.
- La fixture canonique possede horloge, graine, empreinte, oracles et zero
  dependance reseau. Son empreinte est verifiee avant chargement
  (`fixtures.py:287-315`).
- Les permissions sont coherentes avec un catalogue partage :
  `polyglot_runtime` a `USAGE + SELECT` et aucun droit d'ecriture
  (`0003_catalogue.py:518-523`). L'absence de RLS utilisateur est acceptable
  pour ces donnees publiques partagees ; les droits SQL read-only font la
  frontiere.
- Aucun faux `P-LING` n'est revendique : la fixture et ses metadonnees restent
  explicitement `linguistic_review = pending_human`
  (`fixture-metadata.json:17`, `catalogue.json:5`).

## Preuves et limites d'execution

- Diff inspecte : 24 fichiers W04, 4 778 lignes ajoutees sur la plage
  `4cc3c49..9bf6da9`; aucun changement W17 inclus dans les constats.
- Tests lus : unitaires et proprietes du domaine/DAG, integration migration et
  repository, contrats HTTP/OpenAPI/fixture.
- La commande cible
  `uv run pytest tests/unit/catalogue tests/property/catalogue tests/integration/catalogue tests/contract/catalogue -q`
  a ete lancee, puis interrompue avant resultat final a la demande de
  finalisation immediate. Aucun succes d'execution independant n'est donc
  revendique dans cette revue.
- `git diff --check 4cc3c49..9bf6da9` ne signale pas d'erreur de whitespace.

## Conditions minimales de PASS

1. Rendre immuables toutes les entites possedees par une revision publiee, avec
   tests PostgreSQL de mutation/suppression sur chaque famille enfant.
2. Serialiser ou contraindre de facon sure les mutations du DAG `required`, et
   ajouter un test concurrent reproductible.
3. Fermer les coherences `form -> unit -> sense`, MWE/composants et pack/revision
   au niveau PostgreSQL, avec fixtures negatives.
4. Appliquer curseur et limite dans la requete SQL lexicale, sans charger le
   resultat complet.
5. Etendre le validateur de fixture a toutes les references et tous les statuts
   imbriques, puis prouver le round-trip Alembic W04.

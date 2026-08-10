# W02 - Revue independante ciblee du correctif CI

**Verdict: PASS**

Delta examine: `6a056cc..f820cea`. La revue est limitee aux deux lignes de
comportement ajoutees a `ChangePassword`, au test d'integration associe et au
contrat concurrence/version de `docs/v2/15-architecture-applicative.md`. Aucun
code, index, commit, branche, service ou donnees n'a ete modifie, hors creation
du present rapport demande.

## Findings

Aucun finding Critical ou Important.

## Verification ciblee

### Concurrence et version

Le controle explicite compare la version chargee de l'account a `If-Match`
avant le controle de session active et retourne `version_conflict` en cas
d'ecart. Cela corrige le cas sequentiel ou une premiere modification de mot de
passe incremente la version et revoque simultanement la seconde session. Le CAS
SQL sur `accounts.version` reste l'autorite pour une course survenant apres la
lecture; une seule transaction peut donc produire les effets, evenements et
recu final. Ce comportement respecte l'exigence de controle optimiste et de
`409 version_conflict` du document 15. Evidence:
`backend/src/polyglot/modules/identity/application.py:1262`,
`backend/src/polyglot/modules/identity/persistence.py:842`,
`backend/src/polyglot/modules/identity/persistence.py:854`,
`backend/src/polyglot/modules/identity/persistence.py:864`,
`docs/v2/15-architecture-applicative.md:136`,
`docs/v2/15-architecture-applicative.md:138`.

### Securite, idempotence et ordre des erreurs

L'ajout ne contourne pas l'authentification: le token de session doit toujours
etre resolu et le CSRF valide avant toute resolution de version. Le recu est
ensuite reserve avant le nouveau controle, ce qui preserve l'ordre contractuel:

1. un replay exact terminal retourne le resultat memorise;
2. la meme cle avec corps ou version differents retourne
   `idempotency_conflict`;
3. une nouvelle commande portant une version obsolete retourne
   `version_conflict`, meme si l'ecriture concurrente a revoque sa session;
4. une nouvelle commande a version courante mais avec session revoquee reste
   `unauthenticated`.

Aucun effet metier n'est execute avant le controle de session active. Le recu
provisoire d'une commande rejetee est dans la meme transaction et est annule
avec elle. Le store lie bien la cle a l'acteur, l'operation, l'empreinte,
l'agregat et `expected_version`, conformement au contrat d'idempotence. Evidence:
`backend/src/polyglot/modules/identity/application.py:1231`,
`backend/src/polyglot/modules/identity/application.py:1253`,
`backend/src/polyglot/modules/identity/application.py:1264`,
`backend/src/polyglot/platform/persistence/repositories.py:94`,
`backend/src/polyglot/platform/persistence/repositories.py:117`,
`backend/src/polyglot/platform/persistence/repositories.py:124`,
`docs/v2/15-architecture-applicative.md:139`,
`docs/v2/15-architecture-applicative.md:142`.

### Tests

Le nouveau test reproduit le cas CI exact: deux sessions partent de la meme
version, la premiere commit, puis la seconde utilise une nouvelle cle et la
version obsolete; elle doit recevoir `version_conflict`. Les tests voisins
couvrent deja le replay terminal exact, le conflit d'idempotence, la nouvelle
commande sur session revoquee avec version courante et la course simultanee
protegee par CAS. Evidence:
`backend/tests/integration/identity/test_application.py:680`,
`backend/tests/integration/identity/test_application.py:720`,
`backend/tests/integration/identity/test_application.py:733`,
`backend/tests/integration/identity/test_application.py:737`,
`backend/tests/integration/identity/test_application.py:772`,
`backend/tests/integration/identity/test_application.py:792`,
`backend/tests/integration/identity/test_application.py:828`.

Les tests PostgreSQL n'ont pas ete relances localement: les variables de
connexion runtime/migration ne sont pas configurees dans cette session et les
fixtures d'integration tronquent les tables de test. Le verdict repose donc sur
la preuve statique du delta et sur l'inspection de la couverture ciblee, pas sur
le rapport CI.
